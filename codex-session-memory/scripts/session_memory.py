#!/usr/bin/env python3
from __future__ import annotations

from contextlib import contextmanager
import json
import os
import re
import sqlite3
import tempfile
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fcntl
import yaml

DEFAULT_CODEX_ROOT = Path("/root/.codex")
DEFAULT_EXPORT_ROOT = Path("/mnt/e/obsidian-codex-sessions-vault")
MANIFEST_DIRNAME = ".codex-session-memory"
ARTIFACT_DIRNAME = "artifacts"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_LOCK_FILENAME = "manifest.lock"
SESSION_INDEX_FILENAME = "Session Index.md"
MEMORY_DASHBOARD_FILENAME = "Memory Dashboard.md"
PENDING_CANDIDATES_FILENAME = "Pending Candidates.md"
PROMOTED_LESSONS_FILENAME = "Promoted Lessons.md"
CONFLICTS_FILENAME = "Conflicts.md"
TOP_LESSONS_FILENAME = "Top Lessons.md"
MAX_TOOL_OUTPUT_LINES = 30
MAX_TOOL_OUTPUT_CHARS = 2000
MAX_TIMELINE_HEAD_MESSAGES = 10
MAX_TIMELINE_TAIL_MESSAGES = 10
MAX_TIMELINE_TEXT_LINES = 40
MAX_TIMELINE_TEXT_CHARS = 2000
MAX_REQUEST_TEXT_LINES = 60
MAX_REQUEST_TEXT_CHARS = 4000
MAX_OUTCOME_TEXT_LINES = 60
MAX_OUTCOME_TEXT_CHARS = 4000
MAX_TOOL_HEAD_CALLS = 8
MAX_TOOL_TAIL_CALLS = 8
MAX_TOOL_ARGUMENT_LINES = 30
MAX_TOOL_ARGUMENT_CHARS = 1500
MAX_ASSISTANT_INLINE_COMMANDS = 3
MAX_NOTE_SLUG_LENGTH = 96
MANIFEST_LOAD_RETRIES = 3
MANIFEST_LOAD_RETRY_DELAY_SECONDS = 0.05
ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TOOL_OUTPUT_WRAPPER_RE = re.compile(
    r"^(?:"
    r"Chunk ID:.*|"
    r"Wall time:.*|"
    r"Original token count:.*|"
    r"Total output lines:.*|"
    r"Process exited with code .*|"
    r"Process running with session ID .*|"
    r"Command: .*|"
    r"Output:"
    r")$"
)
TERMINAL_ARGUMENT_FILTERS: dict[str, set[str]] = {
    "exec_command": {"cmd", "workdir", "shell", "tty", "yield_time_ms", "max_output_tokens", "login"},
    "write_stdin": {"chars", "session_id", "yield_time_ms", "max_output_tokens"},
}


@dataclass
class Message:
    timestamp: str
    role: str
    text: str
    phase: str | None = None


@dataclass
class ToolCall:
    timestamp: str
    name: str
    arguments: str
    output: str = ""
    call_id: str | None = None
    kind: str = "function_call"


@dataclass
class SessionRecord:
    session_id: str
    rollout_path: str
    created_at: str = ""
    updated_at: str = ""
    cwd: str = ""
    title: str = ""
    cli_version: str = ""
    model: str = ""
    approval_policy: str = ""
    sandbox_policy: str = ""
    git_branch: str = ""
    git_origin_url: str = ""
    first_user_message: str = ""
    final_message: str = ""
    messages: list[Message] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)

    def note_title(self) -> str:
        seed = self.title or self.first_user_message or self.session_id
        return f"Codex Session - {clip_text(seed, limit=80, suffix='')}"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clip_text(text: str, limit: int = 120, suffix: str = "...") -> str:
    if len(text) <= limit:
        return text
    clipped = text[: max(0, limit - len(suffix))].rstrip()
    return f"{clipped}{suffix}"


