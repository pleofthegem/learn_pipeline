import csv
import json
from pathlib import Path

import pytest

from anonymise_abstracts import (
    anonymise_text,
    anonymise_text_with_counts,
    clean_text_path,
    existing_rows,
    extract_text_from_pdf,
    process_file,
    read_csv_rows,
    read_json_rows,
    resolve_input_path,
    supported_input_files,
    upsert_rows,
    write_csv,
    write_json,
)

ZERO_LOG_FIELDS = {
    "run_id": "",
    "emails_removed_count": "",
    "orcids_removed_count": "",
    "phones_removed_count": "",
}


def test_extract_text_from_pdf(
    sample_pdf_path: Path,
    sample_paragraphs: list[str],
) -> None:
    """Check that PDF text extraction returns all inserted paragraphs."""
    extracted_text = extract_text_from_pdf(sample_pdf_path)

    for paragraph in sample_paragraphs:
        assert paragraph in extracted_text


def test_anonymise_text_replaces_supported_identifiers(sample_text: str) -> None:
    """Check that email, ORCID, and phone values are anonymised."""
    clean_text = anonymise_text(sample_text)

    assert "author@example.com" not in clean_text
    assert "https://orcid.org/0000-0002-1825-0097" not in clean_text
    assert "+44 20 7946 0958" not in clean_text
    assert "[EMAIL_REMOVED]" in clean_text
    assert "[ORCID_REMOVED]" in clean_text
    assert "[PHONE_REMOVED]" in clean_text


def test_anonymise_text_with_counts_counts_removed_identifiers(
    sample_text: str,
) -> None:
    """Check that each supported removal type is counted."""
    clean_text, counts = anonymise_text_with_counts(sample_text)

    assert "author@example.com" not in clean_text
    assert counts == {
        "emails_removed_count": "1",
        "orcids_removed_count": "1",
        "phones_removed_count": "1",
    }


def test_anonymise_text_masks_email_before_adjacent_sentence(
    email_before_adjacent_sentence_text: str,
) -> None:
    """Check that sentence text after an email is preserved."""
    clean_text = anonymise_text(email_before_adjacent_sentence_text)

    assert clean_text == "[EMAIL_REMOVED].This was a test"


def test_process_file_extracts_and_anonymises_pdf(sample_pdf_path: Path) -> None:
    """Check that PDF processing returns metadata and anonymised text."""
    row = process_file(sample_pdf_path)

    assert row["file_name"] == "abstract_001.pdf"
    assert "file_type" not in row
    assert row["emails_removed_count"] == "1"
    assert row["orcids_removed_count"] == "1"
    assert row["phones_removed_count"] == "1"
    assert "author@example.com" not in row["clean_text"]
    assert "[EMAIL_REMOVED]" in row["clean_text"]
    assert "[ORCID_REMOVED]" in row["clean_text"]
    assert "[PHONE_REMOVED]" in row["clean_text"]


