#!/usr/bin/env python3
"""
NetSuite expense-report filler — fills a draft expense report from a CSV.

Adapted from the old netsuite-automation opportunity editor (same Selenium
pattern, new target: the Expense Report form). Login is NetSuite SSO with
2FA, done by hand in the browser — no credentials are stored or typed.

SELECTOR STRATEGY (not absolute xpaths):
  NetSuite sublist cells carry data-field-name plus stable input ids/names.
  Every line field below is located through its sublist cell, e.g.
    td[data-field-name="category"] input
  so the same selectors work for every row: only the focused/edited row
  exposes the display inputs, and clicking Add commits the line and opens
  a fresh blank row with the same selectors. No row-indexed xpaths.

  Field map (from David's Inspect-element HTML, 2026-11-03):
    Header date        id="trandate"            (main form, date field)
    Header report name id="memo" in main_form   (Purpose / Report Name text field)
                       NOTE: the sublist Memo/Vendor input is ALSO id="memo",
                       so sublist fields are scoped to td[data-field-name=...]
                       inside the expense sublist, never by bare By.ID.
    Line Ref No        auto-filled — skipped
    Line Date          td[data-field-name="expensedate"] input#expensedate
    Line Category      td[data-field-name="category"] input#expense_category_display
                       popupselect/autocomplete: type, Tab, verify hidden
                       input#hddn_expense_category_fs got a value.
    Line Amount        td[data-field-name="amount"] input#amount_formattedValue
    Line Business Rsn  td[data-field-name="custcol_reason"] input#custcol_reason
                       (custom field, max 300 chars)
    Line Memo/Vendor   td[data-field-name="memo"] input (scoped to sublist)
                       (max 999 chars; procedure: vendor name goes here)
    Billing Subsidiary auto-filled Vertech — skipped, verified if present
    Line Project       td[data-field-name="customer"] input#expense_customer_display
                       OPTIONAL: only for billable work. Left blank for
                       this offsite report; filled only if the CSV has a
                       project value.
    Line Project Task  td[data-field-name="projecttask"] input#expense_projecttask_display
                       OPTIONAL, required only if a project is set.
    Line Department    td[data-field-name="department"] input[name="inpt_department"]
                       dropdown; value 2 = "Sales and Marketing" (default).
                       The script VERIFIES the display value and only
                       attempts a change if the CSV department differs.
                       Occasional alternative: Executive Management.
    Line EBITDA Addbk  td[data-field-name="cseg_ebitda_add"] input[name="inpt_cseg_ebitda_add"]
                       OPTIONAL: only for CaST executive-management lines,
                       value "Yes". Ignored/blank otherwise.
    Line Attach File   td[data-field-name="expmediaitem"] — NOT a direct file
                       input. Click the "+" button #expmediaitem_popup_new,
                       which opens a popup window (expensereportmediaitem.nl):
                         Attach From = Computer (default, per screenshot)
                         Select File = input[name="mediafile"] in the popup
                         Save        = input#submitter in the popup
                       After the popup Save, the popup closes and the line's
                       expmediaitem field should show the uploaded file.
                       NOTE: popup Save != report Submit. The report itself
                       is NEVER submitted by this script.
    Add line           input#expense_addedit (value "Add")

WHAT IT DOES:
  1. Opens (or re-attaches to) its own Chrome window. YOU log in to
     NetSuite there, including 2FA; the login persists between runs.
  2. Waits until YOU open a NEW, blank Expense Report, then starts on its
     own (no keypress needed, so it can run from a non-interactive shell).
  3. Fills header date + report name, then one line per CSV row:
     date, category, amount, business reason, memo/vendor, department
     check, optional project/task, optional EBITDA, receipt upload, Add.
  4. STOPS BEFORE SUBMITTING the report. Browser stays open for review.
     You click Submit / Submit for Supervisor Approval yourself.

SETUP (on your computer):
  python -m pipenv install
  cp .env.example .env   # NETSUITE_URL only (optional CHROME_PATH); no credentials
  # .env lives next to this script (or in the folder you run from).

PRE-TRIP / POST-TRIP SPLIT:
  One trip folder holds two reports: pre-trip-expenses.csv (airfare +
  prepaid, filed before departure) and post-trip-expenses.csv (hotel,
  meals, ground, filed after return). Folder mode with --phase picks
  one of them:
    python -m pipenv run python netsuite_expense_filler.py "2026_12_MSP" \
        --phase pre-trip --report-name "DFolkner Week Ending 12/05/26"
  Without --phase, a folder with two CSVs is an error. Passing a CSV
  file directly always works, phase or not.

  A trip can need SEVERAL submittals for the same phase (weekly
  submittals as receipts come in). Numbered siblings are supported:
  pre-trip-expenses-1.csv, pre-trip-expenses-2.csv, ... (same for
  post-trip). The unnumbered file counts as the first. With --phase
  and exactly one matching file, it is used as-is; with several,
  --number N picks one:
    ... netsuite_expense_filler.py "2026_12_MSP" --phase pre-trip \
        --number 2 --report-name "DFolkner Week Ending 12/12/26"

DEFAULT FOLDERS + SUBMITTAL ZIPS:
  Prepared submittals arrive as a zip in the Downloads folder. The
  script can extract one into the trip folder before filling:
    ... netsuite_expense_filler.py --trip "2026_12_PHX Christmas" \
        --extract --phase pre-trip \
        --report-name "DFolkner Week Ending 12/05/26"
  --extract [ZIP] takes the newest .zip in Downloads, or the one
  named. --trip NAME resolves the folder under the expense-reports
  root. Defaults (no personal paths are baked into this script):
    expense root   EXPENSE_REPORTS_ROOT in .env,
                   else ~/Documents/Expense Reports
    downloads      EXPENSE_DOWNLOADS_DIR in .env, else ~/Downloads
  --expense-root / --downloads-dir override them per run. Extraction
  is the only write the script does outside NetSuite, and it happens
  only when --extract is passed.

TRIP-FOLDER WORKFLOW (the usual way to run it):
  Download the trip's receipts (images/PDFs) and the expense CSV into
  one folder, e.g. OneDrive > Documents > Expense Reports > 2026_10_MSP,
  then point the script at that folder. It finds the single CSV in the
  folder and takes the receipts from the same folder — no separate
  receipts subfolder needed:
    python -m pipenv run python netsuite_expense_filler.py "2026_10_MSP" \
        --report-name "DFolkner Week Ending 10/31/26"
  Receipts are named per procedure: XX_MM.DD.YY_Vendor_Amount, e.g.
  XX_01.25.26_SampleVendor_15.45.pdf. If the folder is on OneDrive, make
  sure the files are downloaded locally (not cloud-only placeholders)
  before running, or the browser upload cannot read them.
"""

