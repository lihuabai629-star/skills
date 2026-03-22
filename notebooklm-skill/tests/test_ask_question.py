#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import ask_question  # noqa: E402


class FakePage:
    def __init__(self, urls: list[str]) -> None:
        self._urls = list(urls)
        self.wait_calls = 0

    @property
    def url(self) -> str:
        return self._urls[0]

    def wait_for_timeout(self, _ms: int) -> None:
        self.wait_calls += 1
        if len(self._urls) > 1:
            self._urls.pop(0)


class WaitForNotebookPageTests(unittest.TestCase):
    def test_returns_immediately_when_page_is_already_on_notebook_url(self) -> None:
        page = FakePage(["https://notebooklm.google.com/notebook/f711b22c-a098-451a-8995-b5f273cd53f1"])

        status = ask_question._wait_for_notebook_page(page, timeout_ms=1000, poll_ms=10)

        self.assertEqual(status, "ready")
        self.assertEqual(page.wait_calls, 0)

    def test_reports_login_redirect_without_waiting_for_extra_navigation(self) -> None:
        page = FakePage(["https://accounts.google.com/v3/signin/identifier"])

        status = ask_question._wait_for_notebook_page(page, timeout_ms=1000, poll_ms=10)

        self.assertEqual(status, "login")
        self.assertEqual(page.wait_calls, 0)

    def test_can_poll_until_notebook_url_becomes_ready(self) -> None:
        page = FakePage(
            [
                "about:blank",
                "https://notebooklm.google.com/notebook/f711b22c-a098-451a-8995-b5f273cd53f1",
            ]
        )

        status = ask_question._wait_for_notebook_page(page, timeout_ms=1000, poll_ms=10)

        self.assertEqual(status, "ready")
        self.assertEqual(page.wait_calls, 1)


if __name__ == "__main__":
    unittest.main()
