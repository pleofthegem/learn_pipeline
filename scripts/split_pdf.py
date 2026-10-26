"""Split combined abstract e-book PDFs into individual abstract PDFs."""

import argparse
import csv
import json
import re
import shutil
from math import ceil
from collections.abc import Callable
from pathlib import Path

import fitz

from . import split_rules as rules
from .clear_outputs import clear_folder


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Split folders of combined abstract PDFs into single PDFs."
    )
    parser.add_argument(
        "input_folder",
        nargs="?",
        default=rules.INPUT_FOLDER,
        type=str,
        help="Folder of PDFs to check for combined abstract e-books.",
    )
    return parser.parse_args()


def split_combined_pdfs(
    input_folder: Path,
    output_folder: Path = Path(rules.OUTPUT_FOLDER),
    staging_folder: Path = Path(rules.SPLIT_FOLDER),
) -> list[dict[str, object]]:
    """Run the split step using derived pipeline defaults."""
    input_folder = Path(input_folder)
    output_folder = Path(output_folder)
    staging_folder = Path(staging_folder)
    metadata = split_folder(
        input_folder=input_folder,
        output_folder=output_folder,
        staging_folder=staging_folder,
    )
    write_metadata_csv(metadata, staging_folder / rules.METADATA_CSV)
    write_metadata_json(metadata, staging_folder / rules.METADATA_JSON)
    return metadata


def split_folder(
    input_folder: Path,
    output_folder: Path = Path(rules.OUTPUT_FOLDER),
    staging_folder: Path = Path(rules.SPLIT_FOLDER),
) -> list[dict[str, object]]:
    """Split every combined PDF in a folder."""
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
        if path.is_file() and path.suffix.lower() == rules.PDF_SUFFIX
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
    return metadata


def split_pdf(
    pdf_path: Path,
    output_folder: Path,
) -> list[dict[str, object]]:
    """Split one combined PDF into individual abstract PDFs."""
    with fitz.open(pdf_path) as pdf:
        combined_info = combined_pdf_info(pdf)
        if combined_info is None:
            return []

        toc_end_page, entries, page_offset = combined_info
        matched_entries: list[dict[str, object]] = []
        for entry in entries:
            if "pdf_start_page" in entry:
                # The session-contents fallback already validated its boundaries.
                matched_entries.append(entry)
                continue
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
            end_page = int(entry.get("pdf_end_page", end_page))
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
    """Check whether a PDF matches the expected combined abstract format."""
    with fitz.open(pdf_path) as pdf:
        return combined_pdf_info(pdf) is not None


def combined_pdf_info(
    pdf: fitz.Document,
) -> tuple[int, list[dict[str, object]], int] | None:
    """Try the existing TOC formats before session-organised contents."""
    toc_range = find_toc_page_range(pdf)
    if toc_range:
        entries = parse_toc(pdf, toc_range)
        if len(entries) >= 2:
            try:
                return toc_range[1], entries, derive_page_offset(pdf, entries, toc_range[1])
            except ValueError:
                pass
    return session_contents_info(pdf)


def session_contents_rows(page: fitz.Page) -> list[tuple[str, int]]:
    """Read title/page rows from a dotted-leader contents page.

    Authors are italic; page references are right-aligned. Use text positions
    rather than whitespace so wrapped titles and references touching the title
    are handled without confusing years inside titles with page references.
    """
    lines = []
    for block in page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]:
        for line in block.get("lines", []):
            spans = [span for span in line["spans"]
                     if not span["flags"] & 2 and span["bbox"][1] < page.rect.height * rules.CONTENTS_FOOTER_RATIO]
            if spans:
                lines.append((line["bbox"][1], spans))
    rows = []
    for y, spans in sorted(lines, key=lambda item: item[0]):
        if rows and abs(rows[-1][0] - y) < rules.CONTENTS_ROW_TOLERANCE:
            rows[-1][1].extend(spans)
        else:
            rows.append((y, list(spans)))
    entries = []
    title_lines = []
    for _, spans in rows:
        spans.sort(key=lambda span: span["bbox"][0])
        reference = None
        text = []
        for span in spans:
            value = span["text"].strip()
            if value.isdigit() and span["bbox"][0] > page.rect.width * rules.CONTENTS_REFERENCE_MIN_X:
                reference = int(value)
            else:
                value = span["text"]
                # This proceedings font maps its fi/fl ligatures to unrelated
                # Unicode characters. Correct only that font's extracted text.
                if "CrimsonPro" in span["font"]:
                    value = value.replace("Ǟ", "fi").replace("ǡ", "fl")
                text.append(value)
        line = re.sub(r"(?:\.\s*){2,}", " ", "".join(text)).strip(" .")
        if line.casefold() == "contents":
            continue
        if line:
            title_lines.append(line)
        if reference is not None:
            title = " ".join(title_lines).strip()
            if not title:
                return []
            entries.append((title, reference))
            title_lines = []
    return entries


