# NetSuite Expense Report Filler

Fills a NetSuite expense report **draft** from a CSV file using Selenium.
It never submits the report — you review the draft in the browser and
click Submit / Submit for Supervisor Approval yourself.

This is the successor to an older opportunity-entry automation (same
Selenium pattern, new target: the Expense Report form). Login is
NetSuite SSO with 2FA, done by hand in the browser — the script stores
and types no credentials. NetSuite has no API access for this workflow, so
the form is filled through the browser, using stable field selectors
(`data-field-name` sublist cells and input ids) instead of absolute
xpaths.

## How it works

1. Opens its own Chrome window (or re-attaches to it from an earlier
   run, so your login is kept). You log in via SSO + 2FA there.
2. Waits until you open a **new, blank** Expense Report, then starts
   on its own — no keypress needed.
3. Fills the header date and report name.
   Report naming convention (per internal procedure):
   `First Initial Last Name Week Ending MM/DD/YY`
   (e.g. `JSmith Week Ending 10/31/26`)
4. For each CSV row, fills: date, category, amount, business reason,
   memo/vendor, department check, optional project + project task,
   optional EBITDA add-back, then uploads the receipt and clicks Add.
5. Stops before submitting. Browser stays open for your review.

Key field behaviours discovered from the live form:

- **Category** is a popupselect/autocomplete ("Type then tab"): type,
  Tab to commit, verify the hidden value input got a value.
- **Business Reason** is the custom field `custcol_reason` (max 300 chars).
- **Memo/Vendor**: the sublist memo input shares `id="memo"` with the
  header memo field, so line fields are scoped to their sublist cell
  (`td[data-field-name="memo"]`), never by bare id.
- **Ref No** and **Billing Subsidiary** are auto-filled and skipped.
- **Department** defaults to Sales and Marketing; the script verifies
  it and only changes it if the CSV asks for something else.
- **Project / Project Task** are only for billable work, and NetSuite
  requires both together — the script refuses a project without a task.
- **EBITDA Add-back** is only for CaST executive-management lines
  (value "Yes"); otherwise leave it blank.
- **Attach File** is not a direct file input: it opens a popup window
  (Attach From = Computer, Select File, Save in the popup). The popup
  Save is a file-upload save, not the report submit.

## Setup

```bash
python -m pipenv install
cp .env.example .env   # NetSuite URL only — no username/password (SSO)
```

Never commit `.env` — it is already in `.gitignore`.

Note for Windows: the commands in this README use `python -m pipenv ...`
rather than bare `pipenv ...`, because pipenv is often not on PATH on
Windows and `python -m pipenv` is the reliable invocation there.

Python version: the Pipfile deliberately does **not** pin a Python
version. The old project's `python_version = "3.10"` pin would have made
pipenv refuse a newer interpreter, so it was dropped — this code needs
only Python 3.10+ and works with 3.14 as well. `python -m pipenv install`
simply uses whichever Python you run it with.

## Usage

## Trip-folder workflow (the usual way to run it)

Download the trip's receipt images/PDFs and the expense CSV into one
folder — e.g. `OneDrive > Documents > Expense Reports > 2026_10_MSP` —
then point the script at that folder. It finds the single CSV in the
folder and takes the receipts from the same folder, so there is no
separate receipts subfolder to manage:

```bash
python -m pipenv run python netsuite_expense_filler.py "C:\Users\dfolkner\OneDrive - Vertech\Documents\Expense Reports\2026_10_MSP" \
  --report-name "DFolkner Week Ending 10/31/26"
```

## Pre-trip / post-trip split

Per policy, a receipt must be submitted BEFORE the trip, so one trip
folder can hold two reports: `pre-trip-expenses.csv` (airfare + prepaid,
filed before departure) and `post-trip-expenses.csv` (hotel, meals,
ground, filed after return). Use `--phase` to pick one from a folder:

```bash
python -m pipenv run python netsuite_expense_filler.py "C:\Users\dfolkner\OneDrive - Vertech\Documents\Expense Reports\2026_12_Phx" \
  --phase pre-trip --report-name "DFolkner Week Ending 12/05/26"
```

