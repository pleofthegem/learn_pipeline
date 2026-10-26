"""Extract high-level abstract metadata from PDF files."""

import argparse
import csv
from dataclasses import dataclass
from difflib import SequenceMatcher
from collections.abc import Callable
import json
import re
from pathlib import Path

import fitz  # PyMuPDF

from . import extraction_rules as rules


AdditionalInfo = dict[str, str]
RowValue = str | AdditionalInfo
Row = dict[str, RowValue]


@dataclass(frozen=True)
class TextLine:
    """One text line extracted from a PDF."""

    text: str
    size: float


def parse_args() -> argparse.Namespace:
    """Parse command-line options for metadata extraction."""
    parser = argparse.ArgumentParser(
        description="Extract metadata from abstract PDF files."
    )
    parser.add_argument(
        "input_folder",
        nargs="?",
        default=rules.INPUT_FOLDER,
        help="Folder containing PDF abstracts.",
        type=str,
    )
    parser.add_argument(
        "--conference-name",
        default=None,
        help=(
            "Default conference name to use when a PDF does not contain one."
        ),
        type=str,
    )
    parser.add_argument(
        "--conference-place",
        default=None,
        help=(
            "Default conference place to use when a PDF does not contain one."
        ),
        type=str,
    )
    return parser.parse_args()


def extract_text_lines_from_pdf(path: Path) -> list[TextLine]:
    """Extract text lines and font sizes from every page of a PDF file."""
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
    """Extract text from every page of a PDF file."""
    return "\n".join(line.text for line in extract_text_lines_from_pdf(path))


