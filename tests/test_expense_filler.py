"""Offline tests for netsuite_expense_filler.py.

These tests never touch NetSuite or a browser. They cover CSV parsing,
totals, the selector builder, and the business-reason length limit
(NetSuite's custcol_reason field allows 300 chars).
"""

import csv
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The filler needs selenium + python-dotenv at runtime, but these tests
# are offline-only and must run without them installed. Stub the imports
# they need (By, Keys, EC, WebDriverWait, Chrome, load_dotenv) if absent.
try:
    import selenium  # noqa: F401
    import dotenv  # noqa: F401
except ImportError:
    selenium = types.ModuleType("selenium")
    selenium.__path__ = []
    webdriver = types.ModuleType("selenium.webdriver")
    webdriver.__path__ = []
    common = types.ModuleType("selenium.webdriver.common")
    common.__path__ = []
    exceptions_mod = types.ModuleType("selenium.common.exceptions")
    exceptions_mod.__path__ = []
    by_mod = types.ModuleType("selenium.webdriver.common.by")
    keys_mod = types.ModuleType("selenium.webdriver.common.keys")
    action_chains_mod = types.ModuleType("selenium.webdriver.common.action_chains")
    action_chains_mod.ActionChains = object
    support = types.ModuleType("selenium.webdriver.support")
    support.__path__ = []
    ec_mod = types.ModuleType("selenium.webdriver.support.expected_conditions")
    ui_mod = types.ModuleType("selenium.webdriver.support.ui")

    class By:
        ID = "id"
        XPATH = "xpath"
        CSS_SELECTOR = "css selector"
        NAME = "name"

    class Keys:
        TAB = "\t"
        ENTER = "\n"

    by_mod.By = By
    keys_mod.Keys = Keys
    ec_mod.element_to_be_clickable = lambda locator: locator
    ec_mod.presence_of_element_located = lambda locator: locator

    class TimeoutException(Exception):
        pass

    class WebDriverException(Exception):
        pass

    exceptions_mod.TimeoutException = TimeoutException
    exceptions_mod.WebDriverException = WebDriverException
    common.exceptions = exceptions_mod
    ui_mod.WebDriverWait = object
    webdriver.ChromeOptions = object
    webdriver.Chrome = object
    common.by = by_mod
    common.keys = keys_mod
    support.expected_conditions = ec_mod
    support.ui = ui_mod
    selenium.webdriver = webdriver
    sys.modules.update({
        "selenium": selenium,
        "selenium.webdriver": webdriver,
        "selenium.common": types.ModuleType("selenium.common"),
        "selenium.common.exceptions": exceptions_mod,
        "selenium.webdriver.common": common,
        "selenium.webdriver.common.by": by_mod,
        "selenium.webdriver.common.keys": keys_mod,
        "selenium.webdriver.common.action_chains": action_chains_mod,
        "selenium.webdriver.support": support,
        "selenium.webdriver.support.expected_conditions": ec_mod,
        "selenium.webdriver.support.ui": ui_mod,
    })
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

import netsuite_expense_filler as filler

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_CSV = os.path.join(REPO, "sample_expenses.csv")


