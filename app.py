import os
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, send_from_directory, jsonify, request, session
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
app.permanent_session_lifetime = timedelta(days=30)

APP_PIN = os.environ.get('APP_PIN', '')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not APP_PIN:          # no PIN configured → open access
            return f(*args, **kwargs)
        if not session.get('authenticated'):
            return jsonify({'error': 'unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

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


@app.route('/api/auth', methods=['POST'])
def api_auth():
    if not APP_PIN:
        return jsonify({'status': 'ok'})
    data = request.json or {}
    if str(data.get('pin', '')).strip() == str(APP_PIN).strip():
        session.permanent = True
        session['authenticated'] = True
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'wrong pin'}), 401


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'status': 'ok'})


@app.route('/api/today')
@login_required
def api_today():
    # Client passes its local date to avoid server UTC timezone mismatch
    target = request.args.get('date') or today_iso()
    rows = get_all_rows()
    for i, row in enumerate(rows):
        if row and row[0].strip() == target:
            return jsonify({'workout': row_to_dict(row, i + 2)})
    return jsonify({'error': 'No workout found for today', 'date': target}), 404


@app.route('/api/week')
@login_required
def api_week():
    # Client passes its local date anchor to avoid UTC mismatch
    anchor = request.args.get('date')
    if anchor:
        today = datetime.strptime(anchor, '%Y-%m-%d')
        dates = set([(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)])
    else:
        dates = set(week_iso_range())
    rows = get_all_rows()
    week = []
    for i, row in enumerate(rows):
        if row and row[0].strip() in dates:
            week.append(row_to_dict(row, i + 2))
    week.sort(key=lambda r: r['date'])
    return jsonify(week)


@app.route('/api/workout/<date>')
@login_required
def api_workout(date):
    rows = get_all_rows()
    for i, row in enumerate(rows):
        if row and row[0].strip() == date:
            return jsonify({'workout': row_to_dict(row, i + 2)})
    return jsonify({'error': f'No workout for {date}'}), 404


@app.route('/api/log', methods=['POST'])
@login_required
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


STRENGTH_WORKOUTS = {
    'A': {
        'session': 'Session A — Tuesday',
        'focus': 'Lower body strength — the hard session',
        'warmup': 'Leg swings x10 each direction, hip circles x10 each side, bodyweight squat x10 slow',
        'exercises': [
            {'name': 'Eccentric step-downs', 'sets': '3 × 15 each leg', 'tempo': '3 sec down, stand up with both', 'rest': '45 sec', 'notes': '6–8 inch step. Slow lower is everything. RA mod: hold wall lightly for balance.'},
            {'name': 'Bulgarian split squats', 'sets': '3 × 10 each leg', 'tempo': 'Controlled', 'rest': '45 sec', 'notes': 'Rear foot on bench/couch. Bodyweight to start; add 8–10 lb from Wk 5 if pain-free.'},
            {'name': 'Hip thrusters', 'sets': '3 × 15', 'tempo': '1 sec pause at top', 'rest': '45 sec', 'notes': 'Shoulders on bench, feet flat. Bodyweight first; add weight from Wk 3 if easy.'},
            {'name': 'Straight-leg calf raises', 'sets': '3 × 15', 'tempo': '3-1-3 slow', 'rest': '30 sec', 'notes': 'Both legs to start; single-leg from Wk 4. Supports RA feet and ankles.'},
            {'name': 'Side plank', 'sets': '3 × 30 sec each side', 'tempo': 'Hold', 'rest': '30 sec', 'notes': 'On elbow. Increase to 45 sec from Wk 5.'},
        ]
    },
    'B': {
        'session': 'Session B — Thursday',
        'focus': 'Stability + endurance — lower intensity',
        'warmup': 'Hip circles x10, glute bridges x10, ankle rolls x10 each',
        'exercises': [
            {'name': 'Wall sit', 'sets': '3 × 45 sec', 'tempo': 'Hold', 'rest': '45 sec', 'notes': 'Thighs parallel to floor. 60 sec from Wk 3, 75 sec from Wk 6. Low joint stress — good on RA days.'},
            {'name': 'Step-ups', 'sets': '3 × 12 each leg', 'tempo': 'Controlled, drive through heel', 'rest': '45 sec', 'notes': 'Sturdy chair or box (12–16 in). Add 10 lb pack Wk 3, 15 lb Wk 6.'},
            {'name': 'Single-leg RDL', 'sets': '3 × 10 each leg', 'tempo': 'Slow and controlled', 'rest': '45 sec', 'notes': 'Bodyweight only. Hinge at hip, slight knee bend — don\'t round the back.'},
            {'name': 'Banded side walks', 'sets': '3 × 20 each direction', 'tempo': 'Controlled steps', 'rest': '30 sec', 'notes': 'Light band above knees. Protects knee tracking with RA.'},
            {'name': 'Dead bugs', 'sets': '3 × 10 each side', 'tempo': 'Slow, exhale on extend', 'rest': '30 sec', 'notes': 'Lie on back, extend opposite arm/leg, keep low back flat.'},
        ]
    },
    'C': {
        'session': 'Session C — Friday (Week 5+)',
        'focus': 'Upper body + core — legs fresh for Saturday hike',
        'warmup': 'Arm circles x10, band pull-aparts x10, cat-cow x10',
        'exercises': [
            {'name': 'Push-ups', 'sets': '3 × 10', 'tempo': 'Controlled', 'rest': '45 sec', 'notes': 'Standard or incline. RA mod: on fists or push-up handles if wrists reactive.'},
            {'name': 'Band rows', 'sets': '3 × 15', 'tempo': 'Pull elbows back, 1 sec squeeze', 'rest': '45 sec', 'notes': 'Band anchored to door/post. Back + shoulder strength for pole drive on uphills.'},
            {'name': 'Plank', 'sets': '3 × 30–45 sec', 'tempo': 'Hold', 'rest': '30 sec', 'notes': 'On forearms. Increase to 60 sec from Wk 5.'},
            {'name': 'Bird dogs', 'sets': '3 × 10 each side', 'tempo': 'Slow, 2 sec hold', 'rest': '30 sec', 'notes': 'Opposite arm + leg. Back stability for uneven terrain.'},
            {'name': 'Hip flexor + hamstring stretch', 'sets': '2 × 30 sec each side', 'tempo': 'Hold', 'rest': '—', 'notes': 'Low lunge (hip flexor) + standing hamstring fold. Active recovery — legs ready for Saturday.'},
        ]
    }
}


@app.route('/api/strength/<session>')
@login_required
def api_strength(session):
    key = session.upper()
    if key not in STRENGTH_WORKOUTS:
        return jsonify({'error': f'Unknown session: {session}'}), 404
    return jsonify(STRENGTH_WORKOUTS[key])


if __name__ == '__main__':
    app.run(debug=True, port=5001)
