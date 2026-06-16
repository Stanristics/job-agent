import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'jobs.db')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT,
            company     TEXT,
            location    TEXT,
            source      TEXT,
            url         TEXT UNIQUE,
            description TEXT,
            salary      TEXT,
            posted_date TEXT,
            match_score INTEGER DEFAULT 0,
            match_reason TEXT,
            status      TEXT DEFAULT 'pending',  -- pending | approved | rejected | submitted
            cover_letter TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            submitted_at TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Default settings
    defaults = {
        'job_titles':  'Data Scientist,Data Analyst,ML Engineer',
        'location':    'Munich',
        'min_score':   '60',
        'cv_path':     '',
        'applicant_name':  'Stanley Chukwuma Okoro',
        'applicant_email': 'stanleychukwu001@gmail.com',
        'applicant_phone': '+49 017637224355',
        'salary_expectation': '90000-95000',
        'availability': 'Immediately',
    }
    for k, v in defaults.items():
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))

    conn.commit()
    conn.close()
    print("Database initialised.")

if __name__ == '__main__':
    init_db()
