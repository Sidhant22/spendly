"""
Tests for Step 6 — Date Filter on the Profile Page.

Spec: .claude/specs/06-date-filter-profile-page.md

Test plan:
- Auth guard: unauthenticated GET /profile (with and without params) redirects to /login
- Unfiltered baseline: no query params returns 200, all expenses, ₹ symbol, ₹0.00 for empty
- Valid custom date range: filters all three data sections, inclusive boundaries,
  empty-range zero result, active filter values reflected in HTML, ₹ always present
- Preset windows: "This Month", "Last 3 Months", "Last 6 Months" each filter correctly;
  "All Time" (no params) returns all expenses
- Invalid / malformed input: date_from > date_to flashes "Start date must be before end date."
  and falls back to unfiltered; malformed strings do not crash (200); only one param falls back
- DB-level query helpers: get_summary_stats, get_recent_transactions, get_category_breakdown
  all honour date_from/date_to, return correct shapes, ₹ symbol in amounts,
  percentages sum to 100, order preserved
- Template / HTML landmarks: date inputs present, param names in HTML, base.html inherited,
  all four preset labels rendered, All Time link has clean /profile href
- User isolation: another user's expenses never appear in filtered view
"""

import sqlite3
import pytest
import database.db as db_module
from datetime import date
from app import app as flask_app
from database.db import init_db
from database.queries import (
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _insert_expenses(db_file, user_id, rows):
    """Insert expense rows: list of (amount, category, date, description)."""
    conn = sqlite3.connect(db_file)
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        [(user_id, *r) for r in rows],
    )
    conn.commit()
    conn.close()


def _create_user(db_file, name="Alice", email="alice@example.com"):
    """Insert a bare user row and return its id."""
    conn = sqlite3.connect(db_file)
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) "
        "VALUES (?, ?, ?, ?)",
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(monkeypatch, tmp_path):
    """
    Isolated Flask app backed by a fresh temp SQLite file per test.
    Monkeypatches DB_PATH so every get_db() call hits the test DB,
    not the real spendly.db on disk.
    """
    db_file = str(tmp_path / "test_step6.db")
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
    Standalone temp DB fixture for pure query-layer tests (no Flask client).
    Creates the schema and one seed user; returns {"path": ..., "user_id": ...}.
    """
    path = str(tmp_path / "query_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", path)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT, email TEXT UNIQUE, password_hash TEXT, "
        "created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute(
        "CREATE TABLE expenses ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER, amount REAL, category TEXT, "
        "date TEXT, description TEXT, "
        "created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("Bob", "bob@example.com", "hash", "2026-01-01 00:00:00"),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"path": path, "user_id": user_id}


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_profile_requires_login_redirects_to_login(self, client):
        """Unauthenticated GET /profile must redirect to /login."""
        response = client.get("/profile")
        assert response.status_code == 302, (
            "Expected 302 redirect for unauthenticated access to /profile"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect target must be /login"
        )

    def test_profile_with_date_params_still_requires_login(self, client):
        """Even when date params are present, /profile is protected by auth."""
        response = client.get("/profile?date_from=2026-01-01&date_to=2026-12-31")
        assert response.status_code == 302, (
            "Expected 302 redirect when date params are present but user is unauthenticated"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect target must be /login regardless of query params"
        )


# ---------------------------------------------------------------------------
# Unfiltered baseline (no query params)
# ---------------------------------------------------------------------------

class TestUnfilteredBaseline:
    def test_profile_no_params_returns_200(self, client, app):
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile")
        assert response.status_code == 200, (
            "GET /profile with no params must return 200 for authenticated user"
        )

    def test_profile_no_params_shows_all_expenses(self, client, app):
        """With no date params, all user expenses across all dates are summed."""
        user_id = _create_user(db_module.DB_PATH)
        _insert_expenses(db_module.DB_PATH, user_id, [
            (100.00, "Food",      "2026-01-15", "Jan food"),
            (200.00, "Transport", "2026-03-10", "Mar transport"),
            (300.00, "Bills",     "2026-04-20", "Apr bills"),
        ])
        _login_session(client, user_id)

        response = client.get("/profile")
        data = response.data.decode("utf-8")
        assert "600.00" in data, (
            "Unfiltered view must sum all expenses: expected total 600.00"
        )

    def test_profile_no_params_shows_rupee_symbol(self, client, app):
        """The ₹ currency symbol must always appear on the profile page."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile")
        data = response.data.decode("utf-8")
        assert "₹" in data, "₹ symbol must appear on the unfiltered profile page"

    def test_profile_no_params_empty_user_shows_zero_total(self, client, app):
        """A user with no expenses at all must see ₹0.00 total spent."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile")
        data = response.data.decode("utf-8")
        assert "₹0.00" in data, (
            "User with no expenses must see ₹0.00 total on the unfiltered profile page"
        )

    def test_profile_no_params_empty_user_shows_zero_transactions(self, client, app):
        """A user with no expenses must see 0 transactions."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile")
        data = response.data.decode("utf-8")
        # transaction_count == 0 must be rendered somewhere on the page
        assert "0" in data, (
            "User with no expenses must see 0 transaction count on the profile page"
        )


