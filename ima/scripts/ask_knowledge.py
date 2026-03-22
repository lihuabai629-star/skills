#!/usr/bin/env python3
"""
Ask public or knowledge-scoped questions through ima.qq.com.
"""

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager, import_patchright, page_requires_login
from browser_utils import BrowserFactory, IMAUi
from config import HOME_URL, PAGE_LOAD_TIMEOUT_MS, QUERY_RETRIES, QUERY_RETRY_DELAY_SECONDS, QUERY_TIMEOUT_SECONDS
from knowledge_manager import KnowledgeLibrary, select_knowledge_entry


UI_NOISE_LINES = {
    "新对话",
    "我的知识库",
    "知识库广场",
    "问答历史",
    "关于ima",
    "打开电脑版",
    "问问",
    "对话模式",
    "DS 快速",
    "HY 2.0",
    "内容由AI生成仅供参考",
    "暂无历史会话",
}

ANSWER_META_LINES = {
    "ima",
    "停止回答",
    "正在搜索知识库资料...",
}

ANSWER_STOP_LINES = UI_NOISE_LINES | {
    "问答历史",
}

DATE_LINE_RE = re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日$")


def get_latest_markdown_text(page: Any) -> str | None:
    try:
        locator = page.locator("[class*=markdown]").last
        text = " ".join(locator.inner_text(timeout=1000).split())
        return text or None
    except Exception:
        return None


def extract_markdown_answer(
    previous_markdown: str | None,
    current_markdown: str | None,
    question: str,
) -> str | None:
    if not current_markdown:
        return None
    candidate = " ".join(current_markdown.split()).strip()
    if not candidate or candidate == question:
        return None
    if any(marker in candidate for marker in ANSWER_META_LINES):
        return None
    if previous_markdown and candidate == " ".join(previous_markdown.split()).strip():
        return None
    return candidate


def extract_answer_text(before_text: str, after_text: str, question: str) -> str:
    normalized_lines = [" ".join(line.split()) for line in after_text.splitlines()]
    question_indexes = [index for index, line in enumerate(normalized_lines) if line == question]
    if question_indexes:
        candidate_indexes = []
        for index in question_indexes:
            lookahead = normalized_lines[index + 1 : index + 5]
            if any(
                line == "ima" or line.startswith("找到了") or line in ANSWER_META_LINES
                for line in lookahead
            ):
                candidate_indexes.append(index)
        question_index = candidate_indexes[-1] if candidate_indexes else question_indexes[-1]
        answer_lines: list[str] = []
        for line in normalized_lines[question_index + 1 :]:
            if not line:
                continue
            if line in ANSWER_STOP_LINES or DATE_LINE_RE.match(line):
                break
            if line in ANSWER_META_LINES or line.startswith("找到了"):
                continue
            answer_lines.append(line)
        return "\n".join(answer_lines).strip()

    before_lines = {" ".join(line.split()) for line in before_text.splitlines() if line.strip()}
    answer_lines: list[str] = []
    for raw_line in after_text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        if line == question or line in UI_NOISE_LINES:
            continue
        if line in ANSWER_META_LINES or line.startswith("找到了"):
            continue
        if line in before_lines:
            continue
        answer_lines.append(line)
    return "\n".join(answer_lines).strip()


def _resolve_target_knowledge(query: str | None, knowledge_id: str | None) -> dict[str, Any]:
    library = KnowledgeLibrary()
    entries = library.list_entries()
    if not entries:
        raise RuntimeError(
            "No knowledge bases cached. Run: python scripts/run.py knowledge_manager.py list --refresh"
        )

    if knowledge_id:
        for entry in entries:
            if entry["id"] == knowledge_id:
                return entry
        raise RuntimeError(f"Knowledge base id not found: {knowledge_id}")

    if query:
        return select_knowledge_entry(entries, query)

    active = library.get_active()
    if active:
        return active
    raise RuntimeError("No active knowledge base. Run: python scripts/run.py knowledge_manager.py activate --query ...")


