import csv
import json
from pathlib import Path

import fitz
import pytest

from conftest import write_sample_pdf
from extract_abstract_data import (
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


def test_process_pdf_extracts_multiline_conference_metadata(
    tmp_path: Path,
) -> None:
    """Check that multiline conference headers become additional info."""
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
        "place": "Chiang Mai, Thailand",
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
