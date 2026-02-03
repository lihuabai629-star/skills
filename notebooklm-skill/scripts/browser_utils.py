"""
Browser Utilities for NotebookLM Skill
Handles browser launching, stealth features, and common interactions
"""

import json
import time
import random
from pathlib import Path
from typing import Optional, List

from patchright.sync_api import Playwright, BrowserContext, Page
from config import (
    BROWSER_PROFILE_DIR,
    STATE_FILE,
    BROWSER_ARGS,
    USER_AGENT,
    LAUNCH_RETRIES,
    LAUNCH_RETRY_DELAY_SECONDS,
    LOCKFILE_MAX_AGE_SECONDS,
    ALLOW_CHROMIUM_FALLBACK,
)


class BrowserFactory:
    """Factory for creating configured browser contexts"""

    @staticmethod
    def launch_persistent_context(
        playwright: Playwright,
        headless: bool = True,
        user_data_dir: str = str(BROWSER_PROFILE_DIR)
    ) -> BrowserContext:
        """
        Launch a persistent browser context with anti-detection features
        and cookie workaround.
        """
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
                        "user_agent": USER_AGENT,
                        "args": BROWSER_ARGS,
                    }
                    if channel:
                        launch_kwargs["channel"] = channel

                    context = playwright.chromium.launch_persistent_context(**launch_kwargs)

                    # Cookie Workaround for Playwright bug #36139
                    # Session cookies (expires=-1) don't persist in user_data_dir automatically
                    BrowserFactory._inject_cookies(context)

                    return context
                except Exception as e:
                    last_error = e
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
    def _cleanup_stale_profile_locks(user_data_dir: str):
        """Remove stale Chrome lock files that can prevent launches."""
        profile_dir = Path(user_data_dir)
        if not profile_dir.exists():
            return

        now = time.time()
        lock_names = ("SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile")
        removed = []

        for name in lock_names:
            path = profile_dir / name
            if not path.exists():
                continue
            try:
                age_seconds = now - path.stat().st_mtime
                if age_seconds >= LOCKFILE_MAX_AGE_SECONDS:
                    path.unlink()
                    removed.append(name)
            except Exception:
                continue

        if removed:
            print(f"  🧹 Removed stale profile lock(s): {', '.join(removed)}")

    @staticmethod
    def _inject_cookies(context: BrowserContext):
        """Inject cookies from state.json if available"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    if 'cookies' in state and len(state['cookies']) > 0:
                        context.add_cookies(state['cookies'])
                        # print(f"  🔧 Injected {len(state['cookies'])} cookies from state.json")
            except Exception as e:
                print(f"  ⚠️  Could not load state.json: {e}")


class StealthUtils:
    """Human-like interaction utilities"""

    @staticmethod
    def random_delay(min_ms: int = 100, max_ms: int = 500):
        """Add random delay"""
        time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    @staticmethod
    def human_type(page: Page, selector: str, text: str, wpm_min: int = 320, wpm_max: int = 480):
        """Type with human-like speed"""
        # Locator is more robust against DOM detach than a stale element handle
        locator = page.locator(selector)
        try:
            locator.wait_for(timeout=5000)
        except Exception:
            print(f"⚠️ Element not found for typing: {selector}")
            return

        # Retry a few times in case the input re-renders while typing
        for attempt in range(3):
            try:
                locator.click()
                # Clear first to avoid concatenating previous input
                try:
                    locator.fill("")
                except Exception:
                    pass

                for char in text:
                    locator.type(char, delay=random.uniform(25, 75))
                    if random.random() < 0.05:
                        time.sleep(random.uniform(0.15, 0.4))
                return
            except Exception:
                # Re-query on detach and retry
                StealthUtils.random_delay(150, 400)
                continue

        # Fallback: direct fill if typing keeps failing
        try:
            locator.fill(text)
        except Exception:
            print(f"⚠️ Failed to type into element: {selector}")

    @staticmethod
    def realistic_click(page: Page, selector: str):
        """Click with realistic movement"""
        element = page.query_selector(selector)
        if not element:
            return

        # Optional: Move mouse to element (simplified)
        box = element.bounding_box()
        if box:
            x = box['x'] + box['width'] / 2
            y = box['y'] + box['height'] / 2
            page.mouse.move(x, y, steps=5)

        StealthUtils.random_delay(100, 300)
        element.click()
        StealthUtils.random_delay(100, 300)