def clean_lines(text: str) -> list[str]:
    """Normalise extracted text into non-empty lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def normalise_heading(line: str) -> str:
    """Normalise a possible section heading for comparison."""
    heading = line.split(":", 1)[0]
    heading = re.sub(r"\s+", " ", heading).strip(" :").lower()
    return heading


def is_section_heading(line: str) -> bool:
    """Check whether a line looks like a known abstract section heading."""
    return normalise_heading(line) in rules.SECTION_HEADINGS


def first_section_index(lines: list[str]) -> int | None:
    """Find the first recognised section heading in extracted lines."""
    for index, line in enumerate(lines):
        if is_section_heading(line):
            return index
    return None


def is_contact_line(line: str) -> bool:
    """Check whether a line is contact information."""
    lower_line = line.lower()
    return "@" in line or "http://" in lower_line or "https://" in lower_line


def comparable_text(text: str) -> str:
    """Normalise text for loose title comparison."""
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def is_placeholder_line(line: str) -> bool:
    """Check whether a line is leftover template placeholder text."""
    return comparable_text(line) in rules.PLACEHOLDER_LINES


def is_bracketed_title_noise_line(line: str) -> bool:
    """Check whether a title-range line is only bracketed noise text."""
    return bool(rules.BRACKETED_TITLE_NOISE_RE.fullmatch(line))


def is_title_noise_line(line: str) -> bool:
    """Check whether a line should be ignored while extracting titles."""
    return is_placeholder_line(line) or is_bracketed_title_noise_line(line)


def is_water_board_header_line(line: str) -> bool:
    """Check whether a line is the Water Board abstract header."""
    return comparable_text(line) == rules.WATER_BOARD_HEADER


def is_page_number_line(line: str) -> bool:
    """Check whether a line is only a printed page number."""
    return bool(re.fullmatch(r"\d{1,4}", line.strip()))


def is_ignored_water_board_title_line(line: str) -> bool:
    """Check whether a Water Board pre-author line is not part of the title."""
    return (
        is_water_board_header_line(line)
        or is_page_number_line(line)
        or is_title_noise_line(line)
        or comparable_text(line) in rules.WATER_BOARD_TITLE_NOISE_LINES
    )


def title_hint_from_filename(path: Path) -> str:
    """Infer a title hint from filenames shaped like `Author - Title.pdf`."""
    if " - " not in path.stem:
        return ""
    return path.stem.split(" - ", 1)[1].strip()


def pre_section_lines(lines: list[TextLine]) -> list[tuple[int, TextLine]]:
    """Return lines that appear before the first recognised section."""
    texts = [line.text for line in lines]
    section_index = first_section_index(texts)
    limit = section_index if section_index is not None else min(len(lines), rules.HEADER_LINE_LIMIT)
    return list(enumerate(lines[:limit]))


def title_candidates(lines: list[TextLine]) -> list[tuple[int, TextLine]]:
    """Keep pre-section text that can belong to a title."""
    return [(index, line) for index, line in pre_section_lines(lines)
            if not is_contact_line(line.text) and not is_title_noise_line(line.text)]


def find_title_from_filename(
    lines: list[TextLine],
    path: Path,
) -> tuple[str, int] | None:
    """Find a title by matching text against the PDF filename."""
    hint = title_hint_from_filename(path)
    if not hint:
        return None

    expected = comparable_text(hint)
    candidates = title_candidates(lines)
    best_score = 0.0
    best_title = ""
    best_index = -1

    for start in range(len(candidates)):
        for end in range(start, min(start + rules.TITLE_MAX_LINES, len(candidates))):
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

    if best_score >= rules.TITLE_HINT_MIN_SCORE:
        return best_title, best_index
    return None


def find_title_from_layout(lines: list[TextLine]) -> tuple[str, int]:
    """Find a title from the largest text before the first section."""
    candidates = title_candidates(lines)
    if not candidates:
        return "", -1

    largest_size = max(line.size for _, line in candidates)
    smallest_size = min(line.size for _, line in candidates)
    if abs(largest_size - smallest_size) <= rules.TITLE_FONT_TOLERANCE:
        index, line = candidates[0]
        return line.text, index

    title_lines: list[str] = []
    last_index = -1

    for index, line in candidates:
        if abs(line.size - largest_size) > rules.TITLE_FONT_TOLERANCE:
            if title_lines:
                break
            continue

        title_lines.append(line.text)
        last_index = index
        if len(title_lines) == rules.TITLE_MAX_LINES:
            break

    return " ".join(title_lines), last_index


def find_title_from_water_board_layout(
    lines: list[TextLine],
) -> tuple[str, int] | None:
    """Find Water Board titles by joining text before the author list starts."""
    if not any(is_water_board_header_line(line.text) for line in lines[:5]):
        return None

    texts = [line.text for line in lines]
    section_index = first_section_index(texts)
    limit = section_index if section_index is not None else len(lines)
    author_index = find_author_start_index(lines, limit)
    if author_index is None:
        return None

    title_lines: list[str] = []
    last_index = -1
    for index, line in enumerate(lines[:author_index]):
        text = line.text
        if is_contact_line(text) or is_ignored_water_board_title_line(text):
            continue

        title_lines.append(text)
        last_index = index

    if not title_lines:
        return None
    return " ".join(title_lines), last_index


def clean_author_line(line: str) -> str:
    """Remove common author footnote markers from an author line."""
    return ", ".join(parse_author_names(line))


def clean_author_name(name: str) -> str:
    """Remove footnote markers from one author name."""
    name = rules.AUTHOR_MARKER_SUFFIX_RE.sub("", name)
    name = rules.AUTHOR_MARKER_SYMBOL_RE.sub("", name)
    name = re.sub(r"\d+(?=\s|,|\.|$)", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip(" .,;")


def normalise_author_separators(text: str) -> str:
    """Normalise common author separators before comma splitting."""
    return re.sub(r"\s+\band\s+(?=[A-Z])", ", ", text)


def is_initials_only(text: str) -> bool:
    """Check whether text is only author initials."""
    text = clean_author_name(text).replace(" ", "")
    return bool(rules.AUTHOR_INITIALS_ONLY_RE.fullmatch(text))


def parse_author_names(text: str) -> list[str]:
    """Split a comma-separated author list into cleaned author names."""
    text = normalise_author_separators(text)
    names: list[str] = []
    pending_initials = ""
    for part in text.split(","):
        name = clean_author_name(part)
        if name:
            if is_initials_only(name):
                pending_initials = (
                    f"{pending_initials} {name}".strip()
                    if pending_initials else name
                )
                continue
            if pending_initials:
                name = f"{pending_initials} {name}"
                pending_initials = ""
            names.append(name)
    if pending_initials:
        names.append(pending_initials)
    return names


def is_affiliation_text(text: str) -> bool:
    """Check whether text looks like institutional affiliation metadata."""
    lower_text = text.lower()
    return any(keyword in lower_text for keyword in rules.AFFILIATION_KEYWORDS)


def is_probable_author_name(name: str) -> bool:
    """Check whether one comma-separated item looks like an author name."""
    cleaned = clean_author_name(name)
    if not cleaned or is_contact_line(cleaned) or is_placeholder_line(cleaned):
        return False
    if is_affiliation_text(cleaned):
        return False

    words = rules.AUTHOR_WORD_RE.findall(cleaned.replace(".", " "))
    if len(words) < 2 or len(words) > 10:
        return False

    return (
        any(word[0].isupper() for word in words)
        and any(len(word) > 1 for word in words)
    )


def is_probable_author_line(line: str) -> bool:
    """Check whether a line is likely part of a comma-separated author list."""
    if is_author_noise(line):
        return False
    has_marker_shape = has_author_marker_shape(line)
    if "," not in line and not has_marker_shape:
        return False

    probable_names = [
        name for name in parse_author_names(line)
        if is_probable_author_name(name)
    ]
    if len(probable_names) >= 2:
        return True

    return has_marker_shape and len(probable_names) == 1


def is_author_fragment_line(line: str) -> bool:
    """Check whether a line can be part of a wrapped author list."""
    if is_author_noise(line):
        return False

    return (
        is_probable_author_line(line)
        or is_initials_only(line)
        or has_author_marker_shape(line)
    )


def has_author_marker_shape(line: str) -> bool:
    """Check whether text contains a name-style author marker suffix."""
    return bool(rules.AUTHOR_MARKER_SUFFIX_RE.search(line))


def is_author_noise(line: str) -> bool:
    """Exclude section headings, affiliations, contacts and template text."""
    return bool(is_contact_line(line) or is_placeholder_line(line)
                or is_section_heading(line) or rules.KEYWORDS_RE.match(line)
                or is_affiliation_text(line))


def is_author_marker_fragment_line(line: str) -> bool:
    return has_author_marker_shape(line) and not is_author_noise(line)


def find_author_start_index(
    lines: list[TextLine], limit: int, min_index: int = 0,
) -> int | None:
    """Prefer explicit author markers, then a probable author list."""
    marked = find_author_marker_start_index(lines, limit, min_index)
    if marked is not None:
        return marked
    return author_block_start(lines, limit, min_index,
                              lambda index: is_probable_author_line(lines[index].text))


def find_author_marker_start_index(
    lines: list[TextLine], limit: int, min_index: int = 0,
) -> int | None:
    return author_block_start(lines, limit, min_index,
                              lambda index: is_author_marker_start_candidate(lines, index))


def author_block_start(
    lines: list[TextLine], limit: int, min_index: int, matches: Callable[[int], bool],
) -> int | None:
    """Find a matching author line and include any preceding wrapped initials."""
    for index, _ in enumerate(lines[min_index:limit], start=min_index):
        if matches(index):
            while index > 0 and is_initials_only(lines[index - 1].text):
                index -= 1
            return index
    return None


def is_author_marker_start_candidate(
    lines: list[TextLine],
    index: int,
) -> bool:
    """Check whether one line can start a marker-shaped author block."""
    text = lines[index].text
    if not is_author_marker_fragment_line(text):
        return False
    if is_probable_author_line(text):
        return True
    return index > 0 and is_initials_only(lines[index - 1].text)


def extract_title(lines: list[TextLine], path: Path) -> tuple[str, int]:
    """Return the title and its last line index (-1 if missing)."""
    return (find_title_from_filename(lines, path)
            or find_title_from_water_board_layout(lines)
            or find_title_from_layout(lines))


def extract_authors(lines: list[TextLine], title_end_index: int) -> str:
    """Extract authors from comma-separated pre-section author lists."""
    texts = [line.text for line in lines]
    section_index = first_section_index(texts)
    limit = section_index if section_index is not None else len(lines)
    author_lines: list[str] = []
    start = find_author_start_index(
        lines,
        limit,
        min_index=max(title_end_index + 1, 0),
    )
    if start is None:
        start = max(title_end_index + 1, 0)

    for line in lines[start:limit]:
        text = line.text
        if is_section_heading(text):
            break

        if is_author_fragment_line(text) or (
            author_lines
            and author_lines[-1].strip().lower().endswith(" and")
            and is_probable_author_name(clean_author_line(text))
        ):
            author_lines.append(text)
            continue
        if author_lines:
            break

    if author_lines:
        return ", ".join(parse_author_names(" ".join(author_lines)))

    for line in lines[start:limit]:
        text = line.text
        if is_contact_line(text) or is_placeholder_line(text):
            continue
        if is_section_heading(text):
            break

        author = clean_author_line(text)
        if author and is_probable_author_name(author):
            return author

    return ""


def compact_info_text(text: str) -> str:
    """Clean one extracted line for event metadata."""
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,;")


def title_case_if_all_caps(text: str) -> str:
    """Convert all-caps event/place text to display casing."""
    text = compact_info_text(text)
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return text

    uppercase_ratio = sum(char.isupper() for char in letters) / len(letters)
    if uppercase_ratio < 0.75:
        return text

    cased = text.title()
    cased = re.sub(
        r"\b(\d+)(St|Nd|Rd|Th)\b",
        lambda match: f"{match.group(1)}{match.group(2).lower()}",
        cased,
    )
    for acronym in rules.EVENT_ACRONYMS:
        cased = re.sub(
            rf"\b{re.escape(acronym.title())}\b",
            acronym,
            cased,
        )
    for word in ("And", "At", "By", "For", "In", "Of", "On", "Or", "The", "To"):
        cased = re.sub(rf"(?<!^)\b{word}\b", word.lower(), cased)
    return cased


def is_date_line(line: str) -> bool:
    """Check whether a line looks like an event date line."""
    if not rules.YEAR_RE.search(line):
        return False
    return bool(rules.MONTH_RE.search(line) or re.search(r"\d{1,2}\s*[-/]\s*\d{1,2}", line))


def is_probable_place_line(line: str) -> bool:
    """Check whether a short header line looks like a venue place."""
    line = compact_info_text(line)
    if not line or is_contact_line(line) or is_section_heading(line):
        return False
    if rules.EVENT_KEYWORD_RE.search(line) or is_date_line(line):
        return False
    if any(char.isdigit() for char in line):
        return False

    words = line.split()
    if len(words) > 6:
        return False
    return "," in line or line.isupper()


def extract_conference_name(header_lines: list[str]) -> str:
    """Extract a conference/event name from PDF header lines."""
    for index, line in enumerate(header_lines):
        if not rules.EVENT_KEYWORD_RE.search(line):
            continue

        name_lines = [line]
        for extra_line in header_lines[index + 1:index + 4]:
            if (
                is_date_line(extra_line)
                or (is_probable_place_line(extra_line) and "," in extra_line)
                or rules.PLACE_LABEL_RE.match(extra_line)
            ):
                break
            name_lines.append(extra_line)

        return title_case_if_all_caps(" ".join(name_lines))
    return ""


def extract_conference_place(header_lines: list[str]) -> str:
    """Extract a conference place from PDF header lines."""
    for line in header_lines:
        match = rules.PLACE_LABEL_RE.match(line)
        if match:
            return title_case_if_all_caps(match.group(1))

    for index, line in enumerate(header_lines):
        if is_date_line(line):
            match = re.search(r"\b(?:19|20)\d{2}\b\s*,\s*(.+)$", line)
            if match:
                place = compact_info_text(match.group(1))
                if is_probable_place_line(place):
                    return title_case_if_all_caps(place)
            for next_line in header_lines[index + 1:index + 3]:
                if is_probable_place_line(next_line):
                    return title_case_if_all_caps(next_line)
    return ""


def extract_additional_info(
    lines: list[TextLine],
    title_end_index: int,
    default_additional_info: AdditionalInfo | None = None,
) -> AdditionalInfo:
    """Extract conference name and place from PDF header text."""
    texts = [line.text for line in lines]
    section_index = first_section_index(texts)
    limits = [min(len(texts), rules.HEADER_LINE_LIMIT)]
    if section_index is not None:
        limits.append(section_index)
    if title_end_index > 0:
        limits.append(title_end_index)

    header_lines: list[str] = []
    for text in texts[:max(0, min(limits))]:
        cleaned = compact_info_text(text)
        if cleaned and not is_contact_line(cleaned):
            header_lines.append(cleaned)

    defaults = default_additional_info or {}
    name = extract_conference_name(header_lines)
    place = extract_conference_place(header_lines)
    return {
        "name": name or compact_info_text(defaults.get("name", "")),
        "place": place or compact_info_text(defaults.get("place", "")),
    }


def default_additional_info_from_values(
    name: str | None = None,
    place: str | None = None,
) -> AdditionalInfo | None:
    """Build optional batch-level conference metadata from CLI values."""
    additional_info = {
        "name": compact_info_text(name or ""),
        "place": compact_info_text(place or ""),
    }
    if not additional_info["name"] and not additional_info["place"]:
        return None
    return additional_info


def standardise_keywords(keywords: str) -> str:
    """Normalise separators, giving semicolons precedence over commas."""
    separator = ";" if ";" in keywords else ","
    parts = (clean_keyword_part(part) for part in keywords.split(separator))
    return ", ".join(part for part in parts if part)


def clean_keyword_part(keyword: str) -> str:
    """Clean one keyword item after separator splitting."""
    keyword = re.sub(r"\s+", " ", keyword)
    return keyword.strip(" \t\r\n,;:.")


def text_before_inline_section(text: str) -> str:
    """Return text before an inline section heading, if one is present."""
    match = rules.INLINE_SECTION_RE.search(text)
    if not match:
        return text.strip()
    return text[:match.start()].strip()


def is_keyword_continuation_text(text: str) -> bool:
    """Check whether a line looks like wrapped keyword text."""
    text = text.strip()
    if not text:
        return False

    words = re.findall(r"[A-Za-z0-9]+", text)
    if len(words) <= 8:
        return True
    if ";" in text and len(words) <= 14:
        return True
    return False


def extract_keywords_from_text_lines(lines: list[TextLine]) -> str:
    """Extract keywords from a `Keywords:` or `Key words:` block."""
    for index, line in enumerate(lines):
        match = rules.KEYWORDS_RE.match(line.text)
        if not match:
            continue

        keyword_lines: list[str] = []
        first_line = text_before_inline_section(match.group(1))
        if first_line:
            keyword_lines.append(first_line)

        for continuation in lines[index + 1:]:
            text = continuation.text.strip()
            if is_section_heading(text):
                break
            if continuation.size > line.size + rules.KEYWORD_FONT_TOLERANCE:
                break

            text = text_before_inline_section(text)
            if not text:
                break
            if not is_keyword_continuation_text(text):
                break
            keyword_lines.append(text)

        return standardise_keywords(" ".join(keyword_lines))
    return ""


def extract_keywords(lines: list[str]) -> str:
    """Extract keywords from cleaned PDF text lines."""
    return extract_keywords_from_text_lines([
        TextLine(text=line, size=0.0) for line in lines
    ])


def abstract_start(lines: list[str]) -> tuple[int, str]:
    """Find where the abstract description should begin."""
    for index, line in enumerate(lines):
        match = rules.ABSTRACT_RE.match(line)
        if match:
            return index + 1, match.group(1).strip()

    section_index = first_section_index(lines)
    if section_index is None:
        return len(lines), ""
    return section_index + 1, ""


def extract_description(lines: list[str]) -> str:
    """Extract the abstract description text."""
    start_index, same_line_text = abstract_start(lines)
    description_lines: list[str] = []
    if same_line_text:
        description_lines.append(same_line_text)

    for line in lines[start_index:]:
        if rules.KEYWORDS_RE.match(line):
            break
        if description_lines and is_section_heading(line):
            break
        description_lines.append(line)

    return " ".join(description_lines).strip()


def process_pdf(
    path: Path,
    default_additional_info: AdditionalInfo | None = None,
) -> Row:
    """Extract metadata from one PDF abstract."""
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
        "abstract_keywords": extract_keywords_from_text_lines(text_lines),
        "additional_info": extract_additional_info(
            text_lines,
            title_end_index,
            default_additional_info,
        ),
    }


def pdf_input_files(input_dir: Path) -> list[Path]:
    """List PDF files from an input directory."""
    input_dir.mkdir(parents=True, exist_ok=True)
    return sorted(
        path for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def extract_abstract_metadata(
    input_folder: Path = Path(rules.INPUT_FOLDER),
    default_additional_info: AdditionalInfo | None = None,
) -> list[Row]:
    """Extract abstract metadata from every PDF in a folder."""
    return [
        process_pdf(path, default_additional_info)
        for path in pdf_input_files(Path(input_folder))
    ]


def write_csv(rows: list[Row], csv_path: Path) -> None:
    """Write metadata rows to a CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding=rules.CSV_ENCODING) as f:
        writer = csv.DictWriter(f, fieldnames=rules.CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, dict)
                    else value
                )
                for key, value in row.items()
            })