# ---------------------------------------------------------------------------
# Valid custom date range
# ---------------------------------------------------------------------------

class TestCustomDateRange:
    def test_valid_range_filters_summary_stats(self, client, app):
        """Only expenses within the requested range contribute to the summary total."""
        user_id = _create_user(db_module.DB_PATH)
        _insert_expenses(db_module.DB_PATH, user_id, [
            (100.00, "Food",      "2026-02-10", "Feb food"),      # outside range
            (250.00, "Transport", "2026-04-05", "Apr transport"),  # inside range
            (150.00, "Bills",     "2026-04-20", "Apr bills"),     # inside range
        ])
        _login_session(client, user_id)

        response = client.get("/profile?date_from=2026-04-01&date_to=2026-04-30")
        assert response.status_code == 200
        data = response.data.decode("utf-8")
        # Only April expenses: 250 + 150 = 400
        assert "400.00" in data, (
            "Date-filtered view must show only expenses within 2026-04-01 to 2026-04-30 (expected 400.00)"
        )

    def test_valid_range_excludes_expenses_outside_range(self, client, app):
        """Expenses outside the filter range must not appear in the response."""
        user_id = _create_user(db_module.DB_PATH)
        _insert_expenses(db_module.DB_PATH, user_id, [
            (999.00, "Shopping", "2025-12-31", "Last year"),  # outside
            (50.00,  "Food",     "2026-03-15", "Mar food"),   # inside
        ])
        _login_session(client, user_id)

        response = client.get("/profile?date_from=2026-03-01&date_to=2026-03-31")
        data = response.data.decode("utf-8")
        assert "50.00" in data, "Expense inside the range must appear in filtered view"
        assert "999" not in data, "Expense outside the range must not appear in filtered view"

    def test_valid_range_date_boundaries_are_inclusive(self, client, app):
        """Expenses exactly on date_from and date_to must be included (BETWEEN is inclusive)."""
        user_id = _create_user(db_module.DB_PATH)
        _insert_expenses(db_module.DB_PATH, user_id, [
            (100.00, "Food",  "2026-04-01", "Start boundary"),  # on date_from
            (200.00, "Bills", "2026-04-30", "End boundary"),    # on date_to
            (999.00, "Other", "2026-05-01", "Day after end"),   # just outside
        ])
        _login_session(client, user_id)

        response = client.get("/profile?date_from=2026-04-01&date_to=2026-04-30")
        data = response.data.decode("utf-8")
        # Boundary totals: 100 + 200 = 300
        assert "300.00" in data, (
            "Boundary dates must be inclusive — both date_from and date_to expenses must be counted"
        )
        assert "999" not in data, "Expense just after date_to must be excluded"

    def test_valid_range_no_expenses_in_range_shows_zero_no_error(self, client, app):
        """Filtered view with no matching expenses must return 200 and show ₹0.00."""
        user_id = _create_user(db_module.DB_PATH)
        _insert_expenses(db_module.DB_PATH, user_id, [
            (500.00, "Food", "2025-06-01", "Old expense outside window"),
        ])
        _login_session(client, user_id)

        response = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        assert response.status_code == 200, (
            "Empty filtered result must not crash the app — expected 200"
        )
        data = response.data.decode("utf-8")
        assert "₹0.00" in data, (
            "No expenses in the selected range must render ₹0.00 total spent"
        )

    def test_valid_range_active_filter_values_reflected_in_response(self, client, app):
        """The validated date_from and date_to must appear in the rendered HTML
        so the template can pre-fill the custom date inputs and show active state."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile?date_from=2026-03-01&date_to=2026-03-31")
        data = response.data.decode("utf-8")
        assert "2026-03-01" in data, (
            "Active date_from must appear in the rendered template (e.g. as input value)"
        )
        assert "2026-03-31" in data, (
            "Active date_to must appear in the rendered template (e.g. as input value)"
        )

    def test_valid_range_rupee_symbol_always_present(self, client, app):
        """The ₹ symbol must always appear regardless of the active filter."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile?date_from=2026-01-01&date_to=2026-12-31")
        data = response.data.decode("utf-8")
        assert "₹" in data, "₹ symbol must always be present regardless of active filter"

    def test_valid_range_empty_category_breakdown_no_error(self, client, app):
        """When no expenses exist in the range, category breakdown is empty — no 500."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile?date_from=2099-01-01&date_to=2099-12-31")
        assert response.status_code == 200, (
            "Empty category breakdown for an out-of-range filter must not cause an error"
        )


# ---------------------------------------------------------------------------
# Preset windows
# ---------------------------------------------------------------------------

class TestPresetWindows:
    def test_this_month_filters_to_current_month_only(self, client, app):
        """'This Month' shows only expenses from the first of the current month to today."""
        user_id = _create_user(db_module.DB_PATH)
        today = date.today()
        first_of_month = today.replace(day=1).isoformat()
        today_str = today.isoformat()

        _insert_expenses(db_module.DB_PATH, user_id, [
            (300.00, "Food",  today_str,    "Today's expense — must appear"),
            (400.00, "Bills", "2020-01-15", "Old expense — must be excluded"),
        ])
        _login_session(client, user_id)

        response = client.get(
            f"/profile?date_from={first_of_month}&date_to={today_str}"
        )
        assert response.status_code == 200
        data = response.data.decode("utf-8")
        assert "300.00" in data, (
            "Expense on today's date must appear under 'This Month' filter"
        )

    def test_last_3_months_window_filters_correctly(self, client, app):
        """'Last 3 Months' includes expenses from the computed 3-month start through today."""
        user_id = _create_user(db_module.DB_PATH)
        today = date.today()
        today_str = today.isoformat()

        _insert_expenses(db_module.DB_PATH, user_id, [
            (999.00, "Shopping", "2010-01-01", "Very old — must be excluded"),
            (123.00, "Food",     today_str,    "Today — must be included"),
        ])
        _login_session(client, user_id)

        # Replicate the same date arithmetic used by app.py
        m = today.month - 3
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        start_3m = date(y, m, 1).isoformat()

        response = client.get(
            f"/profile?date_from={start_3m}&date_to={today_str}"
        )
        data = response.data.decode("utf-8")
        assert "123.00" in data, "Expense within last 3 months must appear"
        assert "999" not in data, "Expense from 2010 must be excluded from 3-month filter"

    def test_last_6_months_window_filters_correctly(self, client, app):
        """'Last 6 Months' includes expenses from the computed 6-month start through today."""
        user_id = _create_user(db_module.DB_PATH)
        today = date.today()
        today_str = today.isoformat()

        _insert_expenses(db_module.DB_PATH, user_id, [
            (888.00, "Other",     "2010-06-01", "Very old — must be excluded"),
            (222.00, "Transport", today_str,    "Today — must be included"),
        ])
        _login_session(client, user_id)

        m = today.month - 6
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        start_6m = date(y, m, 1).isoformat()

        response = client.get(
            f"/profile?date_from={start_6m}&date_to={today_str}"
        )
        data = response.data.decode("utf-8")
        assert "222.00" in data, "Expense within last 6 months must appear"
        assert "888" not in data, "Expense from 2010 must be excluded from 6-month filter"

    def test_all_time_no_params_returns_all_expenses(self, client, app):
        """'All Time' passes no query params — all expenses across all dates must be visible."""
        user_id = _create_user(db_module.DB_PATH)
        _insert_expenses(db_module.DB_PATH, user_id, [
            (100.00, "Food",   "2015-01-01", "Very old"),
            (200.00, "Bills",  "2020-06-15", "Middle era"),
            (300.00, "Health", "2026-04-30", "Recent"),
        ])
        _login_session(client, user_id)

        response = client.get("/profile")  # no query params = All Time
        assert response.status_code == 200
        data = response.data.decode("utf-8")
        assert "600.00" in data, (
            "All Time (no params) must sum all expenses: expected 600.00"
        )


# ---------------------------------------------------------------------------
# Invalid / malformed input handling
# ---------------------------------------------------------------------------

class TestInvalidInputHandling:
    def test_date_from_greater_than_date_to_flashes_error_message(self, client, app):
        """When date_from > date_to, the flash message 'Start date must be before end date.'
        must appear in the HTML response body."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        # follow_redirects=True ensures flash is rendered in the HTML
        response = client.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01",
            follow_redirects=True,
        )
        assert response.status_code == 200
        data = response.data.decode("utf-8")
        assert "Start date must be before end date." in data, (
            "Flash message 'Start date must be before end date.' must appear in HTML "
            "when date_from is after date_to"
        )

    def test_date_from_greater_than_date_to_falls_back_to_unfiltered(self, client, app):
        """When date_from > date_to, the view falls back to the full unfiltered dataset."""
        user_id = _create_user(db_module.DB_PATH)
        _insert_expenses(db_module.DB_PATH, user_id, [
            (100.00, "Food",  "2026-01-10", "January"),
            (200.00, "Bills", "2026-12-20", "December"),
        ])
        _login_session(client, user_id)

        response = client.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01",
            follow_redirects=True,
        )
        data = response.data.decode("utf-8")
        # Unfiltered total = 100 + 200 = 300
        assert "300.00" in data, (
            "Reversed date range must fall back to unfiltered view — expected total 300.00"
        )

    @pytest.mark.parametrize("bad_from,bad_to", [
        ("not-a-date",  "2026-04-30"),   # invalid date_from text
        ("2026-04-01",  "not-a-date"),   # invalid date_to text
        ("not-a-date",  "not-a-date"),   # both invalid
        ("2026/04/01",  "2026-04-30"),   # wrong separator in date_from
        ("04-01-2026",  "2026-04-30"),   # wrong order (MM-DD-YYYY) in date_from
        ("2026-13-01",  "2026-04-30"),   # month 13 is invalid
        ("2026-04-99",  "2026-04-30"),   # day 99 is invalid
    ])
    def test_malformed_date_does_not_crash(self, client, app, bad_from, bad_to):
        """Any malformed date string must fall back gracefully — the app must return 200."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get(
            f"/profile?date_from={bad_from}&date_to={bad_to}"
        )
        assert response.status_code == 200, (
            f"Malformed dates ('{bad_from}', '{bad_to}') must not crash the app — expected 200"
        )

    def test_malformed_date_falls_back_to_unfiltered_view(self, client, app):
        """A malformed date_from silently falls back — all expenses are shown, not zero."""
        user_id = _create_user(db_module.DB_PATH)
        _insert_expenses(db_module.DB_PATH, user_id, [
            (500.00, "Food", "2026-04-01", "April food"),
        ])
        _login_session(client, user_id)

        response = client.get("/profile?date_from=INVALID&date_to=2026-04-30")
        data = response.data.decode("utf-8")
        assert "500.00" in data, (
            "Malformed date_from must fall back to unfiltered view — all expenses must be shown"
        )

    def test_only_date_from_provided_falls_back_to_unfiltered(self, client, app):
        """Providing only date_from with no date_to must be treated as absent — no filter applied."""
        user_id = _create_user(db_module.DB_PATH)
        _insert_expenses(db_module.DB_PATH, user_id, [
            (100.00, "Food",  "2025-01-01", "Old"),
            (200.00, "Bills", "2026-04-15", "New"),
        ])
        _login_session(client, user_id)

        response = client.get("/profile?date_from=2026-04-01")
        data = response.data.decode("utf-8")
        # Total of both expenses = 300.00
        assert "300.00" in data, (
            "Supplying only date_from (no date_to) must fall back to unfiltered view: expected 300.00"
        )

    def test_only_date_to_provided_falls_back_to_unfiltered(self, client, app):
        """Providing only date_to with no date_from must be treated as absent — no filter applied."""
        user_id = _create_user(db_module.DB_PATH)
        _insert_expenses(db_module.DB_PATH, user_id, [
            (100.00, "Food",  "2025-01-01", "Old"),
            (200.00, "Bills", "2026-04-15", "New"),
        ])
        _login_session(client, user_id)

        response = client.get("/profile?date_to=2026-04-30")
        data = response.data.decode("utf-8")
        assert "300.00" in data, (
            "Supplying only date_to (no date_from) must fall back to unfiltered view: expected 300.00"
        )

    def test_empty_date_params_do_not_crash(self, client, app):
        """Sending empty string values for both params must not crash the app."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile?date_from=&date_to=")
        assert response.status_code == 200, (
            "Empty date params must not crash the app — expected 200"
        )


