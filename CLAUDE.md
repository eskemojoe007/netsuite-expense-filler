# CLAUDE.md — NetSuite Expense Report Filler

## What this is

A Selenium script that fills a NetSuite expense report **draft** from a CSV
file. It is the successor to an older, separate automation that filled
NetSuite *opportunity* records — same pattern (Selenium + `.env` login +
manual 2FA pause), new target: the Expense Report form.

The reason this exists: Vertech expense reports are entered manually in a
NetSuite web portal with **no API access**. The only route is the browser.

## The one safety rule

**The script NEVER submits the report.** It fills the draft, stops, and
leaves the browser open. A human reviews the draft and clicks Submit /
Submit for Supervisor Approval themselves. Any failure (a field that
won't commit, a category that won't resolve, an upload popup that won't
close) also stops the run with the browser left open — never force past
it, never submit to "finish up".

## How to run it

Environment: Windows, Python 3.14. `pipenv` is often not on PATH on
Windows, so every command uses `python -m pipenv`:

```bash
python -m pipenv install          # runtime deps
python -m pipenv install --dev    # + pytest, for tests
cp .env.example .env              # then fill in NETSUITE_URL / USERNAME / PASSWORD
```

`.env` lives in the repo folder, not in a trip folder. The script looks
for it in the working directory first, then next to itself. Never commit
`.env` — it is gitignored.

### Trip-folder workflow (the usual way to run it)

Download the trip's receipt images/PDFs and the expense CSV into one
folder, e.g. `OneDrive > Documents > Expense Reports > 2026_10_MSP`,
then point the script at that folder:

```bash
python -m pipenv run python netsuite_expense_filler.py "C:\Users\dfolkner\OneDrive - Vertech\Documents\Expense Reports\2026_10_MSP" --report-name "DFolkner Week Ending 10/31/26"
```

- The folder must contain exactly **one** `.csv`. Receipt images/PDFs
  alongside it are ignored by the folder scan. Two CSVs → the script
  stops and names them; pass the CSV file itself in that case.
- Passing a CSV file also works; receipts then default to the CSV's
  own folder. `--receipts-dir` overrides either mode.
- The CSV is read and checked **before** the browser opens. Missing
  receipt files are warned about up front; those lines are entered
  without an attachment (same as the per-line warning during a run).
- OneDrive folders: files must be downloaded locally, not cloud-only
  placeholders, or the browser upload cannot read them.

### Other usage

```bash
python -m pipenv run python netsuite_expense_filler.py sample_expenses.csv \
  --report-name "JSmith Week Ending 01/17/26" \
  --receipts-dir receipts
```

- `--report-name` is required. Naming convention (per internal
  procedure): `First Initial Last Name Week Ending MM/DD/YY`.
- `--report-date` defaults to today (`MM/DD/YYYY`).

## CSV format

Columns: `date,category,amount,business_reason,memo_vendor,department,
project,project_task,ebitda_addback,receipt_file`

- `date`: `MM/DD/YYYY`.
- `category`: the exact NetSuite category label. This is a
  popupselect/autocomplete (see below) — the label must match what
  NetSuite offers, or the commit check fails and the run stops.
- `business_reason`: max **300 chars** (NetSuite custom field
  `custcol_reason`). The script enforces this and stops on overflow.
- `memo_vendor`: vendor name, per procedure (Memo field = vendor name
  for manual entries).
- `department`: defaults to `Sales and Marketing`. The script verifies
  the current value and only changes it if the CSV asks for something
  else (occasional alternative: `Executive Management`).
- `project` / `project_task`: only for billable work. NetSuite requires
  both together — the script refuses a project without a task.
- `ebitda_addback`: `Yes` only for CaST executive-management lines;
  otherwise leave blank.
- `receipt_file`: filename in the receipts folder, named per procedure:
  `XX_MM.DD.YY_Vendor_Amount` (e.g. `XX_01.25.26_SampleVendor_15.45.pdf`).
  Receipts must show vendor name + item details.

`sample_expenses.csv` is **random sample data only** — fictional vendors,
`XX_` receipt names. Replace it with a real CSV in the same columns.
No real expenses, receipts, or employee data belong in this repo.

## How the script works (in order)

1. Logs in to NetSuite (SAML), then **pauses for the user to complete
   2FA manually**. Do not automate the 2FA step.
2. Pauses again so the user opens a **blank** Expense Report.
3. Fills header date + report name.
4. For each CSV row: date, category, amount, business reason,
   memo/vendor, department check, optional project/task, optional
   EBITDA, receipt upload, then clicks Add to commit the line.
5. Stops before submitting. Browser stays open for review.

## Selector strategy — do NOT use absolute xpaths

An earlier version of this work used absolute `/html/body/...` xpaths.
They were replaced deliberately. NetSuite sublist cells carry
`data-field-name` plus stable input ids/names, so every line field is
located through its sublist cell, e.g. `td[data-field-name="category"]
input`. The same selectors work for every row: only the focused/edited
row exposes the display inputs, and clicking Add commits the line and
opens a fresh blank row with the same selectors. No row-indexed xpaths.

Field map (from live Inspect-element HTML, 2026-11-03):

