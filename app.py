import os
import sqlite3
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from database.db import get_db, init_db, seed_db, create_user, get_user_by_email
from database.queries import get_user_by_id, get_summary_stats, get_recent_transactions, get_category_breakdown, insert_expense

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

VALID_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def months_ago(reference_date, n):
    m = reference_date.month - n
    y = reference_date.year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return date(y, m, 1).isoformat()


def parse_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        return None

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "GET":
        return render_template("register.html")

    name             = request.form.get("name", "").strip()
    email            = request.form.get("email", "").strip().lower()
    password         = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        flash("All fields are required", "error")
        return render_template("register.html", name=name, email=email)

    if "@" not in email or "." not in email:
        flash("Enter a valid email address", "error")
        return render_template("register.html", name=name, email=email)

    if password != confirm_password:
        flash("Passwords do not match", "error")
        return render_template("register.html", name=name, email=email)

    if len(password) < 8:
        flash("Password must be at least 8 characters", "error")
        return render_template("register.html", name=name, email=email)

    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        flash("Email already registered", "error")
        return render_template("register.html", name=name, email=email)

    flash("Account created! Please sign in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password", "error")
        return render_template("login.html", email=email)

    session.clear()  # prevent session fixation
    session["user_id"]   = user["id"]
    session["user_name"] = user["name"]
    flash(f"Welcome, {user['name']}!", "success")
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect(url_for("landing"))


@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return "Dashboard — coming in Step 4"


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    today = date.today()

    presets = {
        "this_month":    (today.replace(day=1).isoformat(), today.isoformat()),
        "last_3_months": (months_ago(today, 3), today.isoformat()),
        "last_6_months": (months_ago(today, 6), today.isoformat()),
    }

    date_from = parse_date(request.args.get("date_from", "").strip())
    date_to   = parse_date(request.args.get("date_to",   "").strip())

    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.", "error")
        date_from = date_to = None

    if not (date_from and date_to):
        date_from = date_to = None

    user         = get_user_by_id(user_id)
    stats        = get_summary_stats(user_id, date_from, date_to)
    transactions = get_recent_transactions(user_id, date_from=date_from, date_to=date_to)
    categories   = get_category_breakdown(user_id, date_from, date_to)

    return render_template("profile.html",
                           user=user,
                           stats=stats,
                           transactions=transactions,
                           categories=categories,
                           date_from=date_from,
                           date_to=date_to,
                           presets=presets)


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


def _rerender_add_expense(msg, amount_raw, category, date_raw, description):
    flash(msg, "error")
    return render_template(
        "add_expense.html",
        today=date.today().isoformat(),
        categories=VALID_CATEGORIES,
        amount=amount_raw,
        category=category,
        date_val=date_raw,
        description=description,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("add_expense.html", today=date.today().isoformat(), categories=VALID_CATEGORIES)

    user_id = session["user_id"]
    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    date_raw = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return _rerender_add_expense("Amount must be a positive number.", amount_raw, category, date_raw, description)

    if category not in VALID_CATEGORIES:
        return _rerender_add_expense("Please select a valid category.", amount_raw, category, date_raw, description)

    try:
        datetime.strptime(date_raw, "%Y-%m-%d")
    except ValueError:
        return _rerender_add_expense("Please enter a valid date.", amount_raw, category, date_raw, description)

    if len(description) > 200:
        return _rerender_add_expense("Description must be 200 characters or fewer.", amount_raw, category, date_raw, description)

    description = description or None

    insert_expense(user_id, amount, category, date_raw, description)
    flash("Expense added successfully", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5001)
