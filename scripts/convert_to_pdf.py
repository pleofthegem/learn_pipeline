"""Aggregate source files and convert supported inputs to PDF."""

import argparse
import re
import shutil
import subprocess
from pathlib import Path

import fitz

from .conversion_rules import (
    AGGREGATED_FOLDER,
    PDF_OUTPUT_FOLDER,
    OFFICE_SUFFIXES,
    SUPPORTED_SUFFIXES,
    POWERPOINT_PDF_MARKERS,
)


def alter_file_name(file_name: str) -> str:
    """Add or increment a Windows-style duplicate suffix in a file name."""
    path = Path(file_name)
    match = re.match(r"^(?P<stem>.*)\((?P<count>\d+)\)$", path.stem)
    if match:
        stem = match.group("stem")
        count = int(match.group("count")) + 1
    else:
        stem = path.stem
        count = 1

    return f"{stem}({count}){path.suffix}"


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the conversion script."""
    parser = argparse.ArgumentParser(
        description="Aggregate files and convert supported inputs to PDF."
    )
    parser.add_argument(
        "input_folder",
        help="Folder to scan for source files.",
        type=str,
    )
    return parser.parse_args()


def aggregate_files(
    input_folder: Path,
    aggregate_dir: Path = Path(AGGREGATED_FOLDER),
    *,
    suffixes: set[str] = SUPPORTED_SUFFIXES,
) -> list[Path]:
    """Copy every supported file under an input folder into one aggregate folder."""
    input_folder = Path(input_folder)
    aggregate_dir = Path(aggregate_dir)
    input_folder.mkdir(parents=True, exist_ok=True)
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    aggregate_dir_resolved = aggregate_dir.resolve()

    copied: list[Path] = []
    destinations: dict[Path, Path] = {}
    for path in sorted(input_folder.rglob("*")):
        if not path.is_file():
            continue
        if path.resolve().is_relative_to(aggregate_dir_resolved):
            continue
        if path.suffix.lower() not in suffixes:
            continue
        if is_powerpoint_pdf(path):
            continue
        if is_password_protected_pdf(path):
            continue

        relative_path = path.relative_to(input_folder)
        destination = aggregate_destination(aggregate_dir, relative_path)
        while destination in destinations or destination.exists():
            destination = destination.with_name(
                alter_file_name(destination.name))

        destinations[destination] = relative_path
        shutil.copy2(path, destination)
        copied.append(destination)

    return copied


def aggregate_destination(aggregate_dir: Path, relative_path: Path) -> Path:
    """Build an aggregate path from the top-level folder and file name."""
    if len(relative_path.parts) == 1:
        return aggregate_dir / relative_path.name
    return aggregate_dir / f"{relative_path.parts[0]}__{relative_path.name}"


def convert_file_to_pdf(path: Path, output_dir: Path) -> Path:
    """Convert one supported file to PDF."""
    match path.suffix.lower():
        case ".pdf":
            return copy_pdf(path, output_dir)
        case suffix if suffix in OFFICE_SUFFIXES:
            return convert_office_to_pdf(path, output_dir)
        case _:
            raise ValueError(f"Unsupported file type: {path.suffix}")


def is_powerpoint_pdf(path: Path) -> bool:
    """Check whether a PDF path looks like it came from a presentation."""
    if path.suffix.lower() != ".pdf":
        return False

    searchable_path = " ".join(path.parts).casefold()
    return any(marker in searchable_path for marker in POWERPOINT_PDF_MARKERS)


def is_password_protected_pdf(path: Path) -> bool:
    """Check whether a PDF requires a password before text can be read."""
    if path.suffix.lower() != ".pdf":
        return False

    try:
        with fitz.open(path) as pdf:
            return bool(pdf.needs_pass)
    except (fitz.FileDataError, RuntimeError):
        return False


def copy_pdf(path: Path, output_dir: Path) -> Path:
    """Copy an existing PDF into the PDF output folder."""
    if is_powerpoint_pdf(path):
        raise ValueError(f"Unsupported PowerPoint PDF: {path.name}")
    if is_password_protected_pdf(path):
        raise ValueError(f"Unsupported password-protected PDF: {path.name}")

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / path.name
    if path.resolve() == destination.resolve():
        return destination

    shutil.copy2(path, destination)
    return destination


def convert_office_to_pdf(path: Path, output_dir: Path) -> Path:
    """Convert an Office document to PDF with LibreOffice."""
    command = office_converter_command()
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            command,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    pdf_path = output_dir / f"{path.stem}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    return pdf_path


def office_converter_command() -> str:
    """Find a local LibreOffice conversion command."""
    for command in ("soffice", "libreoffice"):
        resolved = shutil.which(command)
        if resolved:
            return resolved
    raise RuntimeError("Office conversion requires soffice or libreoffice.")


def convert_all_to_pdf(files: list[Path], output_dir: Path) -> list[Path]:
    """Convert a list of files to PDF."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return [convert_file_to_pdf(path, output_dir) for path in files]


def convert_inputs_to_pdfs(
    input_folder: Path,
    aggregate_dir: Path = Path(AGGREGATED_FOLDER),
    output_dir: Path = Path(PDF_OUTPUT_FOLDER),
) -> tuple[list[Path], list[Path]]:
    """Aggregate supported source files and convert them to PDFs."""
    aggregated_files = aggregate_files(Path(input_folder), Path(aggregate_dir))
    pdf_files = convert_all_to_pdf(
        files=aggregated_files,
        output_dir=Path(output_dir),
    )
    return aggregated_files, pdf_files


def main() -> None:
    """Run aggregation followed by PDF conversion from the CLI."""
    args = parse_args()
    aggregated_files, pdf_files = convert_inputs_to_pdfs(
        input_folder=Path(args.input_folder),
    )

    print(f"Aggregated {len(aggregated_files)} files.")
    print(f"Converted {len(pdf_files)} PDFs.")
    print(f"PDF files saved in: {PDF_OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()
