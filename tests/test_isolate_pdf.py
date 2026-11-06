from pathlib import Path

import fitz
import pytest

from scripts.isolate_pdf import detect_delimiters, isolate_pdf, read_lines


def make_pdf(path, pages):
    with fitz.open() as pdf:
        for lines in pages:
            page = pdf.new_page()
            for y, text in lines:
                page.insert_text((72, y), text)
        pdf.save(path)


def extracted(path):
    with fitz.open(path) as pdf:
        return " ".join(page.get_text() for page in pdf)


def test_shared_page_has_no_neighbour_text_or_delimiter(tmp_path):
    source = tmp_path / 'source.pdf'
    make_pdf(source, [[(80, 'First proposal'), (130, '************'),
                       (200, 'Second proposal'), (260, '************')]])
    output = tmp_path / 'out'
    summary = isolate_pdf(source, output, start_page=1, expected_count=2)
    first = extracted(output / 'source_paper_001_Unknown_Author.pdf')
    second = extracted(output / 'source_paper_002_Unknown_Author.pdf')
    assert 'First proposal' in first and 'Second proposal' not in first
    assert 'Second proposal' in second and 'First proposal' not in second
    assert '*' not in first + second
    assert summary['separator_count'] == 2
    with fitz.open(output / 'source_paper_001_Unknown_Author.pdf') as pdf:
        assert pdf[0].rect.height < 100
    assert source.exists()


def test_multipage_and_unterminated_final_proposal(tmp_path):
    source = tmp_path / 'source.pdf'
    make_pdf(source, [[(80, 'First proposal')],
                     [(80, 'Continuation'), (130, '************'), (200, 'Second proposal')]])
    summary = isolate_pdf(source, tmp_path / 'out', start_page=1, expected_count=2)
    assert summary['abstracts'][0]['page_count'] == 2
    assert summary['abstracts'][0]['pdf_end_page'] == 2
    assert summary['warnings']
    assert 'Continuation' in extracted(tmp_path / 'out/source_paper_001_Unknown_Author.pdf')


def test_count_mismatch_writes_nothing(tmp_path):
    source = tmp_path / 'source.pdf'
    make_pdf(source, [[(80, 'First'), (130, '************')]])
    output = tmp_path / 'out'
    with pytest.raises(ValueError, match='Expected 2'):
        isolate_pdf(source, output, start_page=1, expected_count=2)
    assert not output.exists()


def test_wrapped_and_separate_span_separators():
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 100), '***')
        page.insert_text((90, 100), '***', fontname='hebo')
        page.insert_text((72, 115), '******')
        separators = detect_delimiters(read_lines(page))
        assert len(separators) == 1
        assert separators[0].y1 > 115


def test_repeated_margins_and_theme_dividers(tmp_path):
    source = tmp_path / 'source.pdf'
    make_pdf(source, [[(50, 'Conference heading'), (100, 'First'),
                       (150, '************'), (790, '1')],
                     [(50, 'Conference heading'), (400, 'THEME 2: SANITATION'), (790, '2')],
                     [(50, 'Conference heading'), (100, 'Second'),
                       (150, '************'), (790, '3')]])
    summary = isolate_pdf(source, tmp_path / 'out', start_page=1, expected_count=2)
    assert summary['abstract_count'] == 2
    text = extracted(tmp_path / 'out/source_paper_002_Unknown_Author.pdf')
    assert 'Conference heading' not in text
    assert 'THEME' not in text
    assert 'Second' in text


def test_missing_separators_and_invalid_page_range(tmp_path):
    source = tmp_path / 'source.pdf'
    make_pdf(source, [[(100, 'Proposal')]])
    with pytest.raises(ValueError, match='No asterisk'):
        isolate_pdf(source, tmp_path / 'out', start_page=1)
    with pytest.raises(ValueError, match='Start/end'):
        isolate_pdf(source, tmp_path / 'out', start_page=0)


def test_printed_ids_control_names_not_boundaries(tmp_path):
    source = tmp_path / 'Abstract Book.pdf'
    make_pdf(source, [[(80, '7147445'), (110, 'First proposal'), (150, '************'),
                       (200, 'ICNSS#10'), (230, 'Second proposal'), (270, '************')],
                     [(80, '714956-1'), (110, 'Third proposal'), (150, '************')],
                     [(80, '149742'), (110, 'Fourth proposal'), (150, '************')]])
    summary = isolate_pdf(source, tmp_path / 'out', start_page=1, expected_count=4)
    assert [row['abstract_id'] for row in summary['abstracts']] == [
        '7147445', 'ICNSS#10', '714956-1', '149742']
    for row in summary['abstracts']:
        assert row['output_file'] == f"Abstract_Book_{row['abstract_id']}_Unknown_Author.pdf"
        assert (tmp_path / 'out' / row['output_file']).exists()


