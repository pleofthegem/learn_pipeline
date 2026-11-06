import csv
import json
from pathlib import Path

import fitz
import pytest

from conftest import write_sample_pdf
from scripts.extract_abstract_data import (
    clean_author_line,
    default_additional_info_from_values,
    extract_abstract_data,
    extract_abstract_metadata,
    extract_keywords,
    is_author_marker_fragment_line,
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
        "Graywater, Indicator organisms, Bacteriophages"
    )
    assert row["additional_info"] == {
        "name": (
            "13th IWA International conference "
            "(Theme-Water Reuse in developing countries)"
        ),
        "place": "",
    }


def test_process_pdf_fills_missing_additional_info_from_default(
    dasgupta_like_pdf: Path,
) -> None:
    """Check that explicit defaults fill fields missing from the PDF header."""
    row = process_pdf(
        dasgupta_like_pdf,
        default_additional_info={
            "name": "Fallback conference",
            "place": "Mumbai, India",
        },
    )

    assert row["additional_info"] == {
        "name": (
            "13th IWA International conference "
            "(Theme-Water Reuse in developing countries)"
        ),
        "place": "Mumbai, India",
    }


def test_process_pdf_uses_empty_additional_info_without_default(
    tmp_path: Path,
) -> None:
    """Check that missing event data stays empty when no default is provided."""
    path = tmp_path / "Meng - Rural Sewage Treatment in China.pdf"
    write_sample_pdf(
        path,
        [
            "Rural Sewage Treatment in China",
            "Wenjing Meng*, Xiao Hu*",
            "*School of Environmental Science and Engineering",
            "Abstract: Rural sewage treatment is a critical issue.",
            "Keywords: treatment, investment",
        ],
    )

    row = process_pdf(path)

    assert row["additional_info"] == {"name": "", "place": ""}


def test_process_pdf_uses_default_additional_info_for_standalone_pdf(
    tmp_path: Path,
) -> None:
    """Check that normal PDFs without event headers use explicit defaults."""
    path = tmp_path / "Meng - Rural Sewage Treatment in China.pdf"
    default_additional_info = {
        "name": "IWA Example Conference",
        "place": "Example City, Example Country",
    }
    write_sample_pdf(
        path,
        [
            "Rural Sewage Treatment in China",
            "Wenjing Meng*, Xiao Hu*",
            "*School of Environmental Science and Engineering",
            "Abstract: Rural sewage treatment is a critical issue.",
            "Keywords: treatment, investment",
        ],
    )

    row = process_pdf(path, default_additional_info)

    assert row["abstract_title"] == "Rural Sewage Treatment in China"
    assert row["additional_info"] == default_additional_info


def test_default_additional_info_from_values_is_optional() -> None:
    """Check that omitted CLI defaults remain absent instead of empty dicts."""
    assert default_additional_info_from_values() is None
    assert default_additional_info_from_values(place="  Nairobi, Kenya ") == {
        "name": "",
        "place": "Nairobi, Kenya",
    }


def test_multiline_conference_name_does_not_imply_an_unlabelled_place(
    tmp_path: Path,
) -> None:
    """Keep a strong event heading but require a location label."""
    path = (
        tmp_path
        / "Chang - Analysis of Ecological Base Flow in an Urban Water Environment System.pdf"
    )
    write_sample_pdf(
        path,
        [
            "IWA 21st INTERNATIONAL CONFERENCE ON",
            "DIFFUSE POLLUTION & EUTROPHICATION",
            "DECEMBER 11-14, 2024,",
            "CHIANG MAI, THAILAND",
            "Analysis of Ecological Base Flow in an Urban Water Environment System",
            "Chia-Ling Changa, Chih-Chao Hob, Jian-Chen Liaoc",
            "Introduction",
            "As urbanization intensifies, the risk and vulnerability increase.",
        ],
    )

    row = process_pdf(path)

    assert row["additional_info"] == {
        "name": (
            "IWA 21st International Conference on "
            "Diffuse Pollution & Eutrophication"
        ),
        "place": "",
    }


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


