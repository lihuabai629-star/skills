#!/usr/bin/env python3
"""
Knowledge base discovery and local library management for IMA.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager, import_patchright, page_requires_login
from browser_utils import BrowserFactory, IMAUi
from config import LIBRARY_FILE


def normalize_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def build_knowledge_id(name: str) -> str:
    normalized = normalize_text(name)
    slug = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "-", normalized).strip("-")
    return slug or normalized.replace(" ", "-")


def select_knowledge_entry(entries: list[dict[str, Any]], query: str) -> dict[str, Any]:
    normalized_query = normalize_text(query)
    exact_matches = [entry for entry in entries if normalize_text(entry["name"]) == normalized_query]
    if exact_matches:
        return exact_matches[0]

    partial_matches = [
        entry for entry in entries if normalized_query in normalize_text(entry["name"])
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]
    if len(partial_matches) > 1:
        names = ", ".join(entry["name"] for entry in partial_matches)
        raise ValueError(f"Ambiguous knowledge base query '{query}': {names}")
    raise ValueError(f"Knowledge base '{query}' not found")


class KnowledgeLibrary:
    def __init__(self) -> None:
        self.library_file = LIBRARY_FILE
        self.library_file.parent.mkdir(parents=True, exist_ok=True)
        self.entries: dict[str, dict[str, Any]] = {}
        self.active_knowledge_id: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.library_file.exists():
            self._save()
            return
        try:
            with open(self.library_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.entries = payload.get("entries", {})
            self.active_knowledge_id = payload.get("active_knowledge_id")
        except Exception:
            self.entries = {}
            self.active_knowledge_id = None

    def _save(self) -> None:
        payload = {
            "entries": self.entries,
            "active_knowledge_id": self.active_knowledge_id,
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.library_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

    def set_entries(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.entries = {entry["id"]: entry for entry in entries}
        if self.active_knowledge_id not in self.entries:
            self.active_knowledge_id = entries[0]["id"] if entries else None
        self._save()
        return self.list_entries()

    def list_entries(self) -> list[dict[str, Any]]:
        return list(self.entries.values())

    def get_active(self) -> dict[str, Any] | None:
        if self.active_knowledge_id:
            return self.entries.get(self.active_knowledge_id)
        return None

    def activate(self, query: str) -> dict[str, Any]:
        entry = select_knowledge_entry(self.list_entries(), query)
        self.active_knowledge_id = entry["id"]
        self._save()
        return entry


def extract_knowledge_entries_from_body(body_text: str) -> list[dict[str, Any]]:
    section_markers = {"我创建的", "我加入的"}
    skip_lines = {
        "个人知识库",
        "共享知识库",
        "新对话",
        "关于ima",
        "打开电脑版",
        "问问",
        "对话模式",
        "暂无历史会话",
        "登录",
        "微信扫码登录",
    }

    cleaned_lines = [" ".join(line.split()) for line in body_text.splitlines()]
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    in_library_section = False
    for text in cleaned_lines:
        if not text:
            continue

        if text in section_markers:
            in_library_section = True
            continue

        if not in_library_section:
            continue

        if text in skip_lines:
            continue
        if text.startswith("已使用") and "/" in text:
            break
        if len(text) > 80:
            continue

        normalized = normalize_text(text)
        if normalized in seen:
            continue
        seen.add(normalized)
        entries.append(
            {
                "id": build_knowledge_id(text),
                "name": text,
            }
        )
    return entries


def discover_knowledge_entries(show_browser: bool = False) -> list[dict[str, Any]]:
    auth = AuthManager()
    if not auth.is_authenticated():
        raise RuntimeError("Not authenticated. Run: python scripts/run.py auth_manager.py setup")

    playwright = None
    context = None
    try:
        playwright = import_patchright()().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=not show_browser)
        page = context.new_page()
        IMAUi.open_wikis(page)

        body_text = IMAUi.get_body_text(page)
        if page_requires_login(body_text):
            raise RuntimeError(
                "Authentication is stale. Run: python scripts/run.py auth_manager.py reauth"
            )

        return extract_knowledge_entries_from_body(body_text)
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


def print_entries(entries: list[dict[str, Any]], active_id: str | None = None) -> None:
    if not entries:
        print("No knowledge bases discovered.")
        return
    for entry in entries:
        prefix = "* " if entry["id"] == active_id else "  "
        print(f"{prefix}{entry['name']} [{entry['id']}]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage IMA knowledge base library")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List known knowledge bases")
    list_parser.add_argument("--refresh", action="store_true", help="Refresh from ima.qq.com")
    list_parser.add_argument("--show-browser", action="store_true", help="Show browser during refresh")

    activate_parser = subparsers.add_parser("activate", help="Select an active knowledge base")
    activate_parser.add_argument("--query", required=True, help="Knowledge base name or partial match")

    search_parser = subparsers.add_parser("search", help="Search cached knowledge bases")
    search_parser.add_argument("--query", required=True, help="Name or partial match")

    args = parser.parse_args()
    library = KnowledgeLibrary()

    if args.command == "list":
        entries = library.list_entries()
        if args.refresh or not entries:
            entries = discover_knowledge_entries(show_browser=args.show_browser)
            library.set_entries(entries)
        print_entries(entries, library.active_knowledge_id)
        return 0

    if args.command == "activate":
        if not library.list_entries():
            library.set_entries(discover_knowledge_entries())
        entry = library.activate(args.query)
        print(f"✅ Activated knowledge base: {entry['name']}")
        return 0

    if args.command == "search":
        entry = select_knowledge_entry(library.list_entries(), args.query)
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
