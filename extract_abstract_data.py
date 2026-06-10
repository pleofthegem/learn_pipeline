"""Extract high-level abstract metadata from PDF files."""

import argparse
import csv
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import re
from pathlib import Path

import fitz  # PyMuPDF

Row = dict[str, str]


@dataclass(frozen=True)
class TextLine:
    """One text line extracted from a PDF.

    Attributes:
        text: Text content of the line.
        size: Largest font size used by the line.
    """

    text: str
    size: float


INPUT_FOLDER: str = "abstracts_raw"
CSV_OUTPUT_FOLDER: str = "abstract_csv"
JSON_OUTPUT_FOLDER: str = "abstract_json"
OUTPUT_CSV: str = "abstract_metadata.csv"
OUTPUT_JSON: str = "abstract_metadata.json"

CSV_FIELDNAMES: list[str] = [
    "filename",
    "abstract_title",
    "abstract_authors",
    "abstract_description",
    "abstract_keywords",
]

SECTION_HEADINGS: set[str] = {
    "abstract",
    "abstract of the project",
    "background",
    "introduction",
    "method",
    "methods",
    "methodology",
    "results",
    "results and discussion",
    "discussion",
    "conclusion",
    "conclusions",
    "keywords",
    "key words",
    "the background of research",
    "nature of issue",
    "findings and results",
    "significance of the research",
    "references",
}

