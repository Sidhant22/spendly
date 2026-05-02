"""
Tests for Step 7 — Add Expense.

Spec: .claude/specs/07-add-expense.md

Test plan:
  Unit tests for insert_expense (database/queries.py):
  - Valid call inserts a row; all fields (user_id, amount, category, date, description)
    can be queried back with correct values
  - description=None stores NULL in the DB column

  GET /expenses/add:
  - Unauthenticated → 302 redirect to /login
  - Authenticated → 200
  - Authenticated response contains <form with method POST
  - Authenticated response contains <select element for categories
  - All 7 category options are present in the rendered HTML (parametrized)

  POST /expenses/add:
  - Unauthenticated → 302 redirect to /login
  - Valid data → 302 redirect to /profile
  - Valid data → flash "Expense added successfully" appears after following redirect
  - Valid data → new expense row exists in DB with all correct field values
  - Missing/empty amount → 200, error message in response body, no row inserted
  - Amount = 0 → 200, error message in response body, no row inserted
  - Non-numeric amount → 200, error message in response body, no row inserted
  - Invalid category → 200, error message in response body, no row inserted
  - Invalid date string → 200, error message in response body, no row inserted
  - Description > 200 chars → 200, error message in response body, no row inserted
  - Description exactly 200 chars → 302 redirect, row inserted (boundary accepted)
  - No description submitted → 302 redirect to /profile, row inserted with description = NULL
  - Blank/whitespace-only description → 302 redirect, row inserted with description = NULL
  - Form values are preserved on validation failure (amount, date re-appear in re-rendered HTML)
  - All 7 valid categories are each individually accepted (parametrized)
"""

import sqlite3
import pytest
import database.db as db_module
from app import app as flask_app
from database.db import init_db
from database.queries import insert_expense


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _create_user(db_file, name="TestUser", email="testuser@example.com"):
    """Insert a bare user row directly into the DB and return its id."""
    conn = sqlite3.connect(db_file)
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (name, email, "hashed_pw", "2026-01-01 00:00:00"),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return user_id


def _login_session(client, user_id):
    """Inject user_id into the Flask session to simulate a logged-in user."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _query_all_expenses(db_file, user_id):
    """Return all expense rows for a given user as a list of plain dicts."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(monkeypatch, tmp_path):
    """
    Isolated Flask app backed by a fresh temporary SQLite file per test.
    Monkeypatches DB_PATH so every get_db() call targets the test DB,
    not the production spendly.db on disk.
    """
    db_file = str(tmp_path / "test_step7.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_file)

    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })

    with flask_app.app_context():
        init_db()
        yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_file(monkeypatch, tmp_path):
    """
    Standalone temp-DB fixture for pure query-layer unit tests (no HTTP client).
    Builds the full schema, inserts one seed user, and returns a dict with
    'path' (str) and 'user_id' (int).
    """
    path = str(tmp_path / "query_unit_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", path)

    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE users ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  name TEXT NOT NULL,"
        "  email TEXT UNIQUE NOT NULL,"
        "  password_hash TEXT NOT NULL,"
        "  created_at TEXT DEFAULT (datetime('now'))"
        ")"
    )
    conn.execute(
        "CREATE TABLE expenses ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  user_id INTEGER NOT NULL REFERENCES users(id),"
        "  amount REAL NOT NULL,"
        "  category TEXT NOT NULL,"
        "  date TEXT NOT NULL,"
        "  description TEXT,"
        "  created_at TEXT DEFAULT (datetime('now'))"
        ")"
    )
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("UnitUser", "unit@example.com", "somehash", "2026-01-01 00:00:00"),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    return {"path": path, "user_id": user_id}


# ---------------------------------------------------------------------------
# Unit tests: insert_expense
# ---------------------------------------------------------------------------