def test_process_pdf_ignores_template_placeholder_title(
    tmp_path: Path,
) -> None:
    """Check that leftover template title text does not become metadata."""
    path = tmp_path / "Water Board 2026_O02.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    y = 72
    for text, size in [
        ("National Water Supply and Drainage Board, Sri Lanka.", 8),
        ("04", 8),
        ("This is a Sample Abstract Title", 16),
        (
            "Author Name*, Author Name**, initials then surnames, "
            "separated by commas, appear here",
            10,
        ),
        ("Evaluating the Multifunctional Benefits of Urban Stormwater", 16),
        ("Nature-Based Technologies", 16),
        ("Md Tashdedul Haque, Lee -Hyung Kim*", 10),
        (
            "Keywords: LID technologies; nature-based solutions; "
            "soil organic carbon; urban heat island",
            12,
        ),
        ("Abstract: Rapid urbanization has intensified environmental issues.", 12),
    ]:
        page.insert_text((72, y), text, fontsize=size)
        y += size + 8
    pdf.save(path)
    pdf.close()

    row = process_pdf(path)

    assert row["abstract_title"] == (
        "Evaluating the Multifunctional Benefits of Urban Stormwater "
        "Nature-Based Technologies"
    )
    assert row["abstract_authors"] == "Md Tashdedul Haque, Lee -Hyung Kim"


def test_process_pdf_ignores_bracketed_title_noise_line(
    tmp_path: Path,
) -> None:
    """Check that hidden bracket-only title noise is ignored."""
    path = tmp_path / "Water Board 2026_P05.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    y = 72
    for text, size in [
        ("National Water Supply and Drainage Board, Sri Lanka.", 8),
        ("202", 8),
        ("(Timothy J. Entwisle, no date)", 16),
        ("This is a Sample Abstract Title", 16),
        (
            "Author Name*, Author Name**, initials then surnames, "
            "separated by commas, appear here",
            10,
        ),
        ("Degradation of organic textile dye using Graphene Oxide and", 16),
        ("Graphitic Carbon Nitride composite (GO/g-C3N4) as a", 16),
        ("Photocatalyst", 16),
        (
            "K.A.C.P. Abeyrathna*, U. A. D Jayasinghe** "
            "and R. A. Maithreepala***",
            10,
        ),
        (
            "Keywords: Graphene Oxide; Graphitic Carbon Nitride; "
            "Textile Dye; Photodegradation",
            12,
        ),
        ("Abstract: This study reports photocatalytic degradation.", 12),
    ]:
        page.insert_text((72, y), text, fontsize=size)
        y += size + 8
    pdf.save(path)
    pdf.close()

    row = process_pdf(path)

    assert row["abstract_title"] == (
        "Degradation of organic textile dye using Graphene Oxide and "
        "Graphitic Carbon Nitride composite (GO/g-C3N4) as a Photocatalyst"
    )
    assert row["abstract_authors"] == (
        "K.A.C.P. Abeyrathna, U. A. D Jayasinghe, R. A. Maithreepala"
    )


def test_process_pdf_extracts_wrapped_comma_separated_authors(
    tmp_path: Path,
) -> None:
    """Check that wrapped author lists are joined before comma parsing."""
    path = tmp_path / "Example - Algal Blooms in Drinking Water Supply Reservoirs.pdf"
    write_sample_pdf(
        path,
        [
            "National Water Supply and Drainage Board, Sri Lanka.",
            "226",
            "Algal Blooms in Drinking Water Supply Reservoirs",
            (
                "L. Wijewardene*, S. Senevirathne**, R. Jayawardena***, "
                "U. Ulrich****, P. Drechsel*****, J. P."
            ),
            "Simaika******, S. K. Weragoda*******, I. Werellagama********",
            "*Department of Limnology and Water Technology, University of Ruhuna",
            "**Department of Limnology and Water Technology, University of Ruhuna",
            "Abstract: Reservoir algal blooms can affect drinking water safety.",
            "Keywords: algae; reservoirs; drinking water",
        ],
    )

    row = process_pdf(path)

    assert row["abstract_authors"] == (
        "L. Wijewardene, S. Senevirathne, R. Jayawardena, "
        "U. Ulrich, P. Drechsel, J. P. Simaika, "
        "S. K. Weragoda, I. Werellagama"
    )


