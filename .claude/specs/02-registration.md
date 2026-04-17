# Spec: Registration

## Overview

Implement user registration so new visitors can create a Spendly account. This step upgrades the existing stub `GET /register` route into a fully functional form that accepts a POST, validates input, hashes the password, and inserts a new row into the `users` table.

On success, the user is shown a success message and redirected to the login page (Post/Redirect/Get pattern). This is the entry point for all authenticated features that follow.

---

## Depends on

- Step 01 — Database setup (`users` table, `get_db()`)

---

## Routes

- `GET /register` — render registration form — public
- `POST /register` — process registration form, insert user, redirect to `/login` — public

---

## Database changes

No new tables or columns.

The existing `users` table:

```
id, name, email, password_hash, created_at
```

covers all requirements.

### New DB helper (`database/db.py`)

```python
create_user(name, email, password)
```

**Responsibilities:**

- Trim and normalize inputs (`name`, `email`)
- Convert `email` to lowercase before storing
- Hash the password using `werkzeug.security.generate_password_hash`
- Insert user using parameterized SQL query
- Return the new user's `id`
- Raise `sqlite3.IntegrityError` if email already exists (UNIQUE constraint)

**Notes:**

- This function must accept **plaintext password only**
- Hashing must happen **inside this function**, not in the route

---

## Templates

### Modify: `templates/register.html`

- Set form:

  ```html
  action="{{ url_for('register') }}" method="post"
  ```

- Add `name` attributes:
  - `name`
  - `email`
  - `password`
  - `confirm_password`

- Add flash message block with categories:
  - `error`
  - `success`

- Preserve user input on validation failure:
  - Keep `name` and `email` values populated
  - Do NOT preserve password fields

- Keep all existing visual design

---

## Files to change

- `app.py`
  - Upgrade `register()` to handle `GET` and `POST`
  - Add validation, flash messages, and redirect logic
  - Follow Post/Redirect/Get pattern

- `database/db.py`
  - Add `create_user()` helper

- `templates/register.html`
  - Wire up form and flash messages
  - Preserve input values

---

## Files to create

None.

---

## New dependencies

No new dependencies.

Uses:

- `werkzeug.security`
- Flask built-ins: `flash`, `redirect`, `url_for`

---

## Rules for implementation

### General

- No SQLAlchemy or ORMs
- Parameterized queries only — never use f-strings in SQL
- Use `url_for()` for all internal links
- All templates must extend `base.html`
- Use CSS variables — never hardcode hex values
- `app.secret_key` must be set (use a hardcoded dev value for now)

---

### Input handling

- Trim whitespace from all inputs before validation
- Normalize email:
  - Convert to lowercase

- Do not modify password input before hashing

---

### Validation (server-side)

Must check:

1. All fields are non-empty
2. Email is in a valid format (basic regex or simple check like presence of `@` and `.`)
3. `password == confirm_password`
4. Password is at least **8 characters long**
5. Email is not already registered (handle `sqlite3.IntegrityError`)

---

### Error handling

- On validation failure:
  - Re-render the form (no redirect)
  - Flash message with category `error`
  - Preserve `name` and `email`

- On DB constraint failure:
  - Flash: `"Email already registered"`
  - Re-render form

---

### Success flow

- On successful registration:
  - Flash message with category `success`
  - Redirect to:

    ```python
    url_for('login')
    ```

- Follow Post/Redirect/Get pattern to prevent duplicate submissions

---

### Security notes

- Passwords must be hashed using `werkzeug.security.generate_password_hash`
- Never store plaintext passwords
- CSRF protection is **not included in this step** and will be added later

---

### Duplicate submission handling

- Duplicate submissions must not create multiple users
- Enforced via UNIQUE constraint on email
- User should see a clear error message if it occurs

---

## Definition of done

- [ ] `GET /register` renders the form without errors
- [ ] Valid submission creates a new user and redirects to `/login`
- [ ] Password is stored as a hash (verified in DB)
- [ ] Mismatched passwords show error, no DB insert
- [ ] Invalid email format shows validation error
- [ ] Short password (<8 chars) shows validation error
- [ ] Duplicate email shows "Email already registered" error
- [ ] Empty fields show validation error
- [ ] Name and email persist on validation failure
- [ ] No duplicate user created on repeated submissions
