#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from memory_scopes import MemoryStore, normalize_project_root, recall_stores, scope_store
from session_memory import (
    DEFAULT_CODEX_ROOT,
    DEFAULT_EXPORT_ROOT,
    clip_text,
    export_session_record,
    find_rollout_files,
    frontmatter_text,
    load_manifest,
    parse_rollout,
    parsed_arguments,
    sanitize_markdown_text,
    slugify,
    utc_now,
)

DEFAULT_SKILLS_ROOT = Path("/root/.codex/skills")
DEFAULT_PID_FILE = DEFAULT_CODEX_ROOT / "codex-session-memory-auto.pid"
DEFAULT_LOG_FILE = DEFAULT_CODEX_ROOT / "logs" / "codex-session-memory-auto.log"
OPENUBMC_DEBUG_KEYWORDS = {
    "openubmc",
    "bmc",
    "dbus",
    "busctl",
    "mdbctl",
    "app.log",
    "framework.log",
    "sel",
    "alarm",
    "telnet",
}
RULE_PREFIXES = (
    "use ",
    "prefer ",
    "do not ",
    "avoid ",
    "keep ",
    "run ",
    "switch to ",
    "先",
    "优先",
    "不要",
    "改用",
    "必须",
    "应该",
)
MIN_RULE_CONFIDENCE = 2
FINAL_MESSAGE_WEIGHT = 4
ASSISTANT_MESSAGE_WEIGHT = 3
USER_CORRECTION_WEIGHT = 2
MAX_ERROR_BACKOFF_SECONDS = 300
QUESTION_MARKERS = ("?", "？")
USER_CORRECTION_PREFIXES = (
    "不要",
    "别",
    "别再",
    "不要用",
    "优先",
    "应该",
    "必须",
    "改用",
    "记得",
    "请先",
    "用 ",
    "use ",
    "prefer ",
    "avoid ",
    "do not ",
)
COMMAND_CONTEXT_KEYWORDS = (
    "busctl",
    "mdbctl",
    "rg",
    "grep",
    "pytest",
    "journalctl",
    "ssh",
    "telnet",
)
TOKEN_RE = re.compile(r"[a-z0-9_.-]+", re.IGNORECASE)


@dataclass(frozen=True)
class CandidateEvidence:
    source: str
    timestamp: str
    excerpt: str


@dataclass(frozen=True)
class CandidateRule:
    text: str
    confidence: int
    sources: tuple[str, ...]
    evidence: tuple[CandidateEvidence, ...] = ()
    command_contexts: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateOccurrence:
    session_id: str
    source_note: str
    request: str
    confidence: int
    sources: tuple[str, ...]
    captured_at: str
    evidence: tuple[CandidateEvidence, ...] = ()
    command_contexts: tuple[str, ...] = ()


@dataclass
class CandidateEntry:
    candidate_id: str
    note_path: str
    created: str
    updated: str
    first_seen: str
    last_seen: str
    status: str
    rule: str
    normalized_rule_key: str
    confidence: int
    scope: str
    domain: str = ""
    project_root: str = ""
    project_slug: str = ""
    source_note: str = ""
    store_path: str = ""
    occurrences: list[CandidateOccurrence] | None = None
    rejection_reason: str = ""
    promoted_lesson_path: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatically export Codex sessions and create lesson candidates.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--daemon", action="store_true", help="run the sync loop forever")
    mode.add_argument("--once", action="store_true", help="run one sync pass and exit")
    mode.add_argument("--status", action="store_true", help="show daemon status")
    mode.add_argument("--stop", action="store_true", help="stop the running daemon")
    parser.add_argument("--interval", type=int, default=45, help="daemon polling interval in seconds")
    parser.add_argument("--codex-root", default=str(DEFAULT_CODEX_ROOT), help="Codex state root")
    parser.add_argument("--out-dir", default=str(DEFAULT_EXPORT_ROOT), help="Obsidian export root")
    parser.add_argument("--skills-root", default=str(DEFAULT_SKILLS_ROOT), help="skills root")
    parser.add_argument("--pid-file", default=str(DEFAULT_PID_FILE), help="pid file for daemon mode")
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_FILE), help="log file for daemon mode")
    parser.add_argument("--json", action="store_true", help="emit JSON output for once/status")
    return parser.parse_args()