def slugify(text: str, fallback: str = "session") -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or fallback


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_time_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    text = stringify(value)
    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return text


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def strip_tool_output_wrapper(text: str) -> str:
    if not text:
        return ""
    lines = text.rstrip().splitlines()
    index = 0
    while index < len(lines):
        current = lines[index].strip()
        if not current:
            index += 1
            continue
        if TOOL_OUTPUT_WRAPPER_RE.match(current):
            index += 1
            continue
        break
    return "\n".join(lines[index:])


def preview_output(
    text: str,
    max_lines: int = MAX_TOOL_OUTPUT_LINES,
    max_chars: int = MAX_TOOL_OUTPUT_CHARS,
    strip_wrappers: bool = False,
) -> str:
    if strip_wrappers:
        text = strip_tool_output_wrapper(text)
    if not text:
        return "(no output captured)"
    lines = text.rstrip().splitlines()
    preview = "\n".join(lines[:max_lines])
    truncated = len(lines) > max_lines or len(preview) > max_chars
    if len(preview) > max_chars:
        preview = preview[:max_chars].rstrip()
    if truncated:
        preview = f"{preview}\n...[truncated]"
    return preview


def preview_note_text(text: str, max_lines: int, max_chars: int) -> str:
    if not text:
        return ""
    lines = text.rstrip().splitlines()
    preview = "\n".join(lines[:max_lines])
    truncated = len(lines) > max_lines or len(preview) > max_chars
    if len(preview) > max_chars:
        preview = preview[:max_chars].rstrip()
    if truncated:
        preview = f"{preview}\n...[truncated]"
    return preview


def sanitize_markdown_text(text: str) -> str:
    if not text:
        return ""
    stripped = ANSI_ESCAPE_RE.sub("", text)
    return CONTROL_CHAR_RE.sub("", stripped)


def pretty_arguments(arguments: str) -> str:
    text = arguments.strip()
    if not text:
        return "{}"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def note_arguments_text(tool_call: ToolCall) -> str | None:
    text = tool_call.arguments.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(parsed, dict):
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    hidden_keys = TERMINAL_ARGUMENT_FILTERS.get(tool_call.name, set())
    filtered = {key: value for key, value in parsed.items() if key not in hidden_keys}
    if not filtered:
        return None
    return preview_note_text(
        json.dumps(filtered, ensure_ascii=False, indent=2),
        max_lines=MAX_TOOL_ARGUMENT_LINES,
        max_chars=MAX_TOOL_ARGUMENT_CHARS,
    )


def parsed_arguments(arguments: str) -> Any | None:
    text = arguments.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def tool_call_command_summary(tool_call: ToolCall) -> str | None:
    parsed = parsed_arguments(tool_call.arguments)
    if not isinstance(parsed, dict):
        return None
    if tool_call.name == "exec_command":
        command = stringify(parsed.get("cmd")).strip()
        return command or None
    if tool_call.name == "write_stdin":
        chars = stringify(parsed.get("chars")).strip()
        if not chars:
            return None
        session_id = stringify(parsed.get("session_id")).strip()
        command = clip_text(chars.replace("\r", "").replace("\n", " "), limit=120)
        if session_id:
            return f"session {session_id}: {command}"
        return command
    return None


def assistant_immediate_commands(record: SessionRecord, message_index: int) -> tuple[list[str], int]:
    if message_index < 0 or message_index >= len(record.messages):
        return [], 0
    message = record.messages[message_index]
    if message.role != "assistant":
        return [], 0

    start = parse_timestamp(message.timestamp)
    next_message_time = None
    for later_message in record.messages[message_index + 1 :]:
        next_message_time = parse_timestamp(later_message.timestamp)
        if next_message_time is not None:
            break

    commands: list[str] = []
    for tool_call in record.tool_calls:
        tool_time = parse_timestamp(tool_call.timestamp)
        if start is not None and tool_time is not None and tool_time <= start:
            continue
        if next_message_time is not None and tool_time is not None and tool_time >= next_message_time:
            continue
        summary = tool_call_command_summary(tool_call)
        if summary:
            commands.append(summary)

    if len(commands) <= MAX_ASSISTANT_INLINE_COMMANDS:
        return commands, 0
    return commands[:MAX_ASSISTANT_INLINE_COMMANDS], len(commands) - MAX_ASSISTANT_INLINE_COMMANDS


