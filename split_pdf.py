"""Split combined abstract e-book PDFs into individual abstract PDFs."""

import argparse
import csv
import json
import re
import shutil
from pathlib import Path

import fitz

SPLIT_FOLDER = "abstracts_split"
OUTPUT_FOLDER = "abstracts_raw"
# Could save metadata under a single folder
METADATA_CSV = "split_abstracts.csv"
METADATA_JSON = "split_abstracts.json"
PDF_SUFFIX = ".pdf"
CODE_PATTERN = re.compile(r"^T\d+_[OP]\d+$")
PAGE_PATTERN = re.compile(r"^\d+$")
SKIP_TOC_LINES = {"CONTENT", "I", "II", "III", "IV", "V"}
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
        argparse.Namespace: Parsed arguments containing the input folder.
    """
    parser = argparse.ArgumentParser(
        description="Split folders of combined abstract PDFs into single PDFs."
    )
    parser.add_argument("input_folder", type=str,
                        help="Folder of combined PDFs.")
    return parser.parse_args()

# Main API for the rest of the repo.


def split_combined_pdfs(
    input_folder: Path,
    output_folder: Path = Path(OUTPUT_FOLDER),
    staging_folder: Path = Path(SPLIT_FOLDER),
) -> list[dict[str, object]]:
    """Run the split step using derived pipeline defaults.

    Args:
        input_folder: Folder containing combined PDF files.
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
        input_folder: Folder containing combined PDF files.
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

    pdf_paths = [
        path
        for path in sorted(Path(input_folder).iterdir())
        if path.is_file() and path.suffix.lower() == PDF_SUFFIX
    ]

    for pdf_path in pdf_paths:
        metadata.extend(
            split_pdf(
                pdf_path=pdf_path,
                output_folder=staging_folder,
            )
        )

    copy_split_pdfs(staging_folder, output_folder)
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
        toc_page_range = find_toc_page_range(pdf)
        if toc_page_range is None:
            return []

        _, toc_end_page = toc_page_range
        entries = parse_toc(pdf, toc_page_range)
        if not entries:
            return []

        page_offset = derive_page_offset(pdf, entries, toc_end_page)
        for entry in entries:
            entry["pdf_start_page"] = find_title_page(
                pdf=pdf,
                title=str(entry["title"]),
                printed_page=int(entry["printed_start_page"]),
                page_offset=page_offset,
                scan_start_page=toc_end_page + 1,
            )

        metadata: list[dict[str, object]] = []
        for index, entry in enumerate(entries):
            start_page = int(entry["pdf_start_page"])
            if index + 1 < len(entries):
                end_page = int(entries[index + 1]["pdf_start_page"]) - 1
            else:
                end_page = pdf.page_count

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


def find_toc_page_range(pdf: fitz.Document) -> tuple[int, int] | None:
    """Find the table-of-contents pages in a combined PDF.

    Args:
        pdf: Open PDF document.

    Returns:
        tuple[int, int] | None: First and last 1-based TOC page numbers, or
            None when the expected TOC pattern is not present.
    """
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
) -> int:
    """Find the actual PDF page where an abstract title appears.

    Args:
        pdf: Open PDF document.
        title: Abstract title from the TOC.
        printed_page: Printed start page from the TOC.
        page_offset: Number added to the printed page to get the likely PDF page.
        scan_start_page: First 1-based PDF page to use for fallback scanning.

    Returns:
        int: 1-based PDF page containing the abstract title.
    """
    # If it's telling the truth
    expected_page = printed_page + page_offset
    if page_has_title(pdf, expected_page, title):
        return expected_page
    # If the contents page lies, go through entire document to find it.
    for page_number in range(scan_start_page, pdf.page_count + 1):
        if page_has_title(pdf, page_number, title):
            return page_number

    return expected_page


def page_has_title(pdf: fitz.Document, page_number: int, title: str) -> bool:
    """Check whether a PDF page contains a TOC title.

    Args:
        pdf: Open PDF document.
        page_number: 1-based PDF page number to inspect.
        title: Title to search for.

    Returns:
        bool: True when the normalised title appears in the page text.
    """
    if page_number < 1 or page_number > pdf.page_count:
        return False

    page_text = " ".join(
        clean_lines(pdf[page_number - 1].get_text("text").splitlines())
    )
    return normalise(title) in normalise(page_text)


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
    # Possibly overengineered generated code.
    # .strip().lower() may be enough.
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
    with path.open("w", newline="", encoding="utf-8") as file:
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
