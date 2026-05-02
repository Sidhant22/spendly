from database.db import get_db
from datetime import datetime


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    dt = datetime.strptime(row["created_at"][:10], "%Y-%m-%d")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": dt.strftime("%B %Y"),
    }


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()
    sql_base = "WHERE user_id = ?"
    params = [user_id]
    if date_from and date_to:
        sql_base += " AND date BETWEEN ? AND ?"
        params += [date_from, date_to]
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt FROM expenses " + sql_base,
        params
    ).fetchone()
    top = conn.execute(
        "SELECT category, SUM(amount) AS s FROM expenses " + sql_base +
        " GROUP BY category ORDER BY s DESC LIMIT 1",
        params
    ).fetchone()
    conn.close()
    return {
        "total_spent": f"₹{row['total']:.2f}",
        "transaction_count": row["cnt"],
        "top_category": top["category"] if top else "—",
    }


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()
    sql_base = "WHERE user_id = ?"
    params = [user_id]
    if date_from and date_to:
        sql_base += " AND date BETWEEN ? AND ?"
        params += [date_from, date_to]
    rows = conn.execute(
        "SELECT date, description, category, amount FROM expenses " +
        sql_base + " ORDER BY date DESC, id DESC LIMIT ?",
        params + [limit]
    ).fetchall()
    conn.close()
    return [
        {
            "date": row["date"],
            "description": row["description"] or "",
            "category": row["category"],
            "amount": f"₹{row['amount']:.2f}",
        }
        for row in rows
    ]


def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()
    sql_base = "WHERE user_id = ?"
    params = [user_id]
    if date_from and date_to:
        sql_base += " AND date BETWEEN ? AND ?"
        params += [date_from, date_to]
    rows = conn.execute(
        "SELECT category, SUM(amount) AS total FROM expenses " + sql_base +
        " GROUP BY category ORDER BY total DESC",
        params
    ).fetchall()
    conn.close()
    if not rows:
        return []
    grand = sum(r["total"] for r in rows)
    result = [
        {"name": r["category"], "amount": f"₹{r['total']:.2f}", "pct": round(r["total"] / grand * 100)}
        for r in rows
    ]
    diff = 100 - sum(item["pct"] for item in result)
    result[0]["pct"] += diff
    return result


def insert_expense(user_id, amount, category, expense_date, description):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, expense_date, description),
        )
    conn.close()
