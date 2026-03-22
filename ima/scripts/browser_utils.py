"""
Browser helpers for the IMA web skill.
"""

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from config import (
    ALLOW_CHROMIUM_FALLBACK,
    BROWSER_ARGS,
    BROWSER_PROFILE_DIR,
    HOME_URL,
    LAUNCH_RETRIES,
    LAUNCH_RETRY_DELAY_SECONDS,
    LOCKFILE_MAX_AGE_SECONDS,
    PAGE_LOAD_TIMEOUT_MS,
    QUERY_EDITOR_SELECTOR,
    SIDEBAR_ITEMS,
    STATE_FILE,
    WIKIS_URL,
)

if TYPE_CHECKING:
    from patchright.sync_api import BrowserContext, Page, Playwright


class BrowserFactory:
    @staticmethod
    def launch_persistent_context(
        playwright: "Playwright",
        headless: bool = True,
        user_data_dir: str = str(BROWSER_PROFILE_DIR),
    ) -> "BrowserContext":
        channels = ["chrome"]
        if ALLOW_CHROMIUM_FALLBACK:
            channels.append(None)

        last_error = None
        for attempt in range(LAUNCH_RETRIES + 1):
            for channel in channels:
                try:
                    BrowserFactory._cleanup_stale_profile_locks(user_data_dir)
                    launch_kwargs = {
                        "user_data_dir": user_data_dir,
                        "headless": headless,
                        "no_viewport": True,
                        "ignore_default_args": ["--enable-automation"],
                        "args": BROWSER_ARGS,
                    }
                    if channel:
                        launch_kwargs["channel"] = channel
                    context = playwright.chromium.launch_persistent_context(**launch_kwargs)
                    BrowserFactory._inject_cookies(context)
                    return context
                except Exception as exc:
                    last_error = exc
                    if channel == "chrome" and ALLOW_CHROMIUM_FALLBACK:
                        print("  ⚠️ Chrome launch failed, falling back to bundled Chromium...")
                        continue

            if attempt < LAUNCH_RETRIES:
                print(f"  ⚠️ Browser launch failed, retrying ({attempt + 1}/{LAUNCH_RETRIES})...")
                time.sleep(LAUNCH_RETRY_DELAY_SECONDS)

        if last_error:
            raise last_error
        raise RuntimeError("Failed to launch browser context")

    @staticmethod
    def _cleanup_stale_profile_locks(user_data_dir: str) -> None:
        profile_dir = Path(user_data_dir)
        if not profile_dir.exists():
            return

        now = time.time()
        lock_names = ("SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile")
        for name in lock_names:
            path = profile_dir / name
            if not path.exists():
                continue
            try:
                age_seconds = now - path.stat().st_mtime
                if age_seconds >= LOCKFILE_MAX_AGE_SECONDS:
                    path.unlink()
            except Exception:
                continue

    @staticmethod
    def _inject_cookies(context: "BrowserContext") -> None:
        if not STATE_FILE.exists():
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as handle:
                state = json.load(handle)
            cookies = state.get("cookies", [])
            if cookies:
                context.add_cookies(cookies)
        except Exception as exc:
            print(f"  ⚠️ Could not inject cookies from state.json: {exc}")


class IMAUi:
    @staticmethod
    def open_home(page: "Page") -> None:
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)

    @staticmethod
    def open_wikis(page: "Page") -> None:
        page.goto(WIKIS_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)

    @staticmethod
    def get_body_text(page: "Page") -> str:
        return page.locator("body").inner_text()

    @staticmethod
    def click_sidebar_item(page: "Page", label: str) -> bool:
        selectors = [
            f"div[style*='cursor:pointer']:has-text('{label}')",
            f"div._baseItemWrap_vnbck_1:has-text('{label}')",
        ]
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.click()
                return True

        text_locator = page.get_by_text(label, exact=True)
        if text_locator.count() > 0:
            text_locator.first.click()
            return True
        return False

    @staticmethod
    def wait_for_query_editor(page: "Page", timeout_ms: int = 10000) -> None:
        page.locator(QUERY_EDITOR_SELECTOR).first.wait_for(timeout=timeout_ms)

    @staticmethod
    def fill_query(page: "Page", text: str) -> None:
        editor = page.locator(QUERY_EDITOR_SELECTOR).first
        editor.click()
        page.keyboard.insert_text(text)

    @staticmethod
    def known_sidebar_labels() -> tuple[str, ...]:
        return SIDEBAR_ITEMS