def test_process_pdf_extracts_water_board_title_until_author_line(
    tmp_path: Path,
) -> None:
    """Check that mixed-size Water Board title lines are joined."""
    path = tmp_path / "Water Board 2026_O68.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    y = 72
    for text, size in [
        ("National Water Supply and Drainage Board, Sri Lanka.", 8),
        ("162", 8),
        ("Assessing", 18),
        ("Outcome-Based Optimization of Electrocoagulation-Flotation for", 16),
        ("Sustainable Sewage Wastewater Reclamation and Reuse", 16),
        ("Polisetty Venkateswara Rao*, Ashish Dwivedi**", 10),
        (
            "*Water and Environment Division, Department of Civil Engineering, "
            "National Institute of Technology",
            11,
        ),
        (
            "Keywords: Electrocoagulation; Sewage wastewater; "
            "Response surface methodology",
            12,
        ),
        ("Abstract: This study investigates electrocoagulation-flotation.", 12),
    ]:
        page.insert_text((72, y), text, fontsize=size)
        y += size + 8
    pdf.save(path)
    pdf.close()

    row = process_pdf(path)

    assert row["abstract_title"] == (
        "Assessing Outcome-Based Optimization of Electrocoagulation-Flotation "
        "for Sustainable Sewage Wastewater Reclamation and Reuse"
    )
    assert row["abstract_authors"] == (
        "Polisetty Venkateswara Rao, Ashish Dwivedi"
    )


def test_process_pdf_handles_abstract_before_keywords_layout(
    tmp_path: Path,
) -> None:
    """Check TS-style numbered authors and post-abstract keywords."""
    path = tmp_path / "TS 1.01-P1-Asef Redwan-6978028.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    y = 72
    for text, size in [
        ("Predicting Effects of Groundwater Elements in Arsenic Mobilization", 14),
        ("using Machine Learning Algorithms: BDT, LR and RF", 14),
        (
            "Tasnia Ashrafi Heya1, Asef Mohammad Redwan2, "
            "Tahsin Habib2, Shubhra Bhattacharjee3 and",
            10.5,
        ),
        ("Md Shakil Kashem4", 10.5),
        ("1University of Dayton, Dayton, Ohio", 10.5),
        (
            "Abstract: Arsenic contamination in groundwater is a global "
            "public health concern.",
            10,
        ),
        ("This study presents a predictive analysis of arsenic levels.", 10),
        (
            "Keywords: Arsenic contamination; machine learning; "
            "spatial distribution",
            10,
        ),
        ("Arsenic, a carcinogenic metalloid found in sediments, poses a", 12),
        ("risk to people worldwide.", 12),
    ]:
        page.insert_text((72, y), text, fontsize=size)
        y += size + 8
    pdf.save(path)
    pdf.close()

    row = process_pdf(path)

    assert row["abstract_title"] == (
        "Predicting Effects of Groundwater Elements in Arsenic Mobilization "
        "using Machine Learning Algorithms: BDT, LR and RF"
    )
    assert row["abstract_authors"] == (
        "Tasnia Ashrafi Heya, Asef Mohammad Redwan, Tahsin Habib, "
        "Shubhra Bhattacharjee, Md Shakil Kashem"
    )
    assert row["abstract_keywords"] == (
        "Arsenic contamination, machine learning, spatial distribution"
    )


def test_process_pdf_keeps_comma_title_line_before_marked_author(
    tmp_path: Path,
) -> None:
    """Check that comma-containing title lines are not treated as authors."""
    path = tmp_path / "Water Board 2026_O16.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    y = 72
    for text, size in [
        ("National Water Supply and Drainage Board, Sri Lanka.", 8),
        ("38", 8),
        ("Urban Stormwater Disinfection, Storage Quality Change and", 16),
        ("Influence on Microalgae: Implications for Reuse Safety", 16),
        ("An Liu*", 10),
        (
            "*College of Chemistry and Environmental Engineering, "
            "Shenzhen University",
            11,
        ),
        (
            "Keywords: Stormwater disinfection; Stormwater storage; "
            "Stormwater reuse",
            12,
        ),
        ("Abstract: Stormwater reuse requires disinfection.", 12),
    ]:
        page.insert_text((72, y), text, fontsize=size)
        y += size + 8
    pdf.save(path)
    pdf.close()

    row = process_pdf(path)

    assert row["abstract_title"] == (
        "Urban Stormwater Disinfection, Storage Quality Change and "
        "Influence on Microalgae: Implications for Reuse Safety"
    )
    assert row["abstract_authors"] == "An Liu"