def terminal_activity_lines(tool_call: ToolCall) -> list[str]:
    parsed = parsed_arguments(tool_call.arguments)
    if not isinstance(parsed, dict):
        return []

    if tool_call.name == "exec_command":
        lines = ["**Terminal Command**", ""]
        command = stringify(parsed.get("cmd"))
        if command:
            lines.append(f"- Command: `{command}`")
        workdir = stringify(parsed.get("workdir"))
        if workdir:
            lines.append(f"- Workdir: `{workdir}`")
        shell = stringify(parsed.get("shell"))
        if shell:
            lines.append(f"- Shell: `{shell}`")
        if "tty" in parsed:
            lines.append(f"- TTY: `{bool(parsed.get('tty'))}`")
        if "yield_time_ms" in parsed:
            lines.append(f"- Yield Time: `{parsed.get('yield_time_ms')} ms`")
        lines.append("")
        return lines

    if tool_call.name == "write_stdin":
        lines = ["**Terminal Input**", ""]
        session_id = stringify(parsed.get("session_id"))
        if session_id:
            lines.append(f"- Session ID: `{session_id}`")
        chars = parsed.get("chars")
        if chars not in (None, ""):
            lines.extend(
                [
                    "",
                    "**Input Preview**",
                    "",
                    "```text",
                    preview_output(stringify(chars), max_lines=20, max_chars=1000),
                    "```",
                    "",
                ]
            )
        else:
            lines.extend(["- Input: `(empty poll)`", ""])
        return lines

    return []


