#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import hashlib
from pathlib import Path
from typing import Any

import yaml

from memory_scopes import DEFAULT_SKILLS_ROOT, MemoryStore, scope_store
from session_memory import frontmatter_text, parse_timestamp, slugify, utc_now

INDEX_MARKDOWN = "INDEX.md"
INDEX_JSON = "index.json"
TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")
DOMAIN_SYNONYMS = Path(__file__).resolve().parent.parent / "references" / "domain-synonyms.json"
SCOPE_PRIORITY = {"global": 0, "project": 1, "domain": 2}
SCOPE_SCORE_BUCKET = 4


@dataclass
class LessonEntry:
    title: str
    domain: str
    note_path: str
    created: str
    updated: str
    keywords: list[str]
    scope: str = "domain"
    project_root: str = ""
    project_slug: str = ""
    store_path: str = ""
    applies_when: str = ""
    problem: str = ""
    rule: str = ""
    evidence: str = ""
    anti_pattern: str = ""
    next_check: str = ""
    session_id: str = ""
    source_note: str = ""
    lesson_id: str = ""
    rule_key: str = ""
    trigger_key: str = ""
    source_sessions: list[str] = field(default_factory=list)
    source_notes: list[str] = field(default_factory=list)
    candidate_notes: list[str] = field(default_factory=list)
    evidence_history: list[str] = field(default_factory=list)
    confidence: int = 0
    merge_count: int = 1
    conflict_status: str = "none"
    score: int = 0
    score_components: dict[str, int] = field(default_factory=dict)


def default_store_for_domain(domain: str) -> Path:
    return scope_store(scope="domain", domain=domain, skills_root=DEFAULT_SKILLS_ROOT).path


