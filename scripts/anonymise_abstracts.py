"""Extract, anonymise, and export abstract text from PDF files."""

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF

from .anonymisation_rules import (
    INPUT_FOLDER,
    OUTPUT_FOLDER,
    CSV_OUTPUT_FOLDER,
    JSON_OUTPUT_FOLDER,
    OUTPUT_CSV,
    OUTPUT_JSON,
    CSV_ENCODING,
    PDF_SUFFIX,
    SUPPORTED_SUFFIXES,
    CSV_FIELDNAMES,
    EMAIL_RE,
    ORCID_RE,
    PHONE_RE,
)


Row = dict[str, str]


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the anonymisation script."""
    parser = argparse.ArgumentParser(
        description="Anonymise abstract text from PDF files."
    )
    parser.add_argument(
        "file_name",
        nargs="?",
        help=(
            "Optional PDF file name or path to process. If omitted, "
            f"all PDF files in {INPUT_FOLDER} are processed."
        ),
        type=str,
    )
    return parser.parse_args()


def extract_text_from_pdf(path: Path) -> str:
    """Extract text from every page of a PDF file."""
    text: list[str] = []
    with fitz.open(path) as pdf:
        for page in pdf:
            text.append(page.get_text())
    return "\n".join(text)


def anonymise_text(text: str) -> str:
    """Replace supported personal identifiers with removal markers."""
    clean_text, _ = anonymise_text_with_counts(text)
    return clean_text


def anonymise_text_with_counts(text: str) -> tuple[str, Row]:
    """Replace supported personal identifiers and count each replacement."""
    text, emails_removed = re.subn(EMAIL_RE, "[EMAIL_REMOVED]", text)
    text, orcids_removed = re.subn(ORCID_RE, "[ORCID_REMOVED]", text)
    text, phones_removed = re.subn(PHONE_RE, "[PHONE_REMOVED]", text)
    return text, {
        "emails_removed_count": str(emails_removed),
        "orcids_removed_count": str(orcids_removed),
        "phones_removed_count": str(phones_removed),
    }


def process_file(path: Path) -> Row:
    """Extract and anonymise one PDF input file."""
    suffix = path.suffix.lower()
    if suffix != PDF_SUFFIX:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    raw_text = extract_text_from_pdf(path)
    clean_text, removal_counts = anonymise_text_with_counts(raw_text)
    return {
        "file_name": path.name,
        **removal_counts,
        "clean_text": clean_text,
    }


def clean_text_path(output_dir: Path, source_path: Path) -> Path:
    """Build the output path for a PDF's cleaned text file."""
    suffix_name = source_path.suffix.lower().lstrip(".")
    return output_dir / f"{source_path.stem}_{suffix_name}_clean.txt"


def supported_input_files(input_dir: Path) -> list[Path]:
    """List PDF input files from the raw abstracts directory."""
    input_dir.mkdir(parents=True, exist_ok=True)
    return sorted(
        path for path in input_dir.iterdir()
        if (
            path.is_file()
            and not path.name.startswith("~$")
            and path.suffix.lower() in SUPPORTED_SUFFIXES
        )
    )


def resolve_input_path(file_name: str, input_dir: Path) -> Path:
    """Resolve a CLI file argument to one concrete PDF input path."""
    candidate = Path(file_name)
    if not candidate.is_absolute() and candidate.parent == Path("."):
        candidate = input_dir / candidate

    if candidate.exists():
        return candidate

    if candidate.suffix:
        raise FileNotFoundError(candidate)

    # Allow a unique stem such as "abstract_001" only when it is unambiguous.
    matches = [
        path for path in supported_input_files(input_dir)
        if path.stem == candidate.name
    ]
    if not matches:
        raise FileNotFoundError(candidate)
    if len(matches) > 1:
        match_names = ", ".join(path.name for path in matches)
        raise ValueError(
            f"Multiple input files match '{file_name}': {match_names}. "
            "Please include the extension."
        )
    return matches[0]