def frontmatter_text(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()


def latest_state_db(codex_root: Path) -> Path | None:
    candidates = sorted(codex_root.glob("state_*.sqlite"))
    return candidates[-1] if candidates else None


def load_thread_metadata(codex_root: Path, session_id: str) -> dict[str, Any]:
    db_path = latest_state_db(codex_root)
    if not db_path or not session_id:
        return {}
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT id, title, updated_at, cwd, approval_mode, sandbox_policy,
                   git_branch, git_origin_url, first_user_message, cli_version
            FROM threads
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
    except sqlite3.Error:
        return {}
    finally:
        connection.close()
    return dict(row) if row else {}


def response_item_is_call(item_type: str) -> bool:
    return item_type.endswith("_call") or item_type in {"function_call", "web_search_call"}


def response_item_is_output(item_type: str) -> bool:
    return item_type.endswith("_output")


def apply_thread_metadata(record: SessionRecord, metadata: dict[str, Any]) -> None:
    if not metadata:
        return
    if not record.title:
        record.title = stringify(metadata.get("title"))
    if not record.updated_at:
        record.updated_at = normalize_time_value(metadata.get("updated_at"))
    if not record.cwd:
        record.cwd = stringify(metadata.get("cwd"))
    if not record.approval_policy:
        record.approval_policy = stringify(metadata.get("approval_mode"))
    if not record.sandbox_policy:
        record.sandbox_policy = stringify(metadata.get("sandbox_policy"))
    if not record.git_branch:
        record.git_branch = stringify(metadata.get("git_branch"))
    if not record.git_origin_url:
        record.git_origin_url = stringify(metadata.get("git_origin_url"))
    if not record.first_user_message:
        record.first_user_message = stringify(metadata.get("first_user_message"))
    if not record.cli_version:
        record.cli_version = stringify(metadata.get("cli_version"))


def handle_response_item(payload: dict[str, Any], timestamp: str, pending: dict[str, ToolCall], tool_calls: list[ToolCall]) -> None:
    item_type = stringify(payload.get("type"))
    if not item_type or item_type == "message":
        return
    if response_item_is_call(item_type):
        call_id = stringify(payload.get("call_id")) or f"call-{len(tool_calls) + 1}"
        name = stringify(payload.get("name") or payload.get("tool_name") or item_type)
        arguments = payload.get("arguments")
        if arguments is None and "query" in payload:
            arguments = payload.get("query")
        if arguments is None:
            arguments = {key: value for key, value in payload.items() if key not in {"type", "call_id"}}
        tool_call = ToolCall(
            timestamp=timestamp,
            name=name,
            arguments=stringify(arguments),
            call_id=call_id,
            kind=item_type,
        )
        pending[call_id] = tool_call
        tool_calls.append(tool_call)
        return
    if response_item_is_output(item_type):
        call_id = stringify(payload.get("call_id"))
        output = stringify(payload.get("output") or payload.get("content") or payload)
        if call_id and call_id in pending:
            existing = pending[call_id].output
            pending[call_id].output = f"{existing}\n{output}".strip() if existing else output
            return
        tool_calls.append(
            ToolCall(
                timestamp=timestamp,
                name=item_type,
                arguments="",
                output=output,
                call_id=call_id or None,
                kind=item_type,
            )
        )


def parse_rollout(rollout_path: str | Path, codex_root: str | Path = DEFAULT_CODEX_ROOT) -> SessionRecord:
    rollout = Path(rollout_path)
    codex_root = Path(codex_root)
    record = SessionRecord(session_id="", rollout_path=str(rollout))
    pending: dict[str, ToolCall] = {}

    with rollout.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            timestamp = stringify(payload.get("timestamp"))
            item_type = stringify(payload.get("type"))
            inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}

            if item_type == "session_meta":
                record.session_id = stringify(inner.get("id"))
                record.created_at = stringify(inner.get("timestamp") or timestamp)
                record.cwd = stringify(inner.get("cwd"))
                record.cli_version = stringify(inner.get("cli_version"))
                continue

            if item_type == "turn_context":
                record.cwd = record.cwd or stringify(inner.get("cwd"))
                record.model = record.model or stringify(inner.get("model"))
                record.approval_policy = record.approval_policy or stringify(inner.get("approval_policy"))
                sandbox_policy = inner.get("sandbox_policy")
                if sandbox_policy:
                    record.sandbox_policy = record.sandbox_policy or stringify(sandbox_policy.get("type") or sandbox_policy)
                continue

            if item_type == "event_msg":
                event_type = stringify(inner.get("type"))
                message = stringify(inner.get("message"))
                if event_type == "user_message" and message:
                    record.messages.append(Message(timestamp=timestamp, role="user", text=message, phase=inner.get("phase")))
                    if not record.first_user_message:
                        record.first_user_message = message
                elif event_type == "agent_message" and message:
                    record.messages.append(Message(timestamp=timestamp, role="assistant", text=message, phase=inner.get("phase")))
                    if inner.get("phase") == "final_answer":
                        record.final_message = message
                continue

            if item_type == "response_item":
                handle_response_item(inner, timestamp, pending, record.tool_calls)

    thread_metadata = load_thread_metadata(codex_root, record.session_id)
    apply_thread_metadata(record, thread_metadata)

    if not record.final_message:
        for message in reversed(record.messages):
            if message.role == "assistant":
                record.final_message = message.text
                break
    if not record.updated_at:
        timestamps = [message.timestamp for message in record.messages if message.timestamp]
        record.updated_at = timestamps[-1] if timestamps else record.created_at
    if not record.title:
        record.title = clip_text(record.first_user_message or record.session_id, limit=80, suffix="")

    return record


def note_rel_path(record: SessionRecord) -> Path:
    stamp = parse_timestamp(record.created_at) or datetime.now(timezone.utc)
    folder = Path(f"{stamp:%Y}") / f"{stamp:%m}"
    fallback = record.session_id or "session"
    slug = slugify(record.title or record.first_user_message or fallback, fallback=fallback)
    if len(slug) < 8 or slug in {"skill", "session"}:
        suffix = fallback.split("-")[0] if "-" in fallback else fallback[:8]
        slug = f"{slug}-{suffix}" if slug else suffix
    if len(slug) > MAX_NOTE_SLUG_LENGTH:
        slug = slug[:MAX_NOTE_SLUG_LENGTH].rstrip("-")
    filename = f"{stamp:%Y-%m-%d-%H%M%S}-{slug}.md"
    return folder / filename


