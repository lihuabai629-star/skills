#!/usr/bin/env python3
"""
Simple NotebookLM Question Interface
Based on MCP server implementation - simplified without sessions

Implements hybrid auth approach:
- Persistent browser profile (user_data_dir) for fingerprint consistency
- Manual cookie injection from state.json for session cookies (Playwright bug workaround)
See: https://github.com/microsoft/playwright/issues/36139
"""

import argparse
import sys
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import (
    QUERY_INPUT_SELECTORS,
    RESPONSE_SELECTORS,
    QUERY_TIMEOUT_SECONDS,
    PAGE_LOAD_TIMEOUT,
    QUERY_RETRIES,
    QUERY_RETRY_DELAY_SECONDS,
    QUERY_MAX_TOTAL_SECONDS,
    QUERY_HEARTBEAT_SECONDS,
)
from browser_utils import BrowserFactory, StealthUtils


# Follow-up reminder (adapted from MCP server for stateless operation)
# Since we don't have persistent sessions, we encourage comprehensive questions
FOLLOW_UP_REMINDER = (
    "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know? "
    "You can always ask another question! Think about it carefully: "
    "before you reply to the user, review their original request and this answer. "
    "If anything is still unclear or missing, ask me another comprehensive question "
    "that includes all necessary context (since each question opens a new browser session)."
)


def _log(message: str):
    """Always flush log output so long-running queries show live progress."""
    print(message, flush=True)


def _wait_for_notebook_page(page, timeout_ms: int = 10000, poll_ms: int = 250) -> str:
    """
    Wait until the page is clearly on a NotebookLM notebook or redirected to login.

    `page.wait_for_url()` is too brittle here: after `goto()` completes, Patchright still
    performs an extra load-state wait and can time out even when `page.url` already matches
    the target notebook. Poll the current URL directly instead.
    """
    deadline = time.time() + (timeout_ms / 1000)
    while True:
        url = page.url or ""
        if url.startswith("https://notebooklm.google.com/"):
            return "ready"
        if "accounts.google.com" in url:
            return "login"
        if time.time() >= deadline:
            raise TimeoutError(f"Timeout {timeout_ms}ms exceeded.")
        page.wait_for_timeout(poll_ms)


