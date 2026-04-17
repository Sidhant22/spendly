Here’s your **updated, cleaned, production-safe spec** with all necessary fixes baked in. You can **replace your current spec entirely with this** 👇

---

# Spec: Login and Logout

## Overview

Implement user login and logout so registered users can authenticate into Spendly and end their session.

This step upgrades the existing stub `GET /login` route into a full `POST` handler that validates credentials, sets a session on success, and redirects to a dashboard placeholder. The `GET /logout` stub is replaced with a route that clears the session and redirects to the landing page.

Authentication must follow secure session practices (including session reset on login) and the Post/Redirect/Get pattern. These routes gate all future authenticated features.

---

## Depends on

- Step 01 — Database setup (`users` table, `get_db()`)
- Step 02 — Registration (`create_user`, hashed passwords stored)

---

## Routes

- `GET /login` — render login form — public
- `POST /login` — validate credentials, set session, redirect to `/dashboard` — public
- `GET /logout` — clear session, redirect to `/` — public (must work even if not logged in)

---

## Database changes

No new tables or columns.

### New DB helper (`database/db.py`)

```python
get_user_by_email(email) -> sqlite3.Row | None
```

**Responsibilities:**

- Look up a user row by email (case-insensitive)
- Use explicit column selection (no `SELECT *`)
- Return the row or `None` if not found

**Query requirements:**

```sql
SELECT id, name, email, password_hash
FROM users
WHERE LOWER(email) = ?
```

---

## Templates

### Modify: `templates/login.html`

- Change form action:

  ```html
  action="{{ url_for('login') }}" method="post"
  ```

- Ensure flash messages render correctly with categories:
  - `error`
  - `success`

- Preserve email input on failed login:

  ```html
  value="{{ email or '' }}"
  ```

- Do NOT preserve password field

---

## Files to change

### `app.py`

- Upgrade `login()` to handle `GET` and `POST`
- Implement `logout()` (replace stub)
- Import:

  ```python
  from werkzeug.security import check_password_hash
  from flask import session
  ```

### `database/db.py`

- Add `get_user_by_email(email)`

### `templates/login.html`

- Wire form to `url_for('login')`
- Preserve email value
- Ensure flash messages display

---

## Files to create

None.

---

## New dependencies

No new dependencies.

Uses:

- `werkzeug.security.check_password_hash`
- Flask: `session`, `flash`, `redirect`, `url_for`

---

## Rules for implementation

### General

- No SQLAlchemy or ORMs
- Parameterised queries only — never use f-strings in SQL
- Use `url_for()` for all internal links
- All templates extend `base.html`
- Use CSS variables — never hardcode hex values

---

### Input handling

- Always use:

  ```python
  request.form.get("field", "")
  ```

- Trim and normalize email:
  - `strip()` whitespace
  - convert to lowercase

- Do not modify password input

---

### Authentication logic

- Fetch user using `get_user_by_email(email)`
- If user is `None`, treat as invalid login
- If user exists:
  - Validate password using `check_password_hash`

- Never distinguish between:
  - "email not found"
  - "wrong password"

Always return:

```text
"Invalid email or password"
```

---

### Error handling

- On failed login:
  - Flash `"Invalid email or password"` with category `error`
  - Immediately re-render `login.html`
  - Preserve email field

---

### Success flow (Login)

On successful authentication:

```python
session.clear()  # prevent session fixation
session["user_id"] = user["id"]
session["user_name"] = user["name"]
```

- Optionally:

  ```python
  session.permanent = True
  ```

- Flash optional success message (optional)

- Redirect to:

  ```python
  url_for("dashboard")
  ```

- Follow Post/Redirect/Get pattern

---

### Session behavior

- Session must store:
  - `user_id`
  - `user_name`

- If a logged-in user visits `/login`:
  - Redirect to `/dashboard`
  - Do not render login form again

---

### Logout behavior

- `GET /logout` must:
  - Always call `session.clear()`
  - Never fail if user is not logged in
  - Optionally flash `"You have been logged out"` with category `success`
  - Redirect to `/`

---

### Security notes

- Use `check_password_hash` for verification
- Never store or compare plaintext passwords
- Clear session before setting new session values (prevents session fixation)

---

## Definition of done

- [ ] `GET /login` renders the form without errors
- [ ] Valid credentials set session and redire`
- [ ] Session contains `user_id` and `user_name` after login
- [ ] Invalid email shows `"Invalid email or password"`
- [ ] Wrong password shows `"Invalid email or password"`
- [ ] No stack traces or sensitive info exposed
- [ ] Email field is preserved after failed login
- [ ] Email input is trimmed and lowercased before lookup
- [ ] Visiting `/login` while logged in redirects to `/`
- [ ] Session is cleared before setting new login session
- [ ] `GET /logout` clears session and redirects to `/`
- [ ] Visiting `/logout` when not logged in works without error
- [ ] Flash message from registration appears on login page after redirect
- [ ] Session persists across requests after login
