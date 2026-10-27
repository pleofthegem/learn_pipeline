"""Anonymisation patterns and export defaults for the optional full workflow."""
from .config import PDF_FOLDER, CLEAN_FOLDER, CSV_FOLDER, JSON_FOLDER

INPUT_FOLDER = PDF_FOLDER
OUTPUT_FOLDER = CLEAN_FOLDER
CSV_OUTPUT_FOLDER = CSV_FOLDER
JSON_OUTPUT_FOLDER = JSON_FOLDER
OUTPUT_CSV: str = "anonymised_abstracts.csv"
OUTPUT_JSON: str = "anonymised_abstracts.json"
CSV_ENCODING: str = "utf-8-sig"
PDF_SUFFIX: str = ".pdf"
SUPPORTED_SUFFIXES: set[str] = {PDF_SUFFIX}
CSV_FIELDNAMES: list[str] = [
    "file_name",
    "run_id",
    "emails_removed_count",
    "orcids_removed_count",
    "phones_removed_count",
    "clean_text_file",
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
