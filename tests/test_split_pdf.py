from pathlib import Path

import fitz

import pytest

from split_pdf import (
    INPUT_FOLDER,
    METADATA_CSV,
    METADATA_JSON,
    find_toc_page_range,
    is_combined_pdf,
    parse_toc,
    parse_args,
    split_combined_pdfs,
    split_folder,
)


def write_combined_pdf(path: Path, cover_pages: int = 1) -> None:
    """Create a small combined PDF with the same TOC shape as the e-book."""
    pdf = fitz.open()

    for page_number in range(cover_pages):
        cover = pdf.new_page()
        cover.insert_text((72, 72), f"Cover page {page_number + 1}", fontsize=12)

    toc = pdf.new_page()
    toc.insert_text(
        (72, 72),
        "\n".join(
            [
                "I",
                "CONTENT",
                "T1_O1",
                "First Abstract Title",
                "1",
                "T1_O2",
                "Second Abstract",
                "Wrapped Title",
                "3",
            ]
        ),
        fontsize=12,
    )

    add_page(pdf, "First Abstract Title\nAuthor One\nIntroduction\nBody")
    add_page(pdf, "First abstract continuation")
    add_page(pdf, "Second Abstract\nWrapped Title\nAuthor Two\nIntroduction\nBody")
    add_page(pdf, "Second abstract continuation")

    pdf.save(path)
    pdf.close()


def add_page(pdf: fitz.Document, text: str) -> None:
    """Add a simple page to a test PDF."""
    page = pdf.new_page()
    page.insert_text((72, 72), text, fontsize=12)


def test_parse_args_defaults_to_raw_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check that the split CLI can run without an explicit input folder."""
    monkeypatch.setattr("sys.argv", ["split_pdf.py"])

    args = parse_args()

    assert args.input_folder == INPUT_FOLDER


def test_parse_args_accepts_explicit_input_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check that an explicit CLI input folder overrides the default."""
    monkeypatch.setattr("sys.argv", ["split_pdf.py", "custom_combined"])

    args = parse_args()

    assert args.input_folder == "custom_combined"


def test_parse_toc_extracts_ids_titles_and_printed_pages(tmp_path: Path) -> None:
    """Check that TOC entries are parsed from the expected format."""
    source = tmp_path / "combined.pdf"
    write_combined_pdf(source)

    with fitz.open(source) as pdf:
        entries = parse_toc(pdf)

    assert entries == [
        {
            "abstract_id": "T1_O1",
            "title": "First Abstract Title",
            "printed_start_page": 1,
        },
        {
            "abstract_id": "T1_O2",
            "title": "Second Abstract Wrapped Title",
            "printed_start_page": 3,
        },
    ]


def test_find_toc_page_range_detects_content_pages(tmp_path: Path) -> None:
    """Check that TOC pages are derived from the expected TOC pattern."""
    source = tmp_path / "combined.pdf"
    write_combined_pdf(source)

    with fitz.open(source) as pdf:
        assert find_toc_page_range(pdf) == (2, 2)


def test_is_combined_pdf_accepts_expected_combined_format(tmp_path: Path) -> None:
    """Check that the naive guard recognises the supported combined format."""
    source = tmp_path / "combined.pdf"
    write_combined_pdf(source)

    assert is_combined_pdf(source)


def test_is_combined_pdf_rejects_ordinary_pdf(tmp_path: Path) -> None:
    """Check that an ordinary single PDF is not treated as combined."""
    source = tmp_path / "ordinary.pdf"
    pdf = fitz.open()
    add_page(pdf, "This PDF has no table of contents.")
    pdf.save(source)
    pdf.close()

    assert not is_combined_pdf(source)


def test_parse_toc_detects_later_content_pages(tmp_path: Path) -> None:
    """Check that TOC parsing is not tied to fixed page numbers."""
    source = tmp_path / "combined.pdf"
    write_combined_pdf(source, cover_pages=3)

    with fitz.open(source) as pdf:
        assert find_toc_page_range(pdf) == (4, 4)
        entries = parse_toc(pdf)

    assert entries[0]["abstract_id"] == "T1_O1"
    assert entries[0]["title"] == "First Abstract Title"


