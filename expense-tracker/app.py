"""Personal expense tracker: Flask + SQLite JSON API, with a plain HTML/JS frontend in static/."""
import os
import re
import sqlite3
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Flask, g, jsonify, request

CATEGORIES = ["Food", "Transport", "Shopping", "Bills", "Entertainment", "Other"]
MIN_DATE = date(2000, 1, 1)  # reject typos like year 0008
MAX_AMOUNT_PAISE = 10_000_000_00  # 1 crore rupees; guards against typos like an extra zero run
DB_PATH = os.environ.get("EXPENSES_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "expenses.db"))

app = Flask(__name__, static_folder="static", static_url_path="")

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL CHECK (length(title) BETWEEN 1 AND 100),
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    category     TEXT    NOT NULL CHECK (category IN ('Food','Transport','Shopping','Bills','Entertainment','Other')),
    date         TEXT    NOT NULL,              -- ISO YYYY-MM-DD, sorts correctly as text
    note         TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
"""


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.close()


def error(message, status=400, fields=None):
    return jsonify({"error": message, "fields": fields or {}}), status


def parse_date(value):
    """Strict YYYY-MM-DD. Returns a date or None."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def to_paise(value):
    """Accepts a number or plain decimal string with at most 2 decimals. Returns int paise or None."""
    if isinstance(value, bool) or value is None:
        return None
    s = str(value).strip()
    # Plain decimals only: no exponent notation, no "Infinity"/"NaN", bounded length so Decimal math is safe.
    if len(s) > 20 or not re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)", s):
        return None
    d = Decimal(s)
    if d != d.quantize(Decimal("0.01")):
        return None
    return int(d * 100)


def validate(payload):
    """Returns (clean_dict, errors_dict)."""
    if not isinstance(payload, dict):
        return None, {"_": "Request body must be a JSON object."}
    errors, clean = {}, {}

    title = payload.get("title")
    title = title.strip() if isinstance(title, str) else ""
    if not title:
        errors["title"] = "Title is required."
    elif len(title) > 100:
        errors["title"] = "Title must be 100 characters or fewer."
    elif all(unicodedata.category(ch)[0] in "PZC" for ch in title):
        # only punctuation, quotes, spaces or control characters, e.g. '" "' or '...'
        errors["title"] = "Title must include at least one letter, number, or symbol."
    clean["title"] = title

    paise = to_paise(payload.get("amount"))
    if paise is None:
        errors["amount"] = "Enter a valid amount with at most 2 decimal places."
    elif paise <= 0:
        errors["amount"] = "Amount must be greater than zero."
    elif paise > MAX_AMOUNT_PAISE:
        errors["amount"] = "Amount is too large."
    clean["amount_paise"] = paise

    category = payload.get("category")
    if not category:
        errors["category"] = "Select a category."
    elif category not in CATEGORIES:
        errors["category"] = "Choose one of: " + ", ".join(CATEGORIES) + "."
    clean["category"] = category

    raw_date = payload.get("date") or date.today().isoformat()
    d = parse_date(raw_date)
    if d is None:
        errors["date"] = "Enter a valid date (YYYY-MM-DD)."
    if d and d > date.today():
        errors["date"] = "Date can't be in the future."
    elif d and d < MIN_DATE:
        errors["date"] = "Date can't be before 1 January 2000."
    clean["date"] = d.isoformat() if d else None

    note = payload.get("note") or ""
    if not isinstance(note, str):
        errors["note"] = "Note must be text."
    elif len(note) > 1000:
        errors["note"] = "Note must be 1000 characters or fewer."
    clean["note"] = note.strip() if isinstance(note, str) else ""

    return clean, errors


def row_to_dict(r):
    return {
        "id": r["id"],
        "title": r["title"],
        "amount": f"{r['amount_paise'] / 100:.2f}",
        "category": r["category"],
        "date": r["date"],
        "note": r["note"],
    }


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/categories")
def categories():
    return jsonify(CATEGORIES)


