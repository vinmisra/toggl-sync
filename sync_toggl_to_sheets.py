import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
from datetime import datetime, timedelta, timezone

# Config
TOGGL_API_TOKEN = os.environ.get("TOGGL_API_TOKEN")
PROJECTS = {"TrueWork": 210645944, "Entertainment": 211402336}
GOOGLE_SHEET_NAME = "TogglLog"

# Auth with Google Sheets
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
client = gspread.authorize(creds)
sheet = client.open(GOOGLE_SHEET_NAME).sheet1

# Existing Toggl IDs
existing_ids = set(sheet.col_values(1))  # First column

# Fetch Toggl time entries from the past 7 days
seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
since_iso = seven_days_ago.isoformat()
url = f"https://api.track.toggl.com/api/v9/me/time_entries?start_date={since_iso}"
res = requests.get(url, auth=(TOGGL_API_TOKEN, "api_token"))
entries = res.json()

# Process and append new entries
id_to_name = {v: k for k, v in PROJECTS.items()}
for entry in entries:
    pid = entry.get("project_id")
    if pid in id_to_name and str(entry["id"]) not in existing_ids:
        row = [
            str(entry["id"]),
            entry.get("description", ""),
            entry.get("start", ""),
            entry.get("stop", ""),
            round(entry.get("duration", 0) / 60, 2),
            id_to_name[pid],
        ]
        sheet.append_row(row)
