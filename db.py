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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY
            )
        """)


# ---------- items ----------

def item_exists(name):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM items WHERE lower(name) = lower(?)", (name,)
        ).fetchone()
        return row is not None


def add_item(name, category=None, expiry_on=None):
    if item_exists(name):
        return False
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO items (name, category, expiry_on) VALUES (?, ?, ?)",
            (name, category, expiry_on),
        )
    return True


def remove_item(name):
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM items WHERE lower(name) = lower(?)", (name,)
        )
        return cur.rowcount


def list_items():
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, name, category, status, expiry_on "
            "FROM items ORDER BY category, name"
        ).fetchall()


def get_item(item_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, name, status FROM items WHERE id = ?", (item_id,)
        ).fetchone()


def set_status(name, status):
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE items SET status = ? WHERE lower(name) = lower(?)",
            (status, name),
        )
        return cur.rowcount


def set_status_by_id(item_id, status):
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE items SET status = ? WHERE id = ?", (status, item_id)
        )
        return cur.rowcount


def list_shopping():
    with get_conn() as conn:
        return conn.execute(
            "SELECT name, status FROM items "
            "WHERE status IN ('low', 'finished') "
            "ORDER BY status, name"
        ).fetchall()


def list_uncategorized():
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, name FROM items WHERE category IS NULL"
        ).fetchall()


def set_category(item_id, category):
    with get_conn() as conn:
        conn.execute(
            "UPDATE items SET category = ? WHERE id = ?", (category, item_id)
        )


def items_expiring_on(date_iso):
    with get_conn() as conn:
        return conn.execute(
            "SELECT name, category FROM items "
            "WHERE expiry_on = ? AND status != 'finished' ORDER BY name",
            (date_iso,),
        ).fetchall()


# ---------- chats that receive alerts ----------

def save_chat(chat_id):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO chats (chat_id) VALUES (?)", (chat_id,)
        )


def get_chats():
    with get_conn() as conn:
        rows = conn.execute("SELECT chat_id FROM chats").fetchall()
        return [row["chat_id"] for row in rows]