def session_contents_info(
    pdf: fitz.Document,
) -> tuple[int, list[dict[str, object]], int] | None:
    """Split session-organised abstract books using the printed contents only.

    The contents supply titles, session boundaries and printed start pages.
    Body-title checks establish/validate the printed-to-PDF page offset, but
    never replace contents ranges. PDF bookmarks are deliberately not used.
    """
    if not any(re.search(r"book\s+of\s+abstracts", pdf[i].get_text(), re.I)
               for i in range(min(2, pdf.page_count))):
        return None
    toc_start = next((i for i in range(pdf.page_count)
                      if re.search(r"(?im)^\s*Contents\s*$", pdf[i].get_text())), None)
    if toc_start is None:
        return None
    rows = []
    toc_end = toc_start + 1
    for index in range(toc_start, pdf.page_count):
        page_rows = session_contents_rows(pdf[index])
        if not page_rows:
            break
        rows.extend(page_rows)
        toc_end = index + 1
    if not rows or not re.match(r"Session\s+\d+\s*:", rows[0][0], re.I):
        return None
    printed_pages = [page for _, page in rows]
    if printed_pages != sorted(set(printed_pages)):
        return None
    entries = []
    session = None
    for row_index, (title, printed_page) in enumerate(rows):
        match = re.match(r"Session\s+(\d+)\s*:", title, re.I)
        if match:
            session = match.group(1)
            continue
        if session is None:
            return None
        entries.append({
            "abstract_id": f"S{session}_A{len(entries) + 1:03d}",
            "title": title,
            "printed_start_page": printed_page,
            "contents_row": row_index,
        })
    if len(entries) < 2:
        return None
    try:
        offset = derive_page_offset(pdf, entries, toc_end)
    except ValueError:
        return None
    if printed_pages[0] + offset <= toc_end or printed_pages[-1] + offset > pdf.page_count:
        return None
    # Verify the mapping across the book, allowing a title to follow its
    # contents-designated start page. Keep every listed abstract in its range.
    verified = 0
    for entry in entries:
        start = int(entry["printed_start_page"]) + offset
        row_index = int(entry["contents_row"])
        end = rows[row_index + 1][1] + offset - 1 if row_index + 1 < len(rows) else pdf.page_count
        if any(page_has_title(pdf, page, str(entry["title"]))
               for page in range(start, min(start + rules.SESSION_TITLE_LOOKAHEAD, end + 1))):
            verified += 1
    if verified < ceil(len(entries) * rules.SESSION_TITLE_COVERAGE):
        return None
    # The final abstract has no following contents entry. End at the final
    # matching printed footer, excluding unnumbered trailing covers.
    last_start = int(entries[-1]["printed_start_page"]) + offset
    numbered_pages = [page for page in range(last_start, pdf.page_count + 1)
                      if str(page - offset) in clean_lines(pdf[page - 1].get_text().splitlines())[-3:]]
    if not numbered_pages:
        return None
    for entry in entries:
        row_index = int(entry.pop("contents_row"))
        entry["pdf_start_page"] = int(entry["printed_start_page"]) + offset
        entry["pdf_end_page"] = (rows[row_index + 1][1] + offset - 1
                                 if row_index + 1 < len(rows) else numbered_pages[-1])
    return toc_end, entries, offset


def parse_toc(
    pdf: fitz.Document,
    toc_page_range: tuple[int, int] | None = None,
) -> list[dict[str, object]]:
    """Parse abstract IDs, titles, and printed start pages from the TOC."""
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
        if line in rules.SKIP_TOC_LINES:
            continue

        if rules.CODE_PATTERN.fullmatch(line):
            abstract_id = line
            title_lines = []
            continue

        if abstract_id and rules.PAGE_PATTERN.fullmatch(line):
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

        match = rules.PRESENTATION_PATTERN.fullmatch(line)
        if match:
            abstract_number = match.group("number")
            abstract_prefix = section_prefix or "PR"
            title = match.group("title")
            title_lines = [title.strip()] if title else []
            continue

        if abstract_number and rules.PAGE_PATTERN.fullmatch(line):
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
    """Find the table-of-contents pages in a combined PDF."""
    code_toc_range = find_code_toc_page_range(pdf)
    if code_toc_range is not None:
        return code_toc_range

    return find_presentation_toc_page_range(pdf)