def test_process_pdf_removes_water_board_qs_noise_and_marker_commas(
    tmp_path: Path,
) -> None:
    """Check that floating Water Board noise and marker commas are ignored."""
    path = tmp_path / "Water Board 2026_O08.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    y = 72
    for text, size in [
        ("National Water Supply and Drainage Board, Sri Lanka.", 8),
        ("18", 8),
        ("qs", 16),
        ("Spatiotemporal Dynamics of Dissolved Organic Matter (DOM)", 16),
        ("in Beira Lake, Sri Lanka", 16),
        (
            "S. Prasad1,2,3,*, Wei Yuansong1,2,3,**, "
            "Tushara Chaminda4,***, M.",
            10,
        ),
        ("Makehelwala7,**********", 10),
        ("1State Key Laboratory of Regional Environment and Sustainability", 11),
        (
            "Keywords: DOM; Urban Lakes; Beira Lake; "
            "Risk-based Monitoring",
            12,
        ),
        ("Abstract: This study analyzes DOM.", 12),
    ]:
        page.insert_text((72, y), text, fontsize=size)
        y += size + 8
    pdf.save(path)
    pdf.close()

    row = process_pdf(path)

    assert row["abstract_title"] == (
        "Spatiotemporal Dynamics of Dissolved Organic Matter (DOM) "
        "in Beira Lake, Sri Lanka"
    )
    assert row["abstract_authors"] == (
        "S. Prasad, Wei Yuansong, Tushara Chaminda, M. Makehelwala"
    )


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


def test_author_marker_detection_matches_suffix_shape() -> None:
    """Check that author markers are detected by suffix shape."""
    assert is_author_marker_fragment_line("S. Prasad1,2,3,*")
    assert is_author_marker_fragment_line("Makehelwala7,**********")
    assert not is_author_marker_fragment_line("*College of Chemistry")
    assert not is_author_marker_fragment_line("Risk * management title")


def test_standardise_keywords_joins_detected_separator_with_comma() -> None:
    """Check that keyword separators are normalised to commas."""
    assert standardise_keywords("water, sanitation, reuse") == (
        "water, sanitation, reuse"
    )
    assert standardise_keywords("water ; sanitation; reuse") == (
        "water, sanitation, reuse"
    )
    assert standardise_keywords("Drinking water; Decentralization.") == (
        "Drinking water, Decentralization"
    )


def test_extract_keywords_standardises_comma_separator() -> None:
    """Check that comma-separated keywords are returned with commas."""
    assert extract_keywords([
        "Abstract: sample",
        "Keywords: water, sanitation, reuse",
    ]) == "water, sanitation, reuse"


def test_extract_keywords_includes_continuation_lines_until_next_heading() -> None:
    """Check that wrapped keyword lines are joined before standardising."""
    assert extract_keywords([
        "Keywords: Hydrochar; Phytotoxicity; Seed",
        "Germination",
        "Abstract: Hydrochar produced via hydrothermal carbonization.",
    ]) == "Hydrochar, Phytotoxicity, Seed Germination"

    assert extract_keywords([
        "Keywords: Chronic kidney disease of unknown etiology; Nanofiltration; Drinking",
        "water; Decentralization.",
        "Introduction:",
        "Safe drinking water is essential.",
    ]) == (
        "Chronic kidney disease of unknown etiology, Nanofiltration, "
        "Drinking water, Decentralization"
    )


def test_extract_keywords_stops_at_inline_section_heading() -> None:
    """Check that same-line section text after keywords is not included."""
    assert extract_keywords([
        (
            "Keywords: arsenic; machine learning Abstract: This should not "
            "be treated as a keyword."
        ),
    ]) == "arsenic, machine learning"


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

    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")

    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        csv_rows = list(csv.DictReader(f))
    with json_path.open(encoding="utf-8") as f:
        json_rows = json.load(f)

    expected_csv_row = {
        key: value for key, value in rows[0].items()
        if isinstance(value, str)
    }
    expected_csv_row["additional_info"] = json.dumps(
        rows[0]["additional_info"],
        ensure_ascii=False,
    )

    assert csv_rows == [expected_csv_row]
    assert json.loads(csv_rows[0]["additional_info"]) == rows[0]["additional_info"]
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
        default_additional_info={
            "name": "Default conference",
            "place": "Default place",
        },
    )

    assert [row["filename"] for row in rows] == [dasgupta_like_pdf.name]
    assert rows[0]["additional_info"]["place"] == "Default place"
    assert csv_path.exists()
    assert json_path.exists()


