"""Extract, anonymise, and export abstract text from PDF files."""

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF

# TODO: implement logging
Row = dict[str, str]

# Locations for saving
INPUT_FOLDER: str = "abstracts_raw"
OUTPUT_FOLDER: str = "abstracts_clean"
CSV_OUTPUT_FOLDER: str = "abstract_csv"
JSON_OUTPUT_FOLDER: str = "abstract_json"
# File for storage
OUTPUT_CSV: str = "anonymised_abstracts.csv"
OUTPUT_JSON: str = "anonymised_abstracts.json"
PDF_SUFFIX: str = ".pdf"
SUPPORTED_SUFFIXES: set[str] = {PDF_SUFFIX}
CSV_FIELDNAMES: list[str] = [
    "file_name",
    "run_id",
    "emails_removed_count",
    "orcids_removed_count",
    "phones_removed_count",
    "clean_text_file",
    "clean_text",
]

# Patterns for personal/contact identifiers removed from extracted text.
EMAIL_RE: str = (
    r"(?<![\w.+-])"
    r"[A-Za-z0-9._%+-]+@"
    r"(?:[A-Za-z0-9-]+\.)+?"
    r"[A-Za-z]{2,}"
    r"(?=$|[^\w.+-]|\.(?=\s|$|[A-Z][a-z]))"
)
ORCID_RE: str = r"\b(?:https?://orcid\.org/)?\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"
PHONE_RE: str = r"(\+?\d[\d\s().-]{7,}\d)"


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the anonymisation script.

    Returns:
        argparse.Namespace: Parsed CLI arguments. The namespace contains
            `file_name`, which is either a PDF file name/path string or `None`
            when all PDFs in `INPUT_FOLDER` should be processed.
    """
    parser = argparse.ArgumentParser(
        description="Anonymise abstract text from PDF files."
    )
    parser.add_argument(
        "file_name",
        nargs="?",
        help=(
            "Optional PDF file name or path to process. If omitted, "
            "all PDF files in abstracts_raw are processed."
        ),
        type=str,
    )
    return parser.parse_args()


def extract_text_from_pdf(path: Path) -> str:
    """Extract text from every page of a PDF file.

    Args:
        path: Path to the PDF file to read.

    Returns:
        str: Combined text extracted from all pages, separated by newlines.
    """
    text: list[str] = []
    with fitz.open(path) as pdf:
        for page in pdf:
            text.append(page.get_text())
    return "\n".join(text)


def anonymise_text(text: str) -> str:
    """Replace supported personal identifiers with removal markers.

    Wrapper for anonymise_text_with_counts

    Args:
        text: Raw text that may contain email addresses, ORCID identifiers, or
            phone numbers.

    Returns:
        str: Text with supported identifiers replaced by removal markers.
    """
    clean_text, _ = anonymise_text_with_counts(text)
    return clean_text


def anonymise_text_with_counts(text: str) -> tuple[str, Row]:
    """Replace supported personal identifiers and count each replacement.

    Args:
        text: Raw text that may contain email addresses, ORCID identifiers, or
            phone numbers.

    Returns:
        tuple[str, Row]: A tuple containing the anonymised text and a row-like
            dictionary with string counts for removed emails, ORCIDs, and phone
            numbers.
    """
    text, emails_removed = re.subn(EMAIL_RE, "[EMAIL_REMOVED]", text)
    text, orcids_removed = re.subn(ORCID_RE, "[ORCID_REMOVED]", text)
    text, phones_removed = re.subn(PHONE_RE, "[PHONE_REMOVED]", text)
    return text, {
        "emails_removed_count": str(emails_removed),
        "orcids_removed_count": str(orcids_removed),
        "phones_removed_count": str(phones_removed),
    }


def process_file(path: Path) -> Row:
    """Extract and anonymise one PDF input file.

    Args:
        path: Path to the PDF file to process.

    Returns:
        Row: Dictionary containing the source file name, removal counts, and
            anonymised text.

    Raises:
        ValueError: If `path` does not have a PDF suffix.
    """
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
    """Build the output path for a PDF's cleaned text file.

    Args:
        output_dir: Directory where cleaned text files are written.
        source_path: Path to the source PDF file.

    Returns:
        Path: Output path using the source stem and suffix, for example
            `abstract_001_pdf_clean.txt`.
    """
    suffix_name = source_path.suffix.lower().lstrip(".")
    return output_dir / f"{source_path.stem}_{suffix_name}_clean.txt"


def supported_input_files(input_dir: Path) -> list[Path]:
    """List PDF input files from the raw abstracts directory.

    Args:
        input_dir: Directory to scan for input files.

    Returns:
        list[Path]: Sorted PDF file paths. Temporary Office lock files are
            excluded if present.
    """
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
    """Resolve a CLI file argument to one concrete PDF input path.

    Args:
        file_name: File name, relative path, absolute path, or unique PDF stem
            provided on the command line.
        input_dir: Directory used to resolve bare file names and stems.

    Returns:
        Path: Resolved PDF file path.

    Raises:
        FileNotFoundError: If the argument cannot be resolved to a file.
        ValueError: If a stem matches multiple PDF files.
    """
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
    """Read existing aggregate rows from a CSV file.

    Args:
        csv_path: Path to the CSV aggregate file.

    Returns:
        list[Row]: Rows normalised to `CSV_FIELDNAMES`. Missing files return an
            empty list, and missing row values are returned as empty strings.
    """
    if not csv_path.exists():
        return []
    csv.field_size_limit(10_000_000)
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            {field: row.get(field) or "" for field in CSV_FIELDNAMES}
            for row in reader
        ]


def read_json_rows(json_path: Path) -> list[Row]:
    """Read existing aggregate rows from a JSON file.

    Args:
        json_path: Path to the JSON aggregate file.

    Returns:
        list[Row]: Dictionary rows normalised to `CSV_FIELDNAMES`. Missing
            files, non-list JSON data, and non-dictionary list items are ignored.
    """
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
    """Find existing aggregate rows for a targeted single-file run.

    Args:
        csv_path: Path to the CSV aggregate file.
        json_path: Path to the JSON aggregate file.

    Returns:
        list[Row]: Rows from the first non-empty aggregate source, preferring
            CSV over JSON. Returns an empty list when neither source has rows.
    """
    for path, reader in (
        (csv_path, read_csv_rows),
        (json_path, read_json_rows),
    ):
        rows = reader(path)
        if rows:
            return rows
    return []


def upsert_rows(existing: list[Row], processed: list[Row]) -> list[Row]:
    """Merge processed rows into existing aggregate rows by file name.

    Args:
        existing: Previously stored aggregate rows.
        processed: Newly processed rows that should replace matching file names
            or be added when no match exists.

    Returns:
        list[Row]: Merged rows sorted by `file_name`.
    """
    rows_by_file = {row["file_name"]: row for row in existing}
    for row in processed:
        rows_by_file[row["file_name"]] = row
    return sorted(rows_by_file.values(), key=lambda row: row["file_name"])


def write_csv(rows: list[Row], csv_path: Path) -> None:
    """Write aggregate rows to a CSV file.

    Args:
        rows: Rows to write using `CSV_FIELDNAMES`.
        csv_path: Destination CSV path. The parent directory is created if
            needed.

    Returns:
        None.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_json(rows: list[Row], json_path: Path) -> None:
    """Write aggregate rows to a JSON file.

    Args:
        rows: Rows to serialise as JSON.
        json_path: Destination JSON path. The parent directory is created if
            needed.

    Returns:
        None.
    """
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get_current_time_data() -> str:
    """Return date-time text for output logging.

    Returns:
        str: Current local date and time formatted as `DD_MM_YYYY__HH_MM`.
    """
    now = datetime.now()
    return datetime.strftime(now, '%d_%m_%Y__%H_%M')


