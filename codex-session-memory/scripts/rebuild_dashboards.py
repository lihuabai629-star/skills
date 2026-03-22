#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from auto_sync import candidate_archive_dir, candidate_inbox_dir, list_active_candidates_for_store, parse_candidate_entry
from lesson_memory import LessonEntry, load_entries
from memory_scopes import DEFAULT_SKILLS_ROOT, MemoryStore, scope_store
from session_memory import (
    CONFLICTS_FILENAME,
    DEFAULT_CODEX_ROOT,
    DEFAULT_EXPORT_ROOT,
    MEMORY_DASHBOARD_FILENAME,
    PENDING_CANDIDATES_FILENAME,
    PROMOTED_LESSONS_FILENAME,
    TOP_LESSONS_FILENAME,
    dashboard_dir,
    dashboard_path,
    frontmatter_text,
    sanitize_markdown_text,
    utc_now,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild Obsidian dashboard notes for Codex memory.")
    parser.add_argument("--out-dir", default=str(DEFAULT_EXPORT_ROOT), help="Obsidian export root")
    parser.add_argument("--codex-root", default=str(DEFAULT_CODEX_ROOT), help="Codex state root")
    parser.add_argument("--skills-root", default=str(DEFAULT_SKILLS_ROOT), help="skills root")
    parser.add_argument("--json", action="store_true", help="emit generated dashboard paths as JSON")
    return parser.parse_args()


def iter_lesson_stores(*, codex_root: str | Path, skills_root: str | Path) -> list[MemoryStore]:
    codex_root = Path(codex_root)
    skills_root = Path(skills_root)
    stores: list[MemoryStore] = [scope_store(scope="global", codex_root=codex_root, skills_root=skills_root)]

    projects_root = codex_root / "memories" / "projects"
    if projects_root.exists():
        for lessons_dir in sorted(projects_root.glob("*/lessons")):
            stores.append(
                MemoryStore(
                    scope="project",
                    path=lessons_dir,
                    project_root="",
                    project_slug=lessons_dir.parent.name,
                )
            )

    if skills_root.exists():
        for skill_dir in sorted(skills_root.iterdir()):
            lessons_dir = skill_dir / "references" / "lessons"
            if not lessons_dir.exists():
                continue
            stores.append(MemoryStore(scope="domain", path=lessons_dir, domain=skill_dir.name))
    return stores


def markdown_link(path: str) -> str:
    text = (path or "").strip()
    if not text:
        return "-"
    return f"[{Path(text).stem}]({text})"


def lesson_absolute_path(entry: LessonEntry) -> str:
    base = Path(entry.store_path) if entry.store_path else Path()
    return str(base / entry.note_path) if entry.note_path else str(base)


def write_dashboard_note(path: Path, *, title: str, tags: list[str], body_lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        frontmatter_text({"title": title, "updated": utc_now(), "tags": tags}),
        "---",
        "",
        f"# {title}",
        "",
        *body_lines,
    ]
    path.write_text(sanitize_markdown_text("\n".join(lines).rstrip() + "\n"), encoding="utf-8")
    return path


def collect_memory_state(*, codex_root: str | Path, skills_root: str | Path) -> dict[str, object]:
    stores = iter_lesson_stores(codex_root=codex_root, skills_root=skills_root)
    lessons: list[LessonEntry] = []
    pending_candidates = []
    promoted_candidates = []

    for store in stores:
        entries = load_entries(store.path)
        for entry in entries:
            entry.store_path = str(store.path)
            if not entry.scope:
                entry.scope = store.scope
            if not entry.project_slug:
                entry.project_slug = store.project_slug
        lessons.extend(entries)
        pending_candidates.extend(list_active_candidates_for_store(store))

        promoted_dir = candidate_archive_dir(candidate_inbox_dir(store), "promoted")
        if promoted_dir.exists():
            for path in sorted(promoted_dir.glob("*.md")):
                promoted_candidates.append(parse_candidate_entry(path, store))

    pending_candidates.sort(key=lambda entry: (entry.confidence, entry.last_seen or entry.updated), reverse=True)
    promoted_candidates.sort(key=lambda entry: (entry.last_seen or entry.updated, entry.confidence), reverse=True)
    lessons.sort(key=lambda entry: entry.updated or entry.created, reverse=True)

    return {
        "stores": stores,
        "lessons": lessons,
        "pending_candidates": pending_candidates,
        "promoted_candidates": promoted_candidates,
    }


def rebuild_dashboards(*, out_dir: str | Path, codex_root: str | Path, skills_root: str | Path) -> dict[str, str]:
    state = collect_memory_state(codex_root=codex_root, skills_root=skills_root)
    lessons: list[LessonEntry] = state["lessons"]  # type: ignore[assignment]
    pending_candidates = state["pending_candidates"]  # type: ignore[assignment]
    promoted_candidates = state["promoted_candidates"]  # type: ignore[assignment]

    conflicts = [entry for entry in lessons if entry.conflict_status != "none"]
    top_lessons = sorted(
        lessons,
        key=lambda entry: (entry.merge_count, entry.confidence, len(entry.source_sessions), entry.updated or entry.created),
        reverse=True,
    )[:20]

    counts = {
        "Global Lessons": len([entry for entry in lessons if entry.scope == "global"]),
        "Project Lessons": len([entry for entry in lessons if entry.scope == "project"]),
        "Domain Lessons": len([entry for entry in lessons if entry.scope == "domain"]),
        "Pending Candidates": len(pending_candidates),
        "Promoted Candidates": len(promoted_candidates),
        "Conflicts": len(conflicts),
    }

    root = dashboard_dir(out_dir)
    dashboard_note = write_dashboard_note(
        dashboard_path(out_dir, MEMORY_DASHBOARD_FILENAME),
        title="Codex Memory Dashboard",
        tags=["codex/dashboard", "codex/memory"],
        body_lines=[
            "## Overview",
            "",
            "| View | Count |",
            "| --- | ---: |",
            *(f"| {label} | {value} |" for label, value in counts.items()),
            "",
            "## Views",
            "",
            f"- [[{PENDING_CANDIDATES_FILENAME.removesuffix('.md')}|Pending Candidates]]",
            f"- [[{PROMOTED_LESSONS_FILENAME.removesuffix('.md')}|Promoted Lessons]]",
            f"- [[{CONFLICTS_FILENAME.removesuffix('.md')}|Conflicts]]",
            f"- [[{TOP_LESSONS_FILENAME.removesuffix('.md')}|Top Lessons]]",
        ],
    )

    pending_lines = [
        "| Candidate ID | Scope | Confidence | Rule | Source Session | Note |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    if not pending_candidates:
        pending_lines.append("| - | - | 0 | No pending candidates | - | - |")
    else:
        for candidate in pending_candidates:
            latest = candidate.occurrences[0] if candidate.occurrences else None
            pending_lines.append(
                f"| {candidate.candidate_id} | {candidate.scope} | {candidate.confidence} | {candidate.rule} | "
                f"{markdown_link(latest.source_note if latest else candidate.source_note)} | {markdown_link(candidate.note_path)} |"
            )
    pending_note = write_dashboard_note(
        dashboard_path(out_dir, PENDING_CANDIDATES_FILENAME),
        title="Pending Candidates",
        tags=["codex/dashboard", "codex/pending-candidates"],
        body_lines=pending_lines,
    )

    promoted_lines = [
        "| Rule | Scope | Confidence | Promoted Lesson | Candidate Note |",
        "| --- | --- | ---: | --- | --- |",
    ]
    if not promoted_candidates:
        promoted_lines.append("| No promoted candidates | - | 0 | - | - |")
    else:
        for candidate in promoted_candidates:
            promoted_lines.append(
                f"| {candidate.rule} | {candidate.scope} | {candidate.confidence} | "
                f"{markdown_link(candidate.promoted_lesson_path)} | {markdown_link(candidate.note_path)} |"
            )
    promoted_note = write_dashboard_note(
        dashboard_path(out_dir, PROMOTED_LESSONS_FILENAME),
        title="Promoted Lessons",
        tags=["codex/dashboard", "codex/promoted-lessons"],
        body_lines=promoted_lines,
    )

    conflict_lines = [
        "| Scope | Title | Merge | Note | Rule |",
        "| --- | --- | ---: | --- | --- |",
    ]
    if not conflicts:
        conflict_lines.append("| - | No conflicts | 0 | - | - |")
    else:
        for entry in conflicts:
            conflict_lines.append(
                f"| {entry.scope} | {entry.title} | {entry.merge_count} | {markdown_link(lesson_absolute_path(entry))} | {entry.rule} |"
            )
    conflicts_note = write_dashboard_note(
        dashboard_path(out_dir, CONFLICTS_FILENAME),
        title="Conflicts",
        tags=["codex/dashboard", "codex/conflicts"],
        body_lines=conflict_lines,
    )

    top_lines = [
        "| Title | Scope | Merge | Confidence | Source Sessions | Note |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    if not top_lessons:
        top_lines.append("| No lessons yet | - | 0 | 0 | 0 | - |")
    else:
        for entry in top_lessons:
            top_lines.append(
                f"| {entry.title} | {entry.scope} | {entry.merge_count} | {entry.confidence} | {len(entry.source_sessions)} | "
                f"{markdown_link(lesson_absolute_path(entry))} |"
            )
    top_note = write_dashboard_note(
        dashboard_path(out_dir, TOP_LESSONS_FILENAME),
        title="Top Lessons",
        tags=["codex/dashboard", "codex/top-lessons"],
        body_lines=top_lines,
    )

    return {
        "dashboard": str(dashboard_note),
        "pending": str(pending_note),
        "promoted": str(promoted_note),
        "conflicts": str(conflicts_note),
        "top_lessons": str(top_note),
        "root": str(root),
    }


def main() -> int:
    args = parse_args()
    payload = rebuild_dashboards(out_dir=args.out_dir, codex_root=args.codex_root, skills_root=args.skills_root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
