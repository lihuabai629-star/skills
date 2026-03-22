import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from browser_utils import IMAUi  # noqa: E402
from config import HOME_URL, PAGE_LOAD_TIMEOUT_MS, WIKIS_URL  # noqa: E402


class FakePage:
    def __init__(self) -> None:
        self.calls = []

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.calls.append(
            {
                "url": url,
                "wait_until": wait_until,
                "timeout": timeout,
            }
        )


class BrowserUtilsTests(unittest.TestCase):
    def test_open_home_uses_home_url_and_default_timeout(self):
        page = FakePage()

        IMAUi.open_home(page)

        self.assertEqual(
            page.calls,
            [
                {
                    "url": HOME_URL,
                    "wait_until": "domcontentloaded",
                    "timeout": PAGE_LOAD_TIMEOUT_MS,
                }
            ],
        )

    def test_open_wikis_uses_wikis_url_and_default_timeout(self):
        page = FakePage()

        IMAUi.open_wikis(page)

        self.assertEqual(
            page.calls,
            [
                {
                    "url": WIKIS_URL,
                    "wait_until": "domcontentloaded",
                    "timeout": PAGE_LOAD_TIMEOUT_MS,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
