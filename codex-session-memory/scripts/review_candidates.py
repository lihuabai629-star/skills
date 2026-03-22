#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from auto_sync import (
    CandidateEntry,
    candidate_archive_dir,
    candidate_inbox_dir,
    list_active_candidates_for_store,
    write_candidate_entry,
    write_inbox_index,
)
from lesson_memory import normalize_keywords, record_lesson
from memory_scopes import DEFAULT_SKILLS_ROOT, recall_stores
from session_memory import DEFAULT_CODEX_ROOT, utc_now


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review, promote, or reject Codex lesson candidates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_scope_args(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--scope", choices=["auto", "all", "global", "project", "domain"], default="auto")
        subparser.add_argument("--domain", default="", help="domain or skill name, for example openubmc-debug")
        subparser.add_argument("--cwd", default="", help="project root used for project scope; defaults to current working directory")
        subparser.add_argument("--codex-root", default=str(DEFAULT_CODEX_ROOT), help="Codex state root")
        subparser.add_argument("--skills-root", default=str(DEFAULT_SKILLS_ROOT), help="skills root for domain memory")

    list_parser = subparsers.add_parser("list", help="list active lesson candidates")
    add_scope_args(list_parser)
    list_parser.add_argument("--json", action="store_true", help="emit JSON output")

    promote_parser = subparsers.add_parser("promote", help="promote one candidate into a formal lesson")
    add_scope_args(promote_parser)
    promote_parser.add_argument("--candidate-id", required=True, help="stable candidate id")
    promote_parser.add_argument("--title", default="", help="optional lesson title override")
    promote_parser.add_argument("--problem", default="", help="optional lesson trigger override")
    promote_parser.add_argument("--rule", default="", help="optional lesson rule override")
    promote_parser.add_argument("--evidence", default="", help="optional evidence override")
    promote_parser.add_argument("--keywords", nargs="*", default=[], help="optional keyword override")
    promote_parser.add_argument("--json", action="store_true", help="emit JSON output")

    reject_parser = subparsers.add_parser("reject", help="reject one candidate")
    add_scope_args(reject_parser)
    reject_parser.add_argument("--candidate-id", required=True, help="stable candidate id")
    reject_parser.add_argument("--reason", default="", help="optional rejection reason")
    reject_parser.add_argument("--json", action="store_true", help="emit JSON output")
    return parser.parse_args()


def resolve_stores(*, scope: str, domain: str, cwd: str, codex_root: str | Path, skills_root: str | Path):
    effective_cwd = cwd or os.getcwd()
    return recall_stores(scope=scope, domain=domain, cwd=effective_cwd, codex_root=codex_root, skills_root=skills_root)


def list_candidates(*, scope: str = "auto", domain: str = "", cwd: str = "", codex_root: str | Path = DEFAULT_CODEX_ROOT, skills_root: str | Path = DEFAULT_SKILLS_ROOT) -> list[CandidateEntry]:
    entries: list[CandidateEntry] = []
    for store in resolve_stores(scope=scope, domain=domain, cwd=cwd, codex_root=codex_root, skills_root=skills_root):
        entries.extend(list_active_candidates_for_store(store))
    entries.sort(key=lambda entry: (entry.confidence, entry.last_seen or entry.updated), reverse=True)
    return entries


def find_candidate(candidate_id: str, *, scope: str, domain: str, cwd: str, codex_root: str | Path, skills_root: str | Path):
    for store in resolve_stores(scope=scope, domain=domain, cwd=cwd, codex_root=codex_root, skills_root=skills_root):
        for candidate in list_active_candidates_for_store(store):
            if candidate.candidate_id == candidate_id:
                return store, candidate
    raise ValueError(f"candidate not found: {candidate_id}")


def infer_problem(candidate: CandidateEntry) -> str:
    occurrences = candidate.occurrences or []
    if not occurrences:
        return "Promoted from the candidate review queue."
    for occurrence in occurrences:
        if occurrence.request:
            return occurrence.request
    return "Promoted from the candidate review queue."


def infer_evidence(candidate: CandidateEntry) -> str:
    occurrences = candidate.occurrences or []
    if not occurrences:
        return "Candidate review queue entry."
    session_ids = [occurrence.session_id for occurrence in occurrences if occurrence.session_id]
    return f"Observed in {len(occurrences)} session(s): {', '.join(session_ids) if session_ids else 'session ids unavailable'}."


def infer_keywords(candidate: CandidateEntry) -> list[str]:
    occurrences = candidate.occurrences or []
    raw_keywords = [candidate.rule]
    raw_keywords.extend(occurrence.request for occurrence in occurrences if occurrence.request)
    return normalize_keywords(raw_keywords)


def archive_candidate(candidate: CandidateEntry, *, status: str, reason: str = "", promoted_lesson_path: str = "") -> Path:
    current_path = Path(candidate.note_path)
    inbox_dir = current_path.parent
    archive_dir = candidate_archive_dir(inbox_dir, status)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / current_path.name

    candidate.status = status
    candidate.updated = utc_now()
    if reason:
        candidate.rejection_reason = reason
    if promoted_lesson_path:
        candidate.promoted_lesson_path = promoted_lesson_path
    candidate.note_path = str(archive_path)
    write_candidate_entry(archive_path, candidate)
    if current_path.exists():
        current_path.unlink()
    write_inbox_index(inbox_dir)
    return archive_path


def promote_candidate(
    *,
    candidate_id: str,
    scope: str = "auto",
    domain: str = "",
    cwd: str = "",
    codex_root: str | Path = DEFAULT_CODEX_ROOT,
    skills_root: str | Path = DEFAULT_SKILLS_ROOT,
    title: str = "",
    problem: str = "",
    rule: str = "",
    evidence: str = "",
    keywords: list[str] | None = None,
) -> dict[str, object]:
    store, candidate = find_candidate(candidate_id, scope=scope, domain=domain, cwd=cwd, codex_root=codex_root, skills_root=skills_root)
    occurrences = candidate.occurrences or []
    latest = occurrences[0] if occurrences else None
    archive_path = candidate_archive_dir(Path(candidate.note_path).parent, "promoted") / Path(candidate.note_path).name
    lesson = record_lesson(
        store=store.path,
        scope=store.scope,
        title=title or candidate.rule,
        domain=store.domain,
        problem=problem or infer_problem(candidate),
        rule=rule or candidate.rule,
        evidence=evidence or infer_evidence(candidate),
        keywords=keywords or infer_keywords(candidate),
        project_root=store.project_root,
        project_slug=store.project_slug,
        session_id=latest.session_id if latest else "",
        source_note=latest.source_note if latest else "",
        candidate_note=str(archive_path),
        confidence=candidate.confidence,
    )
    lesson_path = str(store.path / lesson.note_path)
    archived_path = archive_candidate(candidate, status="promoted", promoted_lesson_path=lesson_path)
    return {"candidate": asdict(candidate), "lesson_path": lesson_path, "archive_path": str(archived_path)}


def reject_candidate(
    *,
    candidate_id: str,
    scope: str = "auto",
    domain: str = "",
    cwd: str = "",
    codex_root: str | Path = DEFAULT_CODEX_ROOT,
    skills_root: str | Path = DEFAULT_SKILLS_ROOT,
    reason: str = "",
) -> dict[str, object]:
    _, candidate = find_candidate(candidate_id, scope=scope, domain=domain, cwd=cwd, codex_root=codex_root, skills_root=skills_root)
    archive_path = archive_candidate(candidate, status="rejected", reason=reason)
    return {"candidate": asdict(candidate), "archive_path": str(archive_path)}


def main() -> int:
    args = parse_args()
    if args.command == "list":
        payload = [asdict(entry) for entry in list_candidates(scope=args.scope, domain=args.domain, cwd=args.cwd, codex_root=args.codex_root, skills_root=args.skills_root)]
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for entry in payload:
                print(f"{entry['candidate_id']} [{entry['scope']}] confidence={entry['confidence']} rule={entry['rule']}")
        return 0

    if args.command == "promote":
        payload = promote_candidate(
            candidate_id=args.candidate_id,
            scope=args.scope,
            domain=args.domain,
            cwd=args.cwd,
            codex_root=args.codex_root,
            skills_root=args.skills_root,
            title=args.title,
            problem=args.problem,
            rule=args.rule,
            evidence=args.evidence,
            keywords=args.keywords,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
        return 0

    if args.command == "reject":
        payload = reject_candidate(
            candidate_id=args.candidate_id,
            scope=args.scope,
            domain=args.domain,
            cwd=args.cwd,
            codex_root=args.codex_root,
            skills_root=args.skills_root,
            reason=args.reason,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
        return 0

    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