| Field | Selector |
|---|---|
| Header date | `id="trandate"` (main form) |
| Header report name | `form[name="main_form"] input[name="memo"]` |
| Line date | `td[data-field-name="expensedate"] input` |
| Line category | `td[data-field-name="category"] input`, display `id="expense_category_display"`, hidden value `id="hddn_expense_category_fs"` |
| Line amount | `td[data-field-name="amount"] input#amount_formattedValue` |
| Line business reason | `td[data-field-name="custcol_reason"] input#custcol_reason` |
| Line memo/vendor | `td[data-field-name="memo"] input` (scoped to the sublist cell) |
| Line project | `td[data-field-name="customer"] input#expense_customer_display`, hidden `hddn_expense_customer_fs` |
| Line project task | `td[data-field-name="projecttask"] input#expense_projecttask_display`, hidden `hddn_expense_projecttask_fs` |
| Line department | `td[data-field-name="department"] input[name="inpt_department"]` (dropdown; the numeric id suffix on the input varies — do not pin it) |
| Line EBITDA add-back | `td[data-field-name="cseg_ebitda_add"] input[name="inpt_cseg_ebitda_add"]` (only option besides blank is "Yes") |
| Line attach file | `td[data-field-name="expmediaitem"]`, "+" button `id="expmediaitem_popup_new"` |
| Add line | `input#expense_addedit` (value "Add") |
| Ref No, Billing Subsidiary | auto-filled — skipped |

### Traps learned from the live form

- **Category is a popupselect/autocomplete** ("Type then tab"): type,
  Tab to commit, then verify the hidden value input got a value.
  Typing alone does not set it. If the hidden input stays empty, stop
  — the suggestion may need Enter instead of Tab, or the exact
  NetSuite label differs.
- **Header memo vs line memo share `id="memo"`.** Header report name
  is scoped to `form[name="main_form"]`; line memo is scoped to its
  sublist cell. Never use bare `By.ID, "memo"`. (An earlier handoff
  had the header labels swapped vs the HTML: the HTML is authoritative
  — `trandate` = date, `memo` = report name. Eyeball this on the
  first live run.)
- **Attach File is a popup flow, NOT a line file input.** Click "+",
  switch to the popup window (`expensereportmediaitem.nl`), send the
  receipt path to `input[name="mediafile"]`, click popup Save
  (`id="submitter"`), wait for the popup to close, switch back, verify
  the line's attach display is non-empty. Popup Save ≠ report Submit.
  If the popup does not close, stop and leave it open for the user.
- **Department dropdown id suffix varies** (`inpt_department_4` in one
  capture) — select by `name`, never by the suffixed id.

## Procedure rules (from Vertech's internal docs)

- Report naming: `First Initial Last Name Week Ending MM/DD/YY`.
- Expenses are recorded in the month they occur; separate reports per
  month. Company-card charges within 5 days; reimbursable expenses
  within the month incurred, with a manager-approved exception up to
  30 days after. **A report filed in a later month than its expenses
  may need the approver's exception — flag this, don't assume it.**
- Memo = vendor name for manual entries; Business Reason = clear
  description; overhead lines need only Category + Department (no
  project/task).
- Receipt naming: `Employee Initials_Date_Vendor_Amount`
  (e.g. `KB_01.25.23_McDonalds_15.45`).

## Tests

```bash
python -m pipenv run python -m pytest tests/ -v
# or, without pytest:
python -m pipenv run python -m unittest discover tests -v
```

Tests are offline only — no NetSuite, no browser:

- `tests/test_expense_filler.py` — CSV parsing, totals, selector
  builder, 300-char business-reason limit, project-requires-task, and
  the trip-folder resolution (`resolve_inputs`: folder with one CSV,
  no CSV, two CSVs, CSV-file default, explicit `--receipts-dir`
  winning, missing path, non-CSV files ignored). It stubs
  selenium/dotenv in memory so it runs without them installed.
- `tests/test_dependencies.py` — checks the **real** selenium (4+) and
  python-dotenv packages are installed, with a clear install hint on
  failure. It deliberately does NOT use the stubs above: a stubbed
  import must not count as installed, so it verifies each module has
  a real installed file behind it. Run it alone for a quick
  environment check:
  `python -m pipenv run python -m pytest tests/test_dependencies.py -v`

When adding a feature, add a test for it in the same style, and keep
the offline tests passing without selenium installed.

## Pipfile notes

- The Pipfile deliberately has **no `[requires] python_version` pin**.
  The old project's `python_version = "3.10"` pin would make pipenv
  refuse a newer interpreter (the developer runs Python 3.14 on
  Windows). The code needs only Python 3.10+, so pipenv uses whatever
  Python it is run with.
- `selenium` + `python-dotenv` are runtime packages; `pytest` is a
  dev package — hence `pipenv install --dev` for tests.

## Current status (2026-11-03)

- Script, sample CSV, tests, Pipfile, README, and this file are in the
  repo and the full test suite passes on Windows / Python 3.14
  (17 tests: 8 original offline tests + 2 dependency tests + 7
  folder-mode tests).
- **No real expense report has been run through this script yet.**
  The first real run is prepared locally (trip folder + CSV +
  receipts) but not yet executed in NetSuite. Before that run, confirm
  with the user: (1) the exact NetSuite category label for the trip,
  (2) the report-name week-ending date, (3) that the header memo field
  is indeed the report name on the live form, and (4) whether the
  approver's exception is needed for the filing timing (see Procedure
  rules above). Do not treat any of these as confirmed until the user
  says so.
- The old opportunity-entry automation (in a separate zip the user
  supplied earlier) is a reusable pattern only — different task, do
  not merge its code in, and its `.env` contents were never seen and
  must never be committed.