# ---------------------------------------------------------------------------
# DB-level query helper tests (no Flask client)
# ---------------------------------------------------------------------------

class TestQueryHelpersDateFilter:
    """
    These tests call query helpers directly, bypassing the Flask layer,
    to verify that date_from / date_to filtering is applied at the SQL level.
    """

    # --- get_summary_stats ---

    def test_get_summary_stats_filtered_by_date(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (100.00, "Food",      "2026-03-01", "March — outside"),
            (200.00, "Transport", "2026-04-15", "April — inside"),
            (300.00, "Bills",     "2026-05-20", "May — outside"),
        ])

        stats = get_summary_stats(uid, date_from="2026-04-01", date_to="2026-04-30")
        assert stats["total_spent"] == "₹200.00", (
            "Summary stats must sum only expenses within the date range"
        )
        assert stats["transaction_count"] == 1, (
            "Transaction count must reflect only the filtered expenses"
        )

    def test_get_summary_stats_no_filter_returns_all(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (100.00, "Food",  "2026-01-01", "Jan"),
            (200.00, "Bills", "2026-06-01", "Jun"),
        ])

        stats = get_summary_stats(uid)
        assert stats["total_spent"] == "₹300.00", (
            "Unfiltered summary stats must sum all expenses"
        )
        assert stats["transaction_count"] == 2

    def test_get_summary_stats_empty_range_returns_zero(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (100.00, "Food", "2026-01-01", "Jan"),
        ])

        stats = get_summary_stats(uid, date_from="2026-06-01", date_to="2026-06-30")
        assert stats["total_spent"] == "₹0.00", (
            "No expenses in range must return ₹0.00 total"
        )
        assert stats["transaction_count"] == 0
        assert stats["top_category"] == "—", (
            "No expenses in range must return '—' for top_category"
        )

    def test_get_summary_stats_total_spent_has_rupee_symbol(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (100.00, "Food", "2026-04-01", "a"),
        ])

        stats = get_summary_stats(uid, date_from="2026-04-01", date_to="2026-04-30")
        assert stats["total_spent"].startswith("₹"), (
            "total_spent must always carry the ₹ symbol"
        )

    # --- get_recent_transactions ---

    def test_get_recent_transactions_filtered_by_date(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (50.00,  "Food",   "2026-02-10", "Feb — outside"),
            (75.00,  "Health", "2026-04-05", "Apr 1 — inside"),
            (25.00,  "Other",  "2026-04-20", "Apr 2 — inside"),
            (999.00, "Bills",  "2026-07-01", "Jul — outside"),
        ])

        txns = get_recent_transactions(uid, date_from="2026-04-01", date_to="2026-04-30")
        assert len(txns) == 2, "Only April transactions should be returned by the date filter"
        amounts = {t["amount"] for t in txns}
        assert "₹75.00" in amounts, "April Health expense must be present"
        assert "₹25.00" in amounts, "April Other expense must be present"

    def test_get_recent_transactions_no_filter_returns_all(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (10.00, "Food",   "2026-01-01", "a"),
            (20.00, "Bills",  "2026-02-01", "b"),
            (30.00, "Health", "2026-03-01", "c"),
        ])

        txns = get_recent_transactions(uid)
        assert len(txns) == 3, "Unfiltered call must return all transactions"

    def test_get_recent_transactions_empty_range_returns_empty_list(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (100.00, "Food", "2026-01-01", "Old"),
        ])

        txns = get_recent_transactions(uid, date_from="2026-06-01", date_to="2026-06-30")
        assert txns == [], "Empty date range must yield an empty transaction list"

    def test_get_recent_transactions_ordered_newest_first(self, db_file):
        """Filtered transactions must still be ordered newest to oldest."""
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (10.00, "Food",   "2026-04-01", "Oldest"),
            (20.00, "Bills",  "2026-04-15", "Middle"),
            (30.00, "Health", "2026-04-30", "Newest"),
        ])

        txns = get_recent_transactions(uid, date_from="2026-04-01", date_to="2026-04-30")
        assert txns[0]["date"] == "2026-04-30", (
            "Most recent transaction must be first in filtered results"
        )
        assert txns[-1]["date"] == "2026-04-01", (
            "Oldest transaction must be last in filtered results"
        )

    def test_get_recent_transactions_amounts_have_rupee_symbol(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (75.50, "Food", "2026-04-10", "a"),
        ])

        txns = get_recent_transactions(uid, date_from="2026-04-01", date_to="2026-04-30")
        for txn in txns:
            assert txn["amount"].startswith("₹"), (
                f"Transaction amount '{txn['amount']}' must start with ₹"
            )

    # --- get_category_breakdown ---

    def test_get_category_breakdown_filtered_by_date(self, db_file):
        """Categories must only reflect expenses within the requested date range."""
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (100.00, "Food",      "2026-03-01", "Mar food — outside"),
            (200.00, "Transport", "2026-04-10", "Apr transport — inside"),
            (100.00, "Bills",     "2026-04-20", "Apr bills — inside"),
        ])

        cats = get_category_breakdown(uid, date_from="2026-04-01", date_to="2026-04-30")
        names = [c["name"] for c in cats]
        assert "Transport" in names, "Transport (April) must appear in filtered breakdown"
        assert "Bills" in names, "Bills (April) must appear in filtered breakdown"
        assert "Food" not in names, (
            "March Food expense must be excluded by the date filter"
        )

    def test_get_category_breakdown_no_filter_includes_all(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (100.00, "Food",  "2026-01-01", "Jan"),
            (200.00, "Bills", "2026-06-01", "Jun"),
        ])

        cats = get_category_breakdown(uid)
        names = [c["name"] for c in cats]
        assert "Food" in names, "Unfiltered breakdown must include Food"
        assert "Bills" in names, "Unfiltered breakdown must include Bills"

    def test_get_category_breakdown_empty_range_returns_empty_list(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (100.00, "Food", "2026-01-01", "Jan"),
        ])

        cats = get_category_breakdown(uid, date_from="2026-06-01", date_to="2026-06-30")
        assert cats == [], "No expenses in range must return empty category breakdown list"

    def test_get_category_breakdown_percentages_sum_to_100(self, db_file):
        """With a date filter active, category percentages must still sum to exactly 100."""
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (300.00, "Food",      "2026-04-01", "a"),
            (150.00, "Transport", "2026-04-10", "b"),
            (50.00,  "Health",    "2026-04-20", "c"),
        ])

        cats = get_category_breakdown(uid, date_from="2026-04-01", date_to="2026-04-30")
        total_pct = sum(c["pct"] for c in cats)
        assert total_pct == 100, (
            f"Category percentages must sum to 100 with active date filter, got {total_pct}"
        )

    def test_get_category_breakdown_amounts_have_rupee_symbol(self, db_file):
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (200.00, "Food", "2026-04-10", "a"),
        ])

        cats = get_category_breakdown(uid, date_from="2026-04-01", date_to="2026-04-30")
        for cat in cats:
            assert cat["amount"].startswith("₹"), (
                f"Category amount '{cat['amount']}' must start with ₹"
            )

    def test_get_category_breakdown_ordered_by_amount_descending(self, db_file):
        """Categories must be ordered from highest to lowest total amount."""
        uid = db_file["user_id"]
        _insert_expenses(db_file["path"], uid, [
            (50.00,  "Health",    "2026-04-01", "smallest"),
            (300.00, "Food",      "2026-04-05", "largest"),
            (100.00, "Transport", "2026-04-10", "middle"),
        ])

        cats = get_category_breakdown(uid, date_from="2026-04-01", date_to="2026-04-30")
        amounts = [float(c["amount"].replace("₹", "")) for c in cats]
        assert amounts == sorted(amounts, reverse=True), (
            "Category breakdown must be ordered highest amount first"
        )
        assert cats[0]["name"] == "Food", "Highest-spend category must appear first"