def load_sample():
    with open(SAMPLE_CSV, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class TestSampleCsv(unittest.TestCase):
    def test_sample_loads_with_expected_columns(self):
        rows = load_sample()
        self.assertGreater(len(rows), 0)
        expected = {"date", "category", "amount", "business_reason", "memo_vendor",
                    "department", "project", "project_task", "ebitda_addback", "receipt_file"}
        self.assertTrue(expected.issubset(rows[0].keys()))

    def test_amounts_parse_and_total_is_positive(self):
        rows = load_sample()
        total = sum(float(r["amount"]) for r in rows)
        self.assertGreater(total, 0)

    def test_business_reasons_within_netsuite_limit(self):
        for row in load_sample():
            self.assertLessEqual(len(row["business_reason"]), 300)

    def test_project_requires_task(self):
        for row in load_sample():
            if row["project"].strip():
                self.assertTrue(row["project_task"].strip(),
                                f"project without task: {row}")

    def test_no_real_receipt_files_referenced(self):
        # Sample CSV must not point at a real trip's receipts.
        for row in load_sample():
            self.assertTrue(row["receipt_file"].startswith("XX_"))


class TestSelectors(unittest.TestCase):
    def test_cell_selector_scopes_to_sublist_cell(self):
        by, value = filler.cell("memo")
        self.assertIn('td[data-field-name="memo"]', value)

    def test_category_and_amount_selectors_differ(self):
        self.assertNotEqual(filler.SEL_LINE_CATEGORY, filler.SEL_LINE_AMOUNT)

    def test_add_line_selector_is_an_id(self):
        by, value = filler.SEL_ADD_LINE
        self.assertEqual(value, "expense_addedit")

    def test_default_cell_selector_skips_hidden_inputs(self):
        # The clickable wait checks only the first match; a hidden helper
        # input first in the cell made the first line time out.
        by, value = filler.cell("memo")
        self.assertIn(':not([type="hidden"])', value)

    def test_line_selectors_pin_documented_input_ids(self):
        expected = {
            filler.SEL_LINE_DATE: ("expensedate", "input#expensedate"),
            filler.SEL_LINE_CATEGORY: ("category", "input#expense_category_display"),
            filler.SEL_LINE_AMOUNT: ("amount", "input#amount_formattedValue"),
            filler.SEL_LINE_BUSINESS_REASON: ("custcol_reason", "input#custcol_reason"),
            filler.SEL_LINE_PROJECT: ("customer", "input#expense_customer_display"),
            filler.SEL_LINE_PROJECT_TASK: ("projecttask", "input#expense_projecttask_display"),
        }
        for (by, value), (field, inp) in expected.items():
            self.assertIn(f'td[data-field-name="{field}"]', value)
            self.assertTrue(value.endswith(inp), value)

    def test_line_selectors_are_scoped_to_the_edit_row(self):
        # After line 1 is Added, its committed row has the same cells and
        # comes first; an unscoped selector clicked line 1 on line 2.
        for by, value in (filler.SEL_LINE_DATE, filler.SEL_LINE_CATEGORY,
                          filler.SEL_LINE_MEMO, filler.SEL_LINE_DEPARTMENT_DISPLAY,
                          filler.SEL_LINE_ATTACH_NEW):
            self.assertTrue(value.startswith("tr.uir-machine-row-focused"), value)
            # ...and to the EXPENSE edit row, not another sublist's.
            self.assertIn(':has(> td[data-field-name="expensedate"])', value)

    def test_find_input_can_split_cell_from_suffix(self):
        # find_input clicks the cell: everything before the last space.
        by, value = filler.SEL_LINE_DEPARTMENT_DISPLAY
        self.assertEqual(value.rsplit(" ", 1)[0], filler.cell_css("department"))

    def test_department_selected_by_name_without_id_suffix(self):
        by, value = filler.SEL_LINE_DEPARTMENT_DISPLAY
        self.assertIn('input[name="inpt_department"]', value)
        self.assertNotIn("inpt_department_", value)

    def test_attach_file_selectors_go_through_their_cell(self):
        # The "+" button is parked off-table until the expmediaitem cell is
        # focused, so it must be found via the cell (find_input focuses it).
        for by, value in (filler.SEL_LINE_ATTACH_NEW, filler.SEL_LINE_ATTACH_DISPLAY):
            self.assertIn(filler.cell_css("expmediaitem") + " ", value)
        self.assertTrue(filler.SEL_LINE_ATTACH_NEW[1].endswith("#expmediaitem_popup_new"))

    def test_only_a_never_saved_report_counts_as_new(self):
        base = "https://1234567.app.netsuite.com/app/accounting/transactions/exprept.nl"
        self.assertTrue(filler.is_new_report_url(base))
        self.assertTrue(filler.is_new_report_url(base + "?whence="))
        # An existing draft has a record id: never fill on top of it.
        self.assertFalse(filler.is_new_report_url(base + "?id=4821"))
        self.assertFalse(filler.is_new_report_url(base + "?id=4821&e=T"))
        self.assertFalse(filler.is_new_report_url(
            "https://1234567.app.netsuite.com/app/center/card.nl"))

    def test_add_check_counts_only_expense_rows(self):
        # Other sublists (calls, events, media) also have sublist rows; the
        # Add commit check must count only rows with an expense date cell.
        xp = filler.EXPENSE_ROWS_XPATH
        self.assertIn('data-ui-role="sublist-row"', xp)
        self.assertIn('td[@data-field-name="expensedate"]', xp)

    def test_chrome_profile_is_outside_the_repo(self):
        # The profile holds NetSuite session cookies — never in the repo.
        self.assertFalse(os.path.abspath(filler.CHROME_PROFILE_DIR)
                         .startswith(os.path.abspath(REPO)))

    def test_header_and_line_memo_are_scoped_apart(self):
        self.assertIn('form[name="main_form"]', filler.SEL_HEADER_REPORT_NAME[1])
        self.assertIn('td[data-field-name="memo"]', filler.SEL_LINE_MEMO[1])


if __name__ == "__main__":
    unittest.main()


class TestFolderMode(unittest.TestCase):
    """resolve_inputs: the trip-folder workflow.

    Download the CSV + receipt files into one folder and hand the script
    that folder; or hand it a CSV file and receipts default to the CSV's
    folder. An explicit --receipts-dir always wins.
    """

    def _make_folder(self, tmp, csv_names):
        folder = os.path.join(tmp, "2026_10_MSP")
        os.makedirs(folder)
        for name in csv_names:
            with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                f.write("date,category,amount,business_reason,memo_vendor,"
                        "department,project,project_task,ebitda_addback,"
                        "receipt_file\n")
        return folder

    def test_folder_with_one_csv_uses_it_and_its_folder_for_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._make_folder(tmp, ["expenses.csv"])
            csv_path, receipts_dir = filler.resolve_inputs(folder, None)
            self.assertEqual(csv_path, os.path.join(folder, "expenses.csv"))
            self.assertEqual(receipts_dir, folder)

    def test_folder_with_no_csv_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._make_folder(tmp, [])
            with self.assertRaises(FileNotFoundError):
                filler.resolve_inputs(folder, None)

    def test_folder_with_two_csvs_fails_and_names_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._make_folder(tmp, ["a.csv", "b.csv"])
            with self.assertRaises(ValueError) as ctx:
                filler.resolve_inputs(folder, None)
            self.assertIn("a.csv", str(ctx.exception))
            self.assertIn("b.csv", str(ctx.exception))

    def test_csv_file_defaults_receipts_to_its_own_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._make_folder(tmp, ["expenses.csv"])
            csv_file = os.path.join(folder, "expenses.csv")
            csv_path, receipts_dir = filler.resolve_inputs(csv_file, None)
            self.assertEqual(csv_path, csv_file)
            self.assertEqual(receipts_dir, folder)

    def test_explicit_receipts_dir_wins_over_both_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._make_folder(tmp, ["expenses.csv"])
            other = os.path.join(tmp, "elsewhere")
            os.makedirs(other)
            _, receipts_dir = filler.resolve_inputs(folder, other)
            self.assertEqual(receipts_dir, other)
            _, receipts_dir = filler.resolve_inputs(
                os.path.join(folder, "expenses.csv"), other)
            self.assertEqual(receipts_dir, other)

    def test_missing_path_fails(self):
        with self.assertRaises(FileNotFoundError):
            filler.resolve_inputs("/definitely/not/a/real/path", None)

    def test_non_csv_files_in_folder_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._make_folder(tmp, ["expenses.csv"])
            # Receipt images/PDFs sitting alongside the CSV must not
            # confuse the folder scan.
            for name in ["receipt.jpg", "trip-confirmation.pdf"]:
                open(os.path.join(folder, name), "w").close()
            csv_path, _ = filler.resolve_inputs(folder, None)
            self.assertEqual(csv_path, os.path.join(folder, "expenses.csv"))