@pytest.mark.parametrize("heading", [
    "Abstract keywords", "ABSTRACT KEYWORDS [maximum 5]", "Abstract key words:",
])
def test_abstract_keyword_heading_before_abstract_is_not_description(tmp_path, heading):
    path = tmp_path / "keywords.pdf"
    write_sample_pdf(path, [
        "Water quality research", "Jane Smith", heading,
        "Southern Bangladesh; Micropollutants; Groundwater; Climate",
        "Resilience", "Abstract", "The study compares water quality.",
    ])
    row = process_pdf(path)
    assert row["abstract_keywords"] == "Southern Bangladesh, Micropollutants, Groundwater, Climate Resilience"
    assert row["abstract_description"] == "The study compares water quality."


@pytest.mark.parametrize('body_heading', ['', 'Introduction'])
@pytest.mark.parametrize('keywords_first', [False, True])
def test_unlabelled_body_is_not_extracted_as_an_abstract(tmp_path, body_heading, keywords_first):
    path = tmp_path / 'paper.pdf'
    first_paragraph = (
        'We measured seasonal water quality changes across several streams to understand '
        'how rainfall influences pollutant concentrations and downstream habitats.'
    )
    last_paragraph = (
        'The measurements show that continuous monitoring provides useful evidence for '
        'water management and helps identify areas requiring further investigation.'
    )
    with fitz.open() as pdf:
        first = pdf.new_page()
        first.insert_text((72, 72), 'Urban stream water quality', fontsize=18)
        first.insert_text((72, 100), 'Jane Smith, John Doe', fontsize=11)
        first.insert_text((72, 120), 'Department of Water, Example University', fontsize=10)
        first.insert_text((72, 135), 'jane@example.com', fontsize=10)
        if keywords_first:
            first.insert_text((72, 155), 'Keywords: streams; rainfall', fontsize=10)
        first.insert_textbox(fitz.Rect(72, 180, 520, 500),
                             (body_heading + '\n' if body_heading else '') + first_paragraph, fontsize=10)
        first.insert_text((72, 750), 'Page 1 of 2', fontsize=10)
        second = pdf.new_page()
        second.insert_text((72, 40), 'Abstract Submission Form', fontsize=10)
        second.insert_text((72, 60), 'Page 2 of 2', fontsize=10)
        second.insert_textbox(fitz.Rect(72, 100, 520, 500),
                              'Results\n' + last_paragraph, fontsize=10)
        if not keywords_first:
            second.insert_text((72, 550), 'Keywords: streams; rainfall', fontsize=10)
        second.insert_text((72, 600), 'References', fontsize=10)
        second.insert_text((72, 620), 'A citation that is not part of the abstract.', fontsize=10)
        pdf.save(path)
    row = process_pdf(path)
    assert row['abstract_description'] == ''
    assert row['abstract_title'] == 'Urban stream water quality'
    assert row['abstract_keywords'] == 'streams, rainfall'


@pytest.mark.parametrize('prefix', ['7147445', '149742', '714956-1', 'ICNSS#10', 'ICNSS # 10', 'T1_O1'])
def test_submission_id_is_removed_before_title_selection(tmp_path, prefix):
    path = tmp_path / 'paper.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), prefix, fontsize=18)
        for y, text in [(100, 'A long research title'), (125, 'continued on a second line'),
                        (150, 'continued on a third line'), (175, 'and finished on a fourth line')]:
            page.insert_text((72, y), text, fontsize=16)
        page.insert_text((72, 210), 'Jane Smith1, John Doe2', fontsize=11)
        page.insert_text((72, 240), 'This is unlabelled body text with enough words to pass the old fallback.')
        pdf.save(path)
    row = process_pdf(path)
    assert row['abstract_title'] == ('A long research title continued on a second line '
                                     'continued on a third line and finished on a fourth line')
    assert row['abstract_description'] == ''


