import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "spendly.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()

    existing = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()

    if existing:
        conn.close()
        return

    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo1234")),
    )
    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()["id"]

    sample_expenses = [
        (user_id, 45.50,  "Food",          "2026-04-01", "Weekly groceries"),
        (user_id, 12.00,  "Transport",     "2026-04-02", "Bus pass top-up"),
        (user_id, 120.00, "Bills",         "2026-04-03", "Electricity bill"),
        (user_id, 30.00,  "Health",        "2026-04-05", "Pharmacy"),
        (user_id, 15.99,  "Entertainment", "2026-04-06", "Streaming subscription"),
        (user_id, 65.00,  "Shopping",      "2026-04-08", "New shoes"),
        (user_id, 22.75,  "Food",          "2026-04-10", "Restaurant dinner"),
        (user_id, 9.50,   "Other",         "2026-04-11", "Miscellaneous"),
    ]

    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        sample_expenses,
    )
    conn.commit()
    conn.close()
