#!/usr/bin/env python3
"""
Authentication manager for the IMA web skill.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from browser_utils import BrowserFactory, IMAUi
from config import (
    AUTH_INFO_FILE,
    BROWSER_UPGRADE_PATH,
    BROWSER_STATE_DIR,
    DATA_DIR,
    HOME_URL,
    LOGIN_REQUIRED_MARKERS,
    LOGIN_TIMEOUT_MINUTES,
    STATE_FILE,
)


def import_patchright():
    from patchright.sync_api import sync_playwright

    return sync_playwright


def page_requires_login(body_text: str) -> bool:
    normalized = " ".join(body_text.split())
    return any(marker in normalized for marker in LOGIN_REQUIRED_MARKERS)


def page_is_supported(page: Any) -> bool:
    return page.url != f"{HOME_URL.rstrip('/')}{BROWSER_UPGRADE_PATH}"


class AuthManager:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.state_file = STATE_FILE
        self.auth_info_file = AUTH_INFO_FILE
        self.browser_state_dir = BROWSER_STATE_DIR

    def is_authenticated(self) -> bool:
        return self.state_file.exists()

    def get_auth_info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "authenticated": self.is_authenticated(),
            "state_file": str(self.state_file),
            "state_exists": self.state_file.exists(),
        }
        if self.auth_info_file.exists():
            try:
                with open(self.auth_info_file, "r", encoding="utf-8") as handle:
                    info.update(json.load(handle))
            except Exception:
                pass
        if self.state_file.exists():
            info["state_age_hours"] = (time.time() - self.state_file.stat().st_mtime) / 3600
        return info

    def setup_auth(self, headless: bool = False, timeout_minutes: float = LOGIN_TIMEOUT_MINUTES) -> bool:
        print("🔐 Starting IMA authentication setup...")
        print(f"  Timeout: {timeout_minutes} minutes")

        playwright = None
        context = None
        try:
            playwright = import_patchright()().start()
            context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
            page = context.new_page()
            IMAUi.open_home(page)

            body_text = IMAUi.get_body_text(page)
            if not page_is_supported(page):
                print("  ❌ Browser launch hit ima browser-upgrade page")
                return False

            if page_requires_login(body_text):
                try:
                    page.get_by_text("登录", exact=True).click(timeout=3000)
                except Exception:
                    pass
                print("\n  ⏳ Please log in to ima.qq.com in the visible browser...")
            else:
                print("  ✅ Already authenticated")

            deadline = time.time() + (timeout_minutes * 60)
            while time.time() < deadline:
                body_text = IMAUi.get_body_text(page)
                if not page_requires_login(body_text):
                    print("  ✅ Login successful")
                    self._save_browser_state(context)
                    self._save_auth_info()
                    return True
                time.sleep(2)

            print("  ❌ Authentication timeout")
            return False
        except Exception as exc:
            print(f"  ❌ Error: {exc}")
            return False
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass

    def validate_auth(self) -> bool:
        if not self.is_authenticated():
            return False

        playwright = None
        context = None
        try:
            playwright = import_patchright()().start()
            context = BrowserFactory.launch_persistent_context(playwright, headless=True)
            page = context.new_page()
            IMAUi.open_home(page)
            body_text = IMAUi.get_body_text(page)
            valid = page_is_supported(page) and not page_requires_login(body_text)
            if valid:
                print("✅ Authentication is valid")
            else:
                print("❌ Authentication is not valid")
            return valid
        except Exception as exc:
            print(f"❌ Validation error: {exc}")
            return False
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass

    def clear_auth(self) -> bool:
        print("🗑️ Clearing authentication data...")
        try:
            if self.state_file.exists():
                self.state_file.unlink()
            if self.auth_info_file.exists():
                self.auth_info_file.unlink()
            if self.browser_state_dir.exists():
                shutil.rmtree(self.browser_state_dir)
                self.browser_state_dir.mkdir(parents=True, exist_ok=True)
            print("✅ Cleared authentication data")
            return True
        except Exception as exc:
            print(f"❌ Error clearing auth: {exc}")
            return False

    def re_auth(self, headless: bool = False, timeout_minutes: float = LOGIN_TIMEOUT_MINUTES) -> bool:
        self.clear_auth()
        return self.setup_auth(headless=headless, timeout_minutes=timeout_minutes)

    def _save_browser_state(self, context: Any) -> None:
        context.storage_state(path=str(self.state_file))
        print(f"  💾 Saved browser state to: {self.state_file}")

    def _save_auth_info(self) -> None:
        payload = {
            "authenticated_at": time.time(),
            "authenticated_at_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(self.auth_info_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)


def print_status(auth: AuthManager) -> None:
    info = auth.get_auth_info()
    print("\n🔐 Authentication Status:")
    print(f"  Authenticated: {'Yes' if info['authenticated'] else 'No'}")
    if "state_age_hours" in info:
        print(f"  State age: {info['state_age_hours']:.1f} hours")
    if "authenticated_at_iso" in info:
        print(f"  Last auth: {info['authenticated_at_iso']}")
    print(f"  State file: {info['state_file']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage ima.qq.com authentication")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show authentication status")
    status_parser.set_defaults(command="status")

    setup_parser = subparsers.add_parser("setup", help="Open browser and authenticate")
    setup_parser.add_argument("--headless", action="store_true", help="Run browser headless")
    setup_parser.add_argument("--timeout-minutes", type=float, default=LOGIN_TIMEOUT_MINUTES)

    reauth_parser = subparsers.add_parser("reauth", help="Clear auth and authenticate again")
    reauth_parser.add_argument("--headless", action="store_true", help="Run browser headless")
    reauth_parser.add_argument("--timeout-minutes", type=float, default=LOGIN_TIMEOUT_MINUTES)

    validate_parser = subparsers.add_parser("validate", help="Validate stored authentication")
    validate_parser.set_defaults(command="validate")

    clear_parser = subparsers.add_parser("clear", help="Clear authentication state")
    clear_parser.set_defaults(command="clear")

    args = parser.parse_args()
    auth = AuthManager()

    if args.command == "status":
        print_status(auth)
        return 0
    if args.command == "setup":
        return 0 if auth.setup_auth(headless=args.headless, timeout_minutes=args.timeout_minutes) else 1
    if args.command == "reauth":
        return 0 if auth.re_auth(headless=args.headless, timeout_minutes=args.timeout_minutes) else 1
    if args.command == "validate":
        return 0 if auth.validate_auth() else 1
    if args.command == "clear":
        return 0 if auth.clear_auth() else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