def test_process_file_rejects_non_pdf_file(tmp_path: Path) -> None:
    """Check that direct non-PDF processing is rejected."""
    unsupported_path = tmp_path / "notes.txt"
    unsupported_path.write_text("Not a PDF", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        process_file(unsupported_path)


def test_clean_text_path_includes_source_extension(tmp_path: Path) -> None:
    """Check that clean-text filenames include the source extension."""
    output_dir = tmp_path / "abstracts_clean"
    source_path = tmp_path / "abstract_001.PDF"

    assert clean_text_path(output_dir, source_path) == (
        output_dir / "abstract_001_pdf_clean.txt"
    )


def test_supported_input_files_filters_and_sorts_pdf_files(
    sample_input_dir: Path,
) -> None:
    """Check that only PDF input files are listed in sorted order."""
    paths = supported_input_files(sample_input_dir)

    assert [path.name for path in paths] == [
        "abstract_001.pdf",
        "abstract_002.pdf",
    ]


def test_resolve_input_path_accepts_exact_file_name(sample_input_dir: Path) -> None:
    """Check that an exact input filename resolves inside the input directory."""
    assert resolve_input_path("abstract_001.pdf", sample_input_dir) == (
        sample_input_dir / "abstract_001.pdf"
    )


def test_resolve_input_path_accepts_unique_stem(sample_input_dir: Path) -> None:
    """Check that a unique stem resolves to its matching PDF file."""
    assert resolve_input_path("abstract_002", sample_input_dir) == (
        sample_input_dir / "abstract_002.pdf"
    )


def test_resolve_input_path_rejects_ambiguous_pdf_stem(tmp_path: Path) -> None:
    """Check that ambiguous PDF stems raise an error instead of guessing."""
    input_dir = tmp_path / "abstracts_raw"
    input_dir.mkdir()
    (input_dir / "abstract_001.pdf").write_text("PDF placeholder", encoding="utf-8")
    (input_dir / "abstract_001.PDF").write_text("PDF placeholder", encoding="utf-8")

    with pytest.raises(ValueError, match="Multiple input files match"):
        resolve_input_path("abstract_001", input_dir)


def test_resolve_input_path_rejects_missing_file(sample_input_dir: Path) -> None:
    """Check that missing explicit filenames raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        resolve_input_path("missing.pdf", sample_input_dir)


def test_read_csv_rows_returns_empty_list_for_missing_file(tmp_path: Path) -> None:
    """Check that missing CSV aggregate files produce no rows."""
    assert read_csv_rows(tmp_path / "missing.csv") == []


def test_read_csv_rows_normalises_rows(tmp_path: Path) -> None:
    """Check that CSV reading keeps only the expected output fields."""
    csv_path = tmp_path / "abstracts.csv"
    csv_path.write_text(
        "file_name,file_type,clean_text_file,clean_text,extra\n"
        "abstract_001.pdf,.pdf,clean.txt,Sample text,ignored\n",
        encoding="utf-8",
    )

    assert read_csv_rows(csv_path) == [{
        "file_name": "abstract_001.pdf",
        **ZERO_LOG_FIELDS,
        "clean_text_file": "clean.txt",
        "clean_text": "Sample text",
    }]


def test_read_json_rows_returns_empty_list_for_missing_file(tmp_path: Path) -> None:
    """Check that missing JSON aggregate files produce no rows."""
    assert read_json_rows(tmp_path / "missing.json") == []


def test_read_json_rows_returns_empty_list_for_non_list_json(tmp_path: Path) -> None:
    """Check that non-list JSON aggregates are ignored."""
    json_path = tmp_path / "abstracts.json"
    json_path.write_text('{"file_name": "abstract_001.pdf"}', encoding="utf-8")

    assert read_json_rows(json_path) == []


def test_read_json_rows_normalises_rows(tmp_path: Path) -> None:
    """Check that JSON reading keeps only valid rows and expected fields."""
    json_path = tmp_path / "abstracts.json"
    json_path.write_text(
        json.dumps([
            {
                "file_name": "abstract_001.pdf",
                "file_type": ".pdf",
                "clean_text_file": "clean.txt",
                "clean_text": "Sample text",
                "extra": "ignored",
            },
            "ignored",
        ]),
        encoding="utf-8",
    )

    assert read_json_rows(json_path) == [{
        "file_name": "abstract_001.pdf",
        **ZERO_LOG_FIELDS,
        "clean_text_file": "clean.txt",
        "clean_text": "Sample text",
    }]


def test_existing_rows_prefers_csv_when_available(tmp_path: Path) -> None:
    """Check that existing row discovery prefers CSV over JSON."""
    csv_path = tmp_path / "abstracts.csv"
    json_path = tmp_path / "abstracts.json"
    csv_rows = [{
        "file_name": "from_csv.pdf",
        **ZERO_LOG_FIELDS,
        "clean_text_file": "csv.txt",
        "clean_text": "CSV text",
    }]
    json_rows = [{
        "file_name": "from_json.pdf",
        **ZERO_LOG_FIELDS,
        "clean_text_file": "json.txt",
        "clean_text": "JSON text",
    }]

    write_csv(csv_rows, csv_path)
    write_json(json_rows, json_path)

    assert existing_rows(csv_path, json_path) == csv_rows


def test_existing_rows_falls_back_to_json(tmp_path: Path) -> None:
    """Check that existing row discovery uses JSON when CSV is absent."""
    csv_path = tmp_path / "missing.csv"
    json_path = tmp_path / "abstracts.json"
    rows = [{
        "file_name": "from_json.pdf",
        **ZERO_LOG_FIELDS,
        "clean_text_file": "json.txt",
        "clean_text": "JSON text",
    }]

    write_json(rows, json_path)

    assert existing_rows(csv_path, json_path) == rows


def test_existing_rows_returns_empty_list_when_no_outputs_exist(
    tmp_path: Path,
) -> None:
    """Check that existing row discovery returns no rows when outputs are absent."""
    assert existing_rows(tmp_path / "missing.csv", tmp_path / "missing.json") == []


def test_upsert_rows_replaces_existing_rows_and_adds_new_rows() -> None:
    """Check that processed rows replace matches and add new filenames."""
    existing = [
        {
            "file_name": "abstract_001.pdf",
            **ZERO_LOG_FIELDS,
            "clean_text_file": "old.txt",
            "clean_text": "Old text",
        },
        {
            "file_name": "abstract_003.pdf",
            **ZERO_LOG_FIELDS,
            "clean_text_file": "third.txt",
            "clean_text": "Third text",
        },
    ]
    processed = [
        {
            "file_name": "abstract_001.pdf",
            **ZERO_LOG_FIELDS,
            "clean_text_file": "new.txt",
            "clean_text": "New text",
        },
        {
            "file_name": "abstract_002.pdf",
            **ZERO_LOG_FIELDS,
            "clean_text_file": "second.txt",
            "clean_text": "Second text",
        },
    ]

    assert upsert_rows(existing, processed) == [
        {
            "file_name": "abstract_001.pdf",
            **ZERO_LOG_FIELDS,
            "clean_text_file": "new.txt",
            "clean_text": "New text",
        },
        {
            "file_name": "abstract_002.pdf",
            **ZERO_LOG_FIELDS,
            "clean_text_file": "second.txt",
            "clean_text": "Second text",
        },
        {
            "file_name": "abstract_003.pdf",
            **ZERO_LOG_FIELDS,
            "clean_text_file": "third.txt",
            "clean_text": "Third text",
        },
    ]


def test_write_csv_creates_parent_directory_and_writes_rows(tmp_path: Path) -> None:
    """Check that CSV writing creates directories and persists rows."""
    csv_path = tmp_path / "abstract_csv" / "abstracts.csv"
    rows = [{
        "file_name": "abstract_001.pdf",
        **ZERO_LOG_FIELDS,
        "clean_text_file": "clean.txt",
        "clean_text": "Sample text",
    }]

    write_csv(rows, csv_path)

    with csv_path.open(newline="", encoding="utf-8") as f:
        assert list(csv.DictReader(f)) == rows


def test_write_json_creates_parent_directory_and_writes_rows(tmp_path: Path) -> None:
    """Check that JSON writing creates directories and persists rows."""
    json_path = tmp_path / "abstract_json" / "abstracts.json"
    rows = [{
        "file_name": "abstract_001.pdf",
        **ZERO_LOG_FIELDS,
        "clean_text_file": "clean.txt",
        "clean_text": "Sample text",
    }]

    write_json(rows, json_path)

    assert json.loads(json_path.read_text(encoding="utf-8")) == rows