def find_code_toc_page_range(pdf: fitz.Document) -> tuple[int, int] | None:
    return matching_page_range(pdf, lambda lines: "CONTENT" in lines)


def find_presentation_toc_page_range(pdf: fitz.Document) -> tuple[int, int] | None:
    return matching_page_range(pdf, lambda lines: any(rules.PRESENTATION_PATTERN.fullmatch(line) for line in lines))


def matching_page_range(
    pdf: fitz.Document, matches: Callable[[list[str]], bool],
) -> tuple[int, int] | None:
    """Find the first consecutive run of matching pages, using 1-based numbers."""
    start = end = None
    for number, page in enumerate(pdf, 1):
        if matches(clean_lines(page.get_text("text").splitlines())):
            start = number if start is None else start
            end = number
        elif start is not None:
            break
    return (start, end) if start is not None else None


def derive_page_offset(
    pdf: fitz.Document,
    entries: list[dict[str, object]],
    toc_end_page: int,
) -> int:
    """Derive the offset between printed TOC pages and PDF pages."""
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
    """Find the actual PDF page where an abstract title appears."""
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
    """Check whether a PDF page starts with a TOC title."""
    if page_number < 1 or page_number > pdf.page_count:
        return False

    page_lines = clean_lines(pdf[page_number - 1].get_text("text").splitlines())
    title_area = title_match_area(page_lines)
    if normalise(title) in normalise(title_area):
        return True

    title_tokens = significant_title_tokens(title)
    if len(title_tokens) < rules.MIN_TITLE_TOKENS:
        return False

    page_tokens = set(significant_title_tokens(title_area))
    matched_tokens = [token for token in title_tokens if token in page_tokens]
    required_matches = max(rules.MIN_TITLE_TOKENS, ceil(len(title_tokens) * rules.TITLE_TOKEN_COVERAGE))
    return len(matched_tokens) >= required_matches


def title_match_area(lines: list[str]) -> str:
    """Return the page region used to decide whether a title starts a page."""
    return " ".join(lines[:rules.TITLE_MATCH_LINE_LIMIT])


def significant_title_tokens(text: str) -> list[str]:
    """Return normalised title tokens used for fuzzy title matching."""
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in rules.FUZZY_TITLE_STOPWORDS
    ]


def save_page_range(
    pdf: fitz.Document, start_page: int, end_page: int, output_path: Path,
) -> None:
    """Save a 1-based inclusive page range to a new PDF."""
    with fitz.open() as output:
        output.insert_pdf(pdf, from_page=start_page - 1, to_page=end_page - 1)
        output.save(output_path)


def copy_split_pdfs(staging_folder: Path, output_folder: Path) -> list[Path]:
    """Copy staged split PDF files into the final output folder."""
    output_folder.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []

    for path in sorted(staging_folder.glob(f"*{rules.PDF_SUFFIX}")):
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
    """Remove combined source PDFs from the final output folder after splitting."""
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
    """Clear split staging files while preserving .gitkeep."""
    clear_folder(folder)


def clean_lines(lines: list[str]) -> list[str]:
    """Strip blank text lines."""
    return [line.strip() for line in lines if line.strip()]


def normalise(text: str) -> str:
    """Normalise text for title matching."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def write_metadata_csv(metadata: list[dict[str, object]], path: Path) -> None:
    """Write split metadata to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=rules.CSV_ENCODING) as file:
        writer = csv.DictWriter(file, fieldnames=rules.METADATA_FIELDS)
        writer.writeheader()
        writer.writerows(metadata)


def write_metadata_json(metadata: list[dict[str, object]], path: Path) -> None:
    """Write split metadata to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2)


def main() -> None:
    """Run the folder splitter from the command line."""
    args = parse_args()
    output_folder = Path(rules.OUTPUT_FOLDER)
    staging_folder = Path(rules.SPLIT_FOLDER)
    csv_path = staging_folder / rules.METADATA_CSV
    json_path = staging_folder / rules.METADATA_JSON
    metadata = split_combined_pdfs(Path(args.input_folder))

    print(f"Split {len(metadata)} abstracts.")
    print(f"PDFs saved in: {output_folder}")
    print(f"Metadata saved to: {csv_path} and {json_path}")


if __name__ == "__main__":
    main()