def artifact_rel_path(record: SessionRecord) -> Path:
    fallback = record.session_id or slugify(record.title, fallback="session")
    return Path(MANIFEST_DIRNAME) / ARTIFACT_DIRNAME / f"{fallback}.json"


def obsidian_link(note_path: str) -> str:
    return note_path.removesuffix(".md").replace("\\", "/")


def windowed_entries(items: list[Any], head: int, tail: int) -> tuple[list[tuple[int, Any]], int]:
    indexed = list(enumerate(items, start=1))
    if len(indexed) <= head + tail:
        return indexed, 0
    return indexed[:head] + indexed[-tail:], len(indexed) - head - tail


def render_session_note(record: SessionRecord) -> str:
    artifact_relative = artifact_rel_path(record).as_posix()
    request_text = record.first_user_message or "_No user message captured._"
    outcome_text = record.final_message or "_No final assistant answer captured._"
    request_preview = preview_note_text(
        request_text,
        max_lines=MAX_REQUEST_TEXT_LINES,
        max_chars=MAX_REQUEST_TEXT_CHARS,
    ) or "_No user message captured._"
    outcome_preview = preview_note_text(
        outcome_text,
        max_lines=MAX_OUTCOME_TEXT_LINES,
        max_chars=MAX_OUTCOME_TEXT_CHARS,
    ) or "_No final assistant answer captured._"
    frontmatter = {
        "title": record.note_title(),
        "session_id": record.session_id,
        "created": record.created_at,
        "updated": record.updated_at,
        "cwd": record.cwd,
        "source_rollout": record.rollout_path,
        "model": record.model,
        "approval_policy": record.approval_policy,
        "sandbox_policy": record.sandbox_policy,
        "git_branch": record.git_branch,
        "git_origin_url": record.git_origin_url,
        "aliases": [record.session_id] if record.session_id else [],
        "tags": ["codex/session", "codex/exported"],
    }
    lines = [
        "---",
        frontmatter_text(frontmatter),
        "---",
        "",
        f"# {record.note_title()}",
        "",
        "> [!info] Session Metadata",
        f"> - Session ID: `{record.session_id}`",
        f"> - Created: `{record.created_at}`",
        f"> - Updated: `{record.updated_at}`",
        f"> - CWD: `{record.cwd}`",
        f"> - Artifact: `{artifact_relative}`",
    ]
    if record.git_branch:
        lines.append(f"> - Git Branch: `{record.git_branch}`")
    if record.model:
        lines.append(f"> - Model: `{record.model}`")

    lines.extend(
        [
            "",
            "## Request",
            "",
            request_preview,
            "",
        ]
    )
    if request_preview != request_text:
        lines.extend(
            [
                f"_Request truncated. Full structured session data lives in `{artifact_relative}`._",
                "",
            ]
        )

    lines.extend(
        [
            "## Outcome",
            "",
            outcome_preview,
            "",
        ]
    )
    if outcome_preview != outcome_text:
        lines.extend(
            [
                f"_Outcome truncated. Full structured session data lives in `{artifact_relative}`._",
                "",
            ]
        )

    lines.extend(
        [
            "## Conversation Timeline",
            "",
        ]
    )

    if not record.messages:
        lines.append("_No conversation messages captured._")
    else:
        timeline_entries, omitted_messages = windowed_entries(
            record.messages,
            head=MAX_TIMELINE_HEAD_MESSAGES,
            tail=MAX_TIMELINE_TAIL_MESSAGES,
        )
        for position, (index, message) in enumerate(timeline_entries, start=1):
            if omitted_messages and position == MAX_TIMELINE_HEAD_MESSAGES + 1:
                lines.extend(
                    [
                        f"_Conversation timeline truncated: omitted {omitted_messages} messages. "
                        f"Full structured session data lives in `{artifact_relative}`._",
                        "",
                    ]
                )
            lines.extend(
                [
                    f"### {index}. {message.role.title()}",
                    "",
                    f"- Timestamp: `{message.timestamp}`",
                ]
            )
            if message.phase:
                lines.append(f"- Phase: `{message.phase}`")
            lines.extend(
                [
                    "",
                    preview_note_text(
                        message.text,
                        max_lines=MAX_TIMELINE_TEXT_LINES,
                        max_chars=MAX_TIMELINE_TEXT_CHARS,
                    )
                    or "_Empty message._",
                    "",
                ]
            )
            immediate_commands, omitted_commands = assistant_immediate_commands(record, index - 1)
            if immediate_commands:
                lines.extend(["**Immediate Commands**", ""])
                lines.extend([f"- `{command}`" for command in immediate_commands])
                if omitted_commands:
                    lines.append(f"- `...[{omitted_commands} more commands]`")
                lines.append("")

    lines.extend(["## Tool Activity", ""])
    if not record.tool_calls:
        lines.append("_No tool activity captured._")
    else:
        tool_entries, omitted_tools = windowed_entries(
            record.tool_calls,
            head=MAX_TOOL_HEAD_CALLS,
            tail=MAX_TOOL_TAIL_CALLS,
        )
        for position, (index, tool_call) in enumerate(tool_entries, start=1):
            if omitted_tools and position == MAX_TOOL_HEAD_CALLS + 1:
                lines.extend(
                    [
                        f"_Tool activity truncated: omitted {omitted_tools} calls. "
                        f"Full structured session data lives in `{artifact_relative}`._",
                        "",
                    ]
                )
            terminal_lines = terminal_activity_lines(tool_call)
            note_arguments = note_arguments_text(tool_call)
            lines.extend(
                [
                    f"### {index}. {tool_call.name}",
                    "",
                    f"- Timestamp: `{tool_call.timestamp}`",
                    f"- Kind: `{tool_call.kind}`",
                    "",
                ]
            )
            if terminal_lines:
                lines.extend(terminal_lines)
            if note_arguments is not None:
                lines.extend(
                    [
                        "**Arguments**",
                        "",
                        "```json",
                        note_arguments,
                        "```",
                        "",
                    ]
                )
            lines.extend(
                [
                    "**Output Preview**",
                    "",
                    "```text",
                    preview_output(tool_call.output, strip_wrappers=True),
                    "```",
                    "",
                ]
            )

    return sanitize_markdown_text("\n".join(lines).rstrip() + "\n")


