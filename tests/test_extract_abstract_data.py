import csv
import json
from pathlib import Path

import pytest

from conftest import write_sample_pdf
from extract_abstract_data import (
    clean_author_line,
    extract_abstract_data,
    extract_abstract_metadata,
    extract_keywords,
    pdf_input_files,
    process_pdf,
    standardise_keywords,
    write_csv,
    write_json,
)


@pytest.fixture
def dasgupta_like_pdf(tmp_path: Path) -> Path:
    """Create a PDF that follows the expected Dasgupta-style structure."""
    path = tmp_path / "Dasgupta - Characterization and Analysis of Graywater.pdf"
    write_sample_pdf(
        path,
        [
            "13th IWA International conference (Theme-Water Reuse in developing countries)",
            "Characterization and Analysis of Graywater.",
            "S Dasgupta*, Z P Bhathena**.",
            "*Department of Microbiology, Bhavan's College, Andheri, Mumbai-58",
            "sohini.dasgupta13@gmail.com",
            "** Department of Microbiology, Bhavan's College, Andheri, Mumbai-58",
            "zarine_bhathena@rediffmail.com",
            "Abstract of the Project:",
            "Water is the most abundant resources in the world.",
            "Graywater can be reused safely after treatment.",
            "Keywords: Graywater ; Indicator organisms; Bacteriophages.",
            "The background of research: Water scarcity is increasing.",
        ],
    )
    return path


def test_process_pdf_extracts_dasgupta_like_metadata(
    dasgupta_like_pdf: Path,
) -> None:
    """Check that title, authors, description, and keywords are extracted."""
    row = process_pdf(dasgupta_like_pdf)

    assert row["filename"] == dasgupta_like_pdf.name
    assert row["abstract_title"] == "Characterization and Analysis of Graywater."
    assert row["abstract_authors"] == "S Dasgupta, Z P Bhathena"
    assert row["abstract_description"] == (
        "Water is the most abundant resources in the world. "
        "Graywater can be reused safely after treatment."
    )
    assert row["abstract_keywords"] == (
        "Graywater; Indicator organisms; Bacteriophages."
    )


def test_process_pdf_uses_filename_hint_instead_of_fixed_header_markers(
    tmp_path: Path,
) -> None:
    """Check that unknown leading header text does not become the title."""
    path = tmp_path / "Patel - Flexible Wetland Treatment Study.pdf"
    write_sample_pdf(
        path,
        [
            "Unexpected Symposium Header That Could Change Next Year",
            "Flexible Wetland Treatment Study",
            "A Patel*, B Dlamini**",
            "*Example affiliation",
            "Abstract: This abstract starts on the heading line.",
            "Keywords: wetlands; treatment",
        ],
    )

    row = process_pdf(path)

    assert row["abstract_title"] == "Flexible Wetland Treatment Study"
    assert row["abstract_authors"] == "A Patel, B Dlamini"


def test_process_pdf_rejects_non_pdf_file(tmp_path: Path) -> None:
    """Check that non-PDF files are rejected when processed directly."""
    path = tmp_path / "abstract.txt"
    path.write_text("Not a PDF", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        process_pdf(path)


def test_clean_author_line_removes_marker_only_commas() -> None:
    """Check that author footnote markers do not leave doubled commas."""
    assert clean_author_line("Nay Lin Maunga,*, Tokuchi Naokob") == (
        "Nay Lin Maunga, Tokuchi Naokob"
    )
    assert clean_author_line("Zhenyu Huang1, Xin Dong1,2*") == (
        "Zhenyu Huang, Xin Dong"
    )


def test_standardise_keywords_joins_detected_separator_with_semicolon() -> None:
    """Check that keyword separators are normalised to semicolons."""
    assert standardise_keywords("water, sanitation, reuse") == (
        "water; sanitation; reuse"
    )
    assert standardise_keywords("water ; sanitation; reuse") == (
        "water; sanitation; reuse"
    )


def test_extract_keywords_standardises_comma_separator() -> None:
    """Check that comma-separated keywords are returned with semicolons."""
    assert extract_keywords([
        "Abstract: sample",
        "Keywords: water, sanitation, reuse",
    ]) == "water; sanitation; reuse"


def test_pdf_input_files_creates_missing_folder(tmp_path: Path) -> None:
    """Check that a missing input folder is treated as an empty PDF folder."""
    input_dir = tmp_path / "abstracts_raw"

    assert pdf_input_files(input_dir) == []
    assert input_dir.exists()


def test_extract_abstract_metadata_filters_to_pdfs(
    tmp_path: Path,
    dasgupta_like_pdf: Path,
) -> None:
    """Check that only PDF files in the input folder are processed."""
    input_dir = tmp_path / "abstracts_raw"
    input_dir.mkdir()
    pdf_path = input_dir / dasgupta_like_pdf.name
    pdf_path.write_bytes(dasgupta_like_pdf.read_bytes())
    (input_dir / "notes.txt").write_text("Unsupported", encoding="utf-8")

    rows = extract_abstract_metadata(input_dir)

    assert [row["filename"] for row in rows] == [dasgupta_like_pdf.name]


def test_write_csv_and_json_outputs_metadata(
    tmp_path: Path,
    dasgupta_like_pdf: Path,
) -> None:
    """Check that extracted metadata can be written as CSV and JSON."""
    rows = [process_pdf(dasgupta_like_pdf)]
    csv_path = tmp_path / "csv" / "abstract_metadata.csv"
    json_path = tmp_path / "json" / "abstract_metadata.json"

    write_csv(rows, csv_path)
    write_json(rows, json_path)

    with csv_path.open(newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    with json_path.open(encoding="utf-8") as f:
        json_rows = json.load(f)

    assert csv_rows == rows
    assert json_rows == rows


def test_extract_abstract_data_is_public_pipeline_api(
    tmp_path: Path,
    dasgupta_like_pdf: Path,
) -> None:
    """Check that the public extraction API writes CSV and JSON metadata."""
    input_dir = tmp_path / "abstracts_raw"
    input_dir.mkdir()
    (input_dir / dasgupta_like_pdf.name).write_bytes(
        dasgupta_like_pdf.read_bytes()
    )
    csv_path = tmp_path / "abstract_csv" / "abstract_metadata.csv"
    json_path = tmp_path / "abstract_json" / "abstract_metadata.json"

    rows = extract_abstract_data(
        input_folder=input_dir,
        csv_path=csv_path,
        json_path=json_path,
    )

    assert [row["filename"] for row in rows] == [dasgupta_like_pdf.name]
    assert csv_path.exists()
    assert json_path.exists()
