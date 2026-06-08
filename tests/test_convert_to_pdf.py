from pathlib import Path

import pytest

import convert_to_pdf
from convert_to_pdf import (
    AGGREGATED_FOLDER,
    PDF_OUTPUT_FOLDER,
    aggregate_files,
    convert_all_to_pdf,
    convert_file_to_pdf,
)


def test_aggregate_files_flattens_nested_input_tree(tmp_path: Path) -> None:
    """Check that nested input files are copied into one aggregate folder."""
    input_folder = tmp_path / "input"
    nested_folder = input_folder / "nested" / "deeper"
    aggregate_dir = tmp_path / AGGREGATED_FOLDER
    nested_folder.mkdir(parents=True)

    (input_folder / "root.pdf").write_text("root", encoding="utf-8")
    (nested_folder / "paper.docx").write_text("nested", encoding="utf-8")

    copied = aggregate_files(input_folder, aggregate_dir)

    assert [path.name for path in copied] == [
        "nested__deeper__paper.docx",
        "root.pdf",
    ]
    assert (aggregate_dir / "root.pdf").read_text(encoding="utf-8") == "root"
    assert (aggregate_dir / "nested__deeper__paper.docx").read_text(
        encoding="utf-8"
    ) == "nested"


def test_aggregate_files_skips_unsupported_file_types(tmp_path: Path) -> None:
    """Check that unsupported files are not copied into the aggregate folder."""
    input_folder = tmp_path / "input"
    aggregate_dir = tmp_path / AGGREGATED_FOLDER
    input_folder.mkdir()
    (input_folder / "paper.pdf").write_text("pdf", encoding="utf-8")
    (input_folder / "notes.txt").write_text("txt", encoding="utf-8")

    copied = aggregate_files(input_folder, aggregate_dir)

    assert copied == [aggregate_dir / "paper.pdf"]
    assert not (aggregate_dir / "notes.txt").exists()


def test_aggregate_files_creates_missing_input_and_aggregate_folders(
    tmp_path: Path,
) -> None:
    """Check that missing aggregation folders do not break an empty run."""
    input_folder = tmp_path / "missing_input"
    aggregate_dir = tmp_path / AGGREGATED_FOLDER

    copied = aggregate_files(input_folder, aggregate_dir)

    assert copied == []
    assert input_folder.exists()
    assert aggregate_dir.exists()


def test_aggregate_files_skips_aggregate_folder_inside_input(tmp_path: Path) -> None:
    """Check that aggregation does not copy files from its own output folder."""
    input_folder = tmp_path / "input"
    aggregate_dir = input_folder / AGGREGATED_FOLDER
    aggregate_dir.mkdir(parents=True)
    (input_folder / "root.pdf").write_text("root", encoding="utf-8")
    (aggregate_dir / "previous.pdf").write_text("previous", encoding="utf-8")

    copied = aggregate_files(input_folder, aggregate_dir)

    assert [path.name for path in copied] == ["root.pdf"]


def test_convert_file_to_pdf_copies_existing_pdf(tmp_path: Path) -> None:
    """Check that PDF inputs are copied to the output directory."""
    source = tmp_path / "paper.pdf"
    output_dir = tmp_path / "pdfs"
    source.write_text("pdf content", encoding="utf-8")

    result = convert_file_to_pdf(source, output_dir)

    assert result == output_dir / "paper.pdf"
    assert result.read_text(encoding="utf-8") == "pdf content"


def test_convert_file_to_pdf_keeps_pdf_already_in_output_dir(tmp_path: Path) -> None:
    """Check that PDF inputs are left in place when already in the output folder."""
    source = tmp_path / "paper.pdf"
    source.write_text("pdf content", encoding="utf-8")

    result = convert_file_to_pdf(source, tmp_path)

    assert result == source
    assert source.read_text(encoding="utf-8") == "pdf content"


def test_convert_file_to_pdf_dispatches_office_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check that Office suffixes use the Office conversion behaviour."""
    source = tmp_path / "paper.docx"
    output_dir = tmp_path / "pdfs"
    source.write_text("docx content", encoding="utf-8")

    def fake_convert_office_to_pdf(path: Path, destination: Path) -> Path:
        assert path == source
        assert destination == output_dir
        return destination / "paper.pdf"

    monkeypatch.setattr(
        convert_to_pdf,
        "convert_office_to_pdf",
        fake_convert_office_to_pdf,
    )

    assert convert_file_to_pdf(source, output_dir) == output_dir / "paper.pdf"


def test_convert_file_to_pdf_rejects_unsupported_suffix(tmp_path: Path) -> None:
    """Check that unsupported file types fail clearly."""
    source = tmp_path / "notes.txt"
    source.write_text("notes", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        convert_file_to_pdf(source, tmp_path / "pdfs")


def test_convert_all_to_pdf_processes_each_file(tmp_path: Path) -> None:
    """Check that batch conversion returns one PDF path per input file."""
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    output_dir = tmp_path / "pdfs"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    assert convert_all_to_pdf([first, second], output_dir) == [
        output_dir / "first.pdf",
        output_dir / "second.pdf",
    ]


def test_convert_all_to_pdf_creates_output_dir_for_empty_input(tmp_path: Path) -> None:
    """Check that an empty conversion run still creates the output folder."""
    output_dir = tmp_path / "pdfs"

    assert convert_all_to_pdf([], output_dir) == []
    assert output_dir.exists()


def test_main_converts_to_abstracts_raw(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check that CLI flow always writes converted PDFs to abstracts_raw."""
    input_folder = tmp_path / "input"
    input_folder.mkdir()

    def fake_parse_args() -> object:
        return type("Args", (), {"input_folder": str(input_folder)})()

    def fake_aggregate_files(path: Path, aggregate_dir: Path) -> list[Path]:
        assert path == input_folder
        assert aggregate_dir == Path(AGGREGATED_FOLDER)
        return [tmp_path / "paper.pdf"]

    def fake_convert_all_to_pdf(files: list[Path], output_dir: Path) -> list[Path]:
        assert files == [tmp_path / "paper.pdf"]
        assert output_dir == Path(PDF_OUTPUT_FOLDER)
        return [output_dir / "paper.pdf"]

    monkeypatch.setattr(convert_to_pdf, "parse_args", fake_parse_args)
    monkeypatch.setattr(convert_to_pdf, "aggregate_files", fake_aggregate_files)
    monkeypatch.setattr(convert_to_pdf, "convert_all_to_pdf", fake_convert_all_to_pdf)

    convert_to_pdf.main()