def session_artifact(record: SessionRecord) -> dict[str, Any]:
    return {
        "generated_at": utc_now(),
        "session": asdict(record),
    }


def manifest_path(out_dir: Path) -> Path:
    return out_dir / MANIFEST_DIRNAME / MANIFEST_FILENAME


def manifest_lock_path(out_dir: Path) -> Path:
    return out_dir / MANIFEST_DIRNAME / MANIFEST_LOCK_FILENAME


def dashboard_dir(out_dir: str | Path) -> Path:
    return Path(out_dir) / MANIFEST_DIRNAME


def dashboard_path(out_dir: str | Path, filename: str) -> Path:
    return dashboard_dir(out_dir) / filename


def load_manifest(out_dir: str | Path) -> dict[str, Any]:
    path = manifest_path(Path(out_dir))
    if not path.exists():
        return {"generated_at": "", "sessions": {}, "rollouts": {}}
    last_error: json.JSONDecodeError | None = None
    for attempt in range(MANIFEST_LOAD_RETRIES):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            break
        except json.JSONDecodeError as exc:
            last_error = exc
            if attempt == MANIFEST_LOAD_RETRIES - 1:
                raise
            time.sleep(MANIFEST_LOAD_RETRY_DELAY_SECONDS)
    else:
        raise last_error or json.JSONDecodeError("manifest read failed", "", 0)
    manifest.setdefault("sessions", {})
    manifest.setdefault("rollouts", {})
    return manifest


