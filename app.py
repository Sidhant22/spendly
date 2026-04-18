import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from database.db import get_db, init_db, seed_db, create_user, get_user_by_email

app = Flask(__name__)
app.secret_key = "dev-secret-key"

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

    user = {
        "name": session["user_name"],
        "email": "demo@spendly.com",
        "member_since": "January 2026",
    }

    stats = {
        "total_spent": "₹320.74",
        "transaction_count": 8,
        "top_category": "Bills",
    }

    transactions = [
        {"date": "Apr 11, 2026", "description": "Miscellaneous",          "category": "Other",         "amount": "₹9.50"},
        {"date": "Apr 10, 2026", "description": "Restaurant dinner",       "category": "Food",          "amount": "₹22.75"},
        {"date": "Apr 08, 2026", "description": "New shoes",               "category": "Shopping",      "amount": "₹65.00"},
        {"date": "Apr 06, 2026", "description": "Streaming subscription",  "category": "Entertainment", "amount": "₹15.99"},
        {"date": "Apr 05, 2026", "description": "Pharmacy",                "category": "Health",        "amount": "₹30.00"},
        {"date": "Apr 03, 2026", "description": "Electricity bill",        "category": "Bills",         "amount": "₹120.00"},
        {"date": "Apr 02, 2026", "description": "Bus pass top-up",         "category": "Transport",     "amount": "₹12.00"},
        {"date": "Apr 01, 2026", "description": "Weekly groceries",        "category": "Food",          "amount": "₹45.50"},
    ]

    categories = [
        {"name": "Bills",         "amount": "₹120.00", "pct": 37},
        {"name": "Food",          "amount": "₹68.25",  "pct": 21},
        {"name": "Shopping",      "amount": "₹65.00",  "pct": 20},
        {"name": "Health",        "amount": "₹30.00",  "pct": 9},
        {"name": "Entertainment", "amount": "₹15.99",  "pct": 5},
        {"name": "Transport",     "amount": "₹12.00",  "pct": 4},
        {"name": "Other",         "amount": "₹9.50",   "pct": 3},
    ]

    return render_template("profile.html",
                           user=user,
                           stats=stats,
                           transactions=transactions,
                           categories=categories)


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
