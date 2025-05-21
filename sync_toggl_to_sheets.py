import requests
import base64
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load .env if it exists (local dev)
if os.path.exists(".env"):
    load_dotenv()

# Config
TOGGL_API_TOKEN = os.environ.get("TOGGL_API_TOKEN")
GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

PROJECTS = {"TrueWork": 210645944, "Entertainment": 211402336}
GOOGLE_SHEET_KEY = "1LnXyqlzjRm6BEejWdGb3y66FgZD2GmaMmfNmYdDW-dU"
WORKSHEET_NAME = "TogglLog"
USER_AGENT = os.environ.get("USER_AGENT", "physicsdemon@gmail.com")


# Auth with Google Sheets
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

if GOOGLE_CREDENTIALS_PATH and os.path.exists(GOOGLE_CREDENTIALS_PATH):
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        GOOGLE_CREDENTIALS_PATH, scope
    )
elif GOOGLE_CREDENTIALS_JSON:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        json.loads(GOOGLE_CREDENTIALS_JSON), scope
    )
else:
    raise RuntimeError(
        "No Google credentials found. Set GOOGLE_CREDENTIALS_PATH or GOOGLE_CREDENTIALS_JSON."
    )

client = gspread.authorize(creds)
sheet = client.open_by_key(GOOGLE_SHEET_KEY).worksheet(WORKSHEET_NAME)

# Existing Toggl IDs - read once from column A before processing new entries
existing_ids = set(sheet.col_values(1))  # Assumes column A is for Toggl IDs

# — Build the Basic Auth header explicitly
token_pair = f"{TOGGL_API_TOKEN}:api_token".encode("utf-8")
auth_header = base64.b64encode(token_pair).decode("ascii")
headers = {
    "Authorization": f"Basic {auth_header}",
    "User-Agent": USER_AGENT,
    "Content-Type": "application/json",
}

# — Fetch only the past 7 days
since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
until = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
url = f"https://api.track.toggl.com/api/v9/me/time_entries?start_date={since}&end_date={until}"

resp = requests.get(url, headers=headers)
if resp.status_code == 401:
    raise RuntimeError(f"Toggl auth failed: {resp.status_code} {resp.text}")

entries = resp.json()
# The redundant existing_ids retrieval that was here has been removed.

# — Append new entries
id_to_name = {v: k for k, v in PROJECTS.items()}

# Determine the starting row for new entries.
# len(sheet.get_all_values()) + 1 is the standard way to find the next available row.
all_sheet_data = sheet.get_all_values()
next_row_to_write = len(all_sheet_data) + 1


# Helper function to format datetime strings for Google Sheets
def format_datetime_for_gsheets(iso_datetime_str: str) -> str:
    if not iso_datetime_str:
        return ""
    try:
        # Replace 'Z' with '+00:00' for consistent parsing by fromisoformat
        if iso_datetime_str.endswith("Z"):
            iso_datetime_str = iso_datetime_str[:-1] + "+00:00"
        dt_obj = datetime.fromisoformat(iso_datetime_str)
        return dt_obj.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        # If parsing fails for any reason, return the original string or an empty one
        return iso_datetime_str  # Or consider returning "" if preferred for errors


for e in entries:
    if e["project_id"] in id_to_name and str(e["id"]) not in existing_ids:
        start_time_str = format_datetime_for_gsheets(e.get("start"))
        stop_time_str = format_datetime_for_gsheets(e.get("stop"))

        row_data = [
            str(e["id"]),
            e.get("description", ""),
            start_time_str,
            stop_time_str,
            round(e.get("duration", 0) / 60, 2),
            id_to_name[e["project_id"]],
        ]
        # Update cells directly, ensuring data starts in column A
        # Using named arguments for update() to resolve deprecation warning and improve clarity.
        # Adding value_input_option='USER_ENTERED' to help Google Sheets parse dates.
        sheet.update(
            range_name=f"A{next_row_to_write}:F{next_row_to_write}",
            values=[row_data],
            value_input_option="USER_ENTERED",
        )

        # Add to existing_ids for the current run to prevent duplicates if API returns same ID multiple times
        existing_ids.add(str(e["id"]))
        next_row_to_write += (
            1  # Move to the next row for the next potential entry in this run
        )