def save_manifest(out_dir: Path, manifest: dict[str, Any]) -> Path:
    path = manifest_path(out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(manifest, ensure_ascii=False, indent=2)
    temp_fd, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    return path


@contextmanager
def locked_manifest_transaction(out_dir: Path):
    lock_path = manifest_lock_path(out_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_session_index(out_dir: Path, manifest: dict[str, Any]) -> Path:
    index_path = out_dir / SESSION_INDEX_FILENAME
    entries = sorted(
        manifest.get("sessions", {}).values(),
        key=lambda item: item.get("updated_at") or item.get("created_at") or "",
        reverse=True,
    )
    lines = [
        "---",
        frontmatter_text(
            {
                "title": "Codex Session Index",
                "updated": manifest.get("generated_at", ""),
                "tags": ["codex/index"],
            }
        ),
        "---",
        "",
        "# Codex Session Index",
        "",
        "| Updated | Session | Note | Tools | Messages |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    if not entries:
        lines.append("| - | - | No exported sessions yet | 0 | 0 |")
    for entry in entries:
        note_link = f"[[{obsidian_link(entry['note_path'])}|Open]]"
        session_label = clip_text(entry.get("title") or entry.get("first_user_message") or entry.get("session_id") or "", 60)
        session_label = session_label.replace("|", "\\|")
        lines.append(
            f"| {entry.get('updated_at') or entry.get('created_at') or '-'} | {session_label} | {note_link} | "
            f"{entry.get('tool_count', 0)} | {entry.get('message_count', 0)} |"
        )
    index_path.write_text(sanitize_markdown_text("\n".join(lines).rstrip() + "\n"), encoding="utf-8")
    return index_path


def export_session_record(record: SessionRecord, out_dir: str | Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    note_relative = note_rel_path(record)
    artifact_relative = artifact_rel_path(record)
    note_path = out_dir / note_relative
    artifact_path = out_dir / artifact_relative

    note_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    note_path.write_text(render_session_note(record), encoding="utf-8")
    artifact_path.write_text(json.dumps(session_artifact(record), ensure_ascii=False, indent=2), encoding="utf-8")

    with locked_manifest_transaction(out_dir):
        manifest = load_manifest(out_dir)
        manifest["generated_at"] = utc_now()
        manifest.setdefault("sessions", {})[record.session_id] = {
            "session_id": record.session_id,
            "title": record.note_title(),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "note_path": note_relative.as_posix(),
            "artifact_path": artifact_relative.as_posix(),
            "rollout_path": record.rollout_path,
            "rollout_mtime": Path(record.rollout_path).stat().st_mtime if Path(record.rollout_path).exists() else None,
            "tool_count": len(record.tool_calls),
            "message_count": len(record.messages),
            "first_user_message": record.first_user_message,
            "final_message": record.final_message,
        }
        manifest.setdefault("rollouts", {})[record.rollout_path] = {
            "session_id": record.session_id,
            "rollout_mtime": Path(record.rollout_path).stat().st_mtime if Path(record.rollout_path).exists() else None,
            "note_path": note_relative.as_posix(),
            "artifact_path": artifact_relative.as_posix(),
        }
        save_manifest(out_dir, manifest)
        index_path = write_session_index(out_dir, manifest)

    return {
        "session_id": record.session_id,
        "note_path": str(note_path),
        "note_rel_path": note_relative.as_posix(),
        "artifact_path": str(artifact_path),
        "artifact_rel_path": artifact_relative.as_posix(),
        "index_path": str(index_path),
    }


def rollout_session_id(rollout_path: str | Path) -> str:
    rollout = Path(rollout_path)
    with rollout.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            if payload.get("type") == "session_meta":
                inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
                return stringify(inner.get("id"))
    return ""


def find_rollout_files(codex_root: str | Path = DEFAULT_CODEX_ROOT) -> list[Path]:
    root = Path(codex_root) / "sessions"
    if not root.exists():
        return []
    return sorted(root.rglob("rollout-*.jsonl"), key=lambda path: path.stat().st_mtime)


def latest_rollout(codex_root: str | Path = DEFAULT_CODEX_ROOT) -> Path | None:
    files = find_rollout_files(codex_root)
    return files[-1] if files else None


def find_rollout_by_session_id(codex_root: str | Path, session_id: str) -> Path | None:
    for rollout in reversed(find_rollout_files(codex_root)):
        if rollout_session_id(rollout) == session_id:
            return rollout
    return None