A trip can need several submittals for the same phase (weekly
submittals as receipts come in). Numbered siblings are supported:
`pre-trip-expenses-2.csv`, `pre-trip-expenses-3.csv`, ... — the
unnumbered file counts as submittal 1. With exactly one candidate,
`--phase` alone picks it; with several, add `--number N`:

```bash
python -m pipenv run python netsuite_expense_filler.py "C:\Users\dfolkner\OneDrive - Vertech\Documents\Expense Reports\2026_12_Phx" \
  --phase pre-trip --number 2 --report-name "DFolkner Week Ending 12/12/26"
```

A pre-trip run also warns (without blocking) if the report date is on
or after the first expense date in the CSV. Passing a CSV file directly
always works, with or without `--phase`.

## Default folders and submittal zips

Prepared submittals arrive as a zip in the Downloads folder. The
script can extract one into the trip folder first, so a prepared
submittal is a single command. `--trip NAME` names the trip folder
under the expense-reports root; `--extract [ZIP]` extracts the newest
`.zip` in Downloads (or the ZIP named) into it:

```bash
python -m pipenv run python netsuite_expense_filler.py --trip "2026_12_PHX Christmas" \
  --extract --phase pre-trip --report-name "DFolkner Week Ending 12/05/26"
```

Folder defaults come from `.env` (never hard-coded): set
`EXPENSE_REPORTS_ROOT` and `EXPENSE_DOWNLOADS_DIR` there; without
them the defaults are `~/Documents/Expense Reports` and `~/Downloads`.
`--expense-root` / `--downloads-dir` override them per run. Extraction
is the only write the script does outside NetSuite, and it happens
only when `--extract` is passed.

Rules and notes:
- A folder without `--phase` must contain **exactly one** `.csv` file.
  Receipt images and PDFs sitting alongside it are ignored by the
  folder scan. If there are two CSVs, the script stops and names them
  — pass the CSV file itself, or add `--phase pre-trip` /
  `--phase post-trip`, in that case.
- Passing a CSV file also works, and receipts then default to the
  CSV's own folder: `--receipts-dir` is only needed if the receipts
  live somewhere else.
- The script reads and checks the CSV **before** opening the browser,
  and warns up front about any receipt files named in the CSV that
  are missing from the folder (those lines are entered without an
  attachment, as before).
- If the folder is on OneDrive, make sure the files are downloaded
  locally (not cloud-only placeholders) before running — the browser
  upload needs a real local file path.
- `.env` lives in the repo folder, not the trip folder. The script
  looks for it next to itself if it is not found in the folder you
  run from.

## Other usage

```bash
python -m pipenv run python netsuite_expense_filler.py sample_expenses.csv \
  --report-name "JSmith Week Ending 01/17/26" \
  --receipts-dir receipts
```

- `sample_expenses.csv` is **random sample data only** — replace it with
  your own CSV in the same columns.
- Put your receipt files in the `--receipts-dir` folder, named per the
  internal procedure: `XX_MM.DD.YY_Vendor_Amount`
  (e.g. `XX_01.25.26_SampleVendor_15.45.pdf`).
- CSV columns: `date,category,amount,business_reason,memo_vendor,`
  `department,project,project_task,ebitda_addback,receipt_file`
- Leave `project`, `project_task`, and `ebitda_addback` blank unless
  they apply to that line.

## Tests

Tests live in `tests/` and need pytest, which is a dev dependency —
plain `pipenv install` won't necessarily include it, so install dev
dependencies first. `tests/test_dependencies.py` is a separate check
that the real selenium + python-dotenv packages are actually installed
(it does not use the stubs the offline tests use, so it fails loudly
with the install command if they are missing — the usual fresh-checkout
problem):

```bash
python -m pipenv install --dev
python -m pipenv run python -m pytest tests/ -v
# or, without pytest:
python -m pipenv run python -m unittest discover tests -v
```

Tests cover only offline logic (CSV parsing, totals, selector building,
business-reason length) — they do not touch NetSuite or a browser.

## Safety

- No credentials anywhere: login is SSO + 2FA by hand. `.env` holds
  only the NetSuite URL and is gitignored.
- No real expenses, receipts, or employee data in the repo — the sample
  CSV and example names are fictional.
- The script stops before submitting; a failed field, a failed category
  commit, or an upload popup that does not close all stop the run with
  the browser left open for you to inspect.
