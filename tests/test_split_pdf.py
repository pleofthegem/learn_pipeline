from pathlib import Path

import fitz

import pytest

from scripts.split_rules import INPUT_FOLDER, METADATA_CSV, METADATA_JSON
from scripts.split_pdf import (
    ContentsEntry,
    calculate_printed_page_offset,
    find_numbered_contents_pages,
    read_combined_pdf_contents,
    resolve_document_page_ranges,
    page_starts_with_title,
    parse_numbered_contents,
    parse_args,
    prepare_individual_pdfs,
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


def write_presentation_combined_pdf(path: Path) -> None:
    """Create a combined PDF with a Water Board style presentation TOC."""
    pdf = fitz.open()
    add_page(pdf, "Cover page")

    toc = pdf.new_page()
    toc.insert_text(
        (72, 72),
        "\n".join(
            [
                "Oral Presentations",
                "Page No.",
                "Session 01",
                "Presentation 01",
                "First Presentation Title",
                "2",
                "Presentation 02 Second Presentation",
                "Wrapped Title",
                "4",
                "Poster Presentations (1 Papers)",
                "Presentation 01 Poster Presentation Title",
                "6",
            ]
        ),
        fontsize=12,
    )

    add_page(pdf, "First Presentation Title\nAuthor One\nAbstract\nBody")
    add_page(pdf, "First presentation continuation")
    add_page(pdf, "Second Presentation\nWrapped Title\nAuthor Two\nAbstract\nBody")
    add_page(pdf, "Second presentation continuation")
    add_page(pdf, "Poster Presentation Title\nAuthor Three\nAbstract\nBody")
    add_page(pdf, "Poster presentation continuation")

    pdf.save(path)
    pdf.close()


def write_presentation_combined_pdf_with_missing_entry(path: Path) -> None:
    """Create a presentation TOC where one listed entry has no body page."""
    pdf = fitz.open()
    add_page(pdf, "Cover page")

    toc = pdf.new_page()
    toc.insert_text(
        (72, 72),
        "\n".join(
            [
                "Oral Presentations",
                "Page No.",
                "Presentation 01 First Presentation Title",
                "2",
                "Presentation 02 Missing Presentation Title",
                "4",
                "Presentation 03 Second Presentation Title",
                "4",
            ]
        ),
        fontsize=12,
    )

    add_page(pdf, "First Presentation Title\nAuthor One\nAbstract\nBody")
    add_page(pdf, "First presentation continuation")
    add_page(pdf, "Second Presentation Title\nAuthor Two\nAbstract\nBody")
    add_page(pdf, "Second presentation continuation")

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

    assert args.input_folder == Path("custom_combined")


def test_parse_numbered_contents_extracts_ids_titles_and_printed_pages(tmp_path: Path) -> None:
    """Check that TOC entries are parsed from the expected format."""
    source = tmp_path / "combined.pdf"
    write_combined_pdf(source)

    with fitz.open(source) as pdf:
        entries = parse_numbered_contents(pdf, find_numbered_contents_pages(pdf))

    assert entries == [
        ContentsEntry('T1_O1', 'First Abstract Title', 1),
        ContentsEntry('T1_O2', 'Second Abstract Wrapped Title', 3),
    ]


def test_parse_numbered_contents_extracts_presentation_style_entries(tmp_path: Path) -> None:
    """Check that Water Board style presentation TOC entries are parsed."""
    source = tmp_path / "combined.pdf"
    write_presentation_combined_pdf(source)

    with fitz.open(source) as pdf:
        entries = parse_numbered_contents(pdf, find_numbered_contents_pages(pdf))

    assert entries == [
        ContentsEntry('O01', 'First Presentation Title', 2),
        ContentsEntry('O02', 'Second Presentation Wrapped Title', 4),
        ContentsEntry('P01', 'Poster Presentation Title', 6),
    ]


def test_find_numbered_contents_pages_detects_content_pages(tmp_path: Path) -> None:
    """Check that TOC pages are derived from the expected TOC pattern."""
    source = tmp_path / "combined.pdf"
    write_combined_pdf(source)

    with fitz.open(source) as pdf:
        assert find_numbered_contents_pages(pdf) == (2, 2)


def test_find_numbered_contents_pages_detects_presentation_pages(tmp_path: Path) -> None:
    """Check that presentation-list TOC pages can be detected."""
    source = tmp_path / "combined.pdf"
    write_presentation_combined_pdf(source)

    with fitz.open(source) as pdf:
        assert find_numbered_contents_pages(pdf) == (2, 2)


def test_read_combined_pdf_contents_accepts_expected_combined_format(tmp_path: Path) -> None:
    """Check that contents validation recognises the supported book format."""
    source = tmp_path / "combined.pdf"
    write_combined_pdf(source)

    with fitz.open(source) as pdf:
        assert read_combined_pdf_contents(pdf) is not None


def test_read_combined_pdf_contents_accepts_presentation_combined_format(tmp_path: Path) -> None:
    """Check that presentation-list PDFs are recognised as combined."""
    source = tmp_path / "combined.pdf"
    write_presentation_combined_pdf(source)

    with fitz.open(source) as pdf:
        assert read_combined_pdf_contents(pdf) is not None


def test_read_combined_pdf_contents_rejects_ordinary_pdf(tmp_path: Path) -> None:
    """Check that an ordinary single PDF is not treated as combined."""
    source = tmp_path / "ordinary.pdf"
    pdf = fitz.open()
    add_page(pdf, "This PDF has no table of contents.")
    pdf.save(source)
    pdf.close()

    with fitz.open(source) as pdf:
        assert read_combined_pdf_contents(pdf) is None


def test_parse_numbered_contents_detects_later_content_pages(tmp_path: Path) -> None:
    """Check that TOC parsing is not tied to fixed page numbers."""
    source = tmp_path / "combined.pdf"
    write_combined_pdf(source, cover_pages=3)

    with fitz.open(source) as pdf:
        assert find_numbered_contents_pages(pdf) == (4, 4)
        entries = parse_numbered_contents(pdf, find_numbered_contents_pages(pdf))

    assert entries[0].entry_id == "T1_O1"
    assert entries[0].title == "First Abstract Title"


def test_prepare_individual_pdfs_writes_one_pdf_per_toc_entry(tmp_path: Path) -> None:
    """Check that a folder of combined PDFs is split into individual PDFs."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    metadata_folder = tmp_path / "split_metadata"
    input_folder.mkdir()
    write_combined_pdf(input_folder / "ebook.pdf")
    (input_folder / "notes.txt").write_text("skip me", encoding="utf-8")

    metadata = prepare_individual_pdfs(
        input_folder=input_folder,
        output_folder=output_folder,
        metadata_folder=metadata_folder,
    )

    assert [row["abstract_id"] for row in metadata] == ["T1_O1", "T1_O2"]
    assert [row["page_count"] for row in metadata] == [2, 2]
    # One source book and two final PDFs; no duplicate PDF staging tree.
    assert len(list(tmp_path.rglob("*.pdf"))) == 3
    assert (input_folder / "ebook.pdf").exists()
    assert (output_folder / "ebook_T1_O1.pdf").exists()
    assert (output_folder / "ebook_T1_O2.pdf").exists()
    assert not (metadata_folder / "ebook_T1_O1.pdf").exists()
    assert not (metadata_folder / "ebook_T1_O2.pdf").exists()

    with fitz.open(output_folder / "ebook_T1_O1.pdf") as first:
        assert first.page_count == 2
        assert "First Abstract Title" in first[0].get_text()

    with fitz.open(output_folder / "ebook_T1_O2.pdf") as second:
        assert second.page_count == 2
        assert "Second Abstract" in second[0].get_text()


def test_prepare_individual_pdfs_writes_presentation_style_pdfs(tmp_path: Path) -> None:
    """Check that presentation-style combined PDFs are split by TOC entries."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    metadata_folder = tmp_path / "split_metadata"
    input_folder.mkdir()
    write_presentation_combined_pdf(input_folder / "water_board.pdf")

    metadata = prepare_individual_pdfs(
        input_folder=input_folder,
        output_folder=output_folder,
        metadata_folder=metadata_folder,
    )

    assert [row["abstract_id"] for row in metadata] == ["O01", "O02", "P01"]
    assert [row["pdf_start_page"] for row in metadata] == [3, 5, 7]
    assert [row["page_count"] for row in metadata] == [2, 2, 2]
    assert (output_folder / "water_board_O01.pdf").exists()
    assert (output_folder / "water_board_O02.pdf").exists()
    assert (output_folder / "water_board_P01.pdf").exists()

    with fitz.open(output_folder / "water_board_P01.pdf") as poster:
        assert poster.page_count == 2
        assert "Poster Presentation Title" in poster[0].get_text()


def test_page_starts_with_title_tolerates_minor_toc_typos(tmp_path: Path) -> None:
    """Check that real title pages survive small TOC extraction typos."""
    source = tmp_path / "title.pdf"
    pdf = fitz.open()
    add_page(
        pdf,
        (
            "The Impact of Geological Features and Lithological Composition\n"
            "on Water Quality in the Upper Kelani River Basin"
        ),
    )
    pdf.save(source)
    pdf.close()

    with fitz.open(source) as pdf:
        assert page_starts_with_title(
            pdf,
            1,
            (
                "The Impact Oo Geological Features and Lithological "
                "Composition on Water Quality in the Upper Kelani River Basin"
            ),
        )


def test_offset_title_fallback_ignores_title_words_in_continuation_body(
    tmp_path: Path,
) -> None:
    """Check that continuation pages cannot be mistaken for title pages."""
    source = tmp_path / "title.pdf"
    title = "Future Water Reservoir Supply Methods"
    pdf = fitz.open()
    add_page(
        pdf,
        "\n".join(
            [
                "IWA Water Safety Conference & Exhibition 2026",
                "101",
                "Methodology:",
                "continuation line 1",
                "continuation line 2",
                "continuation line 3",
                "continuation line 4",
                "continuation line 5",
                "continuation line 6",
                "continuation line 7",
                "continuation line 8",
                "continuation line 9",
                "continuation line 10",
                "The Future Water Reservoir Supply Methods were discussed.",
            ]
        ),
    )
    add_page(pdf, f"{title}\nAuthor One\nAbstract\nBody")
    pdf.save(source)
    pdf.close()

    with fitz.open(source) as pdf:
        assert not page_starts_with_title(pdf, 1, title)
        assert calculate_printed_page_offset(pdf, [ContentsEntry("D1", title, 1)], 0) == 1


def test_offset_fails_when_no_footer_or_title_evidence_exists(tmp_path: Path) -> None:
    """Check that TOC page numbers are not used as unmatched fallbacks."""
    source = tmp_path / "missing.pdf"
    pdf = fitz.open()
    add_page(pdf, "Cover page")
    add_page(pdf, "Different Presentation Title")
    pdf.save(source)
    pdf.close()

    with fitz.open(source) as pdf:
        entries = [ContentsEntry("D1", "Missing Presentation Title", 1)]
        with pytest.raises(ValueError, match="reliable printed-to-PDF page offset"):
            calculate_printed_page_offset(pdf, entries, 1)


def test_prepare_individual_pdfs_keeps_every_presentation_contents_entry(tmp_path: Path) -> None:
    """Check that a missing body title does not discard a contents entry."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    metadata_folder = tmp_path / "split_metadata"
    input_folder.mkdir()
    write_presentation_combined_pdf_with_missing_entry(
        input_folder / "water_board.pdf"
    )

    metadata = prepare_individual_pdfs(
        input_folder=input_folder,
        output_folder=output_folder,
        metadata_folder=metadata_folder,
    )

    assert [row["abstract_id"] for row in metadata] == ["O01", "O02", "O03"]
    assert (output_folder / "water_board_O02.pdf").exists()
    assert (output_folder / "water_board_O01.pdf").exists()
    assert (output_folder / "water_board_O03.pdf").exists()


def test_prepare_individual_pdfs_supports_same_input_and_output_folder(tmp_path: Path) -> None:
    """Check that same-folder splitting leaves only atomic output PDFs."""
    raw_folder = tmp_path / "raw"
    metadata_folder = tmp_path / "split_metadata"
    raw_folder.mkdir()
    write_combined_pdf(raw_folder / "ebook.pdf")

    metadata = prepare_individual_pdfs(
        input_folder=raw_folder,
        output_folder=raw_folder,
        metadata_folder=metadata_folder,
    )

    assert [row["abstract_id"] for row in metadata] == ["T1_O1", "T1_O2"]
    assert not (raw_folder / "ebook.pdf").exists()
    assert (raw_folder / "ebook_T1_O1.pdf").exists()
    assert (raw_folder / "ebook_T1_O2.pdf").exists()
    assert not (metadata_folder / "ebook_T1_O1.pdf").exists()
    assert not (metadata_folder / "ebook_T1_O2.pdf").exists()


def test_prepare_individual_pdfs_keeps_unsplit_pdf_with_same_input_and_output(
    tmp_path: Path,
) -> None:
    """Check that ordinary same-folder PDFs are not removed."""
    raw_folder = tmp_path / "raw"
    metadata_folder = tmp_path / "split_metadata"
    raw_folder.mkdir()
    ordinary_pdf = fitz.open()
    add_page(ordinary_pdf, "This PDF has no table of contents.")
    ordinary_pdf.save(raw_folder / "ordinary.pdf")
    ordinary_pdf.close()

    metadata = prepare_individual_pdfs(
        input_folder=raw_folder,
        output_folder=raw_folder,
        metadata_folder=metadata_folder,
    )

    assert metadata == []
    assert (raw_folder / "ordinary.pdf").exists()


def test_prepare_individual_pdfs_cleans_metadata_folder_before_splitting(tmp_path: Path) -> None:
    """Check that old split outputs are cleared without staging new PDFs."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    metadata_folder = tmp_path / "split_metadata"
    input_folder.mkdir()
    metadata_folder.mkdir()
    write_combined_pdf(input_folder / "ebook.pdf")
    (metadata_folder / ".gitkeep").touch()
    (metadata_folder / "stale.pdf").write_text("old", encoding="utf-8")
    stale_subfolder = metadata_folder / "old"
    stale_subfolder.mkdir()
    (stale_subfolder / "old.txt").write_text("old", encoding="utf-8")

    prepare_individual_pdfs(
        input_folder=input_folder,
        output_folder=output_folder,
        metadata_folder=metadata_folder,
    )

    assert (metadata_folder / ".gitkeep").exists()
    assert not (metadata_folder / "stale.pdf").exists()
    assert not stale_subfolder.exists()
    assert not (metadata_folder / "ebook_T1_O1.pdf").exists()
    assert (output_folder / "ebook_T1_O1.pdf").exists()


def test_prepare_individual_pdfs_skips_pdfs_without_toc(tmp_path: Path) -> None:
    """Check that ordinary PDFs in the folder are ignored."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    metadata_folder = tmp_path / "split_metadata"
    input_folder.mkdir()
    write_combined_pdf(input_folder / "ebook.pdf")
    ordinary_pdf = fitz.open()
    add_page(ordinary_pdf, "This PDF has no table of contents.")
    ordinary_pdf.save(input_folder / "ordinary.pdf")
    ordinary_pdf.close()

    metadata = prepare_individual_pdfs(
        input_folder=input_folder,
        output_folder=output_folder,
        metadata_folder=metadata_folder,
    )

    assert len(metadata) == 2
    assert not (output_folder / "ordinary.pdf").exists()


def test_prepare_individual_pdfs_writes_metadata_files(tmp_path: Path) -> None:
    """Check that manifests are exported separately from final PDFs."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    metadata_folder = tmp_path / "split_metadata"
    input_folder.mkdir()
    write_combined_pdf(input_folder / "ebook.pdf")

    metadata = prepare_individual_pdfs(
        input_folder=input_folder,
        output_folder=output_folder,
        metadata_folder=metadata_folder,
    )

    assert len(metadata) == 2
    assert (metadata_folder / METADATA_CSV).exists()
    assert (metadata_folder / METADATA_JSON).exists()
    assert not (output_folder / METADATA_CSV).exists()
    assert not (output_folder / METADATA_JSON).exists()


def test_prepare_individual_pdfs_creates_missing_folders_for_empty_run(
    tmp_path: Path,
) -> None:
    """Check that missing input/output folders do not break an empty run."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    metadata_folder = tmp_path / "split_metadata"

    metadata = prepare_individual_pdfs(
        input_folder=input_folder,
        output_folder=output_folder,
        metadata_folder=metadata_folder,
    )

    assert metadata == []
    assert input_folder.exists()
    assert output_folder.exists()
    assert metadata_folder.exists()
    assert (metadata_folder / METADATA_CSV).exists()
    assert (metadata_folder / METADATA_JSON).exists()


def test_prepare_individual_pdfs_rejects_metadata_folder_as_output_folder(
    tmp_path: Path,
) -> None:
    """Check that manifest cleanup cannot remove final PDFs."""
    input_folder = tmp_path / "combined"
    output_folder = tmp_path / "raw"
    input_folder.mkdir()

    with pytest.raises(ValueError, match="Metadata folder cannot be or contain"):
        prepare_individual_pdfs(
            input_folder=input_folder,
            output_folder=output_folder,
            metadata_folder=output_folder,
        )



def write_session_contents_pdf(path: Path, *, cover_title="Book of abstracts", wrong_titles=False, duplicate=False):
    """Two printed contents pages, author lines, session dividers, no bookmarks."""
    pdf = fitz.open()
    add_page(pdf, cover_title)
    add_page(pdf, "Contents")
    add_page(pdf, "")
    ranges, toc_rows = [], []
    offset = 3
    for index in range(10):
        if index in (0, 5):
            session = 1 if index == 0 else 2
            toc_rows.append((f"Session {session}: Water research", len(pdf) + 1 - offset, False))
            session_start = len(pdf) + 1
            add_page(pdf, f"Session {session}\nWater research")
            add_page(pdf, "")
            ranges.append((session_start, len(pdf)))
        title = f"Research topic {index} on river management in 2026"
        start = len(pdf) + 1
        toc_rows.append((title, start - offset, True))
        if index == 3:
            add_page(pdf, "Session information")
        add_page(pdf, ("Unrelated document" if wrong_titles else title) + "\nAuthor\nAbstract\nStudy findings")
        add_page(pdf, "Continuation of the abstract")
        ranges.append((start, len(pdf)))
    for index in range(offset, len(pdf)):
        pdf[index].insert_text((72, 750), str(index + 1 - offset))
    for index, (title, number, abstract) in enumerate(toc_rows):
        page = pdf[1 if index < 6 else 2]
        y = 110 + (index % 6) * 65
        # Wrap one title; numeric title content must not become a page reference.
        if index == 1:
            page.insert_text((72, y), title[:25], fontsize=10)
            title = title[25:]
            y += 14
        page.insert_text((72, y), title + " . . .", fontsize=10)
        page.insert_text((520, y), str(1 if duplicate and index == 1 else number), fontsize=10)
        if abstract:
            page.insert_text((72, y+14), "Author One, Author Two 2026", fontsize=9, fontname="heit")
    add_page(pdf, "")
    add_page(pdf, "Back cover")
    pdf.save(path)
    pdf.close()
    return ranges


def test_session_contents_splits_without_bookmarks_or_page_labels(tmp_path):
    from scripts.split_pdf import split_combined_pdf, parse_session_contents
    source = tmp_path / "sessions.pdf"
    expected = write_session_contents_pdf(source)
    with fitz.open(source) as pdf:
        assert pdf.get_toc() == []
        assert pdf.get_page_labels() == []
        info = parse_session_contents(pdf)
        assert info is not None
        resolve_document_page_ranges(pdf, info)
        assert info.page_offset == 3
        assert (info.contents_start_page, info.contents_end_page) == (2, 3)
        assert len(info.entries) == 12
        assert [entry.title for entry in info.entries if entry.kind == "session"] == [
            "Session 1: Water research", "Session 2: Water research",
        ]
        assert all(entry.pdf_start_page == entry.printed_start_page + info.page_offset
                   for entry in info.entries)
        assert all("Author One" not in row.title for row in info.entries)
    with fitz.open(source) as pdf:
        assert read_combined_pdf_contents(pdf) is not None
    destination = tmp_path / "split"
    destination.mkdir()
    rows = split_combined_pdf(source, destination)
    assert len(rows) == 12
    assert [(r["pdf_start_page"], r["pdf_end_page"]) for r in rows] == expected
    for row in rows:
        with fitz.open(destination / row["output_file"]) as part:
            assert len(part) == row["page_count"]
    assert rows[4]["page_count"] == 3  # Start follows printed contents, not title search.
    assert source.exists()


@pytest.mark.parametrize("cover_title", ["Annual report", "Workshop proceedings"])
def test_session_contents_supports_combined_pdfs_without_abstract_book_cover(tmp_path, cover_title):
    from scripts.split_pdf import read_combined_pdf_contents, split_combined_pdf
    source = tmp_path / "combined.pdf"
    expected = write_session_contents_pdf(source, cover_title=cover_title)
    with fitz.open(source) as pdf:
        assert read_combined_pdf_contents(pdf) is not None
    with fitz.open(source) as pdf:
        contents = read_combined_pdf_contents(pdf)
        assert contents is not None
        assert contents.page_offset == 3
        assert len(contents.entries) == 12
    rows = split_combined_pdf(source, tmp_path / 'documents')
    assert [(row['pdf_start_page'], row['pdf_end_page']) for row in rows] == expected


def test_session_contents_ignores_incorrect_bookmarks(tmp_path):
    from scripts.split_pdf import parse_session_contents
    source = tmp_path / "bad_bookmarks.pdf"
    expected = write_session_contents_pdf(source)
    with fitz.open(source) as pdf:
        pdf.set_toc([[1, "Session 1: Incorrect", 1], [2, "Incorrect title", 2]])
        info = parse_session_contents(pdf)
        assert info is not None
        resolve_document_page_ranges(pdf, info)
        assert [(entry.pdf_start_page, entry.pdf_end_page) for entry in info.entries] == expected


@pytest.mark.parametrize('metadata_location', ['input', 'parent_of_input', 'parent_of_output'])
def test_prepare_individual_pdfs_rejects_metadata_cleanup_over_sources(tmp_path, metadata_location):
    inputs, output = tmp_path / 'inputs', tmp_path / 'destination/pdfs'
    inputs.mkdir()
    source = inputs / 'book.pdf'
    write_combined_pdf(source)
    original = source.read_bytes()
    metadata = {'input': inputs, 'parent_of_input': tmp_path,
                'parent_of_output': output.parent}[metadata_location]
    with pytest.raises(ValueError, match='Metadata folder cannot be or contain'):
        prepare_individual_pdfs(inputs, output, metadata)
    assert source.read_bytes() == original


@pytest.mark.parametrize('failure', ['pdf_write', 'manifest_export'])
def test_prepare_individual_pdfs_keeps_book_if_output_writing_fails(tmp_path, monkeypatch, failure):
    from scripts import split_pdf
    working = tmp_path / 'pdfs'
    working.mkdir()
    source = working / 'book.pdf'
    write_combined_pdf(source)
    original = source.read_bytes()
    if failure == 'pdf_write':
        write_range = split_pdf.write_pdf_page_range
        calls = 0
        def fail_second_pdf(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('Cannot write PDF')
            return write_range(*args)
        monkeypatch.setattr(split_pdf, 'write_pdf_page_range', fail_second_pdf)
    else:
        def fail_manifest(*args, **kwargs):
            raise OSError('Cannot write manifest')
        monkeypatch.setattr(split_pdf.json, 'dump', fail_manifest)
    with pytest.raises(OSError, match='Cannot write'):
        prepare_individual_pdfs(working, working, tmp_path / 'metadata')
    assert source.read_bytes() == original
    assert (working / 'book_T1_O1.pdf').exists()


def test_prepare_individual_pdfs_preserves_separate_input_and_unrelated_output(tmp_path):
    inputs, output = tmp_path / 'inputs', tmp_path / 'output'
    inputs.mkdir()
    output.mkdir()
    source = inputs / 'book.pdf'
    write_combined_pdf(source)
    original = source.read_bytes()
    existing = output / 'book.pdf'
    existing.write_bytes(b'Unrelated existing output')
    rows = prepare_individual_pdfs(inputs, output, tmp_path / 'metadata')
    assert len(rows) == 2
    assert source.read_bytes() == original
    assert existing.read_bytes() == b'Unrelated existing output'


def test_range_resolution_maps_entries_even_without_body_titles(tmp_path):
    from scripts.split_pdf import read_combined_pdf_contents, resolve_document_page_ranges
    source = tmp_path / 'missing_title.pdf'
    write_presentation_combined_pdf_with_missing_entry(source)
    with fitz.open(source) as pdf:
        contents = read_combined_pdf_contents(pdf)
        assert contents is not None
        assert (contents.contents_start_page, contents.contents_end_page) == (2, 2)
        assert contents.page_offset == 1
        ranges = resolve_document_page_ranges(pdf, contents)
    assert [entry.entry_id for entry in contents.entries] == ['O01', 'O02', 'O03']
    assert [(entry.entry_id, start, end) for entry, start, end in ranges] == [
        ('O01', 3, 4), ('O02', 5, 6), ('O03', 5, 6),
    ]
    missing = contents.entries[1]
    assert missing.title == 'Missing Presentation Title'
    assert missing.printed_start_page == 4
    assert missing.pdf_start_page == 5
    assert missing.pdf_end_page == 6


@pytest.mark.parametrize('options', [{'wrong_titles': True}, {'duplicate': True}])
def test_contents_references_are_authoritative_without_body_title_matches(tmp_path, options):
    from scripts.split_pdf import split_combined_pdf
    source = tmp_path / 'book.pdf'
    write_session_contents_pdf(source, **options)
    rows = split_combined_pdf(source, tmp_path / 'pdfs')
    assert len(rows) == 12
    assert len({row['output_file'] for row in rows}) == 12
    assert {row['abstract_id'] for row in rows}.issuperset({'S1', 'S2'})
    assert all(row['pdf_start_page'] == row['printed_start_page'] + 3 for row in rows)


def test_numbered_contents_without_any_body_titles_uses_printed_footers(tmp_path):
    from scripts.split_pdf import split_combined_pdf
    source = tmp_path / 'book.pdf'
    with fitz.open() as pdf:
        add_page(pdf, 'Abstract collection')
        add_page(pdf, 'CONTENT\nT1_O1\nFirst listed research title\n1\nT1_O2\nSecond listed research title\n3')
        for number in range(1, 5):
            add_page(pdf, 'Unlabelled research text describing water quality and the results of the study.')
            pdf[-1].insert_text((72, 750), str(number))
        pdf.save(source)
    rows = split_combined_pdf(source, tmp_path / 'pdfs')
    assert [(row['pdf_start_page'], row['pdf_end_page']) for row in rows] == [(3, 4), (5, 6)]


@pytest.mark.parametrize('title', ['', '...', '   '])
def test_empty_title_cannot_establish_a_page_match(tmp_path, title):
    source = tmp_path / 'ordinary.pdf'
    with fitz.open() as pdf:
        add_page(pdf, 'Some text that is not evidence of a missing title.')
        pdf.save(source)
    with fitz.open(source) as pdf:
        assert not page_starts_with_title(pdf, 1, title)


def test_conflicting_footer_offsets_are_not_guessed(tmp_path):
    source = tmp_path / 'conflicting.pdf'
    with fitz.open() as pdf:
        add_page(pdf, 'Cover')
        add_page(pdf, 'Contents')
        for footer in ('1', '2', '1', '2'):
            add_page(pdf, 'Unlabelled document body.')
            pdf[-1].insert_text((72, 750), footer)
        pdf.save(source)
    entries = [ContentsEntry('D1', 'First title not printed', 1),
               ContentsEntry('D2', 'Second title not printed', 2)]
    with fitz.open(source) as pdf, pytest.raises(ValueError, match='reliable printed-to-PDF'):
        calculate_printed_page_offset(pdf, entries, 2)


@pytest.mark.parametrize('body_end,printed_pages', [(10, [1, 2]), (None, [2, 1]), (None, [1, 10])])
def test_invalid_ranges_do_not_partially_mutate_contents(tmp_path, body_end, printed_pages):
    from scripts.split_pdf import CombinedPdfContents
    source = tmp_path / 'combined.pdf'
    with fitz.open() as pdf:
        for _ in range(4):
            add_page(pdf, 'Document page')
        pdf.save(source)
    entries = [ContentsEntry(f'D{index}', 'Title', number) for index, number in enumerate(printed_pages)]
    contents = CombinedPdfContents(1, 2, entries, 2, content_end_page=body_end)
    with fitz.open(source) as pdf, pytest.raises(ValueError):
        resolve_document_page_ranges(pdf, contents)
    assert all(entry.pdf_start_page is None and entry.pdf_end_page is None for entry in entries)