# ---------------------------------------------------------------------------
# Template / HTML landmark checks
# ---------------------------------------------------------------------------

class TestTemplateRendering:
    def test_profile_renders_date_input_fields(self, client, app):
        """The filter bar must contain <input type='date'> fields for the custom range."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile")
        data = response.data.decode("utf-8")
        assert 'type="date"' in data or "type='date'" in data, (
            "Profile page must contain <input type='date'> fields for the custom range filter bar"
        )

    def test_profile_renders_filter_param_names(self, client, app):
        """The filter bar HTML must reference 'date_from' and 'date_to' param names."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile")
        data = response.data.decode("utf-8")
        assert "date_from" in data, "Template must reference 'date_from' param in filter bar"
        assert "date_to" in data, "Template must reference 'date_to' param in filter bar"

    def test_profile_page_extends_base_template(self, client, app):
        """Profile page must extend base.html — full HTML document with doctype or html tag."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile")
        data = response.data.decode("utf-8")
        assert "<!DOCTYPE html>" in data or "<html" in data, (
            "Profile page must render a full HTML document through base.html"
        )

    def test_profile_filter_bar_contains_all_preset_labels(self, client, app):
        """The filter bar must contain all four preset button/link labels."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile")
        data = response.data.decode("utf-8")
        assert "This Month" in data, "Filter bar must include 'This Month' preset label"
        assert "Last 3 Months" in data, "Filter bar must include 'Last 3 Months' preset label"
        assert "Last 6 Months" in data, "Filter bar must include 'Last 6 Months' preset label"
        assert "All Time" in data, "Filter bar must include 'All Time' preset label"

    def test_profile_all_time_link_has_clean_profile_url(self, client, app):
        """The 'All Time' preset must link to /profile with no query params (clean URL)."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile")
        data = response.data.decode("utf-8")
        assert 'href="/profile"' in data or "href='/profile'" in data, (
            "All Time preset link must point to /profile with no query params"
        )

    def test_profile_active_filter_reflected_in_template_when_custom_range_applied(
        self, client, app
    ):
        """When a custom range is active, its dates appear in the rendered HTML
        (so the template can pre-fill or highlight the active filter)."""
        user_id = _create_user(db_module.DB_PATH)
        _login_session(client, user_id)

        response = client.get("/profile?date_from=2026-02-01&date_to=2026-02-28")
        data = response.data.decode("utf-8")
        assert "2026-02-01" in data, "Active date_from must appear in rendered template"
        assert "2026-02-28" in data, "Active date_to must appear in rendered template"


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------

class TestUserIsolation:
    def test_filter_only_returns_current_users_expenses(self, client, app):
        """Expenses belonging to another user must never appear in the filtered view."""
        user_a = _create_user(db_module.DB_PATH, name="Alice", email="alice@example.com")
        user_b = _create_user(db_module.DB_PATH, name="Bob",   email="bob@example.com")

        _insert_expenses(db_module.DB_PATH, user_a, [(100.00, "Food",  "2026-04-10", "Alice April")])
        _insert_expenses(db_module.DB_PATH, user_b, [(999.00, "Bills", "2026-04-15", "Bob April")])

        _login_session(client, user_a)

        response = client.get("/profile?date_from=2026-04-01&date_to=2026-04-30")
        data = response.data.decode("utf-8")
        assert "100.00" in data, "Alice's own expense must appear in her filtered view"
        assert "999" not in data, "Bob's expense must NOT appear in Alice's filtered view"

    def test_unfiltered_view_only_returns_current_users_expenses(self, client, app):
        """Even without a date filter, only the logged-in user's expenses appear."""
        user_a = _create_user(db_module.DB_PATH, name="Alice", email="alice@example.com")
        user_b = _create_user(db_module.DB_PATH, name="Bob",   email="bob@example.com")

        _insert_expenses(db_module.DB_PATH, user_a, [(50.00,  "Food",  "2026-01-01", "Alice")])
        _insert_expenses(db_module.DB_PATH, user_b, [(777.00, "Bills", "2026-01-02", "Bob")])

        _login_session(client, user_a)

        response = client.get("/profile")
        data = response.data.decode("utf-8")
        assert "50.00" in data, "Alice's expense must appear in her unfiltered view"
        assert "777" not in data, "Bob's expense must NOT appear in Alice's unfiltered view"
