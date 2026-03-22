#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from lesson_memory import record_lesson
from memory_scopes import DEFAULT_SKILLS_ROOT, scope_store
from session_memory import DEFAULT_CODEX_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a reusable lesson into a global, project, or domain memory store.")
    parser.add_argument("--scope", choices=["global", "project", "domain"], default="domain", help="memory scope to write")
    parser.add_argument("--domain", default="", help="domain or skill name, for example openubmc-debug")
    parser.add_argument("--cwd", default="", help="project root used for project scope; defaults to current working directory")
    parser.add_argument("--codex-root", default=str(DEFAULT_CODEX_ROOT), help="Codex state root for global/project memory")
    parser.add_argument("--skills-root", default=str(DEFAULT_SKILLS_ROOT), help="skills root for domain memory")
    parser.add_argument("--title", required=True, help="short reusable lesson title")
    parser.add_argument("--problem", required=True, help="what went wrong or what trigger should recall this lesson")
    parser.add_argument("--rule", required=True, help="what to do next time")
    parser.add_argument("--evidence", default="", help="error shape or evidence backing the rule")
    parser.add_argument("--applies-when", default="", help="short trigger sentence for future recall")
    parser.add_argument("--anti-pattern", default="", help="what to avoid repeating")
    parser.add_argument("--next-check", default="", help="quick verification step for next time")
    parser.add_argument("--session-id", default="", help="Codex session id")
    parser.add_argument("--source-note", default="", help="related session note path")
    parser.add_argument("--confidence", type=int, default=0, help="optional confidence score carried into ranking")
    parser.add_argument("--store", default="", help="override lesson store path")
    parser.add_argument("--keywords", nargs="*", default=[], help="keywords used for future matching")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.store:
        store_path = Path(args.store)
        scope = args.scope
        project_root = args.cwd
        project_slug = ""
    else:
        scope_info = scope_store(
            scope=args.scope,
            domain=args.domain,
            cwd=args.cwd or os.getcwd(),
            codex_root=args.codex_root,
            skills_root=args.skills_root,
        )
        store_path = scope_info.path
        scope = scope_info.scope
        project_root = scope_info.project_root
        project_slug = scope_info.project_slug

    entry = record_lesson(
        store=store_path,
        scope=scope,
        title=args.title,
        domain=args.domain,
        problem=args.problem,
        rule=args.rule,
        evidence=args.evidence,
        keywords=args.keywords,
        project_root=project_root,
        project_slug=project_slug,
        applies_when=args.applies_when,
        anti_pattern=args.anti_pattern,
        next_check=args.next_check,
        session_id=args.session_id,
        source_note=args.source_note,
        confidence=args.confidence,
    )
    if args.json:
        print(json.dumps(asdict(entry), ensure_ascii=False, indent=2))
        return 0
    print(f"[OK] scope={scope} wrote lesson: {store_path / entry.note_path}")
    print(f"[OK] updated index: {store_path / 'INDEX.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
