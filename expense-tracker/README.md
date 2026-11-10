# Expense tracker

A small personal expense tracker. You add expenses, edit or delete them, filter the list, and see the total and per-category breakdown for any month or year (the current month by default). It runs locally with no accounts and no deployment.

## How to run

You need Python 3.9 or newer. From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000. On Windows, use `python` instead of `python3`. The SQLite database (`expenses.db`) is created automatically on first start. To use another port, run `PORT=8000 python3 app.py` (in Windows PowerShell: `$env:PORT=8000; python app.py`). To use a different database file, set `EXPENSES_DB=/path/to/file.db`.

## Stack and tradeoffs

The backend is Flask with Python's built-in `sqlite3` module, and the frontend is a single HTML page with plain JavaScript and no build step. I chose Flask because it is small enough to read in one sitting and I can move fast in it. SQLite gives real constraints and date-range queries without a separate server, which a JSON file would not. The frontend has no framework because the UI is one form, one filter bar, and one table, so a framework would add a build step and more setup for whoever runs this, with little benefit. The cost is some manual DOM code in `app.js`, which would get tedious if the UI grew.

Amounts are stored as integer paise (1/100 of a rupee) rather than floats, so totals never drift by fractions of a paisa. The API accepts and returns amounts as two-decimal strings and the UI formats them as INR. Dates are stored as ISO `YYYY-MM-DD` text, which sorts and compares correctly and avoids timezone surprises since an expense date has no time of day. Filtering happens in SQL, not in the browser, and the monthly summary is computed by the server with a single `GROUP BY` query.

Each expense has an auto-incrementing integer `id` as its primary key. The table also has CHECK constraints on title length, a positive amount, and the six allowed categories, so the database rejects bad data even if the application's validation were bypassed.

## What is done

Everything in the brief is implemented: add, list (newest first, all fields shown), edit, delete, the summary (current month by default, with month and year switching), and filters by category, from/to date, and partial title match. Filters combine, and they apply as you type.

Validation runs on the server, which is the source of truth, and errors are shown next to the field that caused them. The rules: the title is required, at most 100 characters, and must contain at least one letter, number, or symbol such as ₹ or an emoji (a title made up only of spaces, quotation marks, or other punctuation is rejected); the amount must be greater than zero, have at most two decimals, and stay below a sanity cap of 1 crore; the category must be one of the six (the form starts on "Select a category", so one has to be chosen); the date must be a real calendar date (so 30 February is rejected), cannot be in the future or before 1 January 2000 (this catches typos like year 0008), and defaults to today; the note is optional and at most 1000 characters.

Edge cases handled: empty states for both "no expenses yet" and "nothing matches these filters", a "From" date later than the "To" date (rejected with a clear message), a title search containing `%` or `_` (escaped, so it matches literally), and user text rendered with `textContent` so a title like `<script>` cannot inject markup. Delete asks for confirmation. The month summary shows a friendly message when nothing has been spent yet.

## What I skipped, and why

I skipped authentication and multi-user support, deployment, and tests, as the brief said they do not matter. I also left out pagination (fine for personal use, but a very long list would load all at once), CSV export, recurring expenses, and budgets.

## Known rough edges

The currency is hard-coded to INR in `static/app.js`; changing it means editing one line. "Today" for the form default comes from the browser's clock, while "current month" for the summary comes from the server's clock, so they could disagree briefly around midnight if the two were in different timezones (they are the same machine here). Expenses cannot be dated in the future; if you need to log upcoming payments, that rule is one check in `validate()` in `app.py`. The edit form reuses the add form at the top of the page, so on a long list you are scrolled up to it when you click Edit. Title search is case-insensitive for English letters only (a SQLite LIKE limitation), so accented letters match case-sensitively. The Flask server is the development server, which is fine for a local single-user app but not for production.

## Project layout

```
expense-tracker/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
└── static/
    ├── index.html
    ├── style.css
    └── app.js
```

`expenses.db` is created automatically on first run. `app.py` holds the API, validation, and schema, and the three files in `static/` hold the frontend. API routes are `GET/POST /api/expenses`, `PUT/DELETE /api/expenses/<id>`, `GET /api/summary` (accepts `?month=YYYY-MM` or `?year=YYYY`), `GET /api/years`, and `GET /api/categories`.