def test_duplicate_ids_fail_before_writing(tmp_path):
    source = tmp_path / 'source.pdf'
    make_pdf(source, [[(80, '7147445'), (110, 'First'), (150, '************'),
                       (200, '7147445'), (230, 'Second'), (270, '************')]])
    with pytest.raises(ValueError, match='Duplicate submission ID'):
        isolate_pdf(source, tmp_path / 'out', start_page=1)
    assert not (tmp_path / 'out').exists()


def test_extra_separator_figure_and_poster_divider(tmp_path):
    source = tmp_path / 'source.pdf'
    make_pdf(source, [[(50, 'Conference'), (100, '7147445'), (130, 'First'),
                       (170, '************'), (790, '1')],
                     [(50, 'Conference'), (100, 'Figure 1 Dry toilet'),
                       (170, '************'), (790, '2')],
                     [(50, 'Conference'), (400, 'POSTER PRESENTATION ABSTRACTS'), (790, '3')],
                     [(50, 'Conference'), (100, '7149502'), (130, 'Second'),
                       (170, '************'), (790, '4')]])
    summary = isolate_pdf(source, tmp_path / 'out', start_page=1, expected_count=2)
    assert summary['abstracts'][0]['page_count'] == 2
    assert 'Figure 1 Dry toilet' in extracted(tmp_path / 'out/source_7147445_Unknown_Author.pdf')
    assert 'POSTER' not in extracted(tmp_path / 'out/source_7149502_Unknown_Author.pdf')
    assert any('caption-only' in warning for warning in summary['warnings'])


def test_first_author_filename_and_heading_metadata(tmp_path):
    source = tmp_path / 'Abstract Book.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 80), '7147445')
        page.insert_text((72, 110), 'Research Title', fontsize=16, fontname='hebo')
        page.insert_text((72, 125), ' ', fontsize=16)
        page.insert_text((72, 140), 'K. S. Shameem1, Another Author2', fontsize=12, fontname='hebo')
        page.insert_text((72, 170), '1 Research Institute', fontname='heit')
        page.insert_text((72, 210), 'Body of abstract')
        page.insert_text((72, 250), '************')
        pdf.save(source)
    result = isolate_pdf(source, tmp_path / 'out', start_page=1)
    row = result['abstracts'][0]
    assert row['title'] == 'Research Title'
    assert row['first_author'] == 'K. S. Shameem'
    assert row['output_file'] == 'Abstract_Book_7147445_K.S.Shameem.pdf'
    assert not result['warnings']
    assert (tmp_path / 'out' / row['output_file']).exists()


def test_comma_between_initial_and_surname(tmp_path):
    source = tmp_path / 'source.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 80), '7149372')
        page.insert_text((72, 110), 'Research Title', fontsize=16, fontname='hebo')
        page.insert_text((72, 140), 'T, Ahmed1 and S. Kumar2', fontname='hebo')
        page.insert_text((72, 180), '************')
        pdf.save(source)
    row = isolate_pdf(source, tmp_path / 'out', start_page=1)['abstracts'][0]
    assert row['first_author'] == 'T Ahmed'
    assert row['output_file'] == 'source_7149372_T.Ahmed.pdf'


@pytest.mark.parametrize("author,expected", [
    ("Govind Agrawala", "G.Agrawala"),
    ("K. S. Shameem", "K.S.Shameem"),
    ("D.R. Cloete", "D.R.Cloete"),
    ("A.Thomas", "A.Thomas"),
    ("RS Cottingham", "R.S.Cottingham"),
    ("Dr. OP Bhuraita", "O.P.Bhuraita"),
    ("Jayalekshmi T R", "T.R.Jayalekshmi"),
    ("C. Eloi Oliveira da Silva", "C.E.O.da_Silva"),
    ("M Lubeck-Schricker", "M.Lubeck-Schricker"),
    ("Bhavana", "Bhavana"),
    ("", "Unknown_Author"),
])
def test_academic_author_name(author, expected):
    from scripts.isolate_pdf import academic_author_name
    assert academic_author_name(author) == expected


def test_contents_validation_failure_preserves_source_and_writes_nothing(tmp_path):
    source = tmp_path / 'source.pdf'
    make_pdf(source, [[(80, '7147445'), (110, 'Actual title'), (150, '************')]])
    with pytest.raises(ValueError, match='Contents title/page mismatch'):
        isolate_pdf(source, tmp_path / 'pdfs', start_page=1,
                    metadata_folder=tmp_path / 'reports',
                    contents_entries=[{'title': 'Different title', 'printed_start_page': 1, 'pdf_start_page': 1}])
    assert source.exists()
    assert not (tmp_path / 'pdfs').exists()
    assert not (tmp_path / 'reports').exists()