class TestInsertExpense:

    def test_insert_expense_valid_call_row_can_be_queried_back(self, db_file):
        """A valid insert_expense call must persist a row with all correct field values."""
        uid = db_file["user_id"]
        path = db_file["path"]

        insert_expense(uid, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _query_all_expenses(path, uid)
        assert len(rows) == 1, "Expected exactly one expense row after insert"
        row = rows[0]
        assert row["user_id"] == uid, "user_id must match the provided user"
        assert row["amount"] == 50.0, "amount must match 50.0"
        assert row["category"] == "Food", "category must be 'Food'"
        assert row["date"] == "2026-03-20", "date must be '2026-03-20'"
        assert row["description"] == "Lunch", "description must be 'Lunch'"

    def test_insert_expense_description_none_stores_null(self, db_file):
        """When description=None is passed the DB column must store NULL (None in Python)."""
        uid = db_file["user_id"]
        path = db_file["path"]

        insert_expense(uid, 120.0, "Bills", "2026-04-01", None)

        rows = _query_all_expenses(path, uid)
        assert len(rows) == 1, "Expected exactly one row after insert with description=None"
        assert rows[0]["description"] is None, (
            "description column must be NULL in the DB when None is passed"
        )


# ---------------------------------------------------------------------------
# GET /expenses/add
# ---------------------------------------------------------------------------

class TestGetAddExpense:

    def test_get_unauthenticated_redirects_to_login(self, client):
        """Unauthenticated GET /expenses/add must return 302 and redirect to /login."""
        response = client.get("/expenses/add")
        assert response.status_code == 302, (
            f"Unauthenticated GET /expenses/add must return 302, got {response.status_code}"
        )
        assert "/login" in response.headers["Location"], (
            "Unauthenticated GET /expenses/add must redirect to /login"
        )

    def test_get_authenticated_returns_200(self, client):
        """Authenticated GET /expenses/add must return HTTP 200."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/expenses/add")
        assert response.status_code == 200, (
            f"Authenticated GET /expenses/add must return 200, got {response.status_code}"
        )

    def test_get_authenticated_response_contains_form_with_post(self, client):
        """The rendered page must include a <form element that specifies POST method."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/expenses/add")
        html = response.data.decode("utf-8")
        assert "<form" in html, "Response must contain a <form element"
        assert "post" in html.lower(), (
            "The <form> must declare method POST (case-insensitive)"
        )

    def test_get_authenticated_response_contains_select_element(self, client):
        """The rendered page must include a <select> element for the category dropdown."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/expenses/add")
        html = response.data.decode("utf-8")
        assert "<select" in html, (
            "Response must contain a <select> element for the category field"
        )

    @pytest.mark.parametrize("category", [
        "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
    ])
    def test_get_authenticated_all_7_category_options_present(self, client, category):
        """Each of the 7 required category options must appear in the rendered HTML."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/expenses/add")
        html = response.data.decode("utf-8")
        assert category in html, (
            f"Category option '{category}' must be present in the add-expense form"
        )

    def test_get_authenticated_renders_full_html_document(self, client):
        """The page must render a full HTML document (extends base.html)."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/expenses/add")
        html = response.data.decode("utf-8")
        assert "<!DOCTYPE html>" in html or "<html" in html, (
            "add_expense.html must extend base.html and yield a complete HTML document"
        )


# ---------------------------------------------------------------------------
# POST /expenses/add — auth guard
# ---------------------------------------------------------------------------

class TestPostAddExpenseAuthGuard:

    def test_post_unauthenticated_redirects_to_login(self, client):
        """Unauthenticated POST /expenses/add must return 302 and redirect to /login."""
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-04-01",
            "description": "Test",
        })
        assert response.status_code == 302, (
            f"Unauthenticated POST must return 302, got {response.status_code}"
        )
        assert "/login" in response.headers["Location"], (
            "Unauthenticated POST /expenses/add must redirect to /login"
        )


# ---------------------------------------------------------------------------
# POST /expenses/add — happy path (valid data)
# ---------------------------------------------------------------------------

class TestPostAddExpenseValidData:

    def test_post_valid_data_redirects_to_profile(self, client):
        """A valid POST /expenses/add must return 302 and redirect to /profile."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "75.50",
            "category": "Food",
            "date": "2026-04-10",
            "description": "Dinner",
        })
        assert response.status_code == 302, (
            f"Valid POST /expenses/add must return 302, got {response.status_code}"
        )
        assert "/profile" in response.headers["Location"], (
            "Valid POST /expenses/add must redirect to /profile"
        )

    def test_post_valid_data_flash_message_expense_added_successfully(self, client):
        """After a valid POST the flash message 'Expense added successfully' must appear on /profile."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "30.00",
                "category": "Transport",
                "date": "2026-04-15",
                "description": "Bus fare",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200, (
            "Following the redirect after a valid POST must return 200"
        )
        html = response.data.decode("utf-8")
        assert "Expense added successfully" in html, (
            "Flash message 'Expense added successfully' must be visible after redirect to /profile"
        )

    def test_post_valid_data_row_inserted_in_db_with_correct_fields(self, client):
        """After a valid POST, a new expense row must exist in the DB with all correct values."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        client.post("/expenses/add", data={
            "amount": "99.99",
            "category": "Shopping",
            "date": "2026-04-20",
            "description": "New jacket",
        })

        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 1, "Exactly one expense row must be in the DB after a valid POST"
        row = rows[0]
        assert row["amount"] == 99.99, f"Stored amount must be 99.99, got {row['amount']}"
        assert row["category"] == "Shopping", f"Stored category must be 'Shopping', got {row['category']}"
        assert row["date"] == "2026-04-20", f"Stored date must be '2026-04-20', got {row['date']}"
        assert row["description"] == "New jacket", (
            f"Stored description must be 'New jacket', got {row['description']}"
        )

    def test_post_valid_data_correct_user_id_stored(self, client):
        """The inserted expense must be linked to the session user's id."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        client.post("/expenses/add", data={
            "amount": "45.00",
            "category": "Health",
            "date": "2026-03-01",
            "description": "Vitamins",
        })

        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 1, "One expense row expected after valid POST"
        assert rows[0]["user_id"] == user_id, (
            "Inserted expense must be associated with the logged-in user's id"
        )


# ---------------------------------------------------------------------------
# POST /expenses/add — no description (optional field)
# ---------------------------------------------------------------------------

class TestPostAddExpenseNoDescription:

    def test_post_omitted_description_redirects_to_profile(self, client):
        """Submitting without a description field must redirect to /profile (302)."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "20.00",
            "category": "Other",
            "date": "2026-05-01",
            # description intentionally omitted
        })
        assert response.status_code == 302, (
            "POST without description must return 302 redirect"
        )
        assert "/profile" in response.headers["Location"], (
            "POST without description must redirect to /profile"
        )

    def test_post_omitted_description_stores_null_in_db(self, client):
        """When description is omitted entirely the DB row must have description = NULL."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        client.post("/expenses/add", data={
            "amount": "20.00",
            "category": "Other",
            "date": "2026-05-01",
            # description intentionally omitted
        })

        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 1, "One expense row must be inserted when description is omitted"
        assert rows[0]["description"] is None, (
            "description must be NULL in the DB when no description was submitted"
        )

    def test_post_whitespace_only_description_stores_null_in_db(self, client):
        """A description of only whitespace must be stripped and stored as NULL."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        client.post("/expenses/add", data={
            "amount": "15.00",
            "category": "Food",
            "date": "2026-05-02",
            "description": "   ",  # whitespace only
        })

        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 1, (
            "One expense row must be inserted for a whitespace-only description"
        )
        assert rows[0]["description"] is None, (
            "Whitespace-only description must be stripped and stored as NULL"
        )


