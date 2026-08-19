from pathlib import Path

import fitz
import pytest

import convert_to_pdf
from convert_to_pdf import (
    AGGREGATED_FOLDER,
    PDF_OUTPUT_FOLDER,
    aggregate_files,
    alter_file_name,
    convert_all_to_pdf,
    convert_file_to_pdf,
    convert_inputs_to_pdfs,
)


def write_encrypted_pdf(path: Path) -> None:
    """Create a small password-protected PDF for conversion tests."""
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Locked PDF")
    pdf.save(
        path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    )
    pdf.close()


def test_aggregate_files_flattens_nested_input_tree(tmp_path: Path) -> None:
    """Check that nested files keep only top-level folder context."""
    input_folder = tmp_path / "input"
    nested_folder = input_folder / "nested" / "deeper"
    aggregate_dir = tmp_path / AGGREGATED_FOLDER
    nested_folder.mkdir(parents=True)

    (input_folder / "root.pdf").write_text("root", encoding="utf-8")
    (nested_folder / "paper.docx").write_text("nested", encoding="utf-8")

    copied = aggregate_files(input_folder, aggregate_dir)

    assert [path.name for path in copied] == [
        "nested__paper.docx",
        "root.pdf",
    ]
    assert (aggregate_dir / "root.pdf").read_text(encoding="utf-8") == "root"
    assert (aggregate_dir / "nested__paper.docx").read_text(
        encoding="utf-8"
    ) == "nested"


def test_alter_file_name_adds_or_increments_duplicate_suffix() -> None:
    """Check that duplicate names use Windows-style suffixes."""
    assert alter_file_name("paper.pdf") == "paper(1).pdf"
    assert alter_file_name("paper(1).pdf") == "paper(2).pdf"


def test_aggregate_files_renames_short_name_collisions(tmp_path: Path) -> None:
    """Check that shortened aggregate names do not overwrite files."""
    input_folder = tmp_path / "input"
    first_folder = input_folder / "nested" / "first"
    second_folder = input_folder / "nested" / "second"
    aggregate_dir = tmp_path / AGGREGATED_FOLDER
    first_folder.mkdir(parents=True)
    second_folder.mkdir(parents=True)
    (first_folder / "paper.pdf").write_text("first", encoding="utf-8")
    (second_folder / "paper.pdf").write_text("second", encoding="utf-8")

    copied = aggregate_files(input_folder, aggregate_dir)

    assert [path.name for path in copied] == [
        "nested__paper.pdf",
        "nested__paper(1).pdf",
    ]
    assert (aggregate_dir / "nested__paper.pdf").read_text(
        encoding="utf-8"
    ) == "first"
    assert (aggregate_dir / "nested__paper(1).pdf").read_text(
        encoding="utf-8"
    ) == "second"


def test_aggregate_files_skips_unsupported_file_types(tmp_path: Path) -> None:
    """Check that unsupported files are not copied into the aggregate folder."""
    input_folder = tmp_path / "input"
    aggregate_dir = tmp_path / AGGREGATED_FOLDER
    input_folder.mkdir()
    (input_folder / "paper.pdf").write_text("pdf", encoding="utf-8")
    (input_folder / "talk_PPT.pdf").write_text("ppt pdf", encoding="utf-8")
    (input_folder / "presentation.pdf").write_text("slides pdf", encoding="utf-8")
    (input_folder / "slides.pptx").write_text("pptx", encoding="utf-8")
    (input_folder / "notes.txt").write_text("txt", encoding="utf-8")

    copied = aggregate_files(input_folder, aggregate_dir)

    assert copied == [aggregate_dir / "paper.pdf"]
    assert not (aggregate_dir / "talk_PPT.pdf").exists()
    assert not (aggregate_dir / "presentation.pdf").exists()
    assert not (aggregate_dir / "slides.pptx").exists()
    assert not (aggregate_dir / "notes.txt").exists()


