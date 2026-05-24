import os
import json
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, jsonify, request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')

SPREADSHEET_ID = '1u3eVEQMuA_HPEhUjm2Nah3VdhO-dQ-EmlBm6Zmjhc-k'
SHEET_NAME = 'Sheet1'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Column indices (0-based)
COL_DATE = 0
COL_DAY = 1
COL_PHASE = 2
COL_TYPE = 3
COL_DESC = 4
COL_PLAN_DIST = 5
COL_PLAN_ELEV = 6
COL_ACT_DIST = 7
COL_ACT_ELEV = 8
COL_ACT_TIME = 9
COL_NOTES = 10


def get_service():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if creds_json:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = service_account.Credentials.from_service_account_file(
            'credentials.json', scopes=SCOPES
        )
    return build('sheets', 'v4', credentials=creds)


def get_all_rows():
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f'{SHEET_NAME}!A2:K500'
    ).execute()
    return result.get('values', [])


def row_to_dict(row, row_index):
    while len(row) < 11:
        row.append('')
    return {
        'row_index': row_index,
        'date': row[COL_DATE],
        'day': row[COL_DAY],
        'phase': row[COL_PHASE],
        'workout_type': row[COL_TYPE],
        'description': row[COL_DESC],
        'planned_distance': row[COL_PLAN_DIST],
        'planned_elev': row[COL_PLAN_ELEV],
        'actual_distance': row[COL_ACT_DIST],
        'actual_elev': row[COL_ACT_ELEV],
        'actual_time': row[COL_ACT_TIME],
        'notes': row[COL_NOTES],
    }


def today_iso():
    return datetime.now().strftime('%Y-%m-%d')


def week_iso_range():
    today = datetime.now()
    return [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]


# ── Routes ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/today')
def api_today():
    target = today_iso()
    rows = get_all_rows()
    for i, row in enumerate(rows):
        if row and row[0].strip() == target:
            return jsonify({'workout': row_to_dict(row, i + 2)})
    return jsonify({'error': 'No workout found for today', 'date': target}), 404


@app.route('/api/week')
def api_week():
    dates = set(week_iso_range())
    rows = get_all_rows()
    week = []
    for i, row in enumerate(rows):
        if row and row[0].strip() in dates:
            week.append(row_to_dict(row, i + 2))
    week.sort(key=lambda r: r['date'])
    return jsonify(week)


@app.route('/api/workout/<date>')
def api_workout(date):
    rows = get_all_rows()
    for i, row in enumerate(rows):
        if row and row[0].strip() == date:
            return jsonify({'workout': row_to_dict(row, i + 2)})
    return jsonify({'error': f'No workout for {date}'}), 404


@app.route('/api/log', methods=['POST'])
def api_log():
    data = request.json
    row_index = data.get('row_index')
    if not row_index:
        return jsonify({'error': 'row_index required'}), 400

    actual_dist = str(data.get('actual_distance', ''))
    actual_elev = str(data.get('actual_elev', ''))
    actual_time = str(data.get('actual_time', ''))
    notes = str(data.get('notes', ''))

    service = get_service()
    range_notation = f'{SHEET_NAME}!H{row_index}:K{row_index}'
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_notation,
        valueInputOption='USER_ENTERED',
        body={'values': [[actual_dist, actual_elev, actual_time, notes]]}
    ).execute()

    return jsonify({'status': 'ok', 'row': row_index})


if __name__ == '__main__':
    app.run(debug=True, port=5001)
