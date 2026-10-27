"""Desktop workflow adapter. No GUI imports, so it is also testable headlessly."""
from pathlib import Path
import shutil

from scripts.config import ROOT
from scripts.conversion_rules import SUPPORTED_SUFFIXES

SUFFIXES = {"abstracts": SUPPORTED_SUFFIXES, "webinar": {".csv"}}


def collect_inputs(mode: str, paths: list[Path]) -> list[Path]:
    """Expand folders and deduplicate supported files without modifying sources."""
    files = set()
    for path in paths:
        if not path.exists():
            raise ValueError(f"Input no longer exists: {path}")
        candidates = path.rglob("*") if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() in SUFFIXES[mode]:
                files.add(candidate.resolve())
    return sorted(files)


def input_folder(mode):
    return ROOT / ("input" if mode == "abstracts" else "webinar/input")


def store_inputs(mode, paths):
    """Import files or folders, filtering folder contents before copying."""
    folder = input_folder(mode)
    folder.mkdir(parents=True, exist_ok=True)
    for source in paths:
        if not source.is_dir() and (not source.is_file() or source.suffix.lower() not in SUFFIXES[mode]):
            raise ValueError(f"Unsupported input: {source.name}")
    files = collect_inputs(mode, paths)
    if not files:
        raise ValueError("No supported files found in the selected folder.")
    for source in files:
        target = folder / source.name
        if source.resolve() == target.resolve():
            continue
        number = 2
        while target.exists():
            target = folder / f"{source.stem} ({number}){source.suffix}"
            number += 1
        shutil.copy2(source, target)


def current_inputs(mode):
    """List exactly the files the workflow will consider."""
    folder = input_folder(mode)
    if mode == "abstracts":
        return collect_inputs(mode, [folder])
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in SUFFIXES[mode])


def useful_outputs(mode):
    output = ROOT / ("output/handoff_bundle" if mode == "abstracts" else "webinar/output")
    if mode == "webinar":
        return sorted(output.glob("*.xlsx"))
    metadata = output / "abstract_metadata.csv"
    return ([metadata] if metadata.exists() else []) + sorted(p for p in (output / "pdfs").glob("*") if p.is_file() and p.suffix.lower() == ".pdf")


def run_job(mode):
    """Run the same workflows and fixed output locations as the terminal."""
    folder = input_folder(mode)
    files = current_inputs(mode)
    if not files:
        raise ValueError("Drop some files into the input box first.")
    result = ROOT / ("output" if mode == "abstracts" else "webinar/output")
    if mode == "abstracts":
        from scripts.main import run_pipeline
        counts = run_pipeline(folder, result)
        return f"Done · {counts['metadata_rows']} abstracts extracted."
    from scripts import process_webinar_report as webinar
    files = webinar.find_input_files(folder)
    webinar.clear_output_workbooks(result)
    used = {webinar.MASTER_WORKBOOK_NAME.casefold()}
    for index, source in enumerate(files, 1):
        print(f"Processing report {index} of {len(files)}", flush=True)
        target = webinar.default_output_path(source, result)
        original, number = target, 2
        while target.name.casefold() in used:
            target = original.with_stem(f"{original.stem} ({number})")
            number += 1
        used.add(target.name.casefold())
        webinar.process_webinar_report(source, ROOT / "webinar/Regions.csv", target)
    webinar.build_master_summary(result)
    return f"Done · {len(files)} reports and a combined summary."