def read_csv_rows(csv_path: Path) -> list[Row]:
    """Read existing aggregate rows from a CSV file."""
    if not csv_path.exists():
        return []
    csv.field_size_limit(10_000_000)
    with csv_path.open(newline="", encoding=CSV_ENCODING) as f:
        reader = csv.DictReader(f)
        return [
            {field: row.get(field) or "" for field in CSV_FIELDNAMES}
            for row in reader
        ]


def read_json_rows(json_path: Path) -> list[Row]:
    """Read existing aggregate rows from a JSON file."""
    if not json_path.exists():
        return []
    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    rows: list[Row] = []
    for row in data:
        if isinstance(row, dict):
            rows.append({
                field: str(row.get(field) or "") for field in CSV_FIELDNAMES
            })
    return rows


def existing_rows(
    csv_path: Path,
    json_path: Path,
) -> list[Row]:
    """Find existing aggregate rows for a targeted single-file run."""
    for path, reader in (
        (csv_path, read_csv_rows),
        (json_path, read_json_rows),
    ):
        rows = reader(path)
        if rows:
            return rows
    return []


def upsert_rows(existing: list[Row], processed: list[Row]) -> list[Row]:
    """Merge processed rows into existing aggregate rows by file name."""
    rows_by_file = {row["file_name"]: row for row in existing}
    for row in processed:
        rows_by_file[row["file_name"]] = row
    return sorted(rows_by_file.values(), key=lambda row: row["file_name"])


def write_csv(rows: list[Row], csv_path: Path) -> None:
    """Write aggregate rows to a CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding=CSV_ENCODING) as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_json(rows: list[Row], json_path: Path) -> None:
    """Write aggregate rows to a JSON file."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get_current_time_data() -> str:
    """Return date-time text for output logging."""
    now = datetime.now()
    return datetime.strftime(now, '%d_%m_%Y__%H_%M')


def anonymise_pdf_abstracts(
    input_dir: Path = Path(INPUT_FOLDER),
    output_dir: Path = Path(OUTPUT_FOLDER),
    csv_path: Path = Path(CSV_OUTPUT_FOLDER) / OUTPUT_CSV,
    json_path: Path = Path(JSON_OUTPUT_FOLDER) / OUTPUT_JSON,
    file_name: str | None = None,
) -> list[Row]:
    """Anonymise PDF abstracts and write clean text, CSV, and JSON outputs."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    csv_path = Path(csv_path)
    json_path = Path(json_path)

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path]
    if file_name:
        paths = [resolve_input_path(file_name, input_dir)]
        if paths[0].suffix.lower() not in SUPPORTED_SUFFIXES:
            supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
            raise ValueError(
                f"Unsupported file type: {paths[0].suffix}. "
                f"Supported types: {supported}"
            )
    else:
        paths = supported_input_files(input_dir)

    processed_at = get_current_time_data()
    run_id = f"run_{processed_at}"
    rows: list[Row] = []
    for path in paths:
        result = process_file(path)
        clean_file = clean_text_path(output_dir, path)
        clean_file.write_text(result["clean_text"], encoding="utf-8")
        rows.append({
            "file_name": result["file_name"],
            "run_id": run_id,
            "emails_removed_count": result["emails_removed_count"],
            "orcids_removed_count": result["orcids_removed_count"],
            "phones_removed_count": result["phones_removed_count"],
            "clean_text_file": str(clean_file),
        })

    output_rows: list[Row] = rows
    if file_name:
        # Keep previous aggregate rows so targeted runs do not discard work.
        output_rows = upsert_rows(
            existing_rows(csv_path, json_path),
            rows
        )

    write_csv(output_rows, csv_path)
    write_json(output_rows, json_path)
    return rows


def main() -> None:
    """Run the PDF anonymisation pipeline from the CLI."""
    args = parse_args()
    try:
        rows = anonymise_pdf_abstracts(file_name=args.file_name)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    csv_path = Path(CSV_OUTPUT_FOLDER) / OUTPUT_CSV
    json_path = Path(JSON_OUTPUT_FOLDER) / OUTPUT_JSON

    print(f"Processed {len(rows)} files.")
    print(f"CSV created: {csv_path}")
    print(f"JSON created: {json_path}")
    print(f"Clean text files saved in: {OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()