def _ask_notebooklm_once(
    question: str,
    notebook_url: str,
    headless: bool = True,
    timeout_seconds: int = QUERY_TIMEOUT_SECONDS
) -> str:
    """
    Ask a question to NotebookLM (single attempt)

    Args:
        question: Question to ask
        notebook_url: NotebookLM notebook URL
        headless: Run browser in headless mode
        timeout_seconds: Answer timeout in seconds

    Returns:
        Answer text from NotebookLM
    """
    _log(f"💬 Asking: {question}")
    _log(f"📚 Notebook: {notebook_url}")

    playwright = None
    context = None

    try:
        # Start playwright
        playwright = sync_playwright().start()

        # Launch persistent browser context using factory
        context = BrowserFactory.launch_persistent_context(
            playwright,
            headless=headless
        )

        # Navigate to notebook
        page = context.new_page()
        _log("  🌐 Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)

        # Wait for NotebookLM
        try:
            status = _wait_for_notebook_page(page, timeout_ms=10000)
        except Exception:
            _log(f"  ⚠️ Notebook open state: url={page.url}")
            try:
                _log(f"  ⚠️ Notebook title: {page.title()}")
            except Exception:
                pass
            if "accounts.google.com" in page.url:
                _log("  ❌ Not authenticated (redirected to login). Run: python scripts/run.py auth_manager.py setup")
                return None
            raise
        if status == "login":
            _log("  ❌ Not authenticated (redirected to login). Run: python scripts/run.py auth_manager.py setup")
            return None

        # Wait for query input (MCP approach)
        _log("  ⏳ Waiting for query input...")
        query_element = None

        for selector in QUERY_INPUT_SELECTORS:
            try:
                query_element = page.wait_for_selector(
                    selector,
                    timeout=10000,
                    state="visible"  # Only check visibility, not disabled!
                )
                if query_element:
                    _log(f"  ✓ Found input: {selector}")
                    break
            except Exception:
                continue

        if not query_element:
            _log("  ❌ Could not find query input")
            return None

        # Type question (human-like, fast)
        _log("  ⏳ Typing question...")
        
        # Use primary selector for typing
        input_selector = QUERY_INPUT_SELECTORS[0]
        StealthUtils.human_type(page, input_selector, question)

        # Submit
        _log("  📤 Submitting...")
        page.keyboard.press("Enter")

        # Small pause
        StealthUtils.random_delay(500, 1500)

        # Wait for response (MCP approach: poll for stable text)
        _log("  ⏳ Waiting for answer...")

        answer = None
        stable_count = 0
        last_text = None
        last_reported_len = 0
        start_time = time.time()
        last_progress_time = start_time
        next_heartbeat = start_time + QUERY_HEARTBEAT_SECONDS
        max_total_seconds = max(timeout_seconds, QUERY_MAX_TOTAL_SECONDS)

        while True:
            now = time.time()
            elapsed = int(now - start_time)
            inactive_for = int(now - last_progress_time)

            if now >= next_heartbeat:
                _log(
                    f"  ⏱️ Waiting... elapsed={elapsed}s, inactive={inactive_for}s, "
                    f"soft-timeout={timeout_seconds}s, hard-timeout={max_total_seconds}s"
                )
                next_heartbeat = now + QUERY_HEARTBEAT_SECONDS

            # Hard cap avoids endless waits if NotebookLM UI gets stuck in "thinking" state.
            if elapsed >= max_total_seconds:
                _log(f"  ❌ Timeout waiting for answer (hit hard limit: {max_total_seconds}s)")
                return None

            # Soft timeout is reset by any observable progress.
            if inactive_for >= timeout_seconds:
                _log(f"  ❌ Timeout waiting for answer (no progress for {timeout_seconds}s)")
                return None

            # Check if NotebookLM is still thinking.
            try:
                thinking_element = page.query_selector('div.thinking-message')
                if thinking_element and thinking_element.is_visible():
                    last_progress_time = now
                    time.sleep(1)
                    continue
            except Exception:
                pass

            # Try to find response with MCP selectors
            saw_progress = False
            for selector in RESPONSE_SELECTORS:
                try:
                    elements = page.query_selector_all(selector)
                    if elements:
                        # Get last (newest) response
                        latest = elements[-1]
                        text = latest.inner_text().strip()

                        if text:
                            if text == last_text:
                                stable_count += 1
                                if stable_count >= 3:  # Stable for 3 polls
                                    answer = text
                                    break
                            else:
                                stable_count = 0
                                last_text = text
                                saw_progress = True

                                # Only report significant growth to keep logs readable.
                                if last_reported_len == 0 or len(text) >= last_reported_len + 200:
                                    _log(f"  ✍️ Answer streaming... {len(text)} chars")
                                    last_reported_len = len(text)
                except Exception:
                    continue

            if answer:
                break

            if saw_progress:
                last_progress_time = now

            time.sleep(1)

        _log("  ✅ Got answer!")
        # Add follow-up reminder to encourage Claude to ask more questions
        return answer + FOLLOW_UP_REMINDER

    except Exception as e:
        _log(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        # Always clean up
        if context:
            try:
                context.close()
            except:
                pass

        if playwright:
            try:
                playwright.stop()
            except:
                pass


def ask_notebooklm(
    question: str,
    notebook_url: str,
    headless: bool = True,
    timeout_seconds: int = QUERY_TIMEOUT_SECONDS,
    retries: int = QUERY_RETRIES,
    retry_delay_seconds: float = QUERY_RETRY_DELAY_SECONDS
) -> str:
    """
    Ask a question to NotebookLM with optional retries.
    """
    auth = AuthManager()
    if not auth.is_authenticated():
        _log("⚠️ Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    last_answer = None
    for attempt in range(retries + 1):
        if attempt > 0:
            _log(f"  🔁 Retry {attempt}/{retries}...")

        last_answer = _ask_notebooklm_once(
            question=question,
            notebook_url=notebook_url,
            headless=headless,
            timeout_seconds=timeout_seconds
        )

        if last_answer:
            return last_answer

        if attempt < retries:
            time.sleep(retry_delay_seconds)

    return last_answer


def main():
    parser = argparse.ArgumentParser(description='Ask NotebookLM a question')

    parser.add_argument('--question', required=True, help='Question to ask')
    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--notebook-id', help='Notebook ID from library')
    parser.add_argument('--show-browser', action='store_true', help='Show browser')
    parser.add_argument('--timeout', type=int, default=QUERY_TIMEOUT_SECONDS, help='Answer timeout in seconds')
    parser.add_argument('--retries', type=int, default=QUERY_RETRIES, help='Retry count on failure')
    parser.add_argument('--retry-delay', type=float, default=QUERY_RETRY_DELAY_SECONDS, help='Retry delay in seconds')

    args = parser.parse_args()

    # Resolve notebook URL
    notebook_url = args.notebook_url

    if not notebook_url and args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id)
        if notebook:
            notebook_url = notebook['url']
        else:
            print(f"❌ Notebook '{args.notebook_id}' not found")
            return 1

    if not notebook_url:
        # Check for active notebook first
        library = NotebookLibrary()
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            print(f"📚 Using active notebook: {active['name']}")
        else:
            # Show available notebooks
            notebooks = library.list_notebooks()
            if notebooks:
                print("\n📚 Available notebooks:")
                for nb in notebooks:
                    mark = " [ACTIVE]" if nb.get('id') == library.active_notebook_id else ""
                    print(f"  {nb['id']}: {nb['name']}{mark}")
                print("\nSpecify with --notebook-id or set active:")
                print("python scripts/run.py notebook_manager.py activate --id ID")
            else:
                print("❌ No notebooks in library. Add one first:")
                print("python scripts/run.py notebook_manager.py add --url URL --name NAME --description DESC --topics TOPICS")
            return 1

    # Ask the question
    answer = ask_notebooklm(
        question=args.question,
        notebook_url=notebook_url,
        headless=not args.show_browser,
        timeout_seconds=args.timeout,
        retries=args.retries,
        retry_delay_seconds=args.retry_delay
    )

    if answer:
        print("\n" + "=" * 60)
        print(f"Question: {args.question}")
        print("=" * 60)
        print()
        print(answer)
        print()
        print("=" * 60)
        return 0
    else:
        print("\n❌ Failed to get answer")
        return 1


if __name__ == "__main__":
    sys.exit(main())
