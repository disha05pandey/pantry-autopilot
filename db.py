import sqlite3
from pathlib import Path

DB_PATH = Path("data/pantry.db")

def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                location TEXT,
                quantity REAL,
                unit TEXT,
                status TEXT NOT NULL DEFAULT 'ok'
                    CHECK (status IN ('ok', 'low', 'finished')),
                purchased_on TEXT DEFAULT (date('now')),
                expiry_on TEXT
            )
        """)
def add_item(name):
    with get_conn() as conn:
        conn.execute("INSERT INTO items (name) VALUES (?)", (name,))


def list_items():
    with get_conn() as conn:
        return conn.execute(
            "SELECT name, status FROM items ORDER BY name"
        ).fetchall()