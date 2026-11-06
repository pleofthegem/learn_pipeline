"""Isolate delimiter-separated proposals without rebuilding their PDF content.

This is an explicit alternative to split_pdf. Page arguments and manifest page
numbers are 1-based; automatic selection of this route is deliberately separate.
"""
import argparse
from collections import Counter
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import unicodedata

import fitz

from .config import INTERMEDIATE_FOLDER, PDF_FOLDER
from .pdf_headings import author_names_from_lines, strip_title_quotes
from .pdf_text import join_pdf_lines

LOG = logging.getLogger(__name__)
SUBMISSION_ID = re.compile(r"(?:\d{6,8}(?:-\d+)?|ICNSS\s*#\s*\d+)", re.I)


@dataclass(frozen=True)
class TextLine:
    text: str
    rect: fitz.Rect


@dataclass(frozen=True)
class Region:
    page: int
    rect: fitz.Rect


def read_lines(page: fitz.Page) -> list[TextLine]:
    """Join spans before matching, preserving the original line coordinates."""
    return [TextLine("".join(s["text"] for s in line["spans"]).strip(),
                     fitz.Rect(line["bbox"]))
            for block in page.get_text("dict")["blocks"] if "lines" in block
            for line in block["lines"]
            if any(s["text"].strip() for s in line["spans"])]


def detect_delimiters(lines: list[TextLine]) -> list[fitz.Rect]:
    """Find standalone asterisk runs, including runs wrapped across adjacent lines."""
    found = []
    pending = None
    count = 0
    for line in sorted(lines, key=lambda line: (line.rect.y0, line.rect.x0)):
        if re.fullmatch(r"[\s*]+", line.text):
            if pending is not None and line.rect.y0 - pending.y1 <= line.rect.height:
                pending |= line.rect
                count += line.text.count("*")
            else:
                if pending is not None and count >= 6:
                    found.append(pending)
                pending = fitz.Rect(line.rect)
                count = line.text.count("*")
        else:
            if pending is not None and count >= 6:
                found.append(pending)
            pending, count = None, 0
    if pending is not None and count >= 6:
        found.append(pending)
    return found