def normalize_keywords(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for keyword in keywords:
        for token in re.split(r"[\s,]+", keyword):
            token = token.strip().lower()
            if not token or token in seen:
                continue
            normalized.append(token)
            seen.add(token)
    return normalized


def tokenize(text: str) -> set[str]:
    return {match.group(0).lower() for match in TOKEN_RE.finditer(text or "")}


def normalize_text_key(text: str) -> str:
    collapsed = " ".join((text or "").strip().split())
    return collapsed.rstrip(".。!！?？").lower()


def normalize_rule_key(text: str) -> str:
    return normalize_text_key(text)


def normalize_trigger_key(applies_when: str, problem: str) -> str:
    return normalize_text_key(applies_when or problem)


def build_lesson_id(scope: str, domain: str, project_slug: str, rule_key: str) -> str:
    identity = "::".join([scope or "domain", domain or "-", project_slug or "-", rule_key or "-"])
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
    label = slugify("-".join(part for part in [scope, domain, project_slug] if part), fallback=scope or "lesson")[:24]
    readable = slugify(rule_key or "lesson", fallback="lesson")[:48]
    return f"{label}-{readable}-{digest}"


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        text = (value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


@lru_cache(maxsize=1)
def load_domain_synonyms() -> dict[str, dict[str, list[str]]]:
    if not DOMAIN_SYNONYMS.exists():
        return {}
    payload = json.loads(DOMAIN_SYNONYMS.read_text(encoding="utf-8"))
    normalized: dict[str, dict[str, list[str]]] = {}
    for domain, mapping in payload.items():
        normalized[domain] = {}
        for key, values in mapping.items():
            normalized[domain][key.lower()] = [value.lower() for value in values]
    return normalized


def expanded_query_tokens(query_tokens: set[str], domain: str) -> set[str]:
    if not domain:
        return set()
    mapping = load_domain_synonyms().get(domain, {})
    expanded: set[str] = set()
    for token in query_tokens:
        expanded.update(tokenize(" ".join(mapping.get(token.lower(), []))))
    return expanded - query_tokens


def preferred_text(existing: str, incoming: str) -> str:
    existing = (existing or "").strip()
    incoming = (incoming or "").strip()
    if not incoming:
        return existing
    if not existing:
        return incoming
    return incoming if len(incoming) > len(existing) else existing


def evidence_items(entry: LessonEntry) -> list[str]:
    if entry.evidence_history:
        return unique_strings(entry.evidence_history)
    if entry.evidence:
        return [entry.evidence]
    return []


def markdown_file_link(path: str) -> str:
    text = (path or "").strip()
    if not text:
        return "not linked"
    label = Path(text).stem or text
    return f"[{label}]({text})"


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


def lesson_filename(title: str, created: str) -> str:
    day = created[:10] if created else utc_now()[:10]
    return f"{day}-{slugify(title, fallback='lesson')}.md"


def unique_note_path(store: Path, filename: str) -> Path:
    candidate = store / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        next_candidate = store / f"{stem}-{counter}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        counter += 1


def lesson_markdown(entry: LessonEntry) -> str:
    evidence = evidence_items(entry)
    frontmatter = {
        "title": entry.title,
        "scope": entry.scope,
        "domain": entry.domain,
        "lesson_id": entry.lesson_id,
        "rule_key": entry.rule_key,
        "trigger_key": entry.trigger_key,
        "created": entry.created,
        "updated": entry.updated,
        "keywords": entry.keywords,
        "project_root": entry.project_root,
        "project_slug": entry.project_slug,
        "applies_when": entry.applies_when,
        "session_id": entry.session_id,
        "source_note": entry.source_note,
        "source_sessions": entry.source_sessions,
        "source_notes": entry.source_notes,
        "candidate_notes": entry.candidate_notes,
        "evidence_history": evidence,
        "confidence": entry.confidence,
        "merge_count": entry.merge_count,
        "conflict_status": entry.conflict_status,
        "tags": build_tags(entry),
    }
    lines = [
        "---",
        frontmatter_text(frontmatter),
        "---",
        "",
        f"# {entry.title}",
        "",
        "## Trigger",
        "",
        entry.problem or "_No trigger description provided._",
        "",
        "## Rule",
        "",
        entry.rule or "_No rule recorded._",
        "",
        "## Evidence",
        "",
        "\n".join(f"- {item}" for item in evidence) if len(evidence) > 1 else (evidence[0] if evidence else "_No evidence recorded._"),
        "",
        "## Anti-Pattern",
        "",
        entry.anti_pattern or "_No anti-pattern recorded._",
        "",
        "## Verification",
        "",
        entry.next_check or "_No verification step recorded._",
        "",
        "## Source",
        "",
        f"- Lesson ID: `{entry.lesson_id or 'unknown'}`",
        f"- Merge Count: `{entry.merge_count}`",
        f"- Conflict Status: `{entry.conflict_status}`",
        f"- Session ID: `{entry.session_id or 'unknown'}`",
        f"- Source Note: {markdown_file_link(entry.source_note)}",
        f"- Source Sessions: {', '.join(f'`{session}`' for session in entry.source_sessions) if entry.source_sessions else 'none'}",
        f"- Source Notes: {', '.join(markdown_file_link(note) for note in entry.source_notes) if entry.source_notes else 'none'}",
        f"- Candidate Notes: {', '.join(markdown_file_link(note) for note in entry.candidate_notes) if entry.candidate_notes else 'none'}",
        f"- Confidence: `{entry.confidence}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def lesson_from_file(path: Path, store: Path) -> LessonEntry:
    frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8"))
    sections = parse_sections(body)
    inferred_scope = infer_scope_from_store(store)
    inferred_project_slug = infer_project_slug_from_store(store) if inferred_scope == "project" else ""
    scope = frontmatter.get("scope", inferred_scope)
    domain = frontmatter.get("domain", "")
    project_slug = frontmatter.get("project_slug", inferred_project_slug)
    rule = sections.get("Rule", "")
    problem = sections.get("Trigger", "")
    applies_when = frontmatter.get("applies_when", "")
    rule_key = frontmatter.get("rule_key", "") or normalize_rule_key(rule)
    trigger_key = frontmatter.get("trigger_key", "") or normalize_trigger_key(applies_when, problem)
    session_id = frontmatter.get("session_id", "")
    source_note = frontmatter.get("source_note", "")
    source_sessions = list(frontmatter.get("source_sessions", [])) or ([session_id] if session_id else [])
    source_notes = list(frontmatter.get("source_notes", [])) or ([source_note] if source_note else [])
    candidate_notes = list(frontmatter.get("candidate_notes", []))
    evidence_history = list(frontmatter.get("evidence_history", []))
    if not evidence_history and sections.get("Evidence") and sections.get("Evidence") != "_No evidence recorded._":
        evidence_history = [sections.get("Evidence", "")]
    return LessonEntry(
        title=frontmatter.get("title", path.stem),
        domain=domain,
        note_path=str(path.relative_to(store)),
        created=frontmatter.get("created", ""),
        updated=frontmatter.get("updated", ""),
        keywords=list(frontmatter.get("keywords", [])),
        scope=scope,
        project_root=frontmatter.get("project_root", ""),
        project_slug=project_slug,
        store_path=str(store),
        applies_when=applies_when,
        problem=problem,
        rule=rule,
        evidence=sections.get("Evidence", ""),
        anti_pattern=sections.get("Anti-Pattern", ""),
        next_check=sections.get("Verification", ""),
        session_id=session_id,
        source_note=source_note,
        lesson_id=frontmatter.get("lesson_id", "") or build_lesson_id(scope, domain, project_slug, rule_key),
        rule_key=rule_key,
        trigger_key=trigger_key,
        source_sessions=source_sessions,
        source_notes=source_notes,
        candidate_notes=candidate_notes,
        evidence_history=evidence_history,
        confidence=int(frontmatter.get("confidence", 0)),
        merge_count=int(frontmatter.get("merge_count", max(1, len(source_sessions) or 1))),
        conflict_status=frontmatter.get("conflict_status", "none"),
    )


def parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(re.finditer(r"^## (.+)$", body, re.MULTILINE))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group(1)] = body[start:end].strip()
    return sections


def infer_scope_from_store(store: Path) -> str:
    text = str(store)
    if "/memories/global/" in text:
        return "global"
    if "/memories/projects/" in text:
        return "project"
    return "domain"


def infer_project_slug_from_store(store: Path) -> str:
    parts = store.parts
    try:
        index = parts.index("projects")
    except ValueError:
        return ""
    return parts[index + 1] if index + 1 < len(parts) else ""


def build_tags(entry: LessonEntry) -> list[str]:
    tags = ["codex/lesson", f"memory/{entry.scope}"]
    if entry.domain:
        tags.append(f"lessons/{entry.domain}")
    if entry.project_slug:
        tags.append(f"project/{entry.project_slug}")
    if entry.conflict_status != "none":
        tags.append("lesson/conflict")
    if entry.merge_count > 1:
        tags.append("lesson/merged")
    return tags


def ensure_store(store: Path) -> None:
    store.mkdir(parents=True, exist_ok=True)


def write_lesson_entry(store: Path, entry: LessonEntry) -> None:
    note_path = store / entry.note_path
    note_path.write_text(lesson_markdown(entry), encoding="utf-8")


def merge_lesson_entries(existing: LessonEntry, incoming: LessonEntry, *, timestamp: str) -> LessonEntry:
    existing.updated = timestamp
    existing.keywords = normalize_keywords([*existing.keywords, *incoming.keywords])
    existing.applies_when = preferred_text(existing.applies_when, incoming.applies_when)
    existing.problem = preferred_text(existing.problem, incoming.problem)
    existing.rule = preferred_text(existing.rule, incoming.rule)
    existing.evidence_history = unique_strings([*evidence_items(existing), *evidence_items(incoming)])
    existing.evidence = existing.evidence_history[-1] if existing.evidence_history else preferred_text(existing.evidence, incoming.evidence)
    existing.anti_pattern = preferred_text(existing.anti_pattern, incoming.anti_pattern)
    existing.next_check = preferred_text(existing.next_check, incoming.next_check)
    existing.session_id = incoming.session_id or existing.session_id
    existing.source_note = incoming.source_note or existing.source_note
    existing.source_sessions = unique_strings([*existing.source_sessions, *incoming.source_sessions])
    existing.source_notes = unique_strings([*existing.source_notes, *incoming.source_notes])
    existing.candidate_notes = unique_strings([*existing.candidate_notes, *incoming.candidate_notes])
    existing.confidence = max(existing.confidence, incoming.confidence)
    existing.merge_count = max(1, existing.merge_count) + 1
    existing.conflict_status = incoming.conflict_status if incoming.conflict_status != "none" else existing.conflict_status
    return existing


def mark_conflict(entries: list[LessonEntry], *, timestamp: str) -> None:
    for entry in entries:
        entry.conflict_status = "conflict"
        entry.updated = timestamp


def write_index_files(store: Path, entries: list[LessonEntry]) -> None:
    scope = infer_scope_from_store(store)
    payload = {
        "generated_at": utc_now(),
        "entries": [{key: value for key, value in asdict(entry).items() if key not in {"score", "score_components"}} for entry in entries],
    }
    (store / INDEX_JSON).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "---",
        frontmatter_text({"title": "Lesson Index", "scope": scope, "updated": payload["generated_at"], "tags": ["codex/lesson-index", f"memory/{scope}"]}),
        "---",
        "",
        "# Lesson Index",
        "",
        "| Updated | Scope | Merge | Conflict | Title | Keywords | Note |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not entries:
        lines.append("| - | - | - | - | No lessons yet | - | - |")
    for entry in entries:
        keywords = ", ".join(entry.keywords)
        note_link = f"[[{entry.note_path.removesuffix('.md')}|Open]]"
        lines.append(
            f"| {entry.updated or entry.created} | {entry.scope} | {entry.merge_count} | {entry.conflict_status} | {entry.title} | {keywords} | {note_link} |"
        )
    (store / INDEX_MARKDOWN).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def rebuild_index(store: Path) -> list[LessonEntry]:
    ensure_store(store)
    entries = [
        lesson_from_file(path, store)
        for path in sorted(store.glob("*.md"))
        if path.name != INDEX_MARKDOWN
    ]
    entries.sort(key=lambda entry: entry.updated or entry.created, reverse=True)
    write_index_files(store, entries)
    return entries


def load_entries(store: Path) -> list[LessonEntry]:
    ensure_store(store)
    index_path = store / INDEX_JSON
    if not index_path.exists():
        return rebuild_index(store)
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    entries = [LessonEntry(**entry) for entry in payload.get("entries", [])]
    for entry in entries:
        entry.store_path = str(store)
        if not entry.scope:
            entry.scope = infer_scope_from_store(store)
        if not entry.project_slug and entry.scope == "project":
            entry.project_slug = infer_project_slug_from_store(store)
    return entries


def record_lesson(
    *,
    store: Path,
    scope: str = "domain",
    title: str,
    domain: str,
    problem: str,
    rule: str,
    evidence: str,
    keywords: list[str],
    project_root: str = "",
    project_slug: str = "",
    applies_when: str = "",
    anti_pattern: str = "",
    next_check: str = "",
    session_id: str = "",
    source_note: str = "",
    candidate_note: str = "",
    confidence: int = 0,
) -> LessonEntry:
    ensure_store(store)
    timestamp = utc_now()
    normalized_keywords = normalize_keywords(keywords)
    normalized_rule = normalize_rule_key(rule)
    normalized_trigger = normalize_trigger_key(applies_when, problem)
    entry = LessonEntry(
        title=title,
        domain=domain,
        note_path="",
        created=timestamp,
        updated=timestamp,
        keywords=normalized_keywords,
        scope=scope,
        project_root=project_root,
        project_slug=project_slug,
        store_path=str(store),
        applies_when=applies_when,
        problem=problem,
        rule=rule,
        evidence=evidence,
        anti_pattern=anti_pattern,
        next_check=next_check,
        session_id=session_id,
        source_note=source_note,
        lesson_id=build_lesson_id(scope, domain, project_slug, normalized_rule),
        rule_key=normalized_rule,
        trigger_key=normalized_trigger,
        source_sessions=unique_strings([session_id]),
        source_notes=unique_strings([source_note]),
        candidate_notes=unique_strings([candidate_note]),
        evidence_history=unique_strings([evidence]),
        confidence=confidence,
        merge_count=1,
        conflict_status="none",
    )
    entries = load_entries(store)

    for existing in entries:
        if existing.lesson_id == entry.lesson_id:
            merged = merge_lesson_entries(existing, entry, timestamp=timestamp)
            write_lesson_entry(store, merged)
            indexed_entries = rebuild_index(store)
            for indexed in indexed_entries:
                if indexed.lesson_id == merged.lesson_id:
                    return indexed
            return merged

    conflicts = [
        existing
        for existing in entries
        if existing.trigger_key and entry.trigger_key and existing.trigger_key == entry.trigger_key and existing.rule_key != entry.rule_key
    ]
    if conflicts:
        mark_conflict(conflicts, timestamp=timestamp)
        entry.conflict_status = "conflict"
        for conflict in conflicts:
            write_lesson_entry(store, conflict)

    note_path = unique_note_path(store, lesson_filename(title, timestamp))
    entry.note_path = str(note_path.relative_to(store))
    write_lesson_entry(store, entry)
    indexed_entries = rebuild_index(store)
    for indexed in indexed_entries:
        if indexed.lesson_id == entry.lesson_id and indexed.note_path == entry.note_path:
            return indexed
    return entry


def recency_score(timestamp: str) -> int:
    parsed = parse_timestamp(timestamp)
    if not parsed:
        return 0
    age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    days = age.days
    if days <= 7:
        return 4
    if days <= 30:
        return 3
    if days <= 90:
        return 2
    if days <= 365:
        return 1
    return 0


def score_entry(entry: LessonEntry, query: str, domain: str | None = None) -> tuple[int, dict[str, int]]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0, {}
    title_tokens = tokenize(entry.title)
    keyword_tokens = set(entry.keywords)
    applies_tokens = tokenize(entry.applies_when)
    rule_tokens = tokenize(entry.rule)
    problem_tokens = tokenize(entry.problem)

    lexical = 0
    lexical += 10 * len(query_tokens & title_tokens)
    lexical += 7 * len(query_tokens & keyword_tokens)
    lexical += 5 * len(query_tokens & applies_tokens)
    lexical += 4 * len(query_tokens & rule_tokens)
    lexical += 3 * len(query_tokens & problem_tokens)
    if query.lower() in " ".join([entry.title, entry.problem, entry.rule, entry.applies_when]).lower():
        lexical += 6

    synonym_tokens = expanded_query_tokens(query_tokens, domain or entry.domain)
    searchable_tokens = title_tokens | keyword_tokens | applies_tokens | rule_tokens | problem_tokens
    synonyms = 4 * len(synonym_tokens & searchable_tokens)

    normalized_query = normalize_text_key(query)
    exact_trigger = 0
    if normalized_query and entry.trigger_key:
        if normalized_query == entry.trigger_key:
            exact_trigger = 8
        elif normalized_query in entry.trigger_key or entry.trigger_key in normalized_query:
            exact_trigger = 5

    confidence_bonus = min(8, max(0, entry.confidence) // 3)
    merge_bonus = min(12, max(0, entry.merge_count - 1) * 4)
    source_bonus = min(8, max(0, len(entry.source_sessions) - 1) * 2)
    recency_bonus = recency_score(entry.updated or entry.created)
    domain_bonus = 5 if domain and entry.domain == domain else 0

    components = {
        "lexical": lexical,
        "synonyms": synonyms,
        "exact_trigger": exact_trigger,
        "confidence": confidence_bonus,
        "merge": merge_bonus,
        "source_sessions": source_bonus,
        "recency": recency_bonus,
        "domain_match": domain_bonus,
    }
    return sum(components.values()), components


def find_lessons(store: Path, query: str, domain: str | None = None, limit: int = 5) -> list[LessonEntry]:
    entries = load_entries(store)
    matched: list[LessonEntry] = []
    for entry in entries:
        if domain and entry.domain != domain:
            continue
        score, components = score_entry(entry, query, domain=domain)
        if score <= 0:
            continue
        entry.score = score
        entry.score_components = components
        matched.append(entry)
    matched.sort(
        key=lambda entry: (
            entry.score,
            entry.merge_count,
            len(entry.source_sessions),
            entry.updated or entry.created,
        ),
        reverse=True,
    )
    return matched[:limit]


def find_lessons_across_scopes(
    *,
    query: str,
    stores: list[MemoryStore],
    domain: str = "",
    limit: int = 5,
) -> list[LessonEntry]:
    collected: list[tuple[int, LessonEntry]] = []
    for store_index, store in enumerate(stores):
        scoped_domain = domain if store.scope == "domain" and domain else None
        matches = find_lessons(store.path, query, domain=scoped_domain, limit=limit)
        for match in matches:
            match.store_path = str(store.path)
            if not match.scope:
                match.scope = store.scope
            if not match.project_root:
                match.project_root = store.project_root
            if not match.project_slug:
                match.project_slug = store.project_slug
            collected.append((store_index, match))
    collected.sort(
        key=lambda item: (
            item[1].score // SCOPE_SCORE_BUCKET,
            SCOPE_PRIORITY.get(item[1].scope, 0),
            item[1].score,
            item[1].updated or item[1].created,
        ),
        reverse=True,
    )
    return [entry for _, entry in collected[:limit]]
