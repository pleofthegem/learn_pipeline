"""Split combined PDFs into the documents listed in their contents.

prepare_individual_pdfs manages a batch and its manifests; split_combined_pdf
writes one combined PDF's document ranges. Contents readers return page mappings
without writing files. All PDF page numbers in metadata are 1-based.
"""

import argparse
import csv
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Literal

import fitz

from . import split_rules as rules
from .clear_outputs import clear_folder


@dataclass
class ContentsEntry:
    """One printed contents entry, retaining its original reference and PDF mapping.

    Every entry is a split document; kind records its label without excluding it.
    A missing PDF start/end means that the entry has not been resolved.
    """

    entry_id: str
    title: str
    printed_start_page: int
    kind: Literal["document", "session"] = "document"
    pdf_start_page: int | None = None
    pdf_end_page: int | None = None


@dataclass
class CombinedPdfContents:
    """All contents entries, the inclusive contents-page range, and page offset.

    PDF pages are 1-based; expected PDF page = printed page + page_offset.
    Every entry, including a session-labelled entry, is included in splitting.
    content_end_page is the last numbered body page, or None to use the PDF end.
    """

    contents_start_page: int
    contents_end_page: int
    entries: list[ContentsEntry]
    page_offset: int
    content_end_page: int | None = None


def parse_args() -> argparse.Namespace:
    """Read the optional input-folder argument; default to the configured PDF folder."""
    parser = argparse.ArgumentParser(
        description="Split combined PDFs into individual documents using their contents."
    )
    parser.add_argument(
        "input_folder",
        nargs="?",
        default=rules.INPUT_FOLDER,
        type=Path,
        help="Folder of PDFs to check for supported combined-document contents.",
    )
    return parser.parse_args()


def prepare_individual_pdfs(
    input_folder: Path,
    output_folder: Path = rules.OUTPUT_FOLDER,
    metadata_folder: Path = rules.SPLIT_METADATA_FOLDER,
) -> list[dict[str, object]]:
    """Prepare individual PDFs from a batch of combined PDFs and export a manifest.

    Inspect PDFs directly inside input_folder. Write the documents listed in
    recognised contents straight into output_folder; ordinary PDFs are left untouched.
    Clear metadata_folder (except .gitkeep) and write the split CSV/JSON manifests there.
    No split PDFs are staged or copied between output folders.

    When input and output are the same working folder, remove successfully split
    combined PDFs after all PDF writes and manifest exports succeed. With separate
    input and output folders, preserve input PDFs. On failure, keep source PDFs;
    partial PDFs may remain in output_folder. Return one metadata row per document.
    """
    input_folder, output_folder = Path(input_folder), Path(output_folder)
    metadata_folder = Path(metadata_folder)
    metadata_root = metadata_folder.resolve()
    if any(folder.resolve().is_relative_to(metadata_root)
           for folder in (input_folder, output_folder)):
        raise ValueError("Metadata folder cannot be or contain the input or output folder.")

    input_folder.mkdir(parents=True, exist_ok=True)
    output_folder.mkdir(parents=True, exist_ok=True)
    clear_folder(metadata_folder)
    # Snapshot the batch so newly written PDFs are not processed again.
    sources = sorted(
        path for path in input_folder.iterdir()
        if path.is_file() and path.suffix.lower() == rules.PDF_SUFFIX
    )
    metadata = []
    split_sources = []
    for source in sources:
        rows = split_combined_pdf(source, output_folder)
        metadata.extend(rows)
        if rows:
            split_sources.append(source)

    write_split_manifest(metadata, metadata_folder)
    if input_folder.resolve() == output_folder.resolve():
        for source in split_sources:
            source.unlink()
    return metadata


