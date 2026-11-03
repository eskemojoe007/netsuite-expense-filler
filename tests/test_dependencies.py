"""Dependency check: are the packages the filler actually needs installed?

This is deliberately separate from test_expense_filler.py, which stubs
selenium/dotenv so the offline logic tests can run without them. This
file does NO stubbing: it imports the real packages, so it fails loudly
(and tells you how to fix it) when selenium or python-dotenv is missing
— the thing that most often breaks a fresh checkout.

Run it on its own for a quick environment check:

    python -m pipenv run python -m pytest tests/test_dependencies.py -v
"""

import importlib
import os
import unittest

INSTALL_HINT = (
    "Run: python -m pipenv install  (on Windows: python -m pipenv install)"
)

# (dotted module, attribute that must exist on it or None)
REQUIRED_MODULES = [
    ("selenium", "__version__"),
    ("selenium.webdriver", "Chrome"),
    ("selenium.webdriver", "ChromeOptions"),
    ("selenium.webdriver.common.by", "By"),
    ("selenium.webdriver.common.keys", "Keys"),
    ("selenium.webdriver.support.expected_conditions", "element_to_be_clickable"),
    ("selenium.webdriver.support.expected_conditions", "presence_of_element_located"),
    ("selenium.webdriver.support.ui", "WebDriverWait"),
    ("selenium.common.exceptions", "TimeoutException"),
    ("dotenv", "load_dotenv"),
]


class TestDependenciesInstalled(unittest.TestCase):
    def test_required_packages_import(self):
        for module_name, attr in REQUIRED_MODULES:
            with self.subTest(module=module_name):
                try:
                    module = importlib.import_module(module_name)
                except ImportError as exc:
                    self.fail(
                        f"Missing dependency: {module_name} could not be "
                        f"imported ({exc}). {INSTALL_HINT}"
                    )
                # The offline tests (test_expense_filler.py) stub selenium
                # in sys.modules so they can run without it. A stub has no
                # real file behind it, so a stubbed import must NOT count
                # as "installed" here — otherwise this check would pass
                # on a machine where selenium is actually missing.
                module_file = getattr(module, "__file__", None)
                if not module_file or not os.path.exists(module_file):
                    self.fail(
                        f"Missing dependency: {module_name} has no real "
                        f"installed file behind it (only a test stub was "
                        f"found). {INSTALL_HINT}"
                    )
                if attr is not None:
                    self.assertTrue(
                        hasattr(module, attr),
                        f"{module_name} imported but has no {attr!r}. "
                        f"Your install may be broken — try reinstalling. "
                        f"{INSTALL_HINT}",
                    )

    def test_selenium_major_version_is_4_or_newer(self):
        try:
            selenium = importlib.import_module("selenium")
        except ImportError as exc:
            self.fail(f"Missing dependency: selenium ({exc}). {INSTALL_HINT}")
        selenium_file = getattr(selenium, "__file__", None)
        if not selenium_file or not os.path.exists(selenium_file):
            self.fail(
                "Missing dependency: selenium has no real installed file "
                f"behind it (only a test stub was found). {INSTALL_HINT}"
            )
        version = getattr(selenium, "__version__", "")
        major = version.split(".")[0] if version else ""
        self.assertTrue(
            major.isdigit() and int(major) >= 4,
            f"selenium version {version!r} is too old or unknown; "
            f"the filler needs Selenium 4+. {INSTALL_HINT}",
        )


if __name__ == "__main__":
    unittest.main()
