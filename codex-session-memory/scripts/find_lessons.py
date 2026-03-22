#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from lesson_memory import find_lessons, find_lessons_across_scopes, infer_scope_from_store
from memory_scopes import DEFAULT_SKILLS_ROOT, MemoryStore, recall_stores
from session_memory import DEFAULT_CODEX_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search lessons recorded for Codex, project, or domain workflows.")
    parser.add_argument("--query", required=True, help="keywords, symptom, service name, or failure signature")
    parser.add_argument("--scope", choices=["auto", "all", "global", "project", "domain"], default="auto", help="memory scope selection")
    parser.add_argument("--domain", default="", help="skill or domain name")
    parser.add_argument("--cwd", default="", help="project root; defaults to current working directory")
    parser.add_argument("--codex-root", default=str(DEFAULT_CODEX_ROOT), help="Codex state root for global/project memory")
    parser.add_argument("--skills-root", default=str(DEFAULT_SKILLS_ROOT), help="skills root for domain memory")
    parser.add_argument("--store", default="", help="override lesson store path and search that store only")
    parser.add_argument("--limit", type=int, default=5, help="maximum lessons to return")
    parser.add_argument("--explain", action="store_true", help="show score component breakdowns")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    return parser.parse_args()


def format_score_components(components: dict[str, int]) -> str:
    ordered_keys = [
        "lexical",
        "synonyms",
        "exact_trigger",
        "confidence",
        "merge",
        "source_sessions",
        "recency",
        "domain_match",
    ]
    return ", ".join(f"{key}={components.get(key, 0)}" for key in ordered_keys)


def main() -> int:
    args = parse_args()
    if args.store:
        store = Path(args.store)
        inferred_scope = infer_scope_from_store(store)
        matches = find_lessons(store, args.query, domain=args.domain if inferred_scope == "domain" and args.domain else None, limit=args.limit)
        for match in matches:
            match.store_path = str(store)
            if not match.scope:
                match.scope = inferred_scope
    else:
        stores = recall_stores(
            domain=args.domain,
            cwd=args.cwd or os.getcwd(),
            scope=args.scope,
            codex_root=args.codex_root,
            skills_root=args.skills_root,
        )
        matches = find_lessons_across_scopes(query=args.query, stores=stores, domain=args.domain, limit=args.limit)

    if args.json:
        print(json.dumps([asdict(match) for match in matches], ensure_ascii=False, indent=2))
        return 0

    if not matches:
        print("[INFO] no matching lessons")
        return 0

    for index, match in enumerate(matches, start=1):
        source_count = len(match.source_sessions or ([match.session_id] if match.session_id else []))
        print(
            f"{index}. [{match.scope}] {match.title} [{match.score}] "
            f"merge={match.merge_count} conflict={match.conflict_status} sources={source_count}"
        )
        if match.store_path:
            print(f"   store: {match.store_path}")
        print(f"   note: {Path(match.store_path) / match.note_path if match.store_path else match.note_path}")
        if match.lesson_id:
            print(f"   lesson_id: {match.lesson_id}")
        if match.keywords:
            print(f"   keywords: {', '.join(match.keywords)}")
        if match.applies_when:
            print(f"   trigger: {match.applies_when}")
        if match.rule:
            print(f"   rule: {match.rule}")
        if args.explain and match.score_components:
            print(f"   score components: {format_score_components(match.score_components)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