def split_combined_pdf(
    pdf_path: Path,
    output_folder: Path,
) -> list[dict[str, object]]:
    """Read one combined PDF and write each listed document to output_folder.

    Keep the source PDF. Return one manifest row per generated PDF, or [] for an
    unrecognised contents format. Errors propagate; partial outputs may remain.
    """
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    metadata = []
    with fitz.open(pdf_path) as pdf:
        contents = read_combined_pdf_contents(pdf)
        if contents is None:
            return []
        for entry, start_page, end_page in resolve_document_page_ranges(pdf, contents):
            output_file = f"{pdf_path.stem}_{entry.entry_id}.pdf"
            write_pdf_page_range(pdf, start_page, end_page, output_folder / output_file)
            metadata.append({
                "source_file": pdf_path.name,
                # Preserve the existing manifest column for downstream consumers.
                "abstract_id": entry.entry_id,
                "title": entry.title,
                "printed_start_page": entry.printed_start_page,
                "pdf_start_page": start_page,
                "pdf_end_page": end_page,
                "page_count": end_page - start_page + 1,
                "output_file": output_file,
            })
    return metadata


def resolve_document_page_ranges(
    pdf: fitz.Document,
    contents: CombinedPdfContents,
) -> list[tuple[ContentsEntry, int, int]]:
    """Set every entry's inclusive PDF range and return (entry, start, end) tuples.

    Use printed references plus the shared offset, never body-title matches. Each
    entry ends before the next distinct start; entries sharing a start share its
    range. The final entry ends at content_end_page, or the PDF's final page.
    Raise ValueError for invalid bounds or unordered starts before mutating entries.
    """
    last_page = contents.content_end_page if contents.content_end_page is not None else pdf.page_count
    if not contents.contents_end_page < last_page <= pdf.page_count:
        raise ValueError("Content end page must lie inside the PDF body.")
    starts = [entry.printed_start_page + contents.page_offset for entry in contents.entries]
    if any(current < previous for previous, current in zip(starts, starts[1:])):
        raise ValueError("Contents page references must be in reading order.")
    if any(start <= contents.contents_end_page or start > last_page for start in starts):
        raise ValueError("Contents page references point outside the document body.")

    distinct_starts = sorted(set(starts))
    following_starts = distinct_starts[1:] + [last_page + 1]
    end_by_start = {start: following - 1 for start, following in zip(distinct_starts, following_starts)}
    ranges = []
    for entry, start in zip(contents.entries, starts):
        entry.pdf_start_page = start
        entry.pdf_end_page = end_by_start[start]
        ranges.append((entry, start, entry.pdf_end_page))
    return ranges


def read_combined_pdf_contents(pdf: fitz.Document) -> CombinedPdfContents | None:
    """Read supported contents and establish their printed-to-PDF offset.

    Try code/presentation contents first, then session contents. Return None when
    the structure or offset cannot be recognised. Entry page ranges remain unset
    until resolve_document_page_ranges is called. This does not write files.
    """
    contents_pages = find_numbered_contents_pages(pdf)
    if contents_pages:
        first_page, last_page = contents_pages
        entries = parse_numbered_contents(pdf, contents_pages)
        if len(entries) >= 2:
            try:
                offset = calculate_printed_page_offset(pdf, entries, last_page)
                return CombinedPdfContents(first_page, last_page, entries, offset)
            except ValueError:
                pass
    return parse_session_contents(pdf)