@pytest.mark.parametrize('title,expected', [
    ('7147445 Research on water quality', 'Research on water quality'),
    ('ICNSS#10: Research on water quality', 'Research on water quality'),
    ('714956-1 — Research on water quality', 'Research on water quality'),
    ('2026 Advances in sanitation', '2026 Advances in sanitation'),
    ('1. Research on water quality', '1. Research on water quality'),
    ('Research using dataset 7147445', 'Research using dataset 7147445'),
    ('12345678 Research on water quality', '12345678 Research on water quality'),
])
def test_clean_title_prefix_preserves_unrecognised_numbers(title, expected):
    from scripts.extract_abstract_data import clean_title_prefix
    assert clean_title_prefix(title) == expected


@pytest.mark.parametrize('heading,expected', [
    ('Abstract', 'A clearly labelled summary.'),
    ('Abstract: A clearly labelled summary.', 'A clearly labelled summary.'),
    ('Abstract Book', ''),
    ('Abstracted research data', ''),
    ('Introduction', ''),
    ('Summary', ''),
])
def test_description_requires_explicit_abstract_label(tmp_path, heading, expected):
    path = tmp_path / 'paper.pdf'
    paragraphs = ['Water quality research', 'Jane Smith', heading]
    if heading != 'Abstract: A clearly labelled summary.':
        paragraphs.append('A clearly labelled summary.')
    paragraphs.append('Keywords: water; sanitation')
    write_sample_pdf(path, paragraphs)
    row = process_pdf(path)
    assert row['abstract_description'] == expected
    assert row['abstract_keywords'] == 'water, sanitation'


def test_multiline_paper_title_is_excluded_from_event_metadata(tmp_path):
    path = tmp_path / 'paper.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        for y, text in [(65, 'IWA 21st International Conference'), (85, 'December 11-14, 2024')]:
            page.insert_text((72, y), text, fontsize=10)
        page.insert_text((72, 120), 'WASTEWATER TREATMENT', fontsize=16)
        page.insert_text((72, 145), 'AT THE INTERNATIONAL CONFERENCE 2026', fontsize=16)
        page.insert_text((72, 175), 'Jane Smith1, John Doe2', fontsize=11)
        page.insert_text((72, 210), 'Location: This is a study site, not the event venue', fontsize=10)
        pdf.save(path)
    row = process_pdf(path)
    assert row['abstract_title'] == 'WASTEWATER TREATMENT AT THE INTERNATIONAL CONFERENCE 2026'
    assert row['additional_info'] == {'name': 'IWA 21st International Conference', 'place': ''}


@pytest.mark.parametrize('label', ['Venue', 'Location', 'Host city', 'Conference location', 'Event venue'])
def test_explicit_event_labels_before_title_are_accepted(tmp_path, label):
    path = tmp_path / 'paper.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 60), 'Conference name: Example Water Conference', fontsize=10)
        page.insert_text((72, 80), f'{label}: London, UK', fontsize=10)
        page.insert_text((72, 120), 'Water quality research', fontsize=16)
        page.insert_text((72, 150), 'Jane Smith1, John Doe2', fontsize=11)
        pdf.save(path)
    assert process_pdf(path)['additional_info'] == {'name': 'Example Water Conference', 'place': 'London, UK'}


@pytest.mark.parametrize('header', [
    ['December 11-14, 2024', 'WASTEWATER TREATMENT'],
    ['December 11-14, 2024, London, UK'],
    ['Unexpected Symposium Header That Could Change Next Year'],
    ['A discussion of conference outcomes'],
])
def test_weak_event_evidence_is_left_blank(header):
    from scripts.extract_abstract_data import TextLine, extract_additional_info
    lines = [TextLine(text, 10) for text in header] + [TextLine('Water quality research', 16)]
    assert extract_additional_info(lines, len(lines) - 1, title='Water quality research') == {'name': '', 'place': ''}


def test_conference_name_does_not_absorb_following_text():
    from scripts.extract_abstract_data import extract_conference_name
    assert extract_conference_name(['13th IWA International Conference', 'UNRELATED HEADER TEXT']) == '13th IWA International Conference'


@pytest.mark.parametrize('field,headers', [
    ('place', ['Venue: London, UK', 'Location: Paris, France']),
    ('name', ['Conference: Water Research', 'Event: Sanitation Research']),
])
def test_conflicting_explicit_event_labels_are_left_blank(field, headers):
    from scripts.extract_abstract_data import TextLine, extract_additional_info
    lines = [TextLine(text, 10) for text in headers] + [TextLine('Water quality research', 16)]
    assert extract_additional_info(lines, len(lines) - 1, title='Water quality research')[field] == ''


