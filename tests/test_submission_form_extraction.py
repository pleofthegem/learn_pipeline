"""Regression coverage for labelled, boxed submission forms like F1-7097890."""
import csv
import json
from pathlib import Path

import fitz
import pytest

from scripts.extract_abstract_data import extract_abstract_data, extract_submission_form, process_pdf


@pytest.fixture
def submission_form_pdf(tmp_path: Path):
    def create(*, conference=True, keywords=False, keyword_heading="KEYWORDS:"):
        path = tmp_path / 'arbitrary-name.pdf'
        with fitz.open() as pdf:
            page = pdf.new_page()
            def text(x, y, value):
                page.insert_text((x, y), value, fontsize=10)
            text(90, 40, 'Abstract Submission Form')
            text(460, 40, 'Page 1 of 2')
            text(90, 65, 'Instructions: Copy/Paste information into the boxes below.')
            text(90, 90, 'PAPER TITLE')
            text(95, 110, 'Comparing urban stream water quality')
            text(95, 124, 'during wet and dry seasons')
            text(90, 150, 'AUTHORS and AFFILIATIONS (organization, city, province or state, country)')
            text(90, 164, 'Add more entries as needed.')
            for x in (90, 110, 240, 540):
                page.draw_line((x, 175), (x, 375))
            for i in range(6):
                y = 175 + 40 * i
                page.draw_line((90, y), (540, y))
            names = ['Mahtab Bagheban', 'Pooneh Malekan', 'Roghieh Rostami',
                     'Omid Khosravi\nAghaei', 'Bahman Akbarpour']
            for i, name in enumerate(names):
                y = 190 + 40 * i
                text(95, y, str(i + 1))
                text(120, y, name)
                text(250, y, 'Reference Laboratory, Tehran, Iran')
                text(250, y + 13, 'contact@example.com')
            text(90, 400, 'PRESENTER and EMAIL ADDRESS')
            text(95, 420, 'Mahtab Bagheban')
            text(250, 420, 'presenter@example.com')
            text(90, 460, 'ABSTRACT [maximum 500 words]')
            text(95, 485, 'Context: Seasonal water quality varies.')
            text(95, 505, 'Research aim: Compare wet and dry seasons.')
            text(95, 525, 'Methodology: Samples were collected.')
            text(95, 545, 'Findings: Pollution increased during the dry season.')
            if conference:
                page.insert_text((35, 740), 'Example Water Conference 2026 Toronto', fontsize=14, rotate=90)
            page = pdf.new_page()
            text(90, 40, 'Example Water 2026 Abstract Submission Form')
            text(460, 40, 'Page 2 of 2')
            text(95, 85, 'Data collection: Thirty-six stream locations.')
            text(95, 105, 'Analysis procedures: Compare measured pollutants.')
            text(95, 125, 'Questions addressed: What changes with rainfall?')
            text(95, 145, 'Conclusion: Continuous monitoring is necessary.')
            if keywords:
                text(90, 180, keyword_heading)
                text(95, 200, 'urban streams; seasonal variation')
            text(90, 240, 'PREFERRED PRESENTATION TYPE')
            text(95, 260, 'Platform, Poster')
            text(90, 300, 'THEME (see Conference Abstract Submission for details)')
            text(95, 320, 'Micropollutants in water')
            text(90, 360, 'SPECIAL TOPIC (see Conference Abstract Submission for details)')
            text(95, 380, 'Surface water')
            pdf.save(path)
        return path
    return create


def test_submission_form_extracts_labelled_fields_and_complete_abstract(submission_form_pdf):
    path = submission_form_pdf()
    original = path.read_bytes()
    row = process_pdf(path, {'name': 'Fallback', 'place': 'Elsewhere'})
    assert row['abstract_title'] == 'Comparing urban stream water quality during wet and dry seasons'
    assert row['abstract_authors'] == (
        'Mahtab Bagheban, Pooneh Malekan, Roghieh Rostami, '
        'Omid Khosravi Aghaei, Bahman Akbarpour'
    )
    assert row['abstract_description'] == (
        'Context: Seasonal water quality varies. '
        'Research aim: Compare wet and dry seasons. '
        'Methodology: Samples were collected. '
        'Findings: Pollution increased during the dry season. '
        'Data collection: Thirty-six stream locations. '
        'Analysis procedures: Compare measured pollutants. '
        'Questions addressed: What changes with rainfall? '
        'Conclusion: Continuous monitoring is necessary.'
    )
    assert row['abstract_keywords'] == ''
    assert row['additional_info'] == {'name': 'Example Water Conference 2026', 'place': 'Toronto'}
    assert path.read_bytes() == original


@pytest.mark.parametrize('heading', ['KEYWORDS:', 'Abstract keywords', 'ABSTRACT KEYWORDS [maximum 5]'])
def test_submission_form_keywords_defaults_and_metadata_exports(submission_form_pdf, tmp_path, heading):
    path = submission_form_pdf(conference=False, keywords=True, keyword_heading=heading)
    csv_path, json_path = tmp_path / 'metadata.csv', tmp_path / 'metadata.json'
    rows = extract_abstract_data(
        tmp_path, csv_path, json_path, {'name': 'Fallback Conference', 'place': 'London'},
    )
    assert len(rows) == 1
    row = rows[0]
    assert row['filename'] == path.name
    assert row['abstract_keywords'] == 'urban streams, seasonal variation'
    assert row['additional_info'] == {'name': 'Fallback Conference', 'place': 'London'}
    assert row['abstract_description'].endswith('Conclusion: Continuous monitoring is necessary.')
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        exported = list(csv.DictReader(stream))
    assert exported[0]['abstract_authors'] == row['abstract_authors']
    assert json.loads(json_path.read_text()) == rows


def test_incomplete_form_signature_defers_to_existing_extractors(tmp_path):
    assert extract_submission_form(
        tmp_path / 'ordinary.pdf', ['PAPER TITLE', 'Some research', 'Abstract', 'Some text.'],
    ) is None