def parse_session_contents(pdf: fitz.Document) -> CombinedPdfContents | None:
    """Read session contents and establish their offset and final body page.

    Read consecutive dotted-leader contents pages beginning with a session row.
    Retain every row, assign stable IDs, establish the printed-to-PDF offset and
    find the final numbered body page. Return None for an unrecognised structure
    or offset. Leave entry ranges unset for the shared range resolver.
    """
    first_page = next((number for number, page in enumerate(pdf, 1)
                       if rules.CONTENTS_HEADING_RE.search(page.get_text())), None)
    if first_page is None:
        return None

    rows = []
    last_page = first_page
    for number in range(first_page, pdf.page_count + 1):
        page_rows = read_session_contents_rows(pdf[number - 1])
        if not page_rows:
            break
        rows.extend(page_rows)
        last_page = number
    if not rows or not rules.SESSION_HEADING_RE.match(rows[0][0]):
        return None
    entries = []
    session = None
    document_number = 0
    for title, printed_page in rows:
        heading = rules.SESSION_HEADING_RE.match(title)
        if heading:
            session = heading.group(1)
            entries.append(ContentsEntry(f"S{session}", title, printed_page, kind="session"))
        else:
            document_number += 1
            entries.append(ContentsEntry(f"S{session}_A{document_number:03d}", title, printed_page))
    if len(entries) < 2:
        return None
    anchors = [entry for entry in entries if entry.kind != "session"] or entries
    try:
        offset = calculate_printed_page_offset(pdf, anchors, last_page)
    except ValueError:
        return None
    first_body_page = entries[0].printed_start_page + offset
    final_page = find_last_numbered_page(pdf, first_body_page, offset)
    return CombinedPdfContents(first_page, last_page, entries, offset,
                               content_end_page=final_page)


def find_last_numbered_page(pdf: fitz.Document, first_page: int, page_offset: int) -> int | None:
    """Search backward from the PDF end for a footer matching page minus offset.

    Inspect final nonblank lines on valid PDF pages at or after first_page. Return a
    1-based PDF page, or None when no matching printed page number is found.
    """
    for number in range(pdf.page_count, max(1, first_page) - 1, -1):
        footer = strip_nonempty_lines(pdf[number - 1].get_text().splitlines())[-rules.FOOTER_LINE_COUNT:]
        if str(number - page_offset) in footer:
            return number
    return None


def read_session_contents_rows(page: fitz.Page) -> list[tuple[str, int]]:
    """Read title/page rows from a dotted-leader contents page.

    In this format, italic text is author information and right-margin numbers
    are page references. Merge spans on the same visual row and accumulate title
    lines until a reference appears. Ignore footer text and dotted leaders.
    Return (title, printed_page) pairs, or [] for an empty/unusable page.
    """
    # Keep title/reference spans, then merge fragments at the same vertical position.
    lines = []
    for block in page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]:
        for line in block.get("lines", []):
            spans = [
                span for span in line["spans"]
                if not span["flags"] & 2
                and span["bbox"][1] < page.rect.height * rules.CONTENTS_FOOTER_RATIO
            ]
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
                for font_name, substitutions in rules.CONTENTS_FONT_CORRECTIONS.items():
                    if font_name in span["font"]:
                        for source, replacement in substitutions.items():
                            value = value.replace(source, replacement)
                text.append(value)
        line = rules.CONTENTS_LEADER_RE.sub(" ", "".join(text)).strip(" .")
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


def parse_numbered_contents(
    pdf: fitz.Document,
    contents_pages: tuple[int, int],
) -> list[ContentsEntry]:
    """Read code/presentation entries from a known inclusive, 1-based page range.

    Code entries take precedence if both patterns occur. Return entries with
    printed references and unset PDF ranges; this does not locate contents pages.
    """
    first_page, last_page = contents_pages
    lines = []
    for number in range(first_page, min(last_page, pdf.page_count) + 1):
        lines.extend(strip_nonempty_lines(pdf[number - 1].get_text("text").splitlines()))
    return parse_code_contents_entries(lines) or parse_presentation_contents_entries(lines)


def parse_code_contents_entries(lines: list[str]) -> list[ContentsEntry]:
    """Read code → title lines → printed page sequences, keeping codes as IDs.

    Ignore configured contents headers and incomplete entries without a page.
    """
    entries: list[ContentsEntry] = []
    entry_id: str | None = None
    title_lines: list[str] = []

    for line in lines:
        if line in rules.SKIP_TOC_LINES:
            continue

        if rules.CODE_PATTERN.fullmatch(line):
            entry_id = line
            title_lines = []
            continue

        if entry_id and rules.PAGE_PATTERN.fullmatch(line):
            entries.append(ContentsEntry(entry_id, " ".join(title_lines), int(line)))
            entry_id = None
            title_lines = []
            continue

        if entry_id:
            title_lines.append(line)

    return entries


