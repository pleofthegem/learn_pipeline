"""Contents-page formats, title matching rules, and split export defaults."""
import re
from .config import PDF_FOLDER, SPLIT_METADATA_FOLDER

INPUT_FOLDER = PDF_FOLDER
OUTPUT_FOLDER = PDF_FOLDER
# Retain the existing export filenames and ID column for downstream consumers.
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
CONTENTS_HEADING_RE = re.compile(r"^\s*Contents\s*$", re.IGNORECASE | re.MULTILINE)
SESSION_HEADING_RE = re.compile(r"Session\s+(\d+)\s*:", re.IGNORECASE)
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
MIN_TITLE_TOKENS = 4
TITLE_TOKEN_COVERAGE = 0.85
CONTENTS_FOOTER_RATIO = 0.9
CONTENTS_REFERENCE_MIN_X = 0.8
CONTENTS_ROW_TOLERANCE = 2
FOOTER_LINE_COUNT = 3
CONTENTS_LEADER_RE = re.compile(r"(?:\.\s*){2,}")
# This font encodes fi/fl ligatures as unrelated Unicode characters.
CONTENTS_FONT_CORRECTIONS = {"CrimsonPro": {"Ǟ": "fi", "ǡ": "fl"}}
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
