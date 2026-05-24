"""
One-time script to populate the Google Sheet from Bars_Training_Plan.md.
Run once after setting up credentials.

Usage:
    python3 populate_sheet.py
    python3 populate_sheet.py --dry-run   # preview rows without writing
"""

import re
import sys
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SPREADSHEET_ID = '1u3eVEQMuA_HPEhUjm2Nah3VdhO-dQ-EmlBm6Zmjhc-k'
SHEET_NAME = 'Sheet1'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
PLAN_FILE = '../Bars_Training_Plan.md'

HEADERS = [
    'Date', 'Day', 'Phase', 'Workout Type', 'Description',
    'Planned Distance', 'Planned Elev (ft)',
    'Actual Distance', 'Actual Elev (ft)', 'Actual Time (mins)', 'Notes/Feel'
]


def get_service():
    import json
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if creds_json:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = service_account.Credentials.from_service_account_file(
            'credentials.json', scopes=SCOPES
        )
    return build('sheets', 'v4', credentials=creds)


def parse_date(raw):
    """Convert 'May 25', 'Jun 1', '**Aug 21**' etc. to '2026-MM-DD'."""
    raw = raw.strip().replace('**', '').strip()
    for fmt in ('%b %d', '%B %d'):
        try:
            dt = datetime.strptime(f'{raw} 2026', f'{fmt} %Y')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return raw  # fallback: return as-is


def parse_plan(filepath):
    rows = []
    current_phase = ''

    with open(filepath, 'r') as f:
        content = f.read()

    # Extract phase from section headers like "## Phase 1 — Foundation"
    phase_pattern = re.compile(r'^## Phase \d+ — (.+)', re.MULTILINE)

    # Split content by phase sections
    sections = re.split(r'(?=^## Phase)', content, flags=re.MULTILINE)

    for section in sections:
        # Get phase name from section header
        phase_match = phase_pattern.search(section)
        if phase_match:
            current_phase = phase_match.group(1).split('(')[0].strip()

        # Find all table rows (lines starting with |)
        lines = section.split('\n')
        for line in lines:
            if not line.startswith('|'):
                continue
            # Skip header rows and separator rows
            if '---' in line or 'Date' in line or 'Workout Type' in line:
                continue

            cols = [c.strip() for c in line.split('|')]
            cols = [c for c in cols if c != '']  # remove empty edge splits

            if len(cols) < 6:
                continue

            # cols[0] = Date, cols[1] = Day, cols[2] = Phase,
            # cols[3] = Workout Type, cols[4] = Description,
            # cols[5] = Planned Distance, cols[6] = Planned Elev
            # cols[7-10] = actuals (empty)

            raw_date = cols[0]
            if not raw_date or raw_date in ('—', '-'):
                continue

            date_iso = parse_date(raw_date)

            row = [
                date_iso,
                cols[1] if len(cols) > 1 else '',
                cols[2] if len(cols) > 2 else current_phase,
                cols[3] if len(cols) > 3 else '',
                cols[4] if len(cols) > 4 else '',
                cols[5] if len(cols) > 5 else '',
                cols[6] if len(cols) > 6 else '',
                '',  # actual distance
                '',  # actual elev
                '',  # actual time
                '',  # notes
            ]
            rows.append(row)

    return rows


def clear_sheet(service):
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f'{SHEET_NAME}!A1:K500'
    ).execute()


def write_to_sheet(service, rows):
    all_values = [HEADERS] + rows
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f'{SHEET_NAME}!A1',
        valueInputOption='USER_ENTERED',
        body={'values': all_values}
    ).execute()

    # Bold + freeze header row
    sheet_id = get_sheet_id(service)
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={
            'requests': [
                {
                    'repeatCell': {
                        'range': {'sheetId': sheet_id, 'startRowIndex': 0, 'endRowIndex': 1},
                        'cell': {'userEnteredFormat': {'textFormat': {'bold': True}}},
                        'fields': 'userEnteredFormat.textFormat.bold'
                    }
                },
                {
                    'updateSheetProperties': {
                        'properties': {'sheetId': sheet_id, 'gridProperties': {'frozenRowCount': 1}},
                        'fields': 'gridProperties.frozenRowCount'
                    }
                }
            ]
        }
    ).execute()


def get_sheet_id(service):
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta['sheets']:
        if s['properties']['title'] == SHEET_NAME:
            return s['properties']['sheetId']
    return 0


def main():
    dry_run = '--dry-run' in sys.argv

    print(f'Parsing {PLAN_FILE}...')
    plan_path = os.path.join(os.path.dirname(__file__), PLAN_FILE)
    rows = parse_plan(plan_path)
    print(f'Found {len(rows)} workout rows.')

    for r in rows[:5]:
        print(f'  {r[0]} | {r[1]} | {r[3]} | {r[5]}')
    if len(rows) > 5:
        print(f'  ... and {len(rows) - 5} more')

    if dry_run:
        print('\n[DRY RUN] No changes written.')
        return

    print(f'\nWriting to sheet {SPREADSHEET_ID}...')
    service = get_service()
    clear_sheet(service)
    write_to_sheet(service, rows)
    print(f'Done. {len(rows)} rows written + header.')
    print(f'\nOpen: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}')


if __name__ == '__main__':
    main()