@pytest.mark.parametrize('designation', [
    '1Director - Operations, Energy Tech Solutions Pvt. Ltd., Pune;',
    'Director - Operations, Energy Tech Solutions Pvt. Ltd., Pune;',
    '1Senior Consultant, Water Solutions Private Limited, Pune;',
])
def test_single_numbered_author_is_not_replaced_by_designation(tmp_path, designation):
    path = tmp_path / 'paper.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 80), 'Effective Decentralised Treatment', fontsize=16)
        page.insert_text((72, 110), 'R. S. Babar1', fontsize=12)
        page.insert_text((72, 140), designation, fontsize=10)
        page.insert_text((72, 160), 'rahulbabar1204@gmail.com', fontsize=10)
        page.insert_text((72, 190), 'India faces water stress, pollution, and population growth.', fontsize=12)
        pdf.save(path)
    row = process_pdf(path)
    assert row['abstract_authors'] == 'R. S. Babar'
    assert row['abstract_description'] == ''


def test_designation_is_not_appended_to_wrapped_author_list(tmp_path):
    path = tmp_path / 'paper.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 80), 'Water quality research', fontsize=16)
        for y, text in [(110, 'Jane Smith1, John Doe2,'), (130, 'R. S. Babar3'),
                        (150, '3Director - Operations, Energy Tech Solutions Pvt. Ltd., Pune;')]:
            page.insert_text((72, y), text, fontsize=11, fontname='heit' if y == 150 else 'hebo')
        pdf.save(path)
    assert process_pdf(path)['abstract_authors'] == 'Jane Smith, John Doe, R. S. Babar'


def test_filename_and_metadata_share_formatted_author_block(tmp_path):
    from scripts.isolate_pdf import Region, extract_proposal_heading
    path = tmp_path / 'paper.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 60), '7149387')
        page.insert_text((72, 90), 'Water quality research', fontsize=16, fontname='hebo')
        page.insert_text((72, 120), 'R. S. Babar, Jane Smith', fontsize=12, fontname='hebo')
        # Deliberately no known job titles or institution keywords, and the same
        # font size as the names: typography, rather than a blacklist, separates it.
        page.insert_text((72, 150), 'Unfamiliar Appointment, Curious Services, Pune', fontsize=12, fontname='heit')
        page.insert_text((72, 180), 'Jane Doe, John Smith', fontsize=12)
        pdf.save(path)
    row = process_pdf(path)
    assert row['abstract_authors'] == 'R. S. Babar, Jane Smith'
    with fitz.open(path) as pdf:
        title, first = extract_proposal_heading(pdf, [Region(1, pdf[0].rect)])
    assert first == 'R. S. Babar'
    assert title == row['abstract_title']


def test_author_reader_stops_before_affiliation_and_does_not_search_body(tmp_path):
    path = tmp_path / 'rice_straw.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 70), 'Rice Straw as a Natural Plant-Based Coagulant', fontsize=16)
        page.insert_text((72, 95), 'for Water Treatment', fontsize=16)
        page.insert_text((72, 130), 'Bhavana1, Mahesh1, A.K. Patel2', fontsize=12)
        page.insert_text((72, 160), '1Unfamiliar Association, Warangal, India', fontsize=12)
        page.insert_text((72, 200), 'and chemical polymer flocculants like PAM, Alum pose environmental', fontsize=12)
        page.insert_text((72, 230), 'Jane Smith, John Doe', fontsize=12)
        pdf.save(path)
    assert process_pdf(path)['abstract_authors'] == 'Bhavana, Mahesh, A.K. Patel'


def test_missing_author_block_does_not_fall_through_to_body(tmp_path):
    path = tmp_path / 'paper.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 70), 'Water quality research', fontsize=16)
        page.insert_text((72, 110), '1Unfamiliar Association, London, UK', fontsize=12)
        page.insert_text((72, 150), 'A short body sentence.', fontsize=12)
        page.insert_text((72, 180), 'Jane Smith, John Doe', fontsize=12, fontname='hebo')
        pdf.save(path)
    assert process_pdf(path)['abstract_authors'] == ''


