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
import re
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
    print(f"💬 Asking: {question}")
    print(f"📚 Notebook: {notebook_url}")

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
        print("  🌐 Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)

        # Wait for NotebookLM
        try:
            page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=10000)
        except Exception:
            if "accounts.google.com" in page.url:
                print("  ❌ Not authenticated (redirected to login). Run: python scripts/run.py auth_manager.py setup")
                return None
            raise

        # Wait for query input (MCP approach)
        print("  ⏳ Waiting for query input...")
        query_element = None

        for selector in QUERY_INPUT_SELECTORS:
            try:
                query_element = page.wait_for_selector(
                    selector,
                    timeout=10000,
                    state="visible"  # Only check visibility, not disabled!
                )
                if query_element:
                    print(f"  ✓ Found input: {selector}")
                    break
            except:
                continue

        if not query_element:
            print("  ❌ Could not find query input")
            return None

        # Type question (human-like, fast)
        print("  ⏳ Typing question...")
        
        # Use primary selector for typing
        input_selector = QUERY_INPUT_SELECTORS[0]
        StealthUtils.human_type(page, input_selector, question)

        # Submit
        print("  📤 Submitting...")
        page.keyboard.press("Enter")

        # Small pause
        StealthUtils.random_delay(500, 1500)

        # Wait for response (MCP approach: poll for stable text)
        print("  ⏳ Waiting for answer...")

        answer = None
        stable_count = 0
        last_text = None
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            # Check if NotebookLM is still thinking (most reliable indicator)
            try:
                thinking_element = page.query_selector('div.thinking-message')
                if thinking_element and thinking_element.is_visible():
                    time.sleep(1)
                    continue
            except:
                pass

            # Try to find response with MCP selectors
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
                except:
                    continue

            if answer:
                break

            time.sleep(1)

        if not answer:
            print("  ❌ Timeout waiting for answer")
            return None

        print("  ✅ Got answer!")
        # Add follow-up reminder to encourage Claude to ask more questions
        return answer + FOLLOW_UP_REMINDER

    except Exception as e:
        print(f"  ❌ Error: {e}")
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
        print("⚠️ Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    last_answer = None
    for attempt in range(retries + 1):
        if attempt > 0:
            print(f"  🔁 Retry {attempt}/{retries}...")

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