def _open_knowledge_base(page: Any, entry: dict[str, Any]) -> None:
    IMAUi.open_wikis(page)
    page.wait_for_timeout(2500)
    page.get_by_text(entry["name"], exact=True).first.click(timeout=10000)
    page.wait_for_timeout(2500)


def _ask_once(
    question: str,
    scope: str,
    show_browser: bool,
    timeout_seconds: int,
    knowledge_query: str | None,
    knowledge_id: str | None,
) -> str | None:
    playwright = None
    context = None
    try:
        playwright = import_patchright()().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=not show_browser)
        page = context.new_page()
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)

        body_text = IMAUi.get_body_text(page)
        if scope == "knowledge":
            auth = AuthManager()
            if not auth.is_authenticated() or page_requires_login(body_text):
                print("⚠️ Knowledge mode requires login. Run: python scripts/run.py auth_manager.py setup")
                return None
            target = _resolve_target_knowledge(knowledge_query, knowledge_id)
            _open_knowledge_base(page, target)

        IMAUi.wait_for_query_editor(page)
        before_text = IMAUi.get_body_text(page)
        before_markdown = get_latest_markdown_text(page)
        IMAUi.fill_query(page, question)
        page.keyboard.press("Enter")

        stable_count = 0
        last_answer = None
        start = time.time()
        while time.time() - start < timeout_seconds:
            after_text = IMAUi.get_body_text(page)
            answer = extract_answer_text(before_text, after_text, question)
            if not answer:
                current_markdown = get_latest_markdown_text(page)
                answer = extract_markdown_answer(before_markdown, current_markdown, question)
            if answer:
                if answer == last_answer:
                    stable_count += 1
                    if stable_count >= 2:
                        return answer
                else:
                    last_answer = answer
                    stable_count = 0
            page.wait_for_timeout(1000)

        return last_answer
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


def ask_ima(
    question: str,
    scope: str,
    show_browser: bool = False,
    timeout_seconds: int = QUERY_TIMEOUT_SECONDS,
    retries: int = QUERY_RETRIES,
    retry_delay_seconds: float = QUERY_RETRY_DELAY_SECONDS,
    knowledge_query: str | None = None,
    knowledge_id: str | None = None,
) -> str | None:
    last_answer = None
    for attempt in range(retries + 1):
        if attempt > 0:
            print(f"🔁 Retry {attempt}/{retries}...")
            time.sleep(retry_delay_seconds)
        last_answer = _ask_once(
            question=question,
            scope=scope,
            show_browser=show_browser,
            timeout_seconds=timeout_seconds,
            knowledge_query=knowledge_query,
            knowledge_id=knowledge_id,
        )
        if last_answer:
            return last_answer
    return last_answer


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask questions through ima.qq.com")
    parser.add_argument("--question", required=True, help="Question to ask")
    parser.add_argument(
        "--scope",
        default="public",
        choices=("public", "knowledge"),
        help="Whether to ask on the public home page or a selected knowledge base",
    )
    parser.add_argument("--show-browser", action="store_true", help="Show browser while asking")
    parser.add_argument("--timeout", type=int, default=QUERY_TIMEOUT_SECONDS)
    parser.add_argument("--retries", type=int, default=QUERY_RETRIES)
    parser.add_argument("--retry-delay", type=float, default=QUERY_RETRY_DELAY_SECONDS)
    parser.add_argument("--knowledge-query", help="Knowledge base name or partial match")
    parser.add_argument("--knowledge-id", help="Knowledge base id")
    args = parser.parse_args()

    answer = ask_ima(
        question=args.question,
        scope=args.scope,
        show_browser=args.show_browser,
        timeout_seconds=args.timeout,
        retries=args.retries,
        retry_delay_seconds=args.retry_delay,
        knowledge_query=args.knowledge_query,
        knowledge_id=args.knowledge_id,
    )
    if not answer:
        print("❌ No answer received")
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
