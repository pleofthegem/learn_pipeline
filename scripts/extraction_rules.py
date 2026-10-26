"""Metadata field names and the supported abstract layout patterns."""
import re
from .config import PDF_FOLDER, HANDOFF_FOLDER, JSON_FOLDER

INPUT_FOLDER = PDF_FOLDER
CSV_OUTPUT_FOLDER = HANDOFF_FOLDER
JSON_OUTPUT_FOLDER = JSON_FOLDER
OUTPUT_CSV: str = "abstract_metadata.csv"
OUTPUT_JSON: str = "abstract_metadata.json"
CSV_ENCODING: str = "utf-8-sig"

HEADER_LINE_LIMIT = 12
TITLE_MAX_LINES = 3
TITLE_HINT_MIN_SCORE = 0.75
TITLE_FONT_TOLERANCE = 0.1
KEYWORD_FONT_TOLERANCE = 0.5
EVENT_ACRONYMS = ("IWA", "AI", "UN", "UK", "USA")

CSV_FIELDNAMES: list[str] = [
    "filename",
    "abstract_title",
    "abstract_authors",
    "abstract_description",
    "abstract_keywords",
    "additional_info",
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
PLACEHOLDER_LINES: set[str] = {
    "this is a sample abstract title",
    "author name author name initials then surnames separated by commas appear here",
}
WATER_BOARD_HEADER = "national water supply and drainage board sri lanka"
WATER_BOARD_TITLE_NOISE_LINES: set[str] = {"qs"}

KEYWORDS_RE = re.compile(
    r"^\s*(?:keywords?|key\s+words?|index\s+terms)\s*[:.\-–—]?\s*(.*)$",
    re.IGNORECASE,
)
ABSTRACT_RE = re.compile(
    r"^\s*abstract(?:\s+of\s+the\s+project)?\s*[:.\-–—]?\s*(.*)$",
    re.IGNORECASE,
)
BRACKETED_TITLE_NOISE_RE = re.compile(r"^\s*[\(\[\{][^\)\]\}]+[\)\]\}]\s*$")
AUTHOR_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'.-]*")
AUTHOR_INITIALS_ONLY_RE = re.compile(r"(?:[A-Z]\.?){1,10}")
AUTHOR_MARKER_CHARS = "*†‡§"
AUTHOR_MARKER_SUFFIX_RE = re.compile(
    rf"(?<=[A-Za-z])\s*"
    rf"(?:\d+(?:\s*,\s*\d+)*(?:\s*,\s*)?)?"
    rf"[{re.escape(AUTHOR_MARKER_CHARS)}]+"
    rf"(?=\s*(?:,|\.|$))"
)
AUTHOR_MARKER_SYMBOL_RE = re.compile(rf"[{re.escape(AUTHOR_MARKER_CHARS)}]+")
AFFILIATION_KEYWORDS: set[str] = {
    "affiliation",
    "board",
    "centre",
    "center",
    "college",
    "department",
    "division",
    "faculty",
    "institute",
    "laboratory",
    "ministry",
    "national",
    "organisation",
    "organization",
    "school",
    "university",
}
EVENT_KEYWORD_RE = re.compile(
    r"\b("
    r"conference|congress|symposium|workshop|summit|forum|meeting|"
    r"seminar|colloquium|exhibition|expo"
    r")\b",
    re.IGNORECASE,
)
MONTH_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|sept|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
    r")\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
PLACE_LABEL_RE = re.compile(
    r"^\s*(?:venue|location|place|host city)\s*[:.\-–—]\s*(.+)$",
    re.IGNORECASE,
)
INLINE_SECTION_RE = re.compile(
    r"\b(?:"
    r"abstract|background|introduction|methods?|methodology|results|"
    r"discussion|conclusions?|references"
    r")\s*[:.\-–—]",
    re.IGNORECASE,
)
