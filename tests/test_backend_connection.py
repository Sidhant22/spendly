import sqlite3
import pytest
import database.db as db_module
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT, "
        "email TEXT UNIQUE, "
        "password_hash TEXT, "
        "created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute(
        "CREATE TABLE expenses ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER, "
        "amount REAL, "
        "category TEXT, "
        "date TEXT, "
        "description TEXT, "
        "created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) "
        "VALUES ('Test User', 'test@example.com', 'hash', '2026-01-15 10:00:00')"
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"db_file": db_file, "user_id": user_id}


# ---------------------------------------------------------------------------
# get_user_by_id
# ---------------------------------------------------------------------------

def test_get_user_by_id_valid(temp_db):
    user = get_user_by_id(temp_db["user_id"])
    assert user is not None
    assert user["name"] == "Test User"
    assert user["email"] == "test@example.com"
    assert user["member_since"] == "January 2026"


def test_get_user_by_id_nonexistent(temp_db):
    assert get_user_by_id(999) is None


# ---------------------------------------------------------------------------
# get_summary_stats
# ---------------------------------------------------------------------------

def test_get_summary_stats_with_expenses(temp_db):
    user_id = temp_db["user_id"]
    conn = sqlite3.connect(temp_db["db_file"])
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [
            (user_id, 100.00, "Food",      "2026-04-01", "Groceries"),
            (user_id, 200.00, "Food",      "2026-04-02", "Dinner"),
            (user_id,  50.00, "Transport", "2026-04-03", "Bus pass"),
        ],
    )
    conn.commit()
    conn.close()

    stats = get_summary_stats(user_id)
    assert stats["total_spent"] == "₹350.00"
    assert stats["transaction_count"] == 3
    assert stats["top_category"] == "Food"


def test_get_summary_stats_no_expenses(temp_db):
    stats = get_summary_stats(temp_db["user_id"])
    assert stats == {"total_spent": "₹0.00", "transaction_count": 0, "top_category": "—"}


# ---------------------------------------------------------------------------
# get_recent_transactions
# ---------------------------------------------------------------------------

def test_get_recent_transactions_returns_correct_shape(temp_db):
    user_id = temp_db["user_id"]
    conn = sqlite3.connect(temp_db["db_file"])
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [
            (user_id, 100.00, "Food",      "2026-04-01", "Groceries"),
            (user_id, 250.50, "Transport", "2026-04-05", "Train ticket"),
            (user_id,  75.25, "Bills",     "2026-04-03", "Internet"),
        ],
    )
    conn.commit()
    conn.close()

    result = get_recent_transactions(user_id)
    assert len(result) == 3
    for item in result:
        assert {"date", "description", "category", "amount"} <= set(item.keys())

    assert result[0]["date"] == "2026-04-05"
    assert result[0]["amount"] == "₹250.50"
    assert result[2]["date"] == "2026-04-01"


def test_get_recent_transactions_no_expenses(temp_db):
    assert get_recent_transactions(temp_db["user_id"]) == []


def test_get_recent_transactions_respects_limit(temp_db):
    user_id = temp_db["user_id"]
    conn = sqlite3.connect(temp_db["db_file"])
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(user_id, 10.00 * i, "Food", f"2026-04-0{i}", "Item") for i in range(1, 6)],
    )
    conn.commit()
    conn.close()

    result = get_recent_transactions(user_id, limit=2)
    assert len(result) == 2
    assert result[0]["date"] == "2026-04-05"


# ---------------------------------------------------------------------------
# get_category_breakdown
# ---------------------------------------------------------------------------

def test_category_breakdown_multiple_categories(temp_db):
    user_id = temp_db["user_id"]
    conn = sqlite3.connect(temp_db["db_file"])
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [
            (user_id, 200.00, "Bills",     "2026-04-01", "Electricity"),
            (user_id, 100.00, "Food",      "2026-04-02", "Groceries"),
            (user_id,  50.00, "Transport", "2026-04-03", "Bus pass"),
            (user_id,  50.00, "Health",    "2026-04-04", "Pharmacy"),
        ],
    )
    conn.commit()
    conn.close()

    result = get_category_breakdown(user_id)
    amounts = [float(item["amount"].replace("₹", "")) for item in result]
    assert amounts == sorted(amounts, reverse=True)
    for item in result:
        assert isinstance(item["pct"], int)
    assert sum(item["pct"] for item in result) == 100
    assert result[0]["name"] == "Bills"


def test_category_breakdown_no_expenses(temp_db):
    assert get_category_breakdown(temp_db["user_id"]) == []


def test_category_breakdown_single_category(temp_db):
    user_id = temp_db["user_id"]
    conn = sqlite3.connect(temp_db["db_file"])
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(user_id, 75.00, "Shopping", "2026-04-10", "Clothes"),
         (user_id, 25.00, "Shopping", "2026-04-11", "Accessories")],
    )
    conn.commit()
    conn.close()

    result = get_category_breakdown(user_id)
    assert len(result) == 1
    assert result[0]["pct"] == 100