import csv
import os
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()
# .env normally lives next to this script (the repo folder), but the
# script is often run with a trip folder as the working directory, so
# fall back to the script's own folder if the cwd lookup found nothing.
if not os.getenv("NETSUITE_URL"):
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ------------------------------------------------------------------ header --
SEL_HEADER_DATE = (By.ID, "trandate")
# Header report name: the main-form memo field. Scoped by form so it can
# never resolve to the sublist memo input, which shares id="memo".
SEL_HEADER_REPORT_NAME = (By.CSS_SELECTOR, 'form[name="main_form"] input[name="memo"]')

# ------------------------------------------------------------------- lines --
# The expense sublist's edit row: the focused row that has an expense date
# cell. After a line is Added, committed rows ALSO carry the same
# data-field-name cells, and they come first in the DOM — an unscoped
# td[data-field-name=...] matched line 1's committed cell on line 2.
# Other sublists on the page have their own focused row, hence :has().
EDIT_ROW = 'tr.uir-machine-row-focused:has(> td[data-field-name="expensedate"])'


def cell_css(field_name):
    """The field's cell in the edit row (what find_input clicks to focus)."""
    return f'{EDIT_ROW} > td[data-field-name="{field_name}"]'


def cell(field_name, suffix='input:not([type="hidden"])'):
    """Sublist cell input for a field in the edit row, scoped so duplicate
    ids elsewhere on the page (notably memo) and committed rows cannot be
    picked up by mistake.

    Selenium's clickable wait only looks at the FIRST match, and NetSuite
    cells also hold hidden helper inputs, so pin the suffix to the visible
    input (its documented id/name where we have one)."""
    return (By.CSS_SELECTOR, f"{cell_css(field_name)} {suffix}")

SEL_LINE_DATE = cell("expensedate", "input#expensedate")
SEL_LINE_CATEGORY = cell("category", "input#expense_category_display")
SEL_LINE_CATEGORY_HIDDEN = (By.ID, "hddn_expense_category_fs")
SEL_LINE_AMOUNT = cell("amount", "input#amount_formattedValue")
SEL_LINE_BUSINESS_REASON = cell("custcol_reason", "input#custcol_reason")
SEL_LINE_MEMO = cell("memo")
SEL_LINE_PROJECT = cell("customer", "input#expense_customer_display")
SEL_LINE_PROJECT_HIDDEN = (By.ID, "hddn_expense_customer_fs")
SEL_LINE_PROJECT_TASK = cell("projecttask", "input#expense_projecttask_display")
SEL_LINE_PROJECT_TASK_HIDDEN = (By.ID, "hddn_expense_projecttask_fs")
# Dropdowns: match by name — the numeric id suffix varies (inpt_department_4).
SEL_LINE_DEPARTMENT_DISPLAY = cell("department", 'input[name="inpt_department"]')
SEL_LINE_EBITDA_DISPLAY = cell("cseg_ebitda_add", 'input[name="inpt_cseg_ebitda_add"]')
# Attach File "+" is parked with the cell's input; it only shows once the
# expmediaitem cell is focused, so it is located through the cell too.
SEL_LINE_ATTACH_NEW = cell("expmediaitem", "a#expmediaitem_popup_new")
SEL_LINE_ATTACH_DISPLAY = cell("expmediaitem", "input#expense_expmediaitem_display")
SEL_LINE_ATTACH_HIDDEN = (By.ID, "hddn_expense_expmediaitem_fs")
SEL_ADD_LINE = (By.ID, "expense_addedit")

