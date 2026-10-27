"""Supported source formats and presentation exclusion rules."""
from .config import AGGREGATED_FOLDER, PDF_FOLDER

PDF_OUTPUT_FOLDER = PDF_FOLDER
OFFICE_SUFFIXES: set[str] = {".doc", ".docx"}
SUPPORTED_SUFFIXES: set[str] = {'.pdf', *OFFICE_SUFFIXES}
POWERPOINT_PDF_MARKERS: tuple[str, ...] = ("pptx", "ppt", "presentation")
