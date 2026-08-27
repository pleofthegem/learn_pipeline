"""Prepare and summarise a Zoom webinar attendee report."""

import argparse
import csv
import re
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

ATTENDEE_MARKER = "Attendee Details"
CSV_ENCODINGS = ("utf-8-sig", "cp1252")
DATE_TIME_FORMAT = "%m/%d/%Y %I:%M:%S %p"
NOTETAKER_NAMES = ("Otter.ai", "Fireflies.ai", "Notetaker")
ATTENDEE_FOOTER_MARKERS = {
    "other attended",
    "other attendeed",
    "other attendee",
    "other attendees",
}
WEBINAR_FOLDER = Path(__file__).resolve().parent
INPUT_FOLDER = WEBINAR_FOLDER / "input"
OUTPUT_FOLDER = WEBINAR_FOLDER / "output"
REGIONS_FILE = WEBINAR_FOLDER / "Regions.csv"
CLEAN_SHEET_NAME = "Cleaned data"
SUMMARY_SHEET_NAME = "Summary"
MASTER_SHEET_NAME = "Master summary"
MASTER_WORKBOOK_NAME = "master_webinar_summary.xlsx"

ROLE_ALIASES = {
    "attended": ("attended", "attendance status"),
    "user_name": ("user name", "user name original name"),
    "first_name": ("first name",),
    "last_name": ("last name",),
    "email": ("email", "email address"),
    "city": ("city",),
    "country_region": ("country region", "country code"),
    "organization": ("organization", "organisation"),
    "registration_time": ("registration time", "registered at"),
    "approval_status": ("approval status",),
    "join_time": ("join time", "joined at", "join date time"),
    "leave_time": ("leave time", "left at", "leave date time"),
    "session_minutes": (
        "time in session minutes",
        "session duration minutes",
        "duration minutes",
    ),
    "is_guest": ("is guest", "guest"),
    "age": ("age",),
    "gender": ("gender",),
    "type_of_organisation": (
        "type of organisation",
        "type of organization",
        "organisation type",
        "organization type",
    ),
    "member": ("iwa member",),
    "career_level": ("career level",),
    "source": ("source",),
    "consent": ("consent",),
    "country_name": (
        "country region name",
        "country name",
        "full country name",
    ),
}

ROLE_TOKEN_ALTERNATIVES = {
    "age": (("age",),),
    "gender": (("gender",),),
    "type_of_organisation": (
        ("type", "organisation"),
        ("type", "organization"),
    ),
    "member": (("iwa", "member"),),
    "career_level": (("career", "level"),),
    "source": (("hear",),),
    "consent": (("consent",), ("agree", "contacted")),
}

CONNECTION_SPECIFIC_ROLES = (
    "attended",
    "user_name",
    "first_name",
    "last_name",
    "email",
    "join_time",
    "leave_time",
    "session_minutes",
    "is_guest",
    "country_name",
)

SUMMARY_COLUMNS = [
    "Email",
    "No. connections",
    "Total time in session (mins)",
    "Last leave time",
    "Attended",
    "IWA member?",
    "Age",
    "Gender",
    "Country",
    "Region",
    "Type of organisation",
    "Career level",
    "Source",
]

MASTER_COLUMNS = ["Webinar", *SUMMARY_COLUMNS]

def read_csv_rows(path: Path) -> list[list[str]]:
    """Read CSV rows, accepting Zoom's UTF-8 files and the legacy region file."""
    for encoding in CSV_ENCODINGS:
        try:
            with path.open(encoding=encoding, newline="") as csv_file:
                return list(csv.reader(csv_file))
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Could not decode CSV file: {path}")


def find_attendee_section(rows: list[list[str]]) -> int:
    """Return the index of the attendee column header."""
    for index, row in enumerate(rows):
        if any(value.strip() == ATTENDEE_MARKER for value in row):
            header_index = index + 1
            if header_index >= len(rows):
                break
            return header_index

    raise ValueError(f"Could not find the '{ATTENDEE_MARKER}' section")


def extract_report_value(rows: list[list[str]], field_name: str) -> str:
    """Extract a named value from the report preamble."""
    normalised_field_name = normalise_column_name(field_name)
    for index, row in enumerate(rows[:-1]):
        labels = [normalise_column_name(value) for value in row]
        if normalised_field_name not in labels:
            continue

        value_index = labels.index(normalised_field_name)
        values = rows[index + 1]
        if value_index < len(values):
            return values[value_index].strip()

    raise ValueError(f"Could not find '{field_name}' in the report preamble")


