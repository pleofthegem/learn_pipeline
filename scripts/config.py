"""Shared filesystem layout. Defaults are anchored to the project, not the shell."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT_FOLDER = ROOT / "input"
OUTPUT_ROOT = ROOT / "output"
HANDOFF_FOLDER = OUTPUT_ROOT / "handoff_bundle"
PDF_FOLDER = HANDOFF_FOLDER / "pdfs"
INTERMEDIATE_FOLDER = OUTPUT_ROOT / "intermediate_outputs"
AGGREGATED_FOLDER = INTERMEDIATE_FOLDER / "abstracts_aggregated"
SPLIT_METADATA_FOLDER = INTERMEDIATE_FOLDER / "abstracts_split"
CLEAN_FOLDER = INTERMEDIATE_FOLDER / "abstracts_clean"
CSV_FOLDER = INTERMEDIATE_FOLDER / "csv"
JSON_FOLDER = INTERMEDIATE_FOLDER / "json"
WEBINAR_FOLDER = ROOT / "webinar"