def test_split_folder_writes_one_pdf_per_toc_entry(tmp_path: Path) -> None:
    """Check that a folder of combined PDFs is split into individual PDFs."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    staging_folder = tmp_path / "split_staging"
    input_folder.mkdir()
    write_combined_pdf(input_folder / "ebook.pdf")
    (input_folder / "notes.txt").write_text("skip me", encoding="utf-8")

    metadata = split_folder(
        input_folder=input_folder,
        output_folder=output_folder,
        staging_folder=staging_folder,
    )

    assert [row["abstract_id"] for row in metadata] == ["T1_O1", "T1_O2"]
    assert [row["page_count"] for row in metadata] == [2, 2]
    assert (output_folder / "ebook_T1_O1.pdf").exists()
    assert (output_folder / "ebook_T1_O2.pdf").exists()
    assert (staging_folder / "ebook_T1_O1.pdf").exists()
    assert (staging_folder / "ebook_T1_O2.pdf").exists()

    with fitz.open(output_folder / "ebook_T1_O1.pdf") as first:
        assert first.page_count == 2
        assert "First Abstract Title" in first[0].get_text()

    with fitz.open(output_folder / "ebook_T1_O2.pdf") as second:
        assert second.page_count == 2
        assert "Second Abstract" in second[0].get_text()


def test_split_folder_supports_same_input_and_output_folder(tmp_path: Path) -> None:
    """Check that new split PDFs are not processed again during the same run."""
    raw_folder = tmp_path / "raw"
    staging_folder = tmp_path / "split_staging"
    raw_folder.mkdir()
    write_combined_pdf(raw_folder / "ebook.pdf")

    metadata = split_folder(
        input_folder=raw_folder,
        output_folder=raw_folder,
        staging_folder=staging_folder,
    )

    assert [row["abstract_id"] for row in metadata] == ["T1_O1", "T1_O2"]
    assert (raw_folder / "ebook.pdf").exists()
    assert (raw_folder / "ebook_T1_O1.pdf").exists()
    assert (raw_folder / "ebook_T1_O2.pdf").exists()
    assert (staging_folder / "ebook_T1_O1.pdf").exists()
    assert (staging_folder / "ebook_T1_O2.pdf").exists()


def test_split_folder_cleans_staging_folder_before_splitting(tmp_path: Path) -> None:
    """Check that each run starts with an empty staging folder."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    staging_folder = tmp_path / "split_staging"
    input_folder.mkdir()
    staging_folder.mkdir()
    write_combined_pdf(input_folder / "ebook.pdf")
    (staging_folder / "stale.pdf").write_text("old", encoding="utf-8")
    stale_subfolder = staging_folder / "old"
    stale_subfolder.mkdir()
    (stale_subfolder / "old.txt").write_text("old", encoding="utf-8")

    split_folder(
        input_folder=input_folder,
        output_folder=output_folder,
        staging_folder=staging_folder,
    )

    assert not (staging_folder / "stale.pdf").exists()
    assert not stale_subfolder.exists()
    assert (staging_folder / "ebook_T1_O1.pdf").exists()
    assert (output_folder / "ebook_T1_O1.pdf").exists()


def test_split_folder_skips_pdfs_without_toc(tmp_path: Path) -> None:
    """Check that ordinary PDFs in the folder are ignored."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    staging_folder = tmp_path / "split_staging"
    input_folder.mkdir()
    write_combined_pdf(input_folder / "ebook.pdf")
    ordinary_pdf = fitz.open()
    add_page(ordinary_pdf, "This PDF has no table of contents.")
    ordinary_pdf.save(input_folder / "ordinary.pdf")
    ordinary_pdf.close()

    metadata = split_folder(
        input_folder=input_folder,
        output_folder=output_folder,
        staging_folder=staging_folder,
    )

    assert len(metadata) == 2
    assert not (output_folder / "ordinary.pdf").exists()


def test_split_combined_pdfs_writes_metadata_files(tmp_path: Path) -> None:
    """Check that the public module API derives config and writes metadata."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    staging_folder = tmp_path / "split_staging"
    input_folder.mkdir()
    write_combined_pdf(input_folder / "ebook.pdf")

    metadata = split_combined_pdfs(
        input_folder=input_folder,
        output_folder=output_folder,
        staging_folder=staging_folder,
    )

    assert len(metadata) == 2
    assert (staging_folder / METADATA_CSV).exists()
    assert (staging_folder / METADATA_JSON).exists()
    assert not (output_folder / METADATA_CSV).exists()
    assert not (output_folder / METADATA_JSON).exists()


def test_split_combined_pdfs_creates_missing_folders_for_empty_run(
    tmp_path: Path,
) -> None:
    """Check that missing input/output folders do not break an empty run."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    staging_folder = tmp_path / "split_staging"

    metadata = split_combined_pdfs(
        input_folder=input_folder,
        output_folder=output_folder,
        staging_folder=staging_folder,
    )

    assert metadata == []
    assert input_folder.exists()
    assert output_folder.exists()
    assert staging_folder.exists()
    assert (staging_folder / METADATA_CSV).exists()
    assert (staging_folder / METADATA_JSON).exists()


def test_split_folder_rejects_staging_folder_as_output_folder(
    tmp_path: Path,
) -> None:
    """Check that staging cannot clean the final output folder."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    input_folder.mkdir()

    with pytest.raises(ValueError, match="Staging folder cannot be the output folder"):
        split_folder(
            input_folder=input_folder,
            output_folder=output_folder,
            staging_folder=output_folder,
        )
