"""Zoom column aliases, report markers, and workbook fields."""
from .config import WEBINAR_FOLDER

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
INPUT_FOLDER = WEBINAR_FOLDER / "input"
OUTPUT_FOLDER = WEBINAR_FOLDER / "output"
REGIONS_FILE = WEBINAR_FOLDER / "Regions.csv"
CLEAN_SHEET_NAME = "Cleaned data"
SUMMARY_SHEET_NAME = "Summary"
MASTER_SHEET_NAME = "Master summary"
MASTER_WORKBOOK_NAME = "master_webinar_summary.xlsx"
COMPACT_ATTENDEE_HEADER_ROLES = {
    "email",
    "join_time",
    "leave_time",
    "session_minutes",
}

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
