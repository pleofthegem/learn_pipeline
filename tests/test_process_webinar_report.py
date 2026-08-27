import csv
from pathlib import Path

import pandas as pd

from webinar.process_webinar_report import (
    CLEAN_SHEET_NAME,
    MASTER_COLUMNS,
    MASTER_SHEET_NAME,
    MASTER_WORKBOOK_NAME,
    SUMMARY_COLUMNS,
    SUMMARY_SHEET_NAME,
    build_master_summary,
    build_output_dataframes,
    default_output_path,
    find_input_files,
    prepare_attendee_dataframe,
    process_webinar_report,
    truncate_at_attendee_footer,
    webinar_name_from_filename,
)

ROW_VALUE_COLUMNS = [
    "Attended",
    "User Name",
    "First Name",
    "Last Name",
    "Email",
    "City",
    "Country/Region",
    "Organization",
    "Registration Time",
    "Approval Status",
    "Join Time",
    "Leave Time",
    "Time in Session (minutes)",
    "Is Guest",
    "Age",
    "Gender",
    "Type of Organisation",
    "IWA member?",
    "Career level?",
    "Source",
    "Consent",
    "Country/Region Name",
]

SOURCE_COLUMNS = [
    "Email Address",
    "Attendance Status",
    "Last Name",
    "First Name",
    "User Name (Original Name)",
    "Organization",
    "City",
    "Country Code",
    "Registered At",
    "Approval Status",
    "Session Duration (minutes)",
    "Joined At",
    "Left At",
    "Guest",
    "What age group are you in?",
    "Gender identity",
    "Which type of organization do you work for?",
    "Are you currently an IWA member?",
    "Current career level",
    "How did you hear about this webinar?",
    "I consent to being contacted",
    "Full Country Name",
]

SOURCE_VALUE_KEYS = {
    "Email Address": "Email",
    "Attendance Status": "Attended",
    "User Name (Original Name)": "User Name",
    "Country Code": "Country/Region",
    "Registered At": "Registration Time",
    "Session Duration (minutes)": "Time in Session (minutes)",
    "Joined At": "Join Time",
    "Left At": "Leave Time",
    "Guest": "Is Guest",
    "What age group are you in?": "Age",
    "Gender identity": "Gender",
    "Which type of organization do you work for?": "Type of Organisation",
    "Are you currently an IWA member?": "IWA member?",
    "Current career level": "Career level?",
    "How did you hear about this webinar?": "Source",
    "I consent to being contacted": "Consent",
    "Full Country Name": "Country/Region Name",
}


def arrange_source_row(row: list[str]) -> list[str]:
    values = dict(zip(ROW_VALUE_COLUMNS, row))
    return [values[SOURCE_VALUE_KEYS.get(column, column)] for column in SOURCE_COLUMNS]


def attendee_row(
    *,
    attended: str,
    name: str,
    email: str,
    city: str,
    country_code: str,
    organization: str,
    registration_time: str,
    approval_status: str,
    join_time: str,
    leave_time: str,
    session_minutes: str,
    age: str,
    gender: str,
    organisation_type: str,
    member: str,
    career_level: str,
    source: str,
    country_name: str,
) -> list[str]:
    first_name, _, last_name = name.partition(" ")
    return [
        attended,
        name,
        first_name,
        last_name,
        email,
        city,
        country_code,
        organization,
        registration_time,
        approval_status,
        join_time,
        leave_time,
        session_minutes,
        "Yes" if attended == "Yes" else "--",
        age,
        gender,
        organisation_type,
        member,
        career_level,
        source,
        "I understand.",
        country_name,
    ]