# Popup window (file upload) — opened by the Attach File "+" button.
SEL_POPUP_FILE = (By.CSS_SELECTOR, 'input[name="mediafile"]')
SEL_POPUP_SAVE = (By.ID, "submitter")

# Report name/date and receipts folder are supplied on the command line
# (see main()). Example report name, per the procedure naming convention
# "First Initial Last Name Week Ending MM/DD/YY":
#   JSmith Week Ending 10/31/26
# No real report, employee, or receipt data is baked into this script.


def take_alert(driver):
    """If a browser alert is open, return its text and accept it; else None.
    An open alert makes every later Selenium call (including page_source for
    the debug dump) fail, so it must be read and cleared first."""
    try:
        alert = driver.switch_to.alert
        text = alert.text
        alert.accept()
        return text or ""
    except WebDriverException:
        return None


def raise_on_alert(driver, label):
    """Stop the run if setting `label` made NetSuite pop an alert."""
    text = take_alert(driver)
    if text is not None:
        raise RuntimeError(f"NetSuite alert after {label}: {text!r}. "
                           "Stopping before any submit.")


def _shown(driver, selector):
    found = driver.find_elements(*selector)
    return bool(found) and found[0].is_displayed()


def focused_cell(driver):
    """data-field-name of the sublist cell NetSuite currently has focused."""
    cells = driver.find_elements(By.CSS_SELECTOR, "td.uir-machine-focused-cell")
    return cells[0].get_attribute("data-field-name") if cells else None


def find_input(driver, wait, selector, label):
    """Wait for a field to be clickable. A timeout names the field instead
    of surfacing a bare TimeoutException.

    Sublist fields: NetSuite's inline row keeps each field's input parked
    off-table (display:none) and moves it into a cell only when that cell
    takes focus — one cell at a time. If the input is not in its cell yet,
    give the cell a real mouse click (move + click, like a person) and wait
    for the input to arrive."""
    by, css = selector
    try:
        if by == By.CSS_SELECTOR and css.startswith(EDIT_ROW):
            # cell() selectors are "<edit row> > td[...] <suffix>"; the
            # suffix never contains a space.
            td_css = css.rsplit(" ", 1)[0]
            td = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, td_css)))
            if not _shown(driver, selector):
                ActionChains(driver).move_to_element(td).click().perform()
                try:
                    WebDriverWait(driver, 5).until(lambda d: _shown(d, selector))
                except TimeoutException:
                    raise RuntimeError(
                        f"{label}: clicking its cell did not move focus there "
                        f"(focused cell is {focused_cell(driver)!r}). "
                        "Stopping before any submit.")
        return wait.until(EC.element_to_be_clickable(selector))
    except TimeoutException:
        raise RuntimeError(f"Timed out finding {label} ({css}). Stopping before any submit.")


def fill_text(driver, wait, selector, value, label):
    el = find_input(driver, wait, selector, label)
    el.clear()
    el.send_keys(value)
    # Tab commits the value (fires NetSuite's onchange/validation) and moves
    # focus to the next cell, the same as typing the form by hand.
    el.send_keys(Keys.TAB)
    time.sleep(0.5)
    print(f"  {label}: {value}")


def fill_popupselect(driver, wait, display_selector, hidden_selector, value, label):
    """Popupselect/autocomplete: type, Tab to commit, verify hidden input."""
    el = find_input(driver, wait, display_selector, label)
    el.clear()
    el.send_keys(value)
    time.sleep(1)
    el.send_keys(Keys.TAB)
    time.sleep(0.5)
    raise_on_alert(driver, label)
    hidden = driver.find_element(*hidden_selector)
    if not hidden.get_attribute("value"):
        raise RuntimeError(
            f"{label} '{value}' did not commit (hidden input empty) — "
            "the suggestion may need Enter instead of Tab, or the exact "
            "NetSuite label differs. Stopping before any submit.")
    print(f"  {label}: {value} (committed)")


def check_department(driver, wait, wanted):
    """Department defaults to Sales and Marketing. Verify it; only attempt
    a change if the CSV asks for something else."""
    el = find_input(driver, wait, SEL_LINE_DEPARTMENT_DISPLAY, "Department")
    current = el.get_attribute("value") or el.get_attribute("title") or ""
    if current.strip() == wanted.strip():
        print(f"  Department: {current} (default, unchanged)")
        return
    # Different department requested: type into the dropdown input and Enter.
    el.clear()
    el.send_keys(wanted)
    time.sleep(1)
    el.send_keys(Keys.ENTER)
    time.sleep(0.5)
    raise_on_alert(driver, "Department")
    current = el.get_attribute("value") or el.get_attribute("title") or ""
    if current.strip() != wanted.strip():
        raise RuntimeError(
            f"Department is '{current}', wanted '{wanted}' — change it by hand "
            "in the browser before continuing. Stopping before any submit.")
    print(f"  Department: {wanted} (changed)")