def parse_presentation_contents_entries(lines: list[str]) -> list[ContentsEntry]:
    """Read Presentation-number → title → printed-page sequences.

    Capture the oral/poster prefix when each entry begins, producing O01/P01 IDs;
    use PR01 when no section is given. Ignore entries without a closing page.
    """
    entries: list[ContentsEntry] = []
    section_prefix: str | None = None
    document_number: str | None = None
    entry_prefix: str | None = None
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
            document_number = match.group("number")
            entry_prefix = section_prefix or "PR"
            title = match.group("title")
            title_lines = [title.strip()] if title else []
            continue

        if document_number and rules.PAGE_PATTERN.fullmatch(line):
            identifier = f"{entry_prefix}{int(document_number):02d}"
            entries.append(ContentsEntry(identifier, " ".join(title_lines), int(line)))
            document_number = None
            entry_prefix = None
            title_lines = []
            continue

        if document_number:
            title_lines.append(line)

    return entries


def find_numbered_contents_pages(pdf: fitz.Document) -> tuple[int, int] | None:
    """Locate the first consecutive contents block, preferring the code format.

    Code pages contain CONTENT; presentation pages contain a Presentation-number
    line. Return inclusive 1-based page numbers, or None if neither matches.
    """
    code_pages = find_consecutive_matching_pages(pdf, lambda lines: "CONTENT" in lines)
    if code_pages is not None:
        return code_pages
    return find_consecutive_matching_pages(
        pdf, lambda lines: any(rules.PRESENTATION_PATTERN.fullmatch(line) for line in lines),
    )


def find_consecutive_matching_pages(
    pdf: fitz.Document, matches: Callable[[list[str]], bool],
) -> tuple[int, int] | None:
    """Return the first consecutive page block accepted by matches, or None.

    Pass stripped nonblank page lines to the predicate. The returned bounds are
    1-based and inclusive; stop at the first nonmatching page after a match.
    """
    start = end = None
    for number, page in enumerate(pdf, 1):
        if matches(strip_nonempty_lines(page.get_text("text").splitlines())):
            start = number if start is None else start
            end = number
        elif start is not None:
            break
    return (start, end) if start is not None else None


def calculate_printed_page_offset(
    pdf: fitz.Document,
    entries: list[ContentsEntry],
    toc_end_page: int,
) -> int:
    """Establish PDF page minus printed page, preferring consistent footers.

    Otherwise locate any listed title after the contents. Title matches are only
    offset evidence; entries without body titles are still split by reference.
    Raise ValueError if neither source establishes an offset; never guess one.
    """
    footer_offset = offset_from_printed_footers(pdf, entries, toc_end_page)
    if footer_offset is not None:
        return footer_offset
    for entry in entries:
        if not entry.title.strip():
            continue
        for number in range(toc_end_page + 1, pdf.page_count + 1):
            if page_starts_with_title(pdf, number, entry.title):
                return number - entry.printed_start_page
    raise ValueError("Could not establish a reliable printed-to-PDF page offset.")


def offset_from_printed_footers(
    pdf: fitz.Document,
    entries: list[ContentsEntry],
    contents_end_page: int,
) -> int | None:
    """Return the uniquely best offset supported by at least two printed footers.

    Inspect numeric final lines after the contents. Count each candidate once per
    page and reject candidates placing any listed start outside the body. Return
    None for insufficient evidence or a tie, allowing title-based offset detection.
    """
    offsets = Counter()
    for number in range(contents_end_page + 1, pdf.page_count + 1):
        footer = strip_nonempty_lines(pdf[number - 1].get_text().splitlines())[-rules.FOOTER_LINE_COUNT:]
        for line in set(footer):
            if not rules.PAGE_PATTERN.fullmatch(line):
                continue
            offset = number - int(line)
            if all(contents_end_page < entry.printed_start_page + offset <= pdf.page_count
                   for entry in entries):
                offsets[offset] += 1
    candidates = offsets.most_common()
    if not candidates or candidates[0][1] < 2:
        return None
    if len(candidates) > 1 and candidates[0][1] == candidates[1][1]:
        return None
    return candidates[0][0]