def test_aggregate_files_skips_pdf_inside_presentation_folder(
    tmp_path: Path,
) -> None:
    """Check that PDF presentations are skipped when the folder names reveal it."""
    input_folder = tmp_path / "input"
    presentation_dir = input_folder / "PRESENTATIONS"
    aggregate_dir = tmp_path / AGGREGATED_FOLDER
    presentation_dir.mkdir(parents=True)
    (presentation_dir / "talk.pdf").write_text("slides pdf", encoding="utf-8")

    copied = aggregate_files(input_folder, aggregate_dir)

    assert copied == []
    assert not (aggregate_dir / "PRESENTATIONS__talk.pdf").exists()


def test_aggregate_files_skips_password_protected_pdf(tmp_path: Path) -> None:
    """Check that locked PDFs are not copied into the aggregate folder."""
    input_folder = tmp_path / "input"
    aggregate_dir = tmp_path / AGGREGATED_FOLDER
    input_folder.mkdir()
    write_encrypted_pdf(input_folder / "locked.pdf")

    copied = aggregate_files(input_folder, aggregate_dir)

    assert copied == []
    assert not (aggregate_dir / "locked.pdf").exists()


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


def test_convert_file_to_pdf_rejects_presentation_suffix(tmp_path: Path) -> None:
    """Check that presentations are not part of the abstract pipeline."""
    source = tmp_path / "slides.pptx"
    source.write_text("slides", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        convert_file_to_pdf(source, tmp_path / "pdfs")


def test_convert_file_to_pdf_rejects_powerpoint_pdf(tmp_path: Path) -> None:
    """Check that presentation-looking PDFs are not copied to abstracts_raw."""
    source = tmp_path / "slides_PPT.pdf"
    source.write_text("slides", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported PowerPoint PDF"):
        convert_file_to_pdf(source, tmp_path / "pdfs")


def test_convert_file_to_pdf_rejects_password_protected_pdf(tmp_path: Path) -> None:
    """Check that locked PDFs are not copied to abstracts_raw."""
    source = tmp_path / "locked.pdf"
    write_encrypted_pdf(source)

    with pytest.raises(ValueError, match="Unsupported password-protected PDF"):
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


def test_convert_inputs_to_pdfs_is_public_pipeline_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check that the public conversion API aggregates then converts."""
    input_folder = tmp_path / "input"
    aggregate_dir = tmp_path / "aggregate"
    expected_output_dir = tmp_path / "pdfs"
    aggregated = [aggregate_dir / "paper.docx"]
    converted = [expected_output_dir / "paper.pdf"]

    def fake_aggregate_files(path: Path, destination: Path) -> list[Path]:
        assert path == input_folder
        assert destination == aggregate_dir
        return aggregated

    def fake_convert_all_to_pdf(
        files: list[Path],
        output_dir: Path,
    ) -> list[Path]:
        assert files == aggregated
        assert output_dir == expected_output_dir
        return converted

    monkeypatch.setattr(convert_to_pdf, "aggregate_files", fake_aggregate_files)
    monkeypatch.setattr(convert_to_pdf, "convert_all_to_pdf", fake_convert_all_to_pdf)

    assert convert_inputs_to_pdfs(
        input_folder,
        aggregate_dir,
        expected_output_dir,
    ) == (
        aggregated,
        converted,
    )


def test_main_converts_to_output_abstracts_raw(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check that CLI flow writes converted PDFs to the default raw folder."""
    input_folder = tmp_path / "input"
    input_folder.mkdir()

    def fake_parse_args() -> object:
        return type("Args", (), {"input_folder": str(input_folder)})()

    def fake_convert_inputs_to_pdfs(
        input_folder: Path,
    ) -> tuple[list[Path], list[Path]]:
        assert input_folder == tmp_path / "input"
        return [tmp_path / "paper.docx"], [Path(PDF_OUTPUT_FOLDER) / "paper.pdf"]

    monkeypatch.setattr(convert_to_pdf, "parse_args", fake_parse_args)
    monkeypatch.setattr(
        convert_to_pdf,
        "convert_inputs_to_pdfs",
        fake_convert_inputs_to_pdfs,
    )

    convert_to_pdf.main()