def write_json(rows: list[Row], json_path: Path) -> None:
    """Write metadata rows to a JSON file."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")


def extract_abstract_data(
    input_folder: Path = Path(rules.INPUT_FOLDER),
    csv_path: Path = Path(rules.CSV_OUTPUT_FOLDER) / rules.OUTPUT_CSV,
    json_path: Path = Path(rules.JSON_OUTPUT_FOLDER) / rules.OUTPUT_JSON,
    default_additional_info: AdditionalInfo | None = None,
) -> list[Row]:
    """Extract abstract metadata and write CSV and JSON outputs."""
    rows = extract_abstract_metadata(
        Path(input_folder),
        default_additional_info,
    )
    write_csv(rows, Path(csv_path))
    write_json(rows, Path(json_path))
    return rows


def main() -> None:
    """Run abstract metadata extraction from the CLI."""
    args = parse_args()
    csv_path = Path(rules.CSV_OUTPUT_FOLDER) / rules.OUTPUT_CSV
    json_path = Path(rules.JSON_OUTPUT_FOLDER) / rules.OUTPUT_JSON
    rows = extract_abstract_data(
        input_folder=Path(args.input_folder),
        csv_path=csv_path,
        json_path=json_path,
        default_additional_info=default_additional_info_from_values(
            name=args.conference_name,
            place=args.conference_place,
        ),
    )

    print(f"Processed {len(rows)} files.")
    print(f"CSV created: {csv_path}")
    print(f"JSON created: {json_path}")


if __name__ == "__main__":
    main()