def page_starts_with_title(pdf: fitz.Document, page_number: int, title: str) -> bool:
    """Match a title against the first configured number of nonblank page lines.

    Accept a punctuation-insensitive substring or the configured significant-word
    overlap. Return False for empty titles or out-of-range 1-based page numbers.
    """
    if page_number < 1 or page_number > pdf.page_count:
        return False

    page_lines = strip_nonempty_lines(pdf[page_number - 1].get_text("text").splitlines())
    title_area = " ".join(page_lines[:rules.TITLE_MATCH_LINE_LIMIT])
    expected = normalise_title_for_matching(title)
    if not expected:
        return False
    if expected in normalise_title_for_matching(title_area):
        return True

    title_tokens = significant_title_tokens(title)
    if len(title_tokens) < rules.MIN_TITLE_TOKENS:
        return False

    page_tokens = set(significant_title_tokens(title_area))
    matched_tokens = [token for token in title_tokens if token in page_tokens]
    required_matches = max(rules.MIN_TITLE_TOKENS, ceil(len(title_tokens) * rules.TITLE_TOKEN_COVERAGE))
    return len(matched_tokens) >= required_matches


def significant_title_tokens(text: str) -> list[str]:
    """Extract lowercase ASCII word/number tokens, excluding configured stopwords."""
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in rules.FUZZY_TITLE_STOPWORDS
    ]


def write_pdf_page_range(
    pdf: fitz.Document, start_page: int, end_page: int, output_path: Path,
) -> None:
    """Save an inclusive 1-based page range without changing the open source PDF.

    The destination folder must exist. PyMuPDF read/save errors propagate.
    """
    with fitz.open() as output:
        output.insert_pdf(pdf, from_page=start_page - 1, to_page=end_page - 1)
        output.save(output_path)


def strip_nonempty_lines(lines: list[str]) -> list[str]:
    """Strip surrounding whitespace from each line and discard empty lines."""
    return [line.strip() for line in lines if line.strip()]


def normalise_title_for_matching(text: str) -> str:
    """Keep lowercase ASCII letters and digits for punctuation-insensitive matching."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def write_split_manifest(metadata: list[dict[str, object]], folder: Path) -> None:
    """Write the same split records to the configured CSV and JSON files in folder.

    Create folder if needed. CSV has a BOM and the configured column order; JSON
    retains the metadata values. Empty batches still produce a header and [].
    Write errors propagate so batch preparation retains the combined source PDFs.
    """
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / rules.METADATA_CSV).open("w", newline="", encoding=rules.CSV_ENCODING) as stream:
        writer = csv.DictWriter(stream, fieldnames=rules.METADATA_FIELDS)
        writer.writeheader()
        writer.writerows(metadata)
    with (folder / rules.METADATA_JSON).open("w", encoding="utf-8") as stream:
        json.dump(metadata, stream, indent=2)


def main() -> None:
    """Run batch splitting from CLI arguments and print counts and output locations."""
    args = parse_args()
    output_folder = rules.OUTPUT_FOLDER
    metadata_folder = rules.SPLIT_METADATA_FOLDER
    csv_path = metadata_folder / rules.METADATA_CSV
    json_path = metadata_folder / rules.METADATA_JSON
    metadata = prepare_individual_pdfs(args.input_folder)

    print(f"Split {len(metadata)} documents.")
    print(f"PDFs saved in: {output_folder}")
    print(f"Metadata saved to: {csv_path} and {json_path}")


if __name__ == "__main__":
    main()