def ensure_log_parent(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)


def is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_proc_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    parts = [part for part in raw.decode("utf-8", errors="ignore").split("\x00") if part]
    return " ".join(parts)


def read_proc_start_time(pid: int) -> str:
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return ""
    parts = stat_text.split()
    return parts[21] if len(parts) > 21 else ""


def current_process_metadata(pid: int | None = None) -> dict[str, object]:
    pid = pid or os.getpid()
    return {
        "pid": pid,
        "cmdline": read_proc_cmdline(pid),
        "proc_start_time": read_proc_start_time(pid),
        "written_at": utc_now(),
    }


def read_pid_metadata(pid_file: Path) -> dict[str, object] | None:
    if not pid_file.exists():
        return None
    raw = pid_file.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        try:
            return {"pid": int(raw)}
        except ValueError:
            return None
    if not isinstance(payload, dict):
        return None
    pid = payload.get("pid")
    try:
        payload["pid"] = int(pid)
    except (TypeError, ValueError):
        return None
    return payload


def read_pid(pid_file: Path) -> int | None:
    metadata = read_pid_metadata(pid_file)
    if not metadata:
        return None
    try:
        return int(metadata.get("pid"))
    except (TypeError, ValueError):
        return None


def process_matches_metadata(metadata: dict[str, object]) -> bool:
    pid = metadata.get("pid")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if not is_process_alive(pid):
        return False

    expected_cmdline = str(metadata.get("cmdline", "")).strip()
    if expected_cmdline and read_proc_cmdline(pid) != expected_cmdline:
        return False

    expected_start_time = str(metadata.get("proc_start_time", "")).strip()
    if expected_start_time and read_proc_start_time(pid) != expected_start_time:
        return False

    return True


def status_payload(pid_file: Path) -> dict[str, object]:
    metadata = read_pid_metadata(pid_file) or {}
    pid = metadata.get("pid")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        pid = None
    return {
        "pid_file": str(pid_file),
        "running": process_matches_metadata(metadata) if metadata else False,
        "pid": pid,
        "cmdline_verified": bool(metadata.get("cmdline")) if metadata else False,
        "start_time_verified": bool(metadata.get("proc_start_time")) if metadata else False,
    }


def cleanup_stale_pid_file(pid_file: Path) -> bool:
    if not pid_file.exists():
        return False
    metadata = read_pid_metadata(pid_file)
    if metadata and process_matches_metadata(metadata):
        return False
    pid_file.unlink()
    return True


def next_sleep_seconds(interval: int, consecutive_errors: int) -> int:
    base_interval = max(1, int(interval))
    if consecutive_errors <= 0:
        return base_interval
    return min(MAX_ERROR_BACKOFF_SECONDS, base_interval * (2**consecutive_errors))


def stop_daemon(pid_file: Path) -> bool:
    metadata = read_pid_metadata(pid_file)
    pid = read_pid(pid_file)
    if not metadata or not pid or not process_matches_metadata(metadata):
        if pid_file.exists():
            pid_file.unlink()
        return False
    os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not is_process_alive(pid):
            break
        time.sleep(0.1)
    if pid_file.exists():
        pid_file.unlink()
    return True


def session_text(record) -> str:
    chunks = [record.first_user_message, record.final_message]
    chunks.extend(message.text for message in record.messages)
    return "\n".join(filter(None, chunks))


def classify_domains(record, *, rules: list[CandidateRule] | None = None) -> list[str]:
    request_text = "\n".join(filter(None, [record.first_user_message, record.final_message])).lower()
    rule_text = "\n".join(rule.text for rule in (rules or [])).lower() or request_text
    domains: list[str] = []
    request_score = sum(1 for keyword in OPENUBMC_DEBUG_KEYWORDS if keyword in request_text)
    rule_score = sum(1 for keyword in OPENUBMC_DEBUG_KEYWORDS if keyword in rule_text)
    if ("openubmc" in request_text or request_score >= 2) and rule_score >= 1:
        domains.append("openubmc-debug")
    return domains


def final_message_timestamp(record) -> str:
    for message in reversed(record.messages):
        if message.role == "assistant" and message.phase == "final_answer" and message.timestamp:
            return message.timestamp
    for message in reversed(record.messages):
        if message.role == "assistant" and message.timestamp:
            return message.timestamp
    return record.updated_at or record.created_at or ""