# ---------------------------------------------------------------------------
# POST /expenses/add — amount validation failures
# ---------------------------------------------------------------------------

class TestPostAddExpenseAmountValidation:

    @pytest.mark.parametrize("bad_amount", [
        "",        # missing / empty
        "0",       # zero is not > 0
        "0.00",    # zero with decimals
        "-5",      # negative
        "-0.01",   # negative small
        "abc",     # non-numeric string
        "1.2.3",   # malformed float
    ])
    def test_post_invalid_amount_returns_200(self, client, bad_amount):
        """Any invalid amount value must re-render the form with HTTP 200."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-04-01",
            "description": "test",
        })
        assert response.status_code == 200, (
            f"Invalid amount '{bad_amount}' must return 200 (re-render form), "
            f"got {response.status_code}"
        )

    def test_post_empty_amount_shows_error_message(self, client):
        """Empty amount must render an error message referencing amount in the response."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "",
            "category": "Food",
            "date": "2026-04-01",
            "description": "test",
        })
        assert response.status_code == 200, "Empty amount must return 200"
        html = response.data.decode("utf-8")
        assert "amount" in html.lower() or "positive" in html.lower(), (
            "Error message for empty amount must reference 'amount' or the positive-number constraint"
        )

    def test_post_zero_amount_shows_error_message(self, client):
        """Amount of 0 must re-render with an error indicating a positive value is required."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-04-01",
            "description": "test",
        })
        assert response.status_code == 200, "Zero amount must return 200"
        html = response.data.decode("utf-8")
        assert "amount" in html.lower() or "positive" in html.lower(), (
            "Error for zero amount must reference 'amount' or the positive-number constraint"
        )

    def test_post_zero_amount_does_not_insert_row(self, client):
        """A zero amount submission must not write any row to the expenses table."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        client.post("/expenses/add", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-04-01",
            "description": "test",
        })

        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 0, "Zero amount must not insert any expense row into the DB"

    def test_post_nonnumeric_amount_returns_200_with_error(self, client):
        """A non-numeric amount string must re-render the form (200) with an error message."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "not-a-number",
            "category": "Food",
            "date": "2026-04-01",
            "description": "test",
        })
        assert response.status_code == 200, (
            "Non-numeric amount must return 200 (re-render form)"
        )
        html = response.data.decode("utf-8")
        assert "amount" in html.lower() or "positive" in html.lower(), (
            "Error for non-numeric amount must reference the amount constraint"
        )

    def test_post_nonnumeric_amount_does_not_insert_row(self, client):
        """A non-numeric amount must not insert any expense row."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        client.post("/expenses/add", data={
            "amount": "abc",
            "category": "Food",
            "date": "2026-04-01",
            "description": "test",
        })

        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 0, "Non-numeric amount must not insert any expense row into the DB"