def normalise_column_name(column_name: str) -> str:
    """Normalise a source heading for order-independent matching."""
    return re.sub(r"[^a-z0-9]+", " ", column_name.casefold()).strip()


def is_attendee_footer(values: Iterable[object]) -> bool:
    """Return whether a row is a standalone attendee footer marker."""
    labels = [
        normalise_column_name(str(value))
        for value in values
        if pd.notna(value) and str(value).strip()
    ]
    return len(labels) == 1 and labels[0] in ATTENDEE_FOOTER_MARKERS


def truncate_at_attendee_footer(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Remove an attendee footer and every dataframe row beneath it."""
    for position, row in enumerate(dataframe.itertuples(index=False, name=None)):
        if is_attendee_footer(row):
            return dataframe.iloc[:position].copy()
    return dataframe


def resolve_attendee_columns(columns: Iterable[str]) -> dict[str, str]:
    """Map source headings to the fields used by the transformations."""
    source_columns = list(columns)
    normalised_columns = {
        column: normalise_column_name(column) for column in source_columns
    }
    resolved: dict[str, str] = {}

    for role, aliases in ROLE_ALIASES.items():
        for column, normalised in normalised_columns.items():
            if normalised in aliases:
                resolved[role] = column
                break
        else:
            alternatives = ROLE_TOKEN_ALTERNATIVES.get(role, ())
            for column, normalised in normalised_columns.items():
                words = set(normalised.split())
                if any(set(tokens).issubset(words) for tokens in alternatives):
                    resolved[role] = column
                    break

    return resolved


def attendee_rows_to_dataframe(
    rows: list[list[str]],
    header_index: int,
    input_path: Path,
) -> pd.DataFrame:
    """Build the attendee dataframe and discard harmless trailing CSV fields."""
    source_header = [value.strip() for value in rows[header_index]]
    while source_header and not source_header[-1]:
        source_header.pop()
    if not source_header or any(not column for column in source_header):
        raise ValueError("Attendee column headings cannot be empty")
    if len(source_header) != len(set(source_header)):
        raise ValueError("Attendee column headings must be unique")
    resolved_columns = resolve_attendee_columns(source_header)
    country_column = resolved_columns.get("country_name")
    country_is_last = (
        country_column is not None and source_header[-1] == country_column
    )

    attendee_rows: list[list[str]] = []
    for line_number, row in enumerate(rows[header_index + 1 :], header_index + 2):
        if is_attendee_footer(row):
            break
        if not any(value.strip() for value in row):
            continue

        if len(row) > len(source_header) and country_is_last:
            country_parts = row[len(source_header) - 1 :]
            while country_parts and not country_parts[-1].strip():
                country_parts.pop()
            row = row[: len(source_header) - 1] + [
                ",".join(country_parts).strip()
            ]

        if len(row) > len(source_header):
            extra_values = row[len(source_header) :]
            if any(value.strip() for value in extra_values):
                raise ValueError(
                    f"{input_path}: CSV line {line_number} has {len(row)} fields, "
                    f"but the attendee header has {len(source_header)}. "
                    f"Unexpected trailing values: {extra_values!r}"
                )
            row = row[: len(source_header)]

        attendee_rows.append(row + [""] * (len(source_header) - len(row)))

    dataframe = pd.DataFrame(attendee_rows, columns=source_header, dtype="string")
    return dataframe


def remove_notetakers(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Remove rows containing known automated notetaker names."""
    pattern = "|".join(re.escape(name) for name in NOTETAKER_NAMES)
    notetaker_cells = dataframe.apply(
        lambda column: column.astype("string").str.contains(
            pattern, case=False, na=False
        )
    )
    return dataframe.loc[~notetaker_cells.any(axis=1)].copy()


def prepare_attendee_dataframe(input_path: Path) -> pd.DataFrame:
    """Remove the report preamble and apply the PowerShell cleanup steps."""
    rows = read_csv_rows(input_path)
    header_index = find_attendee_section(rows)
    dataframe = attendee_rows_to_dataframe(rows, header_index, input_path)
    columns = resolve_attendee_columns(dataframe.columns)

    dataframe["WebinarID"] = extract_report_value(rows, "Webinar ID")
    connection_columns = {
        columns[role]
        for role in CONNECTION_SPECIFIC_ROLES
        if role in columns
    }
    forward_fill_columns = [
        column
        for column in dataframe.columns
        if column not in connection_columns
        and column != "WebinarID"
    ]
    dataframe[forward_fill_columns] = (
        dataframe[forward_fill_columns]
        .replace(r"^\s*$", pd.NA, regex=True)
        .ffill()
    )
    dataframe = remove_notetakers(dataframe)

    return dataframe.reset_index(drop=True)


def find_email_column(
    dataframe: pd.DataFrame,
    resolved_columns: dict[str, str],
) -> str:
    """Find the email field by heading or, as a fallback, by its values."""
    if "email" in resolved_columns:
        return resolved_columns["email"]

    email_counts = {
        column: dataframe[column]
        .astype("string")
        .str.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", na=False)
        .sum()
        for column in dataframe.columns
    }
    email_column, matches = max(email_counts.items(), key=lambda item: item[1])
    if matches == 0:
        raise ValueError("Could not identify an email column from headings or values")
    return email_column


def build_output_dataframes(
    attendee_dataframe: pd.DataFrame,
    regions_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the cleaned connections and one-row-per-email summary."""
    dataframe = attendee_dataframe.copy()
    columns = resolve_attendee_columns(dataframe.columns)
    email_column = find_email_column(dataframe, columns)

    session_minutes_column = columns.get("session_minutes")
    if session_minutes_column:
        dataframe[session_minutes_column] = pd.to_numeric(
            dataframe[session_minutes_column].replace("--", "0"),
            errors="coerce",
        ).fillna(0).astype("int64")
    for role in ("join_time", "leave_time"):
        column = columns.get(role)
        if not column:
            continue
        dataframe[column] = pd.to_datetime(
            dataframe[column].replace("--", pd.NA),
            format=DATE_TIME_FORMAT,
            errors="coerce",
        )

    aggregations: dict[str, tuple[str, str]] = {
        "No. connections": (email_column, "size"),
    }
    if session_minutes_column:
        aggregations["Total time in session (mins)"] = (
            session_minutes_column,
            "sum",
        )
    if "leave_time" in columns:
        aggregations["Last leave time"] = (columns["leave_time"], "max")

    first_value_roles = {
        "Attended": "attended",
        "IWA member?": "member",
        "Age": "age",
        "Gender": "gender",
        "Country": "country_name",
        "Type of organisation": "type_of_organisation",
        "Career level": "career_level",
        "Source": "source",
    }
    for output_column, role in first_value_roles.items():
        if role in columns:
            aggregations[output_column] = (columns[role], "first")

    summary = dataframe.groupby(
        email_column, sort=False, dropna=False
    ).agg(**aggregations)
    summary.index.name = "Email"
    summary = summary.reset_index()
    if "Last leave time" in summary:
        summary["Last leave time"] = (
            summary["Last leave time"]
            .dt.strftime("%H:%M:%S")
            .fillna("00:00:00")
        )
    for output_column in SUMMARY_COLUMNS:
        if output_column not in summary:
            summary[output_column] = ""
    summary["Attended"] = summary["Attended"].replace(
        {"Yes": "Attended", "No": "Did not attend"}
    )
    summary["IWA member?"] = summary["IWA member?"].replace(
        {"Yes": "Member", "No": "Non-member"}
    )

    if "country_name" in columns:
        region_rows = read_csv_rows(regions_path)
        if not region_rows or not {"Country", "Region"}.issubset(region_rows[0]):
            raise ValueError("Regions CSV must contain Country and Region columns")
        regions = pd.DataFrame(region_rows[1:], columns=region_rows[0], dtype="string")
        region_by_country = (
            regions.drop_duplicates(subset="Country", keep="first")
            .set_index("Country")["Region"]
        )
        summary["Region"] = summary["Country"].map(region_by_country)

    summary["No. connections"] = summary["No. connections"].astype("int64")
    if session_minutes_column:
        summary["Total time in session (mins)"] = summary[
            "Total time in session (mins)"
        ].astype("int64")
    summary = summary[SUMMARY_COLUMNS].fillna("")
    summary = truncate_at_attendee_footer(summary)

    clean = dataframe.copy()
    for role in ("join_time", "leave_time"):
        column = columns.get(role)
        if not column:
            continue
        clean[column] = (
            clean[column].dt.strftime("%H:%M:%S").fillna("00:00:00")
        )

    return clean.fillna(""), summary


def default_output_path(
    input_path: Path,
    output_folder: Path = OUTPUT_FOLDER,
) -> Path:
    """Return the workbook path for an input report."""
    raw_suffix = re.compile(r"\s*\(raw\)$", flags=re.IGNORECASE)
    base_stem = raw_suffix.sub("", input_path.stem)
    return output_folder / f"{base_stem}.xlsx"


def webinar_name_from_filename(workbook_path: Path) -> str:
    """Remove the attendee-report marker and everything after it."""
    name = workbook_path.stem
    marker_index = name.casefold().find("attendee report")
    if marker_index != -1:
        name = name[:marker_index]
    return name.rstrip(" _-")


def process_webinar_report(
    input_path: Path,
    regions_path: Path,
    output_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the complete webinar cleanup and summary pipeline."""
    output_path = output_path or default_output_path(input_path)

    attendees = prepare_attendee_dataframe(input_path)
    clean, summary = build_output_dataframes(attendees, regions_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as workbook:
        clean.to_excel(workbook, sheet_name=CLEAN_SHEET_NAME, index=False)
        summary.to_excel(workbook, sheet_name=SUMMARY_SHEET_NAME, index=False)

    return clean, summary


def build_master_summary(
    output_folder: Path = OUTPUT_FOLDER,
    master_path: Path | None = None,
) -> pd.DataFrame:
    """Rebuild one master table from every generated webinar summary."""
    master_path = master_path or output_folder / MASTER_WORKBOOK_NAME
    summaries: list[pd.DataFrame] = []

    for workbook_path in sorted(output_folder.glob("*.xlsx")):
        if workbook_path.resolve() == master_path.resolve():
            continue

        with pd.ExcelFile(workbook_path) as workbook:
            required_sheets = {CLEAN_SHEET_NAME, SUMMARY_SHEET_NAME}
            if not required_sheets.issubset(workbook.sheet_names):
                continue

            summary = pd.read_excel(
                workbook,
                sheet_name=SUMMARY_SHEET_NAME,
                keep_default_na=False,
            )
            summary = truncate_at_attendee_footer(summary).reindex(
                columns=SUMMARY_COLUMNS,
                fill_value="",
            )

        summary.insert(0, "Webinar", webinar_name_from_filename(workbook_path))
        summaries.append(summary)

    master = (
        pd.concat(summaries, ignore_index=True)
        if summaries
        else pd.DataFrame(columns=MASTER_COLUMNS)
    )
    master = master.reindex(columns=MASTER_COLUMNS, fill_value="")

    master_path.parent.mkdir(parents=True, exist_ok=True)
    master.to_excel(master_path, sheet_name=MASTER_SHEET_NAME, index=False)
    return master


def find_input_files(input_path: Path) -> list[Path]:
    """Return one CSV input or every CSV directly inside an input folder."""
    if input_path.is_file():
        if input_path.suffix.casefold() != ".csv":
            raise ValueError(f"Webinar input must be a CSV file: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f"Webinar input does not exist: {input_path}")

    input_files = sorted(
        path
        for path in input_path.iterdir()
        if path.is_file() and path.suffix.casefold() == ".csv"
    )
    if not input_files:
        raise ValueError(f"No CSV files found in webinar input folder: {input_path}")
    return input_files


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Clean and summarise a Zoom webinar attendee report."
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        default=INPUT_FOLDER,
        help="Raw Zoom attendee CSV or folder (default: webinar/input)",
    )
    parser.add_argument(
        "--regions",
        type=Path,
        default=REGIONS_FILE,
        help="CSV mapping Country to Region (default: webinar/Regions.csv)",
    )
    parser.add_argument(
        "--output-folder",
        type=Path,
        default=OUTPUT_FOLDER,
        help="Folder for processed workbooks (default: webinar/output)",
    )
    return parser.parse_args()


def main() -> None:
    """Run the webinar report pipeline from the command line."""
    args = parse_args()
    input_files = find_input_files(args.input_path)

    for input_file in input_files:
        output_path = default_output_path(input_file, args.output_folder)
        clean, summary = process_webinar_report(
            input_path=input_file,
            regions_path=args.regions,
            output_path=output_path,
        )
        print(
            f"Wrote {output_path} with {len(clean)} cleaned rows and "
            f"{len(summary)} summary rows."
        )
        missing_regions = summary.loc[
            summary["Country"].ne("") & summary["Region"].eq(""), "Country"
        ].drop_duplicates()
        if not missing_regions.empty:
            print(
                "No region mapping found for: "
                + ", ".join(sorted(missing_regions.tolist()))
            )

    master_path = args.output_folder / MASTER_WORKBOOK_NAME
    master = build_master_summary(args.output_folder, master_path)
    print(f"Wrote {master_path} with {len(master)} accumulated summary rows.")


if __name__ == "__main__":
    main()