def is_question_like_line(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and stripped.endswith(QUESTION_MARKERS)


def is_fragmentary_rule_line(text: str) -> bool:
    stripped = text.strip()
    if any(marker in stripped for marker in ("。", ".", "！", "!", "？", "?", "；", ";", "，", ",", "：", ":")):
        return False
    if stripped.startswith("先") and len(stripped) < 12:
        return True
    return False


def is_selected_user_correction(text: str) -> bool:
    lowered = text.strip().lower()
    return any(lowered.startswith(prefix) or text.strip().startswith(prefix) for prefix in USER_CORRECTION_PREFIXES)


def tokenize_text(text: str) -> set[str]:
    return {match.group(0).lower() for match in TOKEN_RE.finditer(text)}


def extract_rule_lines(text: str, *, allow_questions: bool = False) -> list[str]:
    rules: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        stripped = raw_line.strip().lstrip("-*").strip()
        stripped = stripped.lstrip("0123456789. ").strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if not any(lowered.startswith(prefix) or stripped.startswith(prefix) for prefix in RULE_PREFIXES):
            continue
        if not allow_questions and is_question_like_line(stripped):
            continue
        if is_fragmentary_rule_line(stripped):
            continue
        if stripped in seen:
            continue
        seen.add(stripped)
        rules.append(stripped)
    return rules


def normalize_rule_key(text: str) -> str:
    collapsed = " ".join(text.strip().split())
    return collapsed.rstrip(".。!！?？").lower()


def iter_rule_sources(record) -> list[tuple[str, str, int, str]]:
    sources: list[tuple[str, str, int, str]] = []
    if record.final_message:
        sources.append(("final_message", record.final_message, FINAL_MESSAGE_WEIGHT, final_message_timestamp(record)))
    for index, message in enumerate(record.messages):
        if not message.text:
            continue
        if message.role == "assistant":
            if message.phase == "final_answer":
                sources.append((f"assistant:{index}", message.text, ASSISTANT_MESSAGE_WEIGHT, message.timestamp))
            continue
        if message.role == "user":
            if is_selected_user_correction(message.text):
                sources.append((f"user:{index}", message.text, USER_CORRECTION_WEIGHT, message.timestamp))
    return sources


def command_contexts_for_rule(record, rule_text: str, *, limit: int = 3) -> tuple[str, ...]:
    contexts: list[str] = []
    seen: set[str] = set()
    rule_lower = rule_text.lower()
    rule_keywords = [keyword for keyword in COMMAND_CONTEXT_KEYWORDS if keyword in rule_lower]
    if not rule_keywords:
        return ()
    for tool_call in record.tool_calls:
        if tool_call.name != "exec_command":
            continue
        parsed = parsed_arguments(tool_call.arguments)
        if not isinstance(parsed, dict):
            continue
        command = sanitize_markdown_text(str(parsed.get("cmd", ""))).strip()
        if not command:
            continue
        command_lower = command.lower()
        matching_keywords = [keyword for keyword in rule_keywords if keyword in command_lower]
        if not matching_keywords:
            continue
        normalized = clip_text(command, limit=160, suffix="...")
        if normalized in seen:
            continue
        seen.add(normalized)
        contexts.append(normalized)
        if len(contexts) >= limit:
            break
    return tuple(contexts)


def extract_rule_candidates(record) -> list[CandidateRule]:
    aggregated: dict[str, dict[str, object]] = {}
    for source_name, text, weight, timestamp in iter_rule_sources(record):
        for line in extract_rule_lines(text):
            key = normalize_rule_key(line)
            if not key:
                continue
            entry = aggregated.setdefault(key, {"text": line, "confidence": 0, "sources": set(), "evidence": {}})
            entry["confidence"] = int(entry["confidence"]) + weight
            if len(line) > len(str(entry["text"])):
                entry["text"] = line
            cast_sources = entry["sources"]
            assert isinstance(cast_sources, set)
            cast_sources.add(source_name)
            cast_evidence = entry["evidence"]
            assert isinstance(cast_evidence, dict)
            cast_evidence[(source_name, timestamp, line)] = CandidateEvidence(
                source=source_name,
                timestamp=timestamp,
                excerpt=clip_text(line, limit=220, suffix="..."),
            )

    candidates: list[CandidateRule] = []
    for entry in aggregated.values():
        confidence = int(entry["confidence"])
        if confidence < MIN_RULE_CONFIDENCE:
            continue
        sources = tuple(sorted(str(source) for source in entry["sources"]))
        evidence_map = entry["evidence"]
        assert isinstance(evidence_map, dict)
        evidence = tuple(
            sorted(
                evidence_map.values(),
                key=lambda item: (item.timestamp, item.source, item.excerpt),
                reverse=True,
            )
        )
        candidates.append(
            CandidateRule(
                text=str(entry["text"]),
                confidence=confidence,
                sources=sources,
                evidence=evidence,
                command_contexts=command_contexts_for_rule(record, str(entry["text"])),
            )
        )
    candidates.sort(key=lambda candidate: (candidate.confidence, len(candidate.sources), candidate.text), reverse=True)
    return candidates


def candidate_inbox_dir(store: MemoryStore) -> Path:
    return store.path / "inbox"


def candidate_archive_dir(inbox_dir: Path, status: str) -> Path:
    return inbox_dir / "archive" / status


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end == -1:
        return {}, text
    frontmatter = yaml.safe_load(text[4:end]) or {}
    body = text[end + len(marker) :]
    return frontmatter, body


def candidate_id_for_rule(store: MemoryStore, rule_text: str) -> str:
    rule_key = normalize_rule_key(rule_text)
    digest = hashlib.sha1(f"{store.label}|{rule_key}".encode("utf-8")).hexdigest()[:10]
    label = slugify(store.label.replace(":", "-"), fallback=store.scope)[:24]
    readable = slugify(rule_text, fallback="rule")[:48]
    return f"{label}-{readable}-{digest}"


def candidate_path(inbox_dir: Path, store: MemoryStore, rule_text: str) -> Path:
    candidate_id = candidate_id_for_rule(store, rule_text)
    return inbox_dir / f"{candidate_id}.md"


def active_candidate_paths(inbox_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(inbox_dir.glob("*.md")):
        if path.name == "INBOX.md":
            continue
        frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        if frontmatter.get("candidate_id") and frontmatter.get("status", "active") == "active":
            paths.append(path)
    return paths


def parse_candidate_entry(path: Path, store: MemoryStore) -> CandidateEntry:
    frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    occurrences = [
        CandidateOccurrence(
            session_id=occurrence.get("session_id", ""),
            source_note=occurrence.get("source_note", ""),
            request=occurrence.get("request", ""),
            confidence=int(occurrence.get("confidence", 0)),
            sources=tuple(occurrence.get("sources", [])),
            captured_at=occurrence.get("captured_at", ""),
            evidence=tuple(
                CandidateEvidence(
                    source=evidence.get("source", ""),
                    timestamp=evidence.get("timestamp", ""),
                    excerpt=evidence.get("excerpt", ""),
                )
                for evidence in occurrence.get("evidence", [])
            ),
            command_contexts=tuple(occurrence.get("command_contexts", [])),
        )
        for occurrence in frontmatter.get("occurrences", [])
    ]
    return CandidateEntry(
        candidate_id=frontmatter.get("candidate_id", path.stem),
        note_path=str(path),
        created=frontmatter.get("created", ""),
        updated=frontmatter.get("updated", ""),
        first_seen=frontmatter.get("first_seen", ""),
        last_seen=frontmatter.get("last_seen", ""),
        status=frontmatter.get("status", "active"),
        rule=frontmatter.get("rule", ""),
        normalized_rule_key=frontmatter.get("normalized_rule_key", ""),
        confidence=int(frontmatter.get("confidence", 0)),
        scope=frontmatter.get("scope", store.scope),
        domain=frontmatter.get("domain", store.domain),
        project_root=frontmatter.get("project_root", store.project_root),
        project_slug=frontmatter.get("project_slug", store.project_slug),
        source_note=frontmatter.get("source_note", ""),
        store_path=str(store.path),
        occurrences=occurrences,
        rejection_reason=frontmatter.get("rejection_reason", ""),
        promoted_lesson_path=frontmatter.get("promoted_lesson_path", ""),
    )


def candidate_tags(store: MemoryStore, status: str) -> list[str]:
    tags = ["codex/lesson-candidate", f"memory/{store.scope}", f"candidate/{status}"]
    if store.domain:
        tags.append(f"lessons/{store.domain}/inbox")
    if store.project_slug:
        tags.append(f"project/{store.project_slug}/inbox")
    return tags


def candidate_markdown(entry: CandidateEntry) -> str:
    occurrences = entry.occurrences or []
    requests = [occurrence.request for occurrence in occurrences if occurrence.request]
    unique_requests = list(dict.fromkeys(requests))
    evidence_lines: list[str] = []
    seen_evidence: set[tuple[str, str, str]] = set()
    command_contexts: list[str] = []
    seen_commands: set[str] = set()
    for occurrence in sorted(occurrences, key=lambda item: item.captured_at, reverse=True):
        for evidence in occurrence.evidence:
            key = (evidence.source, evidence.timestamp, evidence.excerpt)
            if key in seen_evidence:
                continue
            seen_evidence.add(key)
            if evidence.timestamp:
                evidence_lines.append(f"- {evidence.source} @ {evidence.timestamp}: {evidence.excerpt}")
            else:
                evidence_lines.append(f"- {evidence.source}: {evidence.excerpt}")
        for command in occurrence.command_contexts:
            if command in seen_commands:
                continue
            seen_commands.add(command)
            command_contexts.append(command)
    lines = [
        "---",
        frontmatter_text(
            {
                "title": f"Candidate - {entry.rule}",
                "candidate_id": entry.candidate_id,
                "scope": entry.scope,
                "domain": entry.domain,
                "project_root": entry.project_root,
                "project_slug": entry.project_slug,
                "status": entry.status,
                "rule": entry.rule,
                "normalized_rule_key": entry.normalized_rule_key,
                "confidence": entry.confidence,
                "created": entry.created,
                "updated": entry.updated,
                "first_seen": entry.first_seen,
                "last_seen": entry.last_seen,
                "source_note": entry.source_note,
                "rejection_reason": entry.rejection_reason,
                "promoted_lesson_path": entry.promoted_lesson_path,
                "occurrences": [
                    {
                        "session_id": occurrence.session_id,
                        "source_note": occurrence.source_note,
                        "request": occurrence.request,
                        "confidence": occurrence.confidence,
                        "sources": list(occurrence.sources),
                        "captured_at": occurrence.captured_at,
                        "evidence": [
                            {
                                "source": evidence.source,
                                "timestamp": evidence.timestamp,
                                "excerpt": evidence.excerpt,
                            }
                            for evidence in occurrence.evidence
                        ],
                        "command_contexts": list(occurrence.command_contexts),
                    }
                    for occurrence in occurrences
                ],
                "tags": candidate_tags(
                    MemoryStore(
                        scope=entry.scope,
                        path=Path(entry.store_path),
                        domain=entry.domain,
                        project_root=entry.project_root,
                        project_slug=entry.project_slug,
                    ),
                    entry.status,
                ),
            }
        ),
        "---",
        "",
        f"# Candidate - {entry.rule}",
        "",
        "## Rule",
        "",
        entry.rule,
        "",
        "## Request Signals",
        "",
    ]
    if unique_requests:
        lines.extend(f"- {request}" for request in unique_requests)
    else:
        lines.append("- _No request summary captured._")
    lines.extend(["", "## Evidence", ""])
    if evidence_lines:
        lines.extend(evidence_lines)
    else:
        lines.append("- _No evidence excerpts captured._")
    lines.extend(["", "## Command Context", ""])
    if command_contexts:
        lines.extend(f"- `{command}`" for command in command_contexts)
    else:
        lines.append("- _No command context captured._")
    lines.extend(
        [
            "",
            "## Supporting Sessions",
            "",
            "| Session ID | Confidence | Sources | Note |",
            "| --- | --- | --- | --- |",
        ]
    )
    if not occurrences:
        lines.append("| - | - | - | - |")
    else:
        for occurrence in sorted(occurrences, key=lambda item: item.captured_at, reverse=True):
            note_ref = occurrence.source_note or "-"
            lines.append(
                f"| {occurrence.session_id or '-'} | {occurrence.confidence} | {', '.join(occurrence.sources)} | {note_ref} |"
            )
    lines.extend(
        [
            "",
            "## Next Step",
            "",
            "Promote with `review_candidates.py promote --candidate-id ...` when the rule is stable and reusable.",
        ]
    )
    if entry.rejection_reason:
        lines.extend(["", "## Rejection Reason", "", entry.rejection_reason])
    if entry.promoted_lesson_path:
        lines.extend(["", "## Promoted Lesson", "", entry.promoted_lesson_path])
    return "\n".join(lines).rstrip() + "\n"


def write_candidate_entry(path: Path, entry: CandidateEntry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(candidate_markdown(entry), encoding="utf-8")


def write_inbox_index(inbox_dir: Path) -> None:
    notes = [parse_candidate_entry(path, MemoryStore(scope="global", path=inbox_dir.parent)) for path in active_candidate_paths(inbox_dir)]
    notes.sort(key=lambda entry: (entry.confidence, entry.last_seen or entry.updated), reverse=True)
    lines = [
        "---",
        frontmatter_text({"title": "Lesson Candidate Inbox", "updated": utc_now(), "tags": ["codex/lesson-candidate"]}),
        "---",
        "",
        "# Lesson Candidate Inbox",
        "",
        "| Candidate ID | Confidence | Rule | Note |",
        "| --- | --- | --- | --- |",
    ]
    if not notes:
        lines.append("| No pending candidates | - | - | - |")
    for note in notes:
        note_name = Path(note.note_path).stem
        lines.append(f"| {note.candidate_id} | {note.confidence} | {note.rule} | [[{note_name}|Open]] |")
    (inbox_dir / "INBOX.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def merge_evidence(existing: tuple[CandidateEvidence, ...], incoming: tuple[CandidateEvidence, ...]) -> tuple[CandidateEvidence, ...]:
    merged: dict[tuple[str, str, str], CandidateEvidence] = {}
    for evidence in [*existing, *incoming]:
        merged[(evidence.source, evidence.timestamp, evidence.excerpt)] = evidence
    return tuple(sorted(merged.values(), key=lambda item: (item.timestamp, item.source, item.excerpt), reverse=True))


def merge_command_contexts(existing: tuple[str, ...], incoming: tuple[str, ...]) -> tuple[str, ...]:
    merged = list(dict.fromkeys([*existing, *incoming]))
    return tuple(merged)


def merge_occurrence(existing: CandidateOccurrence, incoming: CandidateOccurrence) -> CandidateOccurrence:
    return CandidateOccurrence(
        session_id=incoming.session_id or existing.session_id,
        source_note=incoming.source_note or existing.source_note,
        request=incoming.request or existing.request,
        confidence=incoming.confidence or existing.confidence,
        sources=incoming.sources,
        captured_at=incoming.captured_at or existing.captured_at,
        evidence=incoming.evidence,
        command_contexts=incoming.command_contexts,
    )


def merge_candidate_occurrence(
    *,
    path: Path,
    record,
    store: MemoryStore,
    rule: CandidateRule,
    source_note: str,
) -> CandidateEntry:
    now = utc_now()
    occurrence = CandidateOccurrence(
        session_id=record.session_id,
        source_note=source_note,
        request=record.first_user_message,
        confidence=rule.confidence,
        sources=rule.sources,
        captured_at=now,
        evidence=rule.evidence,
        command_contexts=rule.command_contexts,
    )
    if path.exists():
        entry = parse_candidate_entry(path, store)
    else:
        entry = CandidateEntry(
            candidate_id=candidate_id_for_rule(store, rule.text),
            note_path=str(path),
            created=now,
            updated=now,
            first_seen=now,
            last_seen=now,
            status="active",
            rule=rule.text,
            normalized_rule_key=normalize_rule_key(rule.text),
            confidence=0,
            scope=store.scope,
            domain=store.domain,
            project_root=store.project_root,
            project_slug=store.project_slug,
            source_note=source_note,
            store_path=str(store.path),
            occurrences=[],
        )

    existing_occurrences = entry.occurrences or []
    occurrence_key = occurrence.session_id or occurrence.source_note
    if occurrence_key:
        replaced = False
        for index, existing in enumerate(existing_occurrences):
            existing_key = existing.session_id or existing.source_note
            if existing_key == occurrence_key:
                existing_occurrences[index] = merge_occurrence(existing, occurrence)
                replaced = True
                break
        if not replaced:
            existing_occurrences.append(occurrence)
        entry.last_seen = now
    else:
        existing_occurrences.append(occurrence)
        entry.last_seen = now

    entry.updated = now
    entry.source_note = source_note or entry.source_note
    entry.occurrences = sorted(existing_occurrences, key=lambda item: item.captured_at, reverse=True)
    entry.confidence = sum(item.confidence for item in entry.occurrences)
    return entry


def generate_lesson_candidates(record, *, codex_root: Path, skills_root: Path, source_note: str = "") -> list[str]:
    created: list[str] = []
    rules = extract_rule_candidates(record)
    if not rules:
        return created
    stores = candidate_stores(record, rules=rules, codex_root=codex_root, skills_root=skills_root)
    prune_stale_occurrences(record, rules=rules, current_stores=stores, codex_root=codex_root, skills_root=skills_root)
    for store in stores:
        inbox_dir = candidate_inbox_dir(store)
        for rule in rules:
            path = candidate_path(inbox_dir, store, rule.text)
            entry = merge_candidate_occurrence(path=path, record=record, store=store, rule=rule, source_note=source_note)
            write_candidate_entry(path, entry)
            created.append(str(path))
        write_inbox_index(inbox_dir)
    return created


def list_active_candidates_for_store(store: MemoryStore) -> list[CandidateEntry]:
    inbox_dir = candidate_inbox_dir(store)
    if not inbox_dir.exists():
        return []
    entries = [parse_candidate_entry(path, store) for path in active_candidate_paths(inbox_dir)]
    entries.sort(key=lambda entry: (entry.confidence, entry.last_seen or entry.updated), reverse=True)
    return entries


def cleanup_candidate_stores(record, *, codex_root: Path, skills_root: Path) -> list[MemoryStore]:
    stores: dict[str, MemoryStore] = {}
    global_store = scope_store(scope="global", codex_root=codex_root, skills_root=skills_root)
    stores[global_store.label] = global_store

    project_root = normalize_project_root(record.cwd)
    if project_root:
        project_store = scope_store(scope="project", cwd=project_root, codex_root=codex_root, skills_root=skills_root)
        stores[project_store.label] = project_store

    if not skills_root.exists():
        return list(stores.values())

    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        lessons_dir = skill_dir / "references" / "lessons"
        inbox_dir = lessons_dir / "inbox"
        if not lessons_dir.exists() and not inbox_dir.exists():
            continue
        domain_store = MemoryStore(scope="domain", path=lessons_dir, domain=skill_dir.name)
        stores[domain_store.label] = domain_store

    return list(stores.values())


def prune_stale_occurrences(record, *, rules: list[CandidateRule], current_stores: list[MemoryStore], codex_root: Path, skills_root: Path) -> None:
    session_id = record.session_id.strip()
    if not session_id:
        return

    active_ids_by_store = {
        store.label: {candidate_id_for_rule(store, rule.text) for rule in rules}
        for store in current_stores
    }

    for store in cleanup_candidate_stores(record, codex_root=codex_root, skills_root=skills_root):
        inbox_dir = candidate_inbox_dir(store)
        if not inbox_dir.exists():
            continue
        changed = False
        active_ids = active_ids_by_store.get(store.label, set())
        for path in active_candidate_paths(inbox_dir):
            entry = parse_candidate_entry(path, store)
            occurrences = entry.occurrences or []
            if not any(occurrence.session_id == session_id for occurrence in occurrences):
                continue
            if entry.candidate_id in active_ids:
                continue
            remaining = [occurrence for occurrence in occurrences if occurrence.session_id != session_id]
            changed = True
            if remaining:
                entry.occurrences = sorted(remaining, key=lambda item: item.captured_at, reverse=True)
                entry.confidence = sum(item.confidence for item in entry.occurrences)
                entry.updated = utc_now()
                entry.last_seen = entry.occurrences[0].captured_at
                write_candidate_entry(path, entry)
            else:
                path.unlink(missing_ok=True)
        if changed:
            write_inbox_index(inbox_dir)


def candidate_stores(record, *, rules: list[CandidateRule], codex_root: Path, skills_root: Path) -> list[MemoryStore]:
    stores: list[MemoryStore] = [scope_store(scope="global", codex_root=codex_root, skills_root=skills_root)]
    project_root = normalize_project_root(record.cwd)
    if project_root:
        project_stores = recall_stores(scope="project", cwd=project_root, codex_root=codex_root, skills_root=skills_root)
        stores.extend(project_stores)
    for domain in classify_domains(record, rules=rules):
        stores.append(scope_store(scope="domain", domain=domain, codex_root=codex_root, skills_root=skills_root))
    return stores


def should_skip_rollout(rollout: Path, manifest: dict[str, object]) -> bool:
    rollout_entry = manifest.get("rollouts", {}).get(str(rollout))
    if not rollout_entry:
        return False
    return rollout_entry.get("rollout_mtime") == rollout.stat().st_mtime


def sync_once(codex_root: Path, out_dir: Path, skills_root: Path) -> dict[str, object]:
    manifest = load_manifest(out_dir)
    exported: list[dict[str, str]] = []
    skipped: list[str] = []
    candidates: list[str] = []
    for rollout in find_rollout_files(codex_root):
        if should_skip_rollout(rollout, manifest):
            skipped.append(str(rollout))
            continue
        record = parse_rollout(rollout, codex_root=codex_root)
        result = export_session_record(record, out_dir)
        exported.append(result)
        candidates.extend(generate_lesson_candidates(record, codex_root=codex_root, skills_root=skills_root, source_note=result["note_path"]))
        manifest = load_manifest(out_dir)
    return {"timestamp": utc_now(), "exported": exported, "skipped": skipped, "candidates": candidates}


def run_daemon(interval: int, codex_root: Path, out_dir: Path, skills_root: Path, pid_file: Path, log_file: Path) -> None:
    ensure_log_parent(log_file)
    pid_file.write_text(json.dumps(current_process_metadata(), ensure_ascii=False, indent=2), encoding="utf-8")
    consecutive_errors = 0
    try:
        with log_file.open("a", encoding="utf-8") as log_handle:
            log_handle.write(f"[{utc_now()}] daemon started pid={os.getpid()}\n")
            log_handle.flush()
            while True:
                try:
                    result = sync_once(codex_root, out_dir, skills_root)
                    consecutive_errors = 0
                    log_handle.write(
                        f"[{result['timestamp']}] exported={len(result['exported'])} skipped={len(result['skipped'])} "
                        f"candidates={len(result['candidates'])}\n"
                    )
                    log_handle.flush()
                    sleep_seconds = next_sleep_seconds(interval, consecutive_errors)
                except Exception as exc:  # pragma: no cover
                    consecutive_errors += 1
                    sleep_seconds = next_sleep_seconds(interval, consecutive_errors)
                    log_handle.write(
                        f"[{utc_now()}] error={exc} error_count={consecutive_errors} next_sleep={sleep_seconds}\n"
                    )
                    log_handle.flush()
                time.sleep(sleep_seconds)
    finally:
        metadata = read_pid_metadata(pid_file)
        if pid_file.exists() and metadata and process_matches_metadata(metadata) and read_pid(pid_file) == os.getpid():
            pid_file.unlink()


def main() -> int:
    args = parse_args()
    codex_root = Path(args.codex_root)
    out_dir = Path(args.out_dir)
    skills_root = Path(args.skills_root)
    pid_file = Path(args.pid_file)
    log_file = Path(args.log_file)

    if args.status:
        stale_pid_cleaned = cleanup_stale_pid_file(pid_file)
        payload = status_payload(pid_file)
        payload["stale_pid_cleaned"] = stale_pid_cleaned
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
        return 0

    if args.stop:
        stopped = stop_daemon(pid_file)
        payload = {"stopped": stopped, "pid_file": str(pid_file)}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
        return 0

    if args.once:
        payload = sync_once(codex_root, out_dir, skills_root)
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
        return 0

    cleanup_stale_pid_file(pid_file)
    existing_status = status_payload(pid_file)
    if existing_status["running"]:
        print(f"daemon already running with pid {existing_status['pid']}", file=sys.stderr)
        return 1
    if pid_file.exists():
        pid_file.unlink()
    run_daemon(args.interval, codex_root, out_dir, skills_root, pid_file, log_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