def main() -> None:
    """Run the PDF anonymisation pipeline from the CLI.

    Returns:
        None.

    Raises:
        SystemExit: If the input folder is missing, the requested file cannot
            be resolved, or the requested file is not a PDF.
    """
    args = parse_args()
    input_dir = Path(INPUT_FOLDER)
    output_dir = Path(OUTPUT_FOLDER)
    csv_path = Path(CSV_OUTPUT_FOLDER) / OUTPUT_CSV
    json_path = Path(JSON_OUTPUT_FOLDER) / OUTPUT_JSON

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path]
    if args.file_name:
        try:
            paths = [resolve_input_path(args.file_name, input_dir)]
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        if paths[0].suffix.lower() not in SUPPORTED_SUFFIXES:
            supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
            raise SystemExit(
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
            "clean_text": result["clean_text"],
        })

    output_rows: list[Row] = rows
    if args.file_name:
        # Keep previous aggregate rows so targeted runs do not discard work.
        output_rows = upsert_rows(
            existing_rows(csv_path, json_path),
            rows
        )

    write_csv(output_rows, csv_path)
    write_json(output_rows, json_path)

    print(f"Processed {len(rows)} files.")
    print(f"CSV created: {csv_path}")
    print(f"JSON created: {json_path}")
    print(f"Clean text files saved in: {OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()
