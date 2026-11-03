# NetSuite Expense Report Filler

Fills a NetSuite expense report **draft** from a CSV file using Selenium.
It never submits the report — you review the draft in the browser and
click Submit / Submit for Supervisor Approval yourself.

This is the successor to an older opportunity-entry automation (same
Selenium + `.env` login + manual 2FA-pause pattern, new target: the
Expense Report form). NetSuite has no API access for this workflow, so
the form is filled through the browser, using stable field selectors
(`data-field-name` sublist cells and input ids) instead of absolute
xpaths.

## How it works

1. Logs in to NetSuite (SAML, then pauses for you to complete 2FA manually).
2. Pauses again so you open a blank Expense Report.
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
cp .env.example .env   # edit .env with your NetSuite URL / username / password
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

```bash
python -m pipenv run python -m pytest tests/ -v
# or, without pytest:
python -m pipenv run python -m unittest discover tests -v
```

Tests cover only offline logic (CSV parsing, totals, selector building,
business-reason length) — they do not touch NetSuite or a browser.

## Safety

- No credentials in the repo; `.env` is gitignored.
- No real expenses, receipts, or employee data in the repo — the sample
  CSV and example names are fictional.
- The script stops before submitting; a failed field, a failed category
  commit, or an upload popup that does not close all stop the run with
  the browser left open for you to inspect.