def fill_dropdown(driver, wait, selector, value, label):
    """Type-ahead dropdown (e.g. EBITDA Add-back): type, commit with Tab
    (NOT Enter — Enter in a line field can fire NetSuite's line Add/validate
    and pop an alert; that killed the 2026-11-09 run right before the receipt
    upload), then verify the dropdown shows the value."""
    el = find_input(driver, wait, selector, label)
    el.clear()
    el.send_keys(value)
    time.sleep(1)
    el.send_keys(Keys.TAB)
    time.sleep(0.5)
    raise_on_alert(driver, label)
    current = (el.get_attribute("value") or el.get_attribute("title") or "").strip()
    if current != value.strip():
        raise RuntimeError(
            f"{label} shows '{current}', wanted '{value}' — set it by hand. "
            "Stopping before any submit.")
    print(f"  {label}: {value}")


def attachment_present(hidden_value, display_value):
    """The line's Attach File field holds a file once either its hidden id
    or its display text is non-empty."""
    return bool((hidden_value or "").strip() or (display_value or "").strip())


def upload_receipt(driver, wait, receipt_path, receipt_name):
    """Attach File flow: '+' button -> popup window -> Choose File -> Save
    in the popup -> back to the main window. Popup Save is a file-upload
    save, NOT the report submit."""
    main_window = driver.current_window_handle
    before = set(driver.window_handles)
    # Focus the Attach File cell via its text input (always visible once the
    # cell is focused). The "+" is a hover widget: Selenium can see it as
    # not displayed even in the focused cell (line 3 of the 2026-11-03 run),
    # so trigger its own onclick, which opens the same upload popup.
    raise_on_alert(driver, "the field before Attach File")
    find_input(driver, wait, SEL_LINE_ATTACH_DISPLAY, "Attach File")
    btn = wait.until(EC.presence_of_element_located(SEL_LINE_ATTACH_NEW))
    driver.execute_script("arguments[0].click();", btn)
    try:
        wait.until(lambda d: len(d.window_handles) > len(before))
    except TimeoutException:
        raise RuntimeError("Attach File popup did not open. Stopping before any submit.")
    popup = [h for h in driver.window_handles if h not in before][0]
    driver.switch_to.window(popup)
    try:
        file_input = wait.until(EC.presence_of_element_located(SEL_POPUP_FILE))
        file_input.send_keys(receipt_path)
        time.sleep(0.5)
        save = wait.until(EC.element_to_be_clickable(SEL_POPUP_SAVE))
        save.click()
        # Popup should close on its own after a successful upload.
        wait.until(lambda d: len(d.window_handles) == len(before))
    finally:
        # If the popup is still open (validation error, etc.), leave it
        # open for the user and stop — do not force-close their upload.
        if popup in driver.window_handles:
            print("  WARNING: upload popup is still open — check it by hand.")
            raise RuntimeError("Upload popup did not close after Save. Check it by hand; nothing was submitted.")
        driver.switch_to.window(main_window)
    # Back on the main form, the line's Attach File field should now show it.
    time.sleep(1)
    raise_on_alert(driver, "receipt upload")
    hidden = driver.find_elements(*SEL_LINE_ATTACH_HIDDEN)
    display = driver.find_elements(*SEL_LINE_ATTACH_DISPLAY)
    hidden_val = (hidden[0].get_attribute("value") or "") if hidden else ""
    shown = (display[0].get_attribute("value") or "") if display else ""
    if not attachment_present(hidden_val, shown):
        # Never Add a line without its receipt when the file exists.
        raise RuntimeError(
            f"Attach File is still empty after uploading {receipt_name} — "
            "attach it by hand, then click Add. Stopping before any submit.")
    print(f"  Attached: {receipt_name} ({shown or hidden_val})")


# ----------------------------------------------------------------- browser --
# The filler runs its OWN Chrome: a dedicated profile (kept outside the repo
# and OneDrive) with a fixed remote-debugging port. The first run starts it;
# later runs attach to the same window, so the NetSuite login + 2FA carry
# over between runs. Chrome is started by us, not by chromedriver, so it
# stays open when the script exits or stops — the browser is always left
# open for review. (Chrome refuses a debugging port on the default profile,
# hence the dedicated one.)
CHROME_DEBUG_PORT = 9222
CHROME_PROFILE_DIR = os.path.join(
    os.getenv("LOCALAPPDATA") or os.path.expanduser("~"),
    "netsuite-expense-filler", "chrome-profile")
REPORT_WAIT_SECONDS = 30 * 60


