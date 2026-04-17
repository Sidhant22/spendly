import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash
from database.db import get_db, init_db, seed_db, create_user

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


@app.route("/login")
def login():
    return render_template("login.html")


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
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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