# ---------------------------------------------------------------------------
# POST /expenses/add — category validation failures
# ---------------------------------------------------------------------------

class TestPostAddExpenseCategoryValidation:

    @pytest.mark.parametrize("bad_category", [
        "",                              # empty string
        "food",                          # wrong case
        "FOOD",                          # all-caps
        "Snacks",                        # unlisted category
        "NotACategory",                  # arbitrary string
        "'; DROP TABLE expenses; --",    # injection attempt
    ])
    def test_post_invalid_category_returns_200(self, client, bad_category):
        """Any category not in the 7 allowed values must re-render the form with 200."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": bad_category,
            "date": "2026-04-01",
            "description": "test",
        })
        assert response.status_code == 200, (
            f"Invalid category '{bad_category}' must return 200 (re-render), "
            f"got {response.status_code}"
        )

    def test_post_invalid_category_shows_error_message(self, client):
        """An invalid category must display a user-visible error message in the HTML."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "InvalidCategory",
            "date": "2026-04-01",
            "description": "test",
        })
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "category" in html.lower() or "valid" in html.lower(), (
            "Error for invalid category must reference 'category' or 'valid' in the response"
        )

    def test_post_invalid_category_does_not_insert_row(self, client):
        """An invalid category must not write any row to the expenses table."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "InvalidCategory",
            "date": "2026-04-01",
            "description": "test",
        })

        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 0, "Invalid category must not insert any expense row into the DB"


# ---------------------------------------------------------------------------
# POST /expenses/add — date validation failures
# ---------------------------------------------------------------------------

class TestPostAddExpenseDateValidation:

    @pytest.mark.parametrize("bad_date", [
        "",             # missing date
        "not-a-date",   # arbitrary string
        "2026/04/01",   # wrong separator
        "04-01-2026",   # wrong field order
        "2026-13-01",   # month out of range
        "2026-04-99",   # day out of range
        "20260401",     # no separators
    ])
    def test_post_invalid_date_returns_200(self, client, bad_date):
        """Any malformed date string must re-render the form with HTTP 200."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": bad_date,
            "description": "test",
        })
        assert response.status_code == 200, (
            f"Invalid date '{bad_date}' must return 200 (re-render), "
            f"got {response.status_code}"
        )

    def test_post_invalid_date_shows_error_message(self, client):
        """An invalid date must display a user-visible error message in the HTML."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "not-a-date",
            "description": "test",
        })
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "date" in html.lower() or "valid" in html.lower(), (
            "Error for invalid date must reference 'date' or 'valid' in the response"
        )

    def test_post_invalid_date_does_not_insert_row(self, client):
        """An invalid date must not write any row to the expenses table."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "not-a-date",
            "description": "test",
        })

        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 0, "Invalid date must not insert any expense row into the DB"