def find_chrome():
    candidates = [
        os.getenv("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.getenv("LOCALAPPDATA") or "", r"Google\Chrome\Application\chrome.exe"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise RuntimeError("Chrome not found — set CHROME_PATH in .env to chrome.exe.")


def port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def open_browser(url):
    """Attach to the filler's Chrome, starting it first if it is not running."""
    if port_open(CHROME_DEBUG_PORT):
        print("Attaching to the already-open filler browser (login is kept).")
    else:
        print("Starting the filler browser...")
        cmd = [find_chrome(), f"--remote-debugging-port={CHROME_DEBUG_PORT}",
               f"--user-data-dir={CHROME_PROFILE_DIR}", "--no-first-run",
               "--no-default-browser-check", "--start-maximized", url]
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            # Break away from the launcher's job object too, so stopping a
            # background run (which kills its job) does not kill Chrome.
            subprocess.Popen(cmd, creationflags=flags | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            # The job forbids breakaway: start it normally.
            subprocess.Popen(cmd, creationflags=flags,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while not port_open(CHROME_DEBUG_PORT):
            if time.time() > deadline:
                raise RuntimeError("Chrome started but its debugging port never opened.")
            time.sleep(0.5)
    options = webdriver.ChromeOptions()
    options.debugger_address = f"127.0.0.1:{CHROME_DEBUG_PORT}"
    return webdriver.Chrome(options=options)


def is_new_report_url(url):
    """A never-saved Expense Report is exprept.nl with no record id.
    An existing draft (exprept.nl?id=123) must never be filled on top of."""
    parsed = urlparse(url)
    return (parsed.path.endswith("/exprept.nl")
            and "id" not in parse_qs(parsed.query))


EXPENSE_ROWS_XPATH = '//tr[@data-ui-role="sublist-row"][td[@data-field-name="expensedate"]]'


def has_committed_lines(driver):
    """Any expense row beyond line 1 means lines were already Added."""
    return bool(driver.find_elements(
        By.XPATH, '//tr[@data-ui-role="sublist-row"][@data-line-number!="1"]'
                  '[td[@data-field-name="expensedate"]]'))


def expense_row_count(driver):
    """Rows in the expense sublist: committed lines plus the edit row."""
    return len(driver.find_elements(By.XPATH, EXPENSE_ROWS_XPATH))


def page_messages(driver):
    """Text of any browser alert or visible NetSuite message/dialog — this is
    where NetSuite says why it refused a line (e.g. 'Please enter value(s)
    for: ...')."""
    msgs = []
    try:
        msgs.append("alert: " + driver.switch_to.alert.text)
    except WebDriverException:
        pass
    for el in driver.find_elements(By.CSS_SELECTOR,
            '[role="alertdialog"], [role="dialog"], .uir-message-popup, '
            '.uir-alert-box, .x-window, .x-message-box'):
        try:
            if el.is_displayed() and el.text.strip():
                msgs.append(el.text.strip().replace("\n", " | ")[:300])
        except WebDriverException:
            continue
    return msgs


def add_line(driver, wait, line_no):
    """Click Add and VERIFY NetSuite committed the line: a committed line
    plus a fresh edit row means the expense row count grows past line_no.
    If it does not, stop — never fill the next line on top of this one."""
    before = expense_row_count(driver)
    time.sleep(1)  # let NetSuite finish field-change/upload processing
    add = wait.until(EC.element_to_be_clickable(SEL_ADD_LINE))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", add)
    add.click()
    try:
        WebDriverWait(driver, 10).until(lambda d: expense_row_count(d) > max(before, line_no))
    except (TimeoutException, WebDriverException):
        why = page_messages(driver)
        raise RuntimeError(
            f"Line {line_no} did not commit after Add (expense rows: {before} -> "
            f"{expense_row_count(driver)}). NetSuite says: "
            f"{'; '.join(why) if why else 'nothing visible'}. "
            "Fix it by hand in the browser. Stopping before any submit.")
    print(f"  Added line {line_no}.")


def wait_for_blank_report(driver):
    """Replaces the old press-Enter pause (which needed a keyboard on the
    terminal): poll every tab until one shows a NEW, blank Expense Report,
    then switch to it. The user logs in, does 2FA, and opens the report;
    filling starts on its own."""
    print("Waiting for a blank Expense Report: log in (with 2FA) in the browser,")
    print("then open a NEW Expense Report. Filling starts automatically.")
    warned = set()
    deadline = time.time() + REPORT_WAIT_SECONDS
    while time.time() < deadline:
        for handle in list(driver.window_handles):
            try:
                driver.switch_to.window(handle)
                url = driver.current_url
                if "exprept.nl" not in url or not driver.find_elements(
                        By.CSS_SELECTOR, 'form[name="main_form"] #trandate'):
                    continue
                # Report name still empty: a half-filled report left open by
                # an earlier stopped run is NOT blank, and is never refilled.
                name = driver.find_elements(*SEL_HEADER_REPORT_NAME)
                untouched = bool(name) and not (name[0].get_attribute("value") or "").strip()
                if is_new_report_url(url) and untouched and not has_committed_lines(driver):
                    print(f"Blank Expense Report found: {url}")
                    return
                if url not in warned:
                    print("  That tab is an existing or partly-filled report — "
                          "open a NEW blank Expense Report instead.")
                    warned.add(url)
            except WebDriverException:
                continue  # tab closed or navigating mid-check
        time.sleep(2)
    raise RuntimeError("No blank Expense Report opened within 30 minutes.")


def save_debug_page(driver):
    """Dump the current page HTML next to this script so a failed selector
    can be checked against the real DOM. Written to the repo folder (not
    the trip folder) and gitignored — it can contain real report data."""
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"netsuite_debug_{stamp}.html")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"  Page HTML saved to {path}")
    except Exception as exc:
        print(f"  (could not save page HTML: {exc})")


def run_log_path(stamp=None):
    """Where this run's console output is copied: next to the script (repo
    folder, gitignored — it holds real report data), like the debug HTML."""
    import datetime
    stamp = stamp or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"netsuite_run_{stamp}.log")


class Tee:
    """Write console output to the terminal AND the run log, so a run can
    be traced afterwards even if the terminal output is gone."""

    def __init__(self, stream, log_file):
        self.stream = stream
        self.log_file = log_file

    def write(self, text):
        self.stream.write(text)
        try:
            self.log_file.write(text)
            self.log_file.flush()
        except (OSError, ValueError):
            pass
        return len(text)

    def flush(self):
        self.stream.flush()


def start_run_log():
    path = run_log_path()
    try:
        log_file = open(path, "w", encoding="utf-8")
    except OSError as exc:
        print(f"(could not open run log {path}: {exc})")
        return
    sys.stdout = Tee(sys.stdout, log_file)
    print(f"Run log: {path}")


PHASE_CSV_NAMES = {
    "pre-trip": "pre-trip-expenses.csv",
    "post-trip": "post-trip-expenses.csv",
}


def default_expense_root():
    """Where trip folders live by default: EXPENSE_REPORTS_ROOT from
    .env, else ~/Documents/Expense Reports. (Real paths stay in .env,
    never in this script.)"""
    return (os.getenv("EXPENSE_REPORTS_ROOT")
            or os.path.join(os.path.expanduser("~"), "Documents", "Expense Reports"))


def default_downloads_dir():
    """Where submittal zips land: EXPENSE_DOWNLOADS_DIR from .env,
    else ~/Downloads."""
    return (os.getenv("EXPENSE_DOWNLOADS_DIR")
            or os.path.join(os.path.expanduser("~"), "Downloads"))


def phase_csv_candidates(folder, phase):
    """All CSVs in `folder` belonging to `phase`, in submittal order:
    the unnumbered pre-trip-expenses.csv (submittal 1), then the
    numbered pre-trip-expenses-2.csv, -3.csv, ... siblings."""
    from pathlib import Path
    folder = Path(folder)
    base = PHASE_CSV_NAMES[phase]
    stem = base[:-len(".csv")]
    found = []
    for f in folder.iterdir():
        if not (f.is_file() and f.suffix.lower() == ".csv"):
            continue
        if f.name == base:
            found.append((1, f))
        elif f.name.startswith(stem + "-"):
            suffix = f.name[len(stem) + 1:-len(".csv")]
            if suffix.isdigit():
                found.append((int(suffix), f))
    return [f for _, f in sorted(found)]


def find_submittal_zip(downloads_dir, zip_name=None):
    """The submittal zip in the downloads folder: the file named by
    zip_name, or the most recently modified .zip when none is named."""
    from pathlib import Path
    d = Path(downloads_dir)
    if zip_name:
        candidate = d / zip_name
        if not candidate.is_file():
            raise FileNotFoundError(f"Zip not found: {candidate}")
        return candidate
    if not d.is_dir():
        raise FileNotFoundError(f"Downloads folder not found: {d}")
    zips = [f for f in d.iterdir()
            if f.is_file() and f.suffix.lower() == ".zip"]
    if not zips:
        raise FileNotFoundError(f"No .zip files found in {d}")
    return max(zips, key=lambda f: f.stat().st_mtime)


def extract_submittal(zip_path, dest_folder):
    """Extract a submittal zip into the trip folder. Entries are
    written by basename only (the zips are flat: one CSV + its receipt
    files), so no entry can land outside the folder. Returns the list
    of file names written."""
    import zipfile
    from pathlib import Path
    dest = Path(dest_folder)
    written = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = Path(info.filename).name
            if not name or info.is_dir():
                continue
            (dest / name).write_bytes(zf.read(info))
            written.append(name)
    return written


def resolve_inputs(csv_arg, receipts_dir_arg, phase=None, number=None):
    """Resolve (csv_path, receipts_dir) from the command-line arguments.

    Ways to run it:
      - a CSV file: receipts default to the CSV's own folder, unless
        --receipts-dir is given explicitly. --phase / --number, if
        given, are only labels in this case — the file itself is what
        gets filled.
      - a folder: it must contain exactly one .csv file; that CSV is
        used and receipts default to the same folder.
      - a folder + --phase pre-trip / post-trip: the folder's
        pre-trip / post-trip CSVs are used. One trip folder holds
        several reports (pre-trip filed before departure, post-trip
        after return), and each phase can have several submittals:
        the unnumbered file plus numbered -2, -3, ... siblings. With
        exactly one candidate the phase alone picks it; with several,
        --number N picks one (never guess which report to fill).
        Without --phase, a folder with two CSVs is an error that
        names the phase flag.
    """
    from pathlib import Path
    path = Path(csv_arg)
    if path.is_dir():
        if phase:
            candidates = phase_csv_candidates(path, phase)
            if number is not None:
                wanted = f"{phase}-expenses-{number}.csv"
                chosen = next((f for f in candidates if f.name == wanted), None)
                if chosen is None and number == 1:
                    # The unnumbered file IS submittal 1.
                    base = path / PHASE_CSV_NAMES[phase]
                    if base.is_file():
                        chosen = base
                if chosen is None:
                    avail = ", ".join(f.name for f in candidates) or "none"
                    raise FileNotFoundError(
                        f"No {wanted} found in folder {csv_arg} "
                        f"(available for {phase}: {avail}).")
                csv_path = str(chosen)
            elif len(candidates) == 1:
                csv_path = str(candidates[0])
            elif not candidates:
                present = ", ".join(sorted(
                    f.name for f in path.iterdir()
                    if f.is_file() and f.suffix.lower() == ".csv"))
                raise FileNotFoundError(
                    f"No {PHASE_CSV_NAMES[phase]} found in folder {csv_arg} "
                    f"(found: {present or 'no CSV files'}).")
            else:
                names = ", ".join(f.name for f in candidates)
                raise ValueError(
                    f"Folder {csv_arg} has more than one {phase} CSV "
                    f"({names}) — pick one with --number N, or pass the "
                    f"CSV file itself.")
            receipts_dir = receipts_dir_arg or str(path)
            return csv_path, receipts_dir
        csvs = sorted(f for f in path.iterdir()
                      if f.is_file() and f.suffix.lower() == ".csv")
        if not csvs:
            raise FileNotFoundError(
                f"No .csv file found in folder: {csv_arg}")
        if len(csvs) > 1:
            names = ", ".join(f.name for f in csvs)
            raise ValueError(
                f"Folder {csv_arg} contains more than one .csv file "
                f"({names}) — pass the CSV file itself, or add "
                f"--phase pre-trip / --phase post-trip to pick one.")
        csv_path = str(csvs[0])
        receipts_dir = receipts_dir_arg or str(path)
    elif path.is_file():
        csv_path = str(path)
        receipts_dir = receipts_dir_arg or str(path.parent) or "."
    else:
        raise FileNotFoundError(f"CSV or folder not found: {csv_arg}")
    return csv_path, receipts_dir


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fill a NetSuite expense report draft from a CSV. Never submits.")
    parser.add_argument("csv_path", nargs="?", default=None,
                        help="CSV of expense lines (see sample_expenses.csv), "
                             "OR a folder containing exactly one CSV plus "
                             "its receipt files (trip-folder workflow). "
                             "Omit when --trip names the folder.")
    parser.add_argument("--report-name", required=True,
                        help='e.g. "JSmith Week Ending 10/31/26"')
    parser.add_argument("--report-date", default=None,
                        help="Header date, e.g. 11/3/2026 (defaults to today, MM/DD/YYYY)")
    parser.add_argument("--receipts-dir", default=None,
                        help="Folder holding the receipt files named in the CSV "
                             "(default: the CSV's folder, or the folder given "
                             "as csv_path)")
    parser.add_argument("--phase", choices=["pre-trip", "post-trip"],
                        default=None,
                        help="Pre-trip / post-trip split: with a folder, pick "
                             "the pre-trip-expenses.csv or post-trip-expenses.csv "
                             "from that folder. With a CSV file, ignored.")
    parser.add_argument("--number", type=int, default=None, metavar="N",
                        help="With --phase and a folder holding several "
                             "submittals for that phase (pre-trip-expenses-2.csv, "
                             "...), fill submittal N. The unnumbered file is 1.")
    parser.add_argument("--trip", default=None, metavar="NAME",
                        help="Trip folder name under the expense-reports root "
                             "(default root: EXPENSE_REPORTS_ROOT in .env, "
                             "else ~/Documents/Expense Reports). Use instead "
                             "of passing the folder path.")
    parser.add_argument("--expense-root", default=None,
                        help="Folder holding the trip folders "
                             "(overrides the default expense-reports root).")
    parser.add_argument("--downloads-dir", default=None,
                        help="Folder submittal zips are downloaded to "
                             "(default: EXPENSE_DOWNLOADS_DIR in .env, "
                             "else ~/Downloads).")
    parser.add_argument("--extract", nargs="?", const=True, default=None,
                        metavar="ZIP",
                        help="Before filling, extract a submittal zip from "
                             "the downloads folder into the trip folder: the "
                             "newest .zip, or the ZIP named. This is the "
                             "only write the script does outside NetSuite.")
    args = parser.parse_args()
    start_run_log()
    # Resolve the target: an explicit path wins; --trip names a folder
    # under the expense-reports root instead.
    target = args.csv_path
    if args.trip:
        root = args.expense_root or default_expense_root()
        target = os.path.join(root, args.trip)
    if args.extract is not None:
        if not target:
            print("Error: --extract needs a trip folder (a folder path or --trip).")
            sys.exit(2)
        dest = target if os.path.isdir(target) else os.path.dirname(os.path.abspath(target))
        downloads = args.downloads_dir or default_downloads_dir()
        zip_arg = None if args.extract is True else args.extract
        try:
            zip_path = find_submittal_zip(downloads, zip_arg)
            written = extract_submittal(zip_path, dest)
        except FileNotFoundError as exc:
            print(f"Error: {exc}")
            sys.exit(2)
        print(f"Extracted {zip_path.name} into {dest}: {', '.join(written)}")
    if not target:
        print("Error: give a CSV file, a trip folder, or --trip NAME.")
        sys.exit(2)
    try:
        csv_path, receipts_dir = resolve_inputs(
            target, args.receipts_dir, phase=args.phase, number=args.number)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        sys.exit(2)
    report_name = args.report_name
    # Read and check the CSV up front, before opening the browser, so a
    # bad folder / missing receipt is caught before login, not mid-run.
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"{csv_path}: {len(rows)} expense lines, "
          f"total ${sum(float(r['amount']) for r in rows):.2f}")
    if args.phase:
        print(f"Phase: {args.phase}")
    missing = [r["receipt_file"] for r in rows
               if not os.path.exists(os.path.join(receipts_dir, r["receipt_file"]))]
    if missing:
        print("WARNING: these receipt files are missing from "
              f"{receipts_dir} (those lines will be entered without an "
              f"attachment): " + ", ".join(missing))
    if args.report_date:
        report_date = args.report_date
    else:
        import datetime
        report_date = datetime.date.today().strftime("%m/%d/%Y")
    if args.phase == "pre-trip" and rows:
        # Policy: pre-trip receipts must be submitted BEFORE the trip.
        # Warn, don't block, if the report date is already on/after the
        # first expense (travel) date in the CSV.
        import datetime as _dt
        try:
            first = _dt.datetime.strptime(rows[0]["date"], "%m/%d/%Y").date()
            report = _dt.datetime.strptime(report_date, "%m/%d/%Y").date()
            if report >= first:
                print(f"WARNING: pre-trip report date {report_date} is on "
                      f"or after the first expense date {rows[0]['date']} — "
                      f"pre-trip receipts are supposed to be submitted "
                      f"before the trip. Continuing anyway; check the "
                      f"report date before submitting.")
        except Exception:
            pass

    url = os.getenv("NETSUITE_URL", "http://netsuite.vertech.com/")
    driver = open_browser(url)
    wait = WebDriverWait(driver, 20)
    try:
        # Login and 2FA are done by hand in the browser — never automated.
        wait_for_blank_report(driver)
        fill_text(driver, wait, SEL_HEADER_DATE, report_date, "Report date")
        fill_text(driver, wait, SEL_HEADER_REPORT_NAME, report_name, "Report name")

        for i, row in enumerate(rows, start=1):
            print(f"Line {i}: {row['date']} {row['memo_vendor']} ${row['amount']}")
            fill_text(driver, wait, SEL_LINE_DATE, row["date"], "Line Date")
            fill_popupselect(driver, wait, SEL_LINE_CATEGORY, SEL_LINE_CATEGORY_HIDDEN,
                             row["category"], "Category")
            fill_text(driver, wait, SEL_LINE_AMOUNT, row["amount"], "Amount")
            reason = row["business_reason"]
            if len(reason) > 300:
                raise RuntimeError(f"Business Reason over 300 chars on line {i}: {reason}")
            fill_text(driver, wait, SEL_LINE_BUSINESS_REASON, reason, "Business Reason")
            fill_text(driver, wait, SEL_LINE_MEMO, row["memo_vendor"], "Memo/Vendor")
            check_department(driver, wait, row.get("department", "Sales and Marketing"))
            # Optional: project + task, only for billable work.
            project = (row.get("project") or "").strip()
            if project:
                fill_popupselect(driver, wait, SEL_LINE_PROJECT, SEL_LINE_PROJECT_HIDDEN,
                                 project, "Project")
                task = (row.get("project_task") or "").strip()
                if not task:
                    raise RuntimeError(f"Line {i} has a project but no project_task — NetSuite requires both.")
                fill_popupselect(driver, wait, SEL_LINE_PROJECT_TASK, SEL_LINE_PROJECT_TASK_HIDDEN,
                                 task, "Project Task")
            # Optional: EBITDA add-back, only for CaST executive-management lines.
            if (row.get("ebitda_addback") or "").strip().lower() == "yes":
                fill_dropdown(driver, wait, SEL_LINE_EBITDA_DISPLAY, "Yes", "EBITDA Add-back")
            # Receipt upload (popup), then Add to commit the line.
            receipt = os.path.join(receipts_dir, row["receipt_file"])
            if not os.path.exists(receipt):
                print(f"  WARNING: receipt file missing, skipped attach: {receipt}")
            else:
                upload_receipt(driver, wait, receipt, row["receipt_file"])
            add_line(driver, wait, i)

        print("\nDONE FILLING — NOT SUBMITTED. Review the draft in the browser,")
        print("then click Submit / Submit for Supervisor Approval yourself.")
        print("The browser stays open after this script exits.")
    except Exception as exc:
        if not port_open(CHROME_DEBUG_PORT):
            # The browser itself was closed (or killed) mid-run.
            print("\nSTOPPED: the filler browser was closed. Nothing was submitted; "
                  "run again to start a fresh browser.")
            sys.exit(1)
        # Safety rule: any failure stops the run with the browser LEFT OPEN
        # (no driver.quit()) so the user can see and fix the draft by hand.
        print(f"\nSTOPPED: {type(exc).__name__}: {exc}")
        # An open alert blocks every later call, including the HTML dump:
        # read it, print it, and clear it first.
        alert = take_alert(driver)
        if alert is not None:
            print(f"  NetSuite alert: {alert}")
        try:
            print(f"  Current page: {driver.current_url}")
            for msg in page_messages(driver):
                print(f"  NetSuite message: {msg}")
        except Exception:
            pass
        save_debug_page(driver)
        print("Nothing was submitted. The browser is left open for review.")
        sys.exit(1)


if __name__ == "__main__":
    main()
