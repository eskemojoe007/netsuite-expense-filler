"""Offline tests for netsuite_expense_filler.py.

These tests never touch NetSuite or a browser. They cover CSV parsing,
totals, the selector builder, and the business-reason length limit
(NetSuite's custcol_reason field allows 300 chars).
"""

import csv
import os
import sys
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

    exceptions_mod.TimeoutException = TimeoutException
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


if __name__ == "__main__":
    unittest.main()
