"""Split combined abstract e-book PDFs into individual abstract PDFs."""

import argparse
import csv
import json
import re
import shutil
from math import ceil
from pathlib import Path

import fitz

# Default folder containing PDFs to check for combined abstract e-books.
INPUT_FOLDER = "abstracts_raw"
# Staging folder for human inspection.
SPLIT_FOLDER = "abstracts_split"
# Shared general input folder for other scripts like anonymise_abstracts.py and extract_abstract_metadata.py
OUTPUT_FOLDER = "abstracts_raw"
METADATA_CSV = "split_abstracts.csv"
METADATA_JSON = "split_abstracts.json"
CSV_ENCODING = "utf-8-sig"
PDF_SUFFIX = ".pdf"
CODE_PATTERN = re.compile(r"^T\d+_[OP]\d+$")
PRESENTATION_PATTERN = re.compile(
    r"^Presentation\s+(?P<number>\d{1,3})(?:\s+(?P<title>.+))?$",
    re.IGNORECASE,
)
PAGE_PATTERN = re.compile(r"^\d+$")
SKIP_TOC_LINES = {"CONTENT", "I", "II", "III", "IV", "V"}
FUZZY_TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "by",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "using",
    "with",
}
TITLE_MATCH_LINE_LIMIT = 12
METADATA_FIELDS = [
    "source_file",
    "abstract_id",
    "title",
    "printed_start_page",
    "pdf_start_page",
    "pdf_end_page",
    "page_count",
    "output_file",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments containing `input_folder`, the
            folder of PDFs to check for combined files. Defaults to
            `INPUT_FOLDER` when
            omitted.
    """
    parser = argparse.ArgumentParser(
        description="Split folders of combined abstract PDFs into single PDFs."
    )
    parser.add_argument(
        "input_folder",
        nargs="?",
        default=INPUT_FOLDER,
        type=str,
        help="Folder of PDFs to check for combined abstract e-books.",
    )
    return parser.parse_args()

# Main API for the rest of the repo.


def split_combined_pdfs(
    input_folder: Path,
    output_folder: Path = Path(OUTPUT_FOLDER),
    staging_folder: Path = Path(SPLIT_FOLDER),
) -> list[dict[str, object]]:
    """Run the split step using derived pipeline defaults.

    Args:
        input_folder: Folder containing PDFs to check for combined files.
        output_folder: Final folder that receives split PDFs.
        staging_folder: Intermediary folder where PDFs are split before being
            copied to the final output folder, and where metadata is written for
            human review.

    Returns:
        list[dict[str, object]]: Metadata rows for every generated PDF.
    """
    input_folder = Path(input_folder)
    output_folder = Path(output_folder)
    staging_folder = Path(staging_folder)
    metadata = split_folder(
        input_folder=input_folder,
        output_folder=output_folder,
        staging_folder=staging_folder,
    )
    write_metadata_csv(metadata, staging_folder / METADATA_CSV)
    write_metadata_json(metadata, staging_folder / METADATA_JSON)
    return metadata


def split_folder(
    input_folder: Path,
    output_folder: Path = Path(OUTPUT_FOLDER),
    staging_folder: Path = Path(SPLIT_FOLDER),
) -> list[dict[str, object]]:
    """Split every combined PDF in a folder.

    Args:
        input_folder: Folder containing PDFs to check for combined files.
        output_folder: Final folder that receives the split PDF files.
        staging_folder: Intermediary folder where PDFs are split before they are
            copied to the final output folder.

    Returns:
        list[dict[str, object]]: Metadata rows for every generated PDF.
    """
    input_folder = Path(input_folder)
    output_folder = Path(output_folder)
    staging_folder = Path(staging_folder)
    input_folder_resolved = input_folder.resolve()
    output_folder_resolved = output_folder.resolve()
    staging_folder_resolved = staging_folder.resolve()

    if input_folder_resolved.is_relative_to(staging_folder_resolved):
        raise ValueError(
            "Staging folder cannot be the input folder or its parent.")
    if staging_folder_resolved == output_folder_resolved:
        raise ValueError("Staging folder cannot be the output folder.")

    input_folder.mkdir(parents=True, exist_ok=True)
    staging_folder.mkdir(parents=True, exist_ok=True)
    output_folder.mkdir(parents=True, exist_ok=True)
    clean_folder(staging_folder)
    metadata: list[dict[str, object]] = []

    # Snapshot paths before writing split PDFs back into the output folder.
    pdf_paths = [
        path
        for path in sorted(Path(input_folder).iterdir())
        if path.is_file() and path.suffix.lower() == PDF_SUFFIX
    ]

    split_source_paths: list[Path] = []
    for pdf_path in pdf_paths:
        split_metadata = split_pdf(
            pdf_path=pdf_path,
            output_folder=staging_folder,
        )
        if split_metadata:
            split_source_paths.append(pdf_path)
        metadata.extend(split_metadata)

    copy_split_pdfs(staging_folder, output_folder)
    remove_split_source_pdfs(split_source_paths, output_folder)
    # Return anything at all?
    return metadata


def split_pdf(
    pdf_path: Path,
    output_folder: Path,
) -> list[dict[str, object]]:
    """Split one combined PDF into individual abstract PDFs.

    Args:
        pdf_path: Combined PDF to split.
        output_folder: Folder that receives the split PDF files.

    Returns:
        list[dict[str, object]]: Metadata rows for generated PDFs. An empty list
            is returned when the PDF does not contain the expected TOC.
    """
    with fitz.open(pdf_path) as pdf:
        combined_info = combined_pdf_info(pdf)
        if combined_info is None:
            return []

        toc_end_page, entries, page_offset = combined_info
        matched_entries: list[dict[str, object]] = []
        for entry in entries:
            pdf_start_page = find_title_page(
                pdf=pdf,
                title=str(entry["title"]),
                printed_page=int(entry["printed_start_page"]),
                page_offset=page_offset,
                scan_start_page=toc_end_page + 1,
            )
            if pdf_start_page is None:
                continue
            entry["pdf_start_page"] = pdf_start_page
            matched_entries.append(entry)

        metadata: list[dict[str, object]] = []
        for index, entry in enumerate(matched_entries):
            start_page = int(entry["pdf_start_page"])
            if index + 1 < len(matched_entries):
                end_page = int(
                    matched_entries[index + 1]["pdf_start_page"]
                ) - 1
            else:
                end_page = pdf.page_count
            if (
                start_page < 1
                or start_page > pdf.page_count
                or end_page < start_page
            ):
                continue

            output_file = f"{pdf_path.stem}_{entry['abstract_id']}.pdf"
            save_page_range(pdf, start_page, end_page,
                            output_folder / output_file)
            metadata.append(
                {
                    "source_file": pdf_path.name,
                    "abstract_id": entry["abstract_id"],
                    "title": entry["title"],
                    "printed_start_page": entry["printed_start_page"],
                    "pdf_start_page": start_page,
                    "pdf_end_page": end_page,
                    "page_count": end_page - start_page + 1,
                    "output_file": output_file,
                }
            )

    return metadata


def is_combined_pdf(pdf_path: Path) -> bool:
    """Check whether a PDF matches the expected combined abstract format.

    Args:
        pdf_path: PDF path to inspect.

    Returns:
        bool: True when the PDF has a parseable combined-abstract TOC and the
            first listed abstract can be found later in the document.
    """
    with fitz.open(pdf_path) as pdf:
        return combined_pdf_info(pdf) is not None


def combined_pdf_info(
    pdf: fitz.Document,
) -> tuple[int, list[dict[str, object]], int] | None:
    """Return parsed combined-PDF info, or None when the format is not matched."""
    toc_page_range = find_toc_page_range(pdf)
    if toc_page_range is None:
        return None

    _, toc_end_page = toc_page_range
    entries = parse_toc(pdf, toc_page_range)
    if len(entries) < 2:
        return None

    try:
        page_offset = derive_page_offset(pdf, entries, toc_end_page)
    except ValueError:
        return None

    return toc_end_page, entries, page_offset


def parse_toc(
    pdf: fitz.Document,
    toc_page_range: tuple[int, int] | None = None,
) -> list[dict[str, object]]:
    """Parse abstract IDs, titles, and printed start pages from the TOC.

    Extracts useful data from the Table of Contents.

    Args:
        pdf: Open PDF document.
        toc_page_range: Optional first and last 1-based PDF pages containing
            TOC entries. When omitted, the range is derived from pages with the
            `CONTENT` heading.

    Returns:
        list[dict[str, object]]: TOC entries with `abstract_id`, `title`, and
            `printed_start_page`.
    """
    if toc_page_range is None:
        toc_page_range = find_toc_page_range(pdf)
    if toc_page_range is None:
        return []

    toc_start_page, toc_end_page = toc_page_range
    lines: list[str] = []
    for page_number in range(
        toc_start_page,
        min(toc_end_page, pdf.page_count) + 1,
    ):
        lines.extend(clean_lines(
            pdf[page_number - 1].get_text("text").splitlines()))

    entries = parse_code_toc_lines(lines)
    if entries:
        return entries

    return parse_presentation_toc_lines(lines)


def parse_code_toc_lines(lines: list[str]) -> list[dict[str, object]]:
    """Parse the original `T1_O1` style combined-PDF TOC lines."""
    entries: list[dict[str, object]] = []
    abstract_id: str | None = None
    title_lines: list[str] = []

    for line in lines:
        if line in SKIP_TOC_LINES:
            continue

        if CODE_PATTERN.fullmatch(line):
            abstract_id = line
            title_lines = []
            continue

        if abstract_id and PAGE_PATTERN.fullmatch(line):
            entries.append(
                {
                    "abstract_id": abstract_id,
                    "title": " ".join(title_lines),
                    "printed_start_page": int(line),
                }
            )
            abstract_id = None
            title_lines = []
            continue

        if abstract_id:
            title_lines.append(line)

    return entries


def parse_presentation_toc_lines(lines: list[str]) -> list[dict[str, object]]:
    """Parse `Presentation 01 ... 02` style combined-PDF TOC lines."""
    entries: list[dict[str, object]] = []
    section_prefix: str | None = None
    abstract_number: str | None = None
    abstract_prefix: str | None = None
    title_lines: list[str] = []

    for line in lines:
        lower_line = line.casefold()
        if lower_line.startswith("oral presentations"):
            section_prefix = "O"
            continue
        if lower_line.startswith("poster presentations"):
            section_prefix = "P"
            continue

        match = PRESENTATION_PATTERN.fullmatch(line)
        if match:
            abstract_number = match.group("number")
            abstract_prefix = section_prefix or "PR"
            title = match.group("title")
            title_lines = [title.strip()] if title else []
            continue

        if abstract_number and PAGE_PATTERN.fullmatch(line):
            entries.append({
                "abstract_id": f"{abstract_prefix}{int(abstract_number):02d}",
                "title": " ".join(title_lines),
                "printed_start_page": int(line),
            })
            abstract_number = None
            abstract_prefix = None
            title_lines = []
            continue

        if abstract_number:
            title_lines.append(line)

    return entries


def find_toc_page_range(pdf: fitz.Document) -> tuple[int, int] | None:
    """Find the table-of-contents pages in a combined PDF.

    Args:
        pdf: Open PDF document.

    Returns:
        tuple[int, int] | None: First and last 1-based TOC page numbers, or
            None when the expected TOC pattern is not present.
    """
    code_toc_range = find_code_toc_page_range(pdf)
    if code_toc_range is not None:
        return code_toc_range

    return find_presentation_toc_page_range(pdf)


def find_code_toc_page_range(pdf: fitz.Document) -> tuple[int, int] | None:
    """Find TOC pages for the original `CONTENT` plus `T1_O1` style."""
    toc_start_page: int | None = None
    toc_end_page: int | None = None

    for page_index in range(pdf.page_count):
        lines = clean_lines(pdf[page_index].get_text("text").splitlines())
        if "CONTENT" in lines:
            page_number = page_index + 1
            if toc_start_page is None:
                toc_start_page = page_number
            toc_end_page = page_number
            continue

        if toc_start_page is not None:
            break

    if toc_start_page is None or toc_end_page is None:
        return None

    return toc_start_page, toc_end_page


def find_presentation_toc_page_range(pdf: fitz.Document) -> tuple[int, int] | None:
    """Find TOC pages for `Presentation 01` style abstract lists."""
    toc_start_page: int | None = None
    toc_end_page: int | None = None

    for page_index in range(pdf.page_count):
        lines = clean_lines(pdf[page_index].get_text("text").splitlines())
        if any(PRESENTATION_PATTERN.fullmatch(line) for line in lines):
            page_number = page_index + 1
            if toc_start_page is None:
                toc_start_page = page_number
            toc_end_page = page_number
            continue

        if toc_start_page is not None:
            break

    if toc_start_page is None or toc_end_page is None:
        return None

    return toc_start_page, toc_end_page


def derive_page_offset(
    pdf: fitz.Document,
    entries: list[dict[str, object]],
    toc_end_page: int,
) -> int:
    """Derive the offset between printed TOC pages and PDF pages.
    Check by using the table of contents' first abstract. Check if the
    title is present.

    Args:
        pdf: Open PDF document.
        entries: Parsed TOC entries.
        toc_end_page: Last 1-based TOC page number.

    Returns:
        int: Offset to add to printed page numbers.

    Raises:
        ValueError: If the first TOC title cannot be found after the TOC.
    """
    first_entry = entries[0]
    title = str(first_entry["title"])
    printed_page = int(first_entry["printed_start_page"])

    for page_number in range(toc_end_page + 1, pdf.page_count + 1):
        if page_has_title(pdf, page_number, title):
            return page_number - printed_page

    raise ValueError(f"Could not derive page offset for title: {title}")


def find_title_page(
    pdf: fitz.Document,
    title: str,
    printed_page: int,
    page_offset: int,
    scan_start_page: int,
) -> int | None:
    """Find the actual PDF page where an abstract title appears.

    Args:
        pdf: Open PDF document.
        title: Abstract title from the TOC.
        printed_page: Printed start page from the TOC.
        page_offset: Number added to the printed page to get the likely PDF page.
        scan_start_page: First 1-based PDF page to use for fallback scanning.

    Returns:
        int | None: 1-based PDF page containing the abstract title, or `None`
            when no matching page can be found.
    """
    expected_page = printed_page + page_offset
    guided_pages = nearby_page_numbers(
        expected_page=expected_page,
        scan_start_page=scan_start_page,
        page_count=pdf.page_count,
    )
    for page_number in guided_pages:
        if page_has_title(pdf, page_number, title):
            return page_number

    for page_number in range(scan_start_page, pdf.page_count + 1):
        if page_number in guided_pages:
            continue
        if page_has_title(pdf, page_number, title):
            return page_number

    return None


def nearby_page_numbers(
    expected_page: int,
    scan_start_page: int,
    page_count: int,
    radius: int = 3,
) -> list[int]:
    """Return nearby page numbers ordered by distance from an expected page."""
    page_numbers: list[int] = []
    for distance in range(radius + 1):
        for page_number in (expected_page - distance, expected_page + distance):
            if (
                page_number < scan_start_page
                or page_number > page_count
                or page_number in page_numbers
            ):
                continue
            page_numbers.append(page_number)
    return page_numbers


def page_has_title(pdf: fitz.Document, page_number: int, title: str) -> bool:
    """Check whether a PDF page starts with a TOC title.

    Args:
        pdf: Open PDF document.
        page_number: 1-based PDF page number to inspect.
        title: Title to search for.

    Returns:
        bool: True when the normalised title appears near the top of the page.
    """
    if page_number < 1 or page_number > pdf.page_count:
        return False

    page_lines = clean_lines(pdf[page_number - 1].get_text("text").splitlines())
    title_area = title_match_area(page_lines)
    if normalise(title) in normalise(title_area):
        return True

    title_tokens = significant_title_tokens(title)
    if len(title_tokens) < 4:
        return False

    page_tokens = set(significant_title_tokens(title_area))
    matched_tokens = [token for token in title_tokens if token in page_tokens]
    required_matches = max(4, ceil(len(title_tokens) * 0.85))
    return len(matched_tokens) >= required_matches


def title_match_area(lines: list[str]) -> str:
    """Return the page region used to decide whether a title starts a page."""
    return " ".join(lines[:TITLE_MATCH_LINE_LIMIT])


def significant_title_tokens(text: str) -> list[str]:
    """Return normalised title tokens used for fuzzy title matching."""
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in FUZZY_TITLE_STOPWORDS
    ]


def save_page_range(
    pdf: fitz.Document,
    start_page: int,
    end_page: int,
    output_path: Path,
) -> None:
    """Save a 1-based inclusive page range to a new PDF.

    Args:
        pdf: Open source PDF document.
        start_page: First 1-based PDF page to copy.
        end_page: Last 1-based PDF page to copy.
        output_path: Destination PDF path.

    Returns:
        None.
    """
    output = fitz.open()
    output.insert_pdf(pdf, from_page=start_page - 1, to_page=end_page - 1)
    output.save(output_path)
    output.close()


def copy_split_pdfs(staging_folder: Path, output_folder: Path) -> list[Path]:
    """Copy staged split PDF files into the final output folder.

    Args:
        staging_folder: Folder containing split PDFs.
        output_folder: Final folder that receives the split PDFs.

    Returns:
        list[Path]: Final paths for copied PDF files.
    """
    output_folder.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []

    for path in sorted(staging_folder.glob(f"*{PDF_SUFFIX}")):
        destination = output_folder / path.name
        if path.resolve() == destination.resolve():
            copied.append(destination)
            continue

        shutil.copy2(path, destination)
        copied.append(destination)

    return copied


def remove_split_source_pdfs(
    source_paths: list[Path],
    output_folder: Path,
) -> list[Path]:
    """Remove combined source PDFs from the final output folder after splitting.

    Args:
        source_paths: Combined PDF paths that produced at least one split PDF.
        output_folder: Final output folder that should contain atomic PDFs only.

    Returns:
        list[Path]: Paths removed from the output folder.
    """
    removed: list[Path] = []
    output_folder = Path(output_folder)

    for source_path in source_paths:
        output_path = output_folder / source_path.name
        if not output_path.is_file():
            continue

        output_path.unlink()
        removed.append(output_path)

    return removed


def clean_folder(folder: Path) -> None:
    """Remove all files and folders inside a folder.

    Args:
        folder: Existing folder whose contents should be removed.

    Returns:
        None.
    """
    for path in folder.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
            continue

        path.unlink()


def clean_lines(lines: list[str]) -> list[str]:
    """Strip blank text lines.

    Args:
        lines: Raw text lines.

    Returns:
        list[str]: Non-empty stripped lines.
    """
    return [line.strip() for line in lines if line.strip()]


def normalise(text: str) -> str:
    """Normalise text for title matching.

    Args:
        text: Text to normalise.

    Returns:
        str: Lowercase alphanumeric text.
    """
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def write_metadata_csv(metadata: list[dict[str, object]], path: Path) -> None:
    """Write split metadata to CSV.

    Args:
        metadata: Metadata rows to write.
        path: CSV output path.

    Returns:
        None.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=CSV_ENCODING) as file:
        writer = csv.DictWriter(file, fieldnames=METADATA_FIELDS)
        writer.writeheader()
        writer.writerows(metadata)


def write_metadata_json(metadata: list[dict[str, object]], path: Path) -> None:
    """Write split metadata to JSON.

    Args:
        metadata: Metadata rows to write.
        path: JSON output path.

    Returns:
        None.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2)


def main() -> None:
    """Run the folder splitter from the command line.

    Returns:
        None.
    """
    args = parse_args()
    output_folder = Path(OUTPUT_FOLDER)
    staging_folder = Path(SPLIT_FOLDER)
    csv_path = staging_folder / METADATA_CSV
    json_path = staging_folder / METADATA_JSON
    metadata = split_combined_pdfs(Path(args.input_folder))

    print(f"Split {len(metadata)} abstracts.")
    print(f"PDFs saved in: {output_folder}")
    print(f"Metadata saved to: {csv_path} and {json_path}")


if __name__ == "__main__":
    main()