KEYWORDS_RE = re.compile(
    r"^\s*(?:keywords?|key\s+words?|index\s+terms)\s*[:.\-–—]?\s*(.*)$",
    re.IGNORECASE,
)
ABSTRACT_RE = re.compile(
    r"^\s*abstract(?:\s+of\s+the\s+project)?\s*[:.\-–—]?\s*(.*)$",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line options for metadata extraction.

    Returns:
        argparse.Namespace: Parsed CLI arguments. The namespace contains
            `input_folder`, the directory of PDF abstracts to process. When it
            is omitted, `INPUT_FOLDER` is used.
    """
    parser = argparse.ArgumentParser(
        description="Extract metadata from abstract PDF files."
    )
    parser.add_argument(
        "input_folder",
        nargs="?",
        default=INPUT_FOLDER,
        help="Folder containing PDF abstracts.",
        type=str,
    )
    return parser.parse_args()


def extract_text_lines_from_pdf(path: Path) -> list[TextLine]:
    """Extract text lines and font sizes from every page of a PDF file.

    Args:
        path: Path to the PDF file to read.

    Returns:
        list[TextLine]: Extracted text lines in PDF order. Each line includes
            its text and largest font size.
    """
    lines: list[TextLine] = []
    with fitz.open(path) as pdf:
        for page in pdf:
            data = page.get_text("dict")
            for block in data["blocks"]:
                for line in block.get("lines", []):
                    text = "".join(
                        span["text"] for span in line.get("spans", [])
                    ).strip()
                    if not text:
                        continue
                    size = max(span["size"] for span in line.get("spans", []))
                    lines.append(TextLine(text=text, size=size))
    return lines


def extract_text_from_pdf(path: Path) -> str:
    """Extract text from every page of a PDF file.

    Args:
        path: Path to the PDF file to read.

    Returns:
        str: Combined text extracted from all pages, separated by newlines.
    """
    return "\n".join(line.text for line in extract_text_lines_from_pdf(path))


def clean_lines(text: str) -> list[str]:
    """Normalise extracted text into non-empty lines.

    Args:
        text: Raw text extracted from a PDF.

    Returns:
        list[str]: Non-empty text lines with surrounding whitespace removed.
    """
    return [line.strip() for line in text.splitlines() if line.strip()]


def normalise_heading(line: str) -> str:
    """Normalise a possible section heading for comparison.

    Args:
        line: Text line that may be a heading.

    Returns:
        str: Lowercase heading text with trailing colons removed and internal
            whitespace collapsed.
    """
    heading = line.split(":", 1)[0]
    heading = re.sub(r"\s+", " ", heading).strip(" :").lower()
    return heading


def is_section_heading(line: str) -> bool:
    """Check whether a line looks like a known abstract section heading.

    Args:
        line: Text line to classify.

    Returns:
        bool: `True` when the line is or starts with a known section heading,
            otherwise `False`.
    """
    return normalise_heading(line) in SECTION_HEADINGS


def first_section_index(lines: list[str]) -> int | None:
    """Find the first recognised section heading in extracted lines.

    Args:
        lines: Cleaned PDF text lines.

    Returns:
        int | None: Zero-based index of the first recognised section heading,
            or `None` when no section heading is found.
    """
    for index, line in enumerate(lines):
        if is_section_heading(line):
            return index
    return None


def is_contact_line(line: str) -> bool:
    """Check whether a line is contact information.

    Args:
        line: Text line to classify.

    Returns:
        bool: `True` when the line contains an email address or URL, otherwise
            `False`.
    """
    lower_line = line.lower()
    return "@" in line or "http://" in lower_line or "https://" in lower_line


def comparable_text(text: str) -> str:
    """Normalise text for loose title comparison.

    Args:
        text: Text to normalise.

    Returns:
        str: Lowercase alphanumeric text with punctuation removed and
            whitespace collapsed.
    """
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def title_hint_from_filename(path: Path) -> str:
    """Infer a title hint from filenames shaped like `Author - Title.pdf`.

    Args:
        path: PDF path being processed.

    Returns:
        str: The filename-derived title hint, or an empty string when the
            filename does not contain a dash separator.
    """
    if " - " not in path.stem:
        return ""
    return path.stem.split(" - ", 1)[1].strip()


def pre_section_lines(lines: list[TextLine]) -> list[tuple[int, TextLine]]:
    """Return lines that appear before the first recognised section.

    Args:
        lines: Text lines extracted from a PDF.

    Returns:
        list[tuple[int, TextLine]]: Pairs of original line index and line data
            before the first recognised section heading.
    """
    texts = [line.text for line in lines]
    section_index = first_section_index(texts)
    limit = section_index if section_index is not None else min(len(lines), 12)
    return list(enumerate(lines[:limit]))


def find_title_from_filename(
    lines: list[TextLine],
    path: Path,
) -> tuple[str, int] | None:
    """Find a title by matching text against the PDF filename.

    Args:
        lines: Text lines extracted from a PDF.
        path: PDF path being processed.

    Returns:
        tuple[str, int] | None: Matched title text and original line index of
            the final title line, or `None` when no close match is found.
    """
    hint = title_hint_from_filename(path)
    if not hint:
        return None

    expected = comparable_text(hint)
    candidates = [
        (index, line) for index, line in pre_section_lines(lines)
        if not is_contact_line(line.text)
    ]
    best_score = 0.0
    best_title = ""
    best_index = -1

    for start in range(len(candidates)):
        for end in range(start, min(start + 3, len(candidates))):
            window = candidates[start:end + 1]
            title = " ".join(line.text for _, line in window)
            score = SequenceMatcher(
                None,
                expected,
                comparable_text(title),
            ).ratio()
            if score > best_score:
                best_score = score
                best_title = title
                best_index = window[-1][0]

    if best_score >= 0.75:
        return best_title, best_index
    return None


def find_title_from_layout(lines: list[TextLine]) -> tuple[str, int]:
    """Find a title from the largest text before the first section.

    Args:
        lines: Text lines extracted from a PDF.

    Returns:
        tuple[str, int]: Title text and original line index of the final title
            line. The index is `-1` when no title line is found.
    """
    candidates = [
        (index, line) for index, line in pre_section_lines(lines)
        if not is_contact_line(line.text)
    ]
    if not candidates:
        return "", -1

    largest_size = max(line.size for _, line in candidates)
    smallest_size = min(line.size for _, line in candidates)
    if abs(largest_size - smallest_size) <= 0.1:
        index, line = candidates[0]
        return line.text, index

    title_lines: list[str] = []
    last_index = -1

    for index, line in candidates:
        if abs(line.size - largest_size) > 0.1:
            if title_lines:
                break
            continue

        title_lines.append(line.text)
        last_index = index
        if len(title_lines) == 3:
            break

    return " ".join(title_lines), last_index


def clean_author_line(line: str) -> str:
    """Remove common author footnote markers from an author line.

    Args:
        line: Raw author line extracted from the PDF.

    Returns:
        str: Author line with simple superscript-style markers removed.
    """
    line = re.sub(r"[*\d]+(?=\s|,|\.|$)", "", line)
    line = re.sub(r"\s*,\s*,+\s*", ", ", line)
    line = re.sub(r"\s+,", ",", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip(" .,;")


def extract_title(lines: list[TextLine], path: Path) -> tuple[str, int]:
    """Extract an abstract title from cleaned PDF lines.

    Args:
        lines: Text lines extracted from a PDF.
        path: PDF path being processed.

    Returns:
        tuple[str, int]: The extracted title and the zero-based index of the
            last line used for the title. The index is `-1` when no title is
            found.
    """
    filename_title = find_title_from_filename(lines, path)
    if filename_title:
        return filename_title
    return find_title_from_layout(lines)


def extract_authors(lines: list[TextLine], title_end_index: int) -> str:
    """Extract authors from the pre-section lines after the title.

    Args:
        lines: Text lines extracted from a PDF.
        title_end_index: Zero-based index of the final title line.

    Returns:
        str: Author names joined in one string, or an empty string when no
            likely author line is found.
    """
    texts = [line.text for line in lines]
    section_index = first_section_index(texts)
    limit = section_index if section_index is not None else min(len(lines), 12)
    authors: list[str] = []

    for line in lines[title_end_index + 1:limit]:
        text = line.text
        if is_contact_line(text):
            continue
        if is_section_heading(text):
            break

        author = clean_author_line(text)
        if author:
            authors.append(author)
        if authors:
            break

    return "; ".join(authors)


def extract_keywords(lines: list[str]) -> str:
    """Extract keywords from a `Keywords:` or `Key words:` line.

    Args:
        lines: Cleaned PDF text lines.

    Returns:
        str: Keyword text after the heading, or an empty string when no keyword
            line is found.
    """
    for index, line in enumerate(lines):
        match = KEYWORDS_RE.match(line)
        if not match:
            continue

        keywords = match.group(1).strip()
        if keywords:
            return keywords
        if index + 1 < len(lines):
            return lines[index + 1].strip()
    return ""


def abstract_start(lines: list[str]) -> tuple[int, str]:
    """Find where the abstract description should begin.

    Args:
        lines: Cleaned PDF text lines.

    Returns:
        tuple[int, str]: The zero-based index where description text starts and
            any description text found on the same line as the abstract
            heading. If no explicit abstract heading is found, the first known
            section heading is used as a fallback.
    """
    for index, line in enumerate(lines):
        match = ABSTRACT_RE.match(line)
        if match:
            return index + 1, match.group(1).strip()

    section_index = first_section_index(lines)
    if section_index is None:
        return len(lines), ""
    return section_index + 1, ""


def extract_description(lines: list[str]) -> str:
    """Extract the abstract description text.

    Args:
        lines: Cleaned PDF text lines.

    Returns:
        str: Description text, usually the text after `Abstract:` up to
            `Keywords:` or the next recognised section heading. Returns an
            empty string when no description can be inferred.
    """
    start_index, same_line_text = abstract_start(lines)
    description_lines: list[str] = []
    if same_line_text:
        description_lines.append(same_line_text)

    for line in lines[start_index:]:
        if KEYWORDS_RE.match(line):
            break
        if description_lines and is_section_heading(line):
            break
        description_lines.append(line)

    return " ".join(description_lines).strip()


def process_pdf(path: Path) -> Row:
    """Extract metadata from one PDF abstract.

    Args:
        path: Path to the PDF file to process.

    Returns:
        Row: Dictionary containing `filename`, `abstract_title`,
            `abstract_authors`, `abstract_description`, and `abstract_keywords`.

    Raises:
        ValueError: If `path` does not have a PDF suffix.
    """
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Unsupported file type: {path.suffix}")

    text_lines = extract_text_lines_from_pdf(path)
    lines = [line.text for line in text_lines]
    title, title_end_index = extract_title(text_lines, path)
    return {
        "filename": path.name,
        "abstract_title": title,
        "abstract_authors": extract_authors(text_lines, title_end_index),
        "abstract_description": extract_description(lines),
        "abstract_keywords": extract_keywords(lines),
    }


def pdf_input_files(input_dir: Path) -> list[Path]:
    """List PDF files from an input directory.

    Args:
        input_dir: Directory to scan for PDF input files.

    Returns:
        list[Path]: Sorted PDF file paths. The input directory is created when
            missing, allowing an empty pipeline step to complete cleanly.
    """
    input_dir.mkdir(parents=True, exist_ok=True)
    return sorted(
        path for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def extract_abstract_metadata(input_folder: Path = Path(INPUT_FOLDER)) -> list[Row]:
    """Extract abstract metadata from every PDF in a folder.

    Args:
        input_folder: Directory containing PDF abstracts.

    Returns:
        list[Row]: Metadata rows sorted by PDF filename.
    """
    return [process_pdf(path) for path in pdf_input_files(Path(input_folder))]


def write_csv(rows: list[Row], csv_path: Path) -> None:
    """Write metadata rows to a CSV file.

    Args:
        rows: Metadata rows to write using `CSV_FIELDNAMES`.
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
    """Write metadata rows to a JSON file.

    Args:
        rows: Metadata rows to serialise as JSON.
        json_path: Destination JSON path. The parent directory is created if
            needed.

    Returns:
        None.
    """
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> None:
    """Run abstract metadata extraction from the CLI.

    Returns:
        None.
    """
    args = parse_args()
    rows = extract_abstract_metadata(Path(args.input_folder))
    csv_path = Path(CSV_OUTPUT_FOLDER) / OUTPUT_CSV
    json_path = Path(JSON_OUTPUT_FOLDER) / OUTPUT_JSON

    write_csv(rows, csv_path)
    write_json(rows, json_path)

    print(f"Processed {len(rows)} files.")
    print(f"CSV created: {csv_path}")
    print(f"JSON created: {json_path}")


if __name__ == "__main__":
    main()