def write_raw_report(
    path: Path,
    webinar_name: str = "Test Webinar",
    webinar_id: str = "123 456 789",
) -> None:
    alice = attendee_row(
        attended="Yes",
        name="Alice Example",
        email="alice@example.com",
        city="London",
        country_code="GB",
        organization="Water Org",
        registration_time="01/01/2026 10:00:00 AM",
        approval_status="approved",
        join_time="01/23/2026 11:30:00 AM",
        leave_time="01/23/2026 12:00:00 PM",
        session_minutes="30",
        age="25 - 34 years",
        gender="Female",
        organisation_type="Utility",
        member="Yes",
        career_level="Middle",
        source="LinkedIn",
        country_name="United Kingdom",
    )
    alice_reconnection = attendee_row(
        attended="Yes",
        name="Alice Example",
        email="alice@example.com",
        city="",
        country_code="",
        organization="",
        registration_time="",
        approval_status="",
        join_time="01/23/2026 12:05:00 PM",
        leave_time="01/23/2026 12:20:00 PM",
        session_minutes="15",
        age="",
        gender="",
        organisation_type="",
        member="",
        career_level="",
        source="",
        country_name="United Kingdom",
    )
    notetaker = attendee_row(
        attended="Yes",
        name="Alice's Notetaker (Otter.ai)",
        email="bot@example.com",
        city="",
        country_code="",
        organization="",
        registration_time="",
        approval_status="",
        join_time="01/23/2026 11:40:00 AM",
        leave_time="01/23/2026 11:50:00 AM",
        session_minutes="10",
        age="",
        gender="",
        organisation_type="",
        member="",
        career_level="",
        source="",
        country_name="United Kingdom",
    )
    bob = attendee_row(
        attended="No",
        name="Bob Example",
        email="bob@example.com",
        city="Paris",
        country_code="FR",
        organization="Research Centre",
        registration_time="01/02/2026 10:00:00 AM",
        approval_status="approved",
        join_time="--",
        leave_time="--",
        session_minutes="--",
        age="35 - 44 years",
        gender="Male",
        organisation_type="Research Institute",
        member="No",
        career_level="Entry",
        source="IWA Website",
        country_name="France",
    )

    rows = [
        ["Attendee Report"],
        ["Report generated time", "01/30/2026 11:01:47 AM"],
        ["Topic", "Webinar ID", "Actual Start Time"],
        [webinar_name, webinar_id, "01/23/2026 11:30:00 AM"],
        ["Host Details"],
        ["Attendee Details"],
        SOURCE_COLUMNS,
        arrange_source_row(alice) + [""],
        arrange_source_row(alice_reconnection),
        arrange_source_row(notetaker),
        arrange_source_row(bob),
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        csv.writer(csv_file).writerows(rows)


def write_regions(path: Path) -> None:
    with path.open("w", encoding="cp1252", newline="") as csv_file:
        csv.writer(csv_file).writerows(
            [
                ["no.", "Country", "Region"],
                ["1", "United Kingdom", "Europe & Central Asia"],
                ["2", "France", "Europe & Central Asia"],
            ]
        )


def test_prepare_attendee_dataframe_removes_preamble_and_notetakers(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report (raw).csv"
    write_raw_report(report_path)

    dataframe = prepare_attendee_dataframe(report_path)

    assert len(dataframe) == 3
    assert dataframe["Email Address"].tolist() == [
        "alice@example.com", "alice@example.com", "bob@example.com"
    ]
    assert dataframe.loc[1, "City"] == "London"
    assert dataframe.loc[1, "Are you currently an IWA member?"] == "Yes"
    assert dataframe.columns.tolist() == SOURCE_COLUMNS + ["WebinarID"]
    assert dataframe["WebinarID"].unique().tolist() == ["123 456 789"]


def test_build_output_dataframes_reproduces_r_summary(tmp_path: Path) -> None:
    report_path = tmp_path / "report (raw).csv"
    regions_path = tmp_path / "Regions.csv"
    write_raw_report(report_path)
    write_regions(regions_path)
    attendees = prepare_attendee_dataframe(report_path)

    _, summary = build_output_dataframes(attendees, regions_path)

    assert summary.columns.tolist() == SUMMARY_COLUMNS
    assert summary.to_dict(orient="records") == [
        {
            "Email": "alice@example.com",
            "No. connections": 2,
            "Total time in session (mins)": 45,
            "Last leave time": "12:20:00",
            "Attended": "Attended",
            "IWA member?": "Member",
            "Age": "25 - 34 years",
            "Gender": "Female",
            "Country": "United Kingdom",
            "Region": "Europe & Central Asia",
            "Type of organisation": "Utility",
            "Career level": "Middle",
            "Source": "LinkedIn",
        },
        {
            "Email": "bob@example.com",
            "No. connections": 1,
            "Total time in session (mins)": 0,
            "Last leave time": "00:00:00",
            "Attended": "Did not attend",
            "IWA member?": "Non-member",
            "Age": "35 - 44 years",
            "Gender": "Male",
            "Country": "France",
            "Region": "Europe & Central Asia",
            "Type of organisation": "Research Institute",
            "Career level": "Entry",
            "Source": "IWA Website",
        },
    ]


def test_build_output_dataframes_cleans_times_and_no_show_values(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report (raw).csv"
    regions_path = tmp_path / "Regions.csv"
    write_raw_report(report_path)
    write_regions(regions_path)
    attendees = prepare_attendee_dataframe(report_path)

    clean, _ = build_output_dataframes(attendees, regions_path)

    assert clean["Joined At"].tolist() == ["11:30:00", "12:05:00", "00:00:00"]
    assert clean["Left At"].tolist() == ["12:00:00", "12:20:00", "00:00:00"]
    assert clean["Session Duration (minutes)"].tolist() == [30, 15, 0]


def test_process_webinar_report_writes_both_dataframes_to_one_workbook(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "Example Attendee report (raw).csv"
    regions_path = tmp_path / "Regions.csv"
    output_folder = tmp_path / "output"
    write_raw_report(report_path)
    write_regions(regions_path)

    output_path = default_output_path(report_path, output_folder)
    clean, summary = process_webinar_report(
        report_path,
        regions_path,
        output_path,
    )

    assert len(clean) == 3
    assert len(summary) == 2
    assert output_path.name == "Example Attendee report.xlsx"
    assert output_path.is_file()

    with pd.ExcelFile(output_path) as workbook:
        assert workbook.sheet_names == [CLEAN_SHEET_NAME, SUMMARY_SHEET_NAME]
        clean_sheet = pd.read_excel(workbook, sheet_name=CLEAN_SHEET_NAME)
        summary_sheet = pd.read_excel(workbook, sheet_name=SUMMARY_SHEET_NAME)

    assert clean_sheet.columns.tolist() == clean.columns.tolist()
    assert summary_sheet.columns.tolist() == SUMMARY_COLUMNS
    assert len(clean_sheet) == 3
    assert len(summary_sheet) == 2


def test_find_input_files_accepts_a_file_or_folder(tmp_path: Path) -> None:
    input_folder = tmp_path / "input"
    input_folder.mkdir()
    second_report = input_folder / "second.CSV"
    first_report = input_folder / "first.csv"
    first_report.touch()
    second_report.touch()
    (input_folder / "notes.txt").touch()

    assert find_input_files(first_report) == [first_report]
    assert find_input_files(input_folder) == [first_report, second_report]


def test_master_summary_rebuilds_all_generated_summaries_without_duplicates(
    tmp_path: Path,
) -> None:
    regions_path = tmp_path / "Regions.csv"
    output_folder = tmp_path / "output"
    write_regions(regions_path)

    reports = (
        ("01_23_Alpha Webinar_Attendee report (raw).csv", "Different Topic", "111"),
        ("04_16_Beta Webinar_Attendee report (raw).csv", "Another Topic", "222"),
    )
    for report_name, webinar_name, webinar_id in reports:
        report_path = tmp_path / report_name
        write_raw_report(report_path, webinar_name, webinar_id)
        process_webinar_report(
            report_path,
            regions_path,
            default_output_path(report_path, output_folder),
        )

    first_master = build_master_summary(output_folder)
    second_master = build_master_summary(output_folder)
    master_path = output_folder / MASTER_WORKBOOK_NAME

    assert first_master.columns.tolist() == MASTER_COLUMNS
    assert len(first_master) == 4
    assert len(second_master) == 4
    assert first_master["Webinar"].value_counts().to_dict() == {
        "01_23_Alpha Webinar": 2,
        "04_16_Beta Webinar": 2,
    }
    assert "WebinarID" not in first_master

    saved_master = pd.read_excel(master_path, sheet_name=MASTER_SHEET_NAME)
    assert len(saved_master) == 4
    assert saved_master.columns.tolist() == MASTER_COLUMNS


def test_webinar_name_is_derived_from_report_filename() -> None:
    assert webinar_name_from_filename(
        Path("04_16_AI in Water_Attendee report.xlsx")
    ) == "04_16_AI in Water"
    assert webinar_name_from_filename(
        Path("01_23_Cranfield University_Attendee Report.xlsx")
    ) == "01_23_Cranfield University"
    assert webinar_name_from_filename(
        Path("01_23_Cranfield University_Attendee report (clean).xlsx")
    ) == "01_23_Cranfield University"


def test_dataframe_footer_and_following_rows_are_removed() -> None:
    dataframe = pd.DataFrame(
        {
            "Email": [
                "included@example.com",
                "Other Attended",
                "excluded@example.com",
            ],
            "Attended": ["Attended", "", "Attended"],
        }
    )

    truncated = truncate_at_attendee_footer(dataframe)

    assert truncated["Email"].tolist() == ["included@example.com"]


def test_regions_csv_contains_valid_utf8_characters() -> None:
    regions_text = Path("webinar/Regions.csv").read_text(encoding="utf-8")

    assert "�" not in regions_text
    assert "C?te d'Ivoire" not in regions_text
    assert "Côte d'Ivoire" in regions_text
    assert "Curaçao" in regions_text
    assert "Türkiye" in regions_text


def test_sparse_report_does_not_require_fixed_source_columns(tmp_path: Path) -> None:
    report_path = tmp_path / "sparse report.csv"
    rows = [
        ["Attendee Report"],
        ["Topic", "Webinar ID"],
        ["Sparse Webinar", "987 654"],
        ["Attendee Details"],
        ["Contact", "Display label", "Custom response"],
        ["person@example.com", "Example Person", "One"],
        ["person@example.com", "Example Person", "Two"],
    ]
    with report_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        csv.writer(csv_file).writerows(rows)

    attendees = prepare_attendee_dataframe(report_path)
    clean, summary = build_output_dataframes(
        attendees,
        tmp_path / "unused-regions.csv",
    )

    assert clean.columns.tolist() == [
        "Contact",
        "Display label",
        "Custom response",
        "WebinarID",
    ]
    assert summary.loc[0, "Email"] == "person@example.com"
    assert summary.loc[0, "No. connections"] == 2
    assert summary.loc[0, "Total time in session (mins)"] == ""
    assert summary.loc[0, "Last leave time"] == ""
    assert summary.loc[0, "Country"] == ""


def test_unexpected_csv_fields_report_file_line_and_values(tmp_path: Path) -> None:
    report_path = tmp_path / "malformed report.csv"
    rows = [
        ["Attendee Report"],
        ["Topic", "Webinar ID"],
        ["Malformed Webinar", "123 987"],
        ["Attendee Details"],
        ["Email", "Display Name"],
        ["person@example.com", "Example Person", "unexpected value"],
    ]
    with report_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        csv.writer(csv_file).writerows(rows)

    try:
        prepare_attendee_dataframe(report_path)
    except ValueError as error:
        message = str(error)
        assert str(report_path) in message
        assert "CSV line 6" in message
        assert "3 fields" in message
        assert "header has 2" in message
        assert "unexpected value" in message
        assert "{line_number}" not in message
    else:
        raise AssertionError("Expected malformed attendee data to be rejected")


def test_unquoted_comma_in_final_country_name_is_rejoined(tmp_path: Path) -> None:
    report_path = tmp_path / "country comma.csv"
    report_path.write_text(
        "Attendee Report\n"
        "Topic,Webinar ID\n"
        "Country Test,555 123\n"
        "Attendee Details\n"
        "Email,Country Name\n"
        "person@example.com,Congo, Democratic Republic of the\n",
        encoding="utf-8-sig",
    )

    attendees = prepare_attendee_dataframe(report_path)

    assert attendees.loc[0, "Country Name"] == "Congo, Democratic Republic of the"


def test_other_attended_footer_and_following_rows_are_removed(tmp_path: Path) -> None:
    report_path = tmp_path / "footer report.csv"
    rows = [
        ["Attendee Report"],
        ["Topic", "Webinar ID"],
        ["Footer Webinar", "789 123"],
        ["Attendee Details"],
        ["Email", "Display Name"],
        ["included@example.com", "Included Person"],
        ["Other Attended"],
        ["excluded@example.com", "Excluded Person"],
    ]
    with report_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        csv.writer(csv_file).writerows(rows)

    attendees = prepare_attendee_dataframe(report_path)
    _, summary = build_output_dataframes(
        attendees,
        tmp_path / "unused-regions.csv",
    )

    assert attendees["Email"].tolist() == ["included@example.com"]
    assert summary["Email"].tolist() == ["included@example.com"]


def test_prepare_attendee_dataframe_requires_attendee_section(tmp_path: Path) -> None:
    report_path = tmp_path / "invalid.csv"
    report_path.write_text("Topic,Webinar ID\nExample,123\n", encoding="utf-8")

    try:
        prepare_attendee_dataframe(report_path)
    except ValueError as error:
        assert "Attendee Details" in str(error)
    else:
        raise AssertionError("Expected the missing attendee section to be rejected")
