import csv
from pathlib import Path

import pandas as pd

from webinar.process_webinar_report import (
    CLEAN_SHEET_NAME,
    SUMMARY_COLUMNS,
    SUMMARY_SHEET_NAME,
    build_output_dataframes,
    default_output_path,
    find_input_files,
    prepare_attendee_dataframe,
    process_webinar_report,
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


def write_raw_report(path: Path) -> None:
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
        ["Test Webinar", "123 456 789", "01/23/2026 11:30:00 AM"],
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
        "Contact", "Display label", "Custom response", "WebinarID"
    ]
    assert summary.loc[0, "Email"] == "person@example.com"
    assert summary.loc[0, "No. connections"] == 2
    assert summary.loc[0, "Total time in session (mins)"] == ""
    assert summary.loc[0, "Last leave time"] == ""
    assert summary.loc[0, "Country"] == ""


def test_prepare_attendee_dataframe_requires_attendee_section(tmp_path: Path) -> None:
    report_path = tmp_path / "invalid.csv"
    report_path.write_text("Topic,Webinar ID\nExample,123\n", encoding="utf-8")

    try:
        prepare_attendee_dataframe(report_path)
    except ValueError as error:
        assert "Attendee Details" in str(error)
    else:
        raise AssertionError("Expected the missing attendee section to be rejected")