@app.get("/api/expenses")
def list_expenses():
    category = request.args.get("category", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()
    q = request.args.get("q", "").strip()

    where, params = [], []
    if category:
        if category not in CATEGORIES:
            return error("Unknown category.", fields={"category": "Unknown category."})
        where.append("category = ?")
        params.append(category)
    for key, value, op in (("from", date_from, ">="), ("to", date_to, "<=")):
        if value:
            d = parse_date(value)
            if d is None:
                return error("Invalid date.", fields={key: "Enter a valid date."})
            where.append(f"date {op} ?")
            params.append(d.isoformat())
    if date_from and date_to and date_from > date_to:
        return error("'From' date is after 'To' date.", fields={"from": "Must not be after the 'To' date."})
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append("title LIKE ? ESCAPE '\\'")
        params.append(f"%{escaped}%")

    sql = "SELECT * FROM expenses"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY date DESC, id DESC"
    rows = db().execute(sql, params).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.post("/api/expenses")
def create_expense():
    clean, errors = validate(request.get_json(silent=True))
    if errors:
        return error("Please fix the highlighted fields.", fields=errors)
    cur = db().execute(
        "INSERT INTO expenses (title, amount_paise, category, date, note) VALUES (?,?,?,?,?)",
        (clean["title"], clean["amount_paise"], clean["category"], clean["date"], clean["note"]),
    )
    db().commit()
    row = db().execute("SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.put("/api/expenses/<int:expense_id>")
def update_expense(expense_id):
    clean, errors = validate(request.get_json(silent=True))
    if errors:
        return error("Please fix the highlighted fields.", fields=errors)
    cur = db().execute(
        "UPDATE expenses SET title=?, amount_paise=?, category=?, date=?, note=? WHERE id=?",
        (clean["title"], clean["amount_paise"], clean["category"], clean["date"], clean["note"], expense_id),
    )
    db().commit()
    if cur.rowcount == 0:
        return error("Expense not found.", 404)
    row = db().execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    return jsonify(row_to_dict(row))


@app.delete("/api/expenses/<int:expense_id>")
def delete_expense(expense_id):
    cur = db().execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    db().commit()
    if cur.rowcount == 0:
        return error("Expense not found.", 404)
    return "", 204


@app.get("/api/years")
def years():
    """Years that have expenses, plus the current year, newest first."""
    rows = db().execute("SELECT DISTINCT substr(date, 1, 4) AS y FROM expenses").fetchall()
    ys = {int(r["y"]) for r in rows} | {date.today().year}
    return jsonify(sorted(ys, reverse=True))


@app.get("/api/summary")
def summary():
    """Total and per-category breakdown for ?month=YYYY-MM, ?year=YYYY, or (default) the current month."""
    month = request.args.get("month", "")
    year = request.args.get("year", "")
    if month:
        if not re.fullmatch(r"\d{4}-\d{2}", month) or parse_date(month + "-01") is None:
            return error("month must be YYYY-MM.")
        y, m = int(month[:4]), int(month[5:])
        start, end = date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1)
        period = month
    elif year:
        if not re.fullmatch(r"\d{4}", year) or not 1 <= int(year) <= 9998:
            return error("year must be YYYY.")
        start, end = date(int(year), 1, 1), date(int(year) + 1, 1, 1)
        period = year
    else:
        today = date.today()
        start, end = date(today.year, today.month, 1), date(today.year + (today.month == 12), today.month % 12 + 1, 1)
        period = start.strftime("%Y-%m")
    rows = db().execute(
        "SELECT category, SUM(amount_paise) AS paise, COUNT(*) AS n FROM expenses "
        "WHERE date >= ? AND date < ? GROUP BY category ORDER BY paise DESC",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    total = sum(r["paise"] for r in rows)
    return jsonify({
        "period": period,
        "total": f"{total / 100:.2f}",
        "count": sum(r["n"] for r in rows),
        "by_category": [
            {"category": r["category"], "total": f"{r['paise'] / 100:.2f}",
             "percent": round(r["paise"] * 100 / total, 1) if total else 0}
            for r in rows
        ],
    })


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