def test_same_style_association_is_not_an_author_continuation(tmp_path):
    path = tmp_path / 'paper.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 70), 'Water quality research', fontsize=16)
        page.insert_text((72, 110), 'Jane Smith1, John Doe2', fontsize=12, fontname='hebo')
        page.insert_text((72, 140), 'Unfamiliar Association, Pune, India', fontsize=12, fontname='hebo')
        pdf.save(path)
    assert process_pdf(path)['abstract_authors'] == 'Jane Smith, John Doe'


@pytest.mark.parametrize('raw,expected', [
    ('Jane Smith1', 'Jane Smith'),
    ('Jane Smith¹²', 'Jane Smith'),
    ('José O’Neill2', 'José O’Neill'),
    ('李明3', '李明'),
    ('Jane2Smith', ''),
    ('Jane_2_Smith', ''),
    ('Jane Smith@example.com', ''),
])
def test_author_names_allow_letters_and_name_punctuation_only(raw, expected):
    from scripts.extract_abstract_data import clean_author_name
    assert clean_author_name(raw) == expected


def test_wrapped_author_line_can_begin_with_and(tmp_path):
    path = tmp_path / 'paper.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 70), 'Water quality research', fontsize=16)
        page.insert_text((72, 110), 'Saumya1, Arvind Singh Senger3', fontsize=12, fontname='hebo')
        page.insert_text((72, 130), 'and Rajarshi Banerjee4', fontsize=12, fontname='hebo')
        page.insert_text((72, 160), 'Unfamiliar Association, Pune, India', fontsize=11, fontname='heit')
        pdf.save(path)
    assert process_pdf(path)['abstract_authors'] == 'Saumya, Arvind Singh Senger, Rajarshi Banerjee'


@pytest.mark.parametrize('title,expected', [
    ('"Water quality research"', 'Water quality research'),
    ('“Water quality research”', 'Water quality research'),
    ("'Water quality research'", 'Water quality research'),
    ('‘Water quality research’', 'Water quality research'),
    ('7147445 “Water quality research”', 'Water quality research'),
    ('“7147445 Water quality research”', 'Water quality research'),
    ('"\'Water quality research\'"', 'Water quality research'),
    ("China's toilet revolution", "China's toilet revolution"),
    ('Use of "green" technologies', 'Use of "green" technologies'),
])
def test_title_cleaning_strips_only_enclosing_quotes(title, expected):
    from scripts.extract_abstract_data import clean_title_prefix
    assert clean_title_prefix(title) == expected


@pytest.mark.parametrize('raw,expected', [
    ('Jane Smith1a', 'Jane Smith'),
    ('Jane Smith1,a', 'Jane Smith'),
    ('Jane Smith1, a *', 'Jane Smith'),
    ('Jane Smith1a,2b*', 'Jane Smith'),
    ('Laure Sionéb2a', 'Laure Sionéb'),
    ('Jane2Smith', ''),
])
def test_mixed_affiliation_suffixes_are_removed_as_a_group(raw, expected):
    from scripts.extract_abstract_data import clean_author_name
    assert clean_author_name(raw) == expected


def test_flat_text_markers_match_silver_membrane_author_list(tmp_path):
    from scripts.isolate_pdf import Region, extract_proposal_heading
    path = tmp_path / 'paper.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 60), '7114124')
        page.insert_text((72, 90), 'Silver-Infused Polymer Nanocomposite Membrane', fontsize=16)
        # All markers use the same font/baseline as the names: no superscript
        # formatting is available to help either author reader.
        page.insert_text((72, 120), 'Vaidhegi Kugarajah1,a*, Chris Felshia1,a,', fontsize=11)
        page.insert_text((72, 140), 'Jenifer J1,s and Hardika S1,a', fontsize=11)
        page.insert_text((72, 170), '1Unfamiliar Association, London, UK', fontsize=11)
        pdf.save(path)
    row = process_pdf(path)
    assert row['abstract_authors'] == 'Vaidhegi Kugarajah, Chris Felshia, Jenifer J, Hardika S'
    with fitz.open(path) as pdf:
        _, first = extract_proposal_heading(pdf, [Region(1, pdf[0].rect)])
    assert first == 'Vaidhegi Kugarajah'