def find_running_margins(pdf: fitz.Document, start: int, end: int) -> set[str]:
    """Identify repeated text at page edges, normalising changing page counters."""
    counts = Counter()
    for number in range(start, end + 1):
        page = pdf[number - 1]
        counts.update({margin_key(line.text) for line in read_lines(page)
                       if at_edge(line.rect, page.rect)})
    threshold = max(3, (end - start + 1) // 2)
    return {key for key, count in counts.items() if count >= threshold}


def margin_key(text: str) -> str:
    if re.fullmatch(r"\d+|[ivxlcdm]+", text, re.I):
        return "<page-number>"
    return re.sub(r"\d+", "#", text)


def at_edge(rect: fitz.Rect, page: fitz.Rect) -> bool:
    return rect.y1 < page.y0 + page.height * .09 or rect.y0 > page.y1 - page.height * .09


def determine_boundaries(
    pdf: fitz.Document, start_page: int, end_page: int, *, remove_margins: bool = True,
) -> tuple[list[list[Region]], int, list[str]]:
    """Partition body regions at separators; omit blank and theme-only pages.

    Retain an unclosed final proposal, reporting that it had no closing separator.
    Coordinates come from text/graphics, never a fixed content clipping height.
    """
    if not 1 <= start_page <= end_page <= len(pdf):
        raise ValueError("Start/end pages must be an ordered range inside the PDF.")
    margins = find_running_margins(pdf, start_page, end_page) if remove_margins else set()
    proposals, current, warnings = [], [], []
    separator_count = 0
    for number in range(start_page, end_page + 1):
        page = pdf[number - 1]
        lines = read_lines(page)
        running = [line for line in lines if at_edge(line.rect, page.rect)
                   and margin_key(line.text) in margins]
        body = [line for line in lines if line not in running]
        # Book section dividers contain only uppercase theme headings.
        words = " ".join(line.text for line in body)
        if ((re.match(r"^THEME\s+\d+\s*:", words) and words.upper() == words)
                or re.fullmatch(r"(?:ORAL|POSTER) PRESENTATION ABSTRACTS", words)):
            LOG.info("Skipping section divider on page %s", number)
            continue
        separators = detect_delimiters(body)
        separator_count += len(separators)
        top, bottom = page.rect.y0, page.rect.y1
        for line in running:
            if line.rect.y1 < page.rect.y0 + page.rect.height * .09:
                top = max(top, line.rect.y1)
            else:
                bottom = min(bottom, line.rect.y0)
        # Drawings/images keep figure-only continuation pages in the output.
        objects = [line.rect for line in body if not any(s.intersects(line.rect) for s in separators)]
        objects += [fitz.Rect(b["bbox"]) for b in page.get_text("dict")["blocks"] if b["type"] == 1]
        objects += [d["rect"] for d in page.get_drawings()
                    if d["rect"].height > 1
                    and not (d.get("fill") == (1.0, 1.0, 1.0) and d.get("color") is None)]
        for low, high, closes in zip(
                [top] + [s.y1 for s in separators],
                [s.y0 for s in separators] + [bottom],
                [True] * len(separators) + [False]):
            selected = [r for r in objects if r.y1 > low and r.y0 < high]
            if high > low and selected:
                if any(r.y0 < low - .5 or r.y1 > high + .5 for r in selected):
                    raise ValueError(f"Content overlaps an isolation boundary on page {number}.")
                y0 = max(low, min(r.y0 for r in selected) - 2)
                y1 = min(high, max(r.y1 for r in selected) + 2)
                current.append(Region(number, fitz.Rect(page.rect.x0, y0, page.rect.x1, y1)))
            if closes:
                if current:
                    proposals.append(current)
                    current = []
                else:
                    warnings.append(f"Separator on page {number} closes an empty region.")
    if current:
        proposals.append(current)
        warnings.append("Final proposal has no closing separator; retained through the selected end page.")
    if not separator_count:
        raise ValueError("No asterisk separators found in the selected pages.")
    return proposals, separator_count, warnings


def proposal_lines(pdf: fitz.Document, regions: list[Region]) -> list[str]:
    """Read text within the retained regions, in page/vertical reading order."""
    return [line.text for region in regions
            for line in sorted(read_lines(pdf[region.page - 1]),
                               key=lambda line: (line.rect.y0, line.rect.x0))
            if region.rect.contains(line.rect)]


def reconcile_figure_continuations(
    pdf: fitz.Document, proposals: list[list[Region]], warnings: list[str],
) -> list[list[Region]]:
    """Attach caption-only fragments after extra separators to the prior proposal.

    Only explicit figure/table captions qualify; unidentified prose stays separate.
    This accommodates figures placed after an abstract's apparent closing rule.
    """
    result = []
    for regions in proposals:
        lines = proposal_lines(pdf, regions)
        if (result and lines and all(re.match(r"^(?:Figure|Fig\.|Table)\s+\d+\b", line, re.I)
                                             for line in lines)):
            result[-1].extend(regions)
            warnings.append(f"Attached caption-only continuation on source page {regions[0].page} "
                            "to the preceding proposal (extra separator).")
        else:
            result.append(list(regions))
    return result


def identify_proposals(pdf: fitz.Document, proposals: list[list[Region]], warnings: list[str]) -> list[str]:
    """Use the printed leading ID for naming, never for locating boundaries."""
    identifiers = []
    for number, regions in enumerate(proposals, 1):
        lines = proposal_lines(pdf, regions)
        if lines and SUBMISSION_ID.fullmatch(lines[0]):
            identifier = re.sub(r"\s+", "", lines[0])
        else:
            identifier = f"paper_{number:03d}"
            warnings.append(f"No leading submission ID on source page {regions[0].page}; "
                            f"using {identifier}.")
        if identifier in identifiers:
            raise ValueError(f"Duplicate submission ID: {identifier}")
        identifiers.append(identifier)
    return identifiers


def filename_component(text: str, *, preserve_hash: bool = False) -> str:
    """Use portable letters/numbers, underscores and hyphens in output names."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    pattern = r"[^\w#-]+" if preserve_hash else r"[^\w-]+"
    return re.sub(pattern, "_", text, flags=re.UNICODE).strip("_")


def academic_author_name(author: str) -> str:
    """Format the first author as initials.surname, retaining existing initials.

    Strip titles, retain surname particles, and handle names printed with trailing
    initials (e.g. Jayalekshmi T R). A single name is retained without invention.
    """
    author = re.sub(r"^(?:(?:Dr|Prof|Mr|Mrs|Ms)\.?\s+)+", "", author.strip(), flags=re.I)
    tokens = [token for token in re.split(r"[.\s]+", author) if token]
    if not tokens:
        return "Unknown_Author"
    if len(tokens) == 1:
        return filename_component(tokens[0])
    trailing = []
    while len(tokens) > 1 and tokens[-1].isupper() and len(tokens[-1]) <= 3:
        trailing.insert(0, tokens.pop())
    surname = [tokens.pop()]
    particles = {"de", "da", "dos", "das", "van", "von", "der", "den", "del", "la", "le", "du", "di"}
    while tokens and tokens[-1].lower() in particles:
        surname.insert(0, tokens.pop())
    given = tokens + trailing
    initials = "".join("".join(c + "." for c in token) if token.isupper() and len(token) <= 3
                       else token[0].upper() + "." for token in given)
    return initials + filename_component(" ".join(surname))


def extract_proposal_heading(pdf: fitz.Document, regions: list[Region]) -> tuple[str, str]:
    """Read the prominent title and immediately following bold author block.

    Use span formatting to exclude superscript affiliations, including inline
    superscript Unicode digits. Never search body prose for a filename author.
    An unsupported heading layout returns an empty author for explicit reporting.
    """
    region = regions[0]
    lines = [line for block in pdf[region.page - 1].get_text("dict")["blocks"]
             for line in block.get("lines", [])
             if region.rect.contains(fitz.Rect(line["bbox"]))
             and any(span["text"].strip() for span in line["spans"])]
    lines.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
    heading = lines[:12]
    sizes = [span["size"] for line in heading for span in line["spans"]
             if any(c.isalpha() for c in span["text"]) and not span["flags"] & 1]
    if not sizes:
        return "", ""
    title_size = max(sizes)
    title_indices = [i for i, line in enumerate(heading)
                     if any(any(c.isalpha() for c in span["text"])
                            and abs(span["size"] - title_size) < .5
                            for span in line["spans"])]
    title = join_pdf_lines("".join(span["text"] for span in heading[i]["spans"]).strip()
                     for i in title_indices)
    authors = author_names_from_lines(lines, max(title_indices))
    first = authors[0] if authors else ""
    return strip_title_quotes(title), re.sub(r"\s+", " ", first).strip()


def extract_proposal(pdf: fitz.Document, regions: list[Region], destination: Path) -> None:
    """Transfer vector/text page regions to tightly sized destination pages."""
    with fitz.open() as output:
        for region in regions:
            page = output.new_page(width=region.rect.width, height=region.rect.height)
            page.show_pdf_page(page.rect, pdf, region.page - 1, clip=region.rect)
        output.save(destination, garbage=4, deflate=True)


def isolate_pdf(
    input_pdf: Path, output_folder: Path, *, start_page: int,
    end_page: int | None = None, expected_count: int | None = None,
    remove_margins: bool = True,
    metadata_folder: Path | None = None,
    contents_entries: list[dict] | None = None,
) -> dict:
    """Write <source stem>_<submission ID>_<first author>.pdf and a source-coordinate manifest.

    Preserve the source and existing output files. Validate boundaries/count before
    writing PDFs; refuse filename collisions. Extraction errors propagate to caller.
    """
    input_pdf, output_folder = Path(input_pdf), Path(output_folder)
    metadata_folder = Path(metadata_folder) if metadata_folder is not None else output_folder
    with fitz.open(input_pdf) as pdf:
        proposals, separators, warnings = determine_boundaries(
            pdf, start_page, end_page if end_page is not None else len(pdf),
            remove_margins=remove_margins)
        proposals = reconcile_figure_continuations(pdf, proposals, warnings)
        identifiers = identify_proposals(pdf, proposals, warnings)
        if expected_count is not None and len(proposals) != expected_count:
            raise ValueError(f"Expected {expected_count} proposals, found {len(proposals)} "
                             f"from {separators} separators.")
        headings = [extract_proposal_heading(pdf, regions) for regions in proposals]
        validation = None
        if contents_entries is not None:
            from .split_pdf import normalise_title_for_matching
            if len(contents_entries) != len(proposals):
                raise ValueError("Contents count does not match isolated proposal count.")
            comparisons = []
            for entry, regions, (title, author), identifier in zip(
                    contents_entries, proposals, headings, identifiers):
                if (entry['pdf_start_page'] != regions[0].page
                        or normalise_title_for_matching(entry['title']) != normalise_title_for_matching(title)):
                    raise ValueError(f"Contents title/page mismatch for {identifier}: {entry['title']}")
                comparisons.append({**entry, 'abstract_id': identifier, 'first_author': author})
            validation = {'contents_abstract_count': len(contents_entries),
                          'produced_pdf_count': len(proposals), 'entries': comparisons}
        for identifier, (_, author) in zip(identifiers, headings):
            if not author:
                warnings.append(f"No reliable first author for {identifier}; using Unknown_Author in filename.")
        rows = [{"source_file": input_pdf.name, "abstract_id": identifier,
                 "title": title, "first_author": author, "printed_start_page": None,
                 "pdf_start_page": regions[0].page, "pdf_end_page": regions[-1].page,
                 "page_count": len(regions),
                 "output_file": f"{filename_component(input_pdf.stem)}_"
                                f"{filename_component(identifier, preserve_hash=True)}_"
                                f"{academic_author_name(author)}.pdf",
                 "regions": [{"page": r.page, "bbox": list(r.rect)} for r in regions]}
                for identifier, regions, (title, author) in zip(identifiers, proposals, headings)]
        summary = {"source_file": input_pdf.name, "separator_count": separators,
                   "abstract_count": len(rows), "warnings": warnings, "abstracts": rows}
        if validation is not None:
            for row, entry, comparison in zip(rows, contents_entries, validation['entries']):
                row['printed_start_page'] = entry['printed_start_page']
                comparison['output_file'] = row['output_file']
        targets = [output_folder / row["output_file"] for row in rows]
        manifest = metadata_folder / "isolation_summary.json"
        validation_path = metadata_folder / 'contents_validation.json'
        if any(path.exists() for path in [*targets, manifest, validation_path]):
            raise FileExistsError("Isolation output already exists; choose an empty output directory.")
        output_folder.mkdir(parents=True, exist_ok=True)
        metadata_folder.mkdir(parents=True, exist_ok=True)
        for regions, destination in zip(proposals, targets):
            LOG.info("Writing %s", destination.name)
            try:
                extract_proposal(pdf, regions, destination)
            except Exception:
                LOG.exception("Failed to isolate %s from source pages %s-%s",
                              destination.name, regions[0].page, regions[-1].page)
                raise
        manifest.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if validation is not None:
            validation_path.write_text(json.dumps(validation, indent=2), encoding='utf-8')
        for warning in warnings:
            LOG.warning(warning)
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("--output-folder", type=Path, default=PDF_FOLDER)
    parser.add_argument("--metadata-folder", type=Path, default=INTERMEDIATE_FOLDER / "abstracts_isolated")
    parser.add_argument("--start-page", type=int, required=True, help="First body page, 1-based.")
    parser.add_argument("--end-page", type=int)
    parser.add_argument("--expected-count", type=int, help="Expected proposal count from the contents.")
    parser.add_argument("--keep-margins", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = isolate_pdf(args.input_pdf, args.output_folder, start_page=args.start_page,
                         end_page=args.end_page, expected_count=args.expected_count,
                         remove_margins=not args.keep_margins, metadata_folder=args.metadata_folder)
    print(f"Isolated {result['abstract_count']} proposals from {result['separator_count']} separators.")


if __name__ == "__main__":
    main()