# ---------------------------------------------------------------------------
# POST /expenses/add — description length validation
# ---------------------------------------------------------------------------

class TestPostAddExpenseDescriptionLength:

    def test_post_description_over_200_chars_returns_200(self, client):
        """A description longer than 200 characters must re-render the form (200)."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-04-01",
            "description": "x" * 201,  # one character over the limit
        })
        assert response.status_code == 200, (
            "Description over 200 chars must return 200 (re-render form)"
        )

    def test_post_description_over_200_chars_shows_error_message(self, client):
        """The error message for a too-long description must appear in the response HTML."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-04-01",
            "description": "a" * 201,
        })
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "200" in html or "description" in html.lower(), (
            "Error for description > 200 chars must mention '200' or 'description' in the response"
        )

    def test_post_description_over_200_chars_does_not_insert_row(self, client):
        """A description exceeding 200 characters must not write any row to the expenses table."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-04-01",
            "description": "z" * 201,
        })

        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 0, "Description > 200 chars must not insert any expense row"

    def test_post_description_exactly_200_chars_is_accepted_with_redirect(self, client):
        """A description of exactly 200 characters must be accepted and produce a 302 redirect."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        exactly_200 = "b" * 200

        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-04-01",
            "description": exactly_200,
        })
        assert response.status_code == 302, (
            "Description of exactly 200 chars is at the boundary and must be accepted (302)"
        )

    def test_post_description_exactly_200_chars_row_inserted_in_db(self, client):
        """A description of exactly 200 characters must be stored verbatim in the DB."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        exactly_200 = "c" * 200

        client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-04-01",
            "description": exactly_200,
        })

        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 1, "One expense row must be inserted for exactly-200-char description"
        assert rows[0]["description"] == exactly_200, (
            "Stored description must equal the exactly-200-char input"
        )


# ---------------------------------------------------------------------------
# POST /expenses/add — form value preservation on validation failure
# ---------------------------------------------------------------------------

class TestPostAddExpenseValuePreservation:

    def test_previously_submitted_amount_preserved_on_category_error(self, client):
        """When a category error triggers re-render, the submitted amount must reappear in HTML."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "123.45",
            "category": "NotACategory",  # invalid — triggers re-render
            "date": "2026-04-01",
            "description": "test",
        })
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "123.45" in html, (
            "Previously submitted amount '123.45' must be preserved in the re-rendered form"
        )

    def test_previously_submitted_date_preserved_on_amount_error(self, client):
        """When an amount error triggers re-render, the submitted date must reappear in HTML."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "abc",          # invalid — triggers re-render
            "category": "Food",
            "date": "2026-06-15",
            "description": "test",
        })
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "2026-06-15" in html, (
            "Previously submitted date '2026-06-15' must be preserved in the re-rendered form"
        )

    def test_previously_submitted_description_preserved_on_date_error(self, client):
        """When a date error triggers re-render, the submitted description must reappear in HTML."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "bad-date",    # invalid — triggers re-render
            "description": "MyUniqueDesc",
        })
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "MyUniqueDesc" in html, (
            "Previously submitted description must be preserved in the re-rendered form"
        )


# ---------------------------------------------------------------------------
# POST /expenses/add — all 7 valid categories are individually accepted
# ---------------------------------------------------------------------------

class TestPostAddExpenseAllValidCategories:

    @pytest.mark.parametrize("category", [
        "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
    ])
    def test_post_each_valid_category_redirects_and_inserts_row(self, client, category):
        """Every one of the 7 allowed categories must be accepted (302) and produce a DB row."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.post("/expenses/add", data={
            "amount": "10.00",
            "category": category,
            "date": "2026-04-01",
            "description": f"Testing {category}",
        })
        assert response.status_code == 302, (
            f"Valid category '{category}' must produce a 302 redirect, "
            f"got {response.status_code}"
        )
        rows = _query_all_expenses(db_module.DB_PATH, user_id)
        assert len(rows) == 1, (
            f"Expense with category '{category}' must be inserted into the DB"
        )
        assert rows[0]["category"] == category, (
            f"Stored category must be '{category}', got '{rows[0]['category']}'"
        )
