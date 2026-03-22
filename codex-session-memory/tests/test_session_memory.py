#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = TEST_DIR / "fixtures"
SCRIPT_DIR = TEST_DIR.parent / "scripts"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def load_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        raise AssertionError(f"missing module: {name}") from exc


class SessionParsingTests(unittest.TestCase):
    def test_default_export_root_points_to_dedicated_vault(self) -> None:
        session_memory = load_module("session_memory")

        self.assertEqual(
            session_memory.DEFAULT_EXPORT_ROOT,
            Path("/mnt/e/obsidian-codex-sessions-vault"),
        )

    def test_apply_thread_metadata_normalizes_epoch_timestamps(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.SessionRecord(session_id="session-test-123", rollout_path="/tmp/demo.jsonl")

        session_memory.apply_thread_metadata(
            record,
            {
                "updated_at": 1773734851,
                "title": "Imported title",
                "approval_mode": "never",
            },
        )

        self.assertEqual(record.updated_at, "2026-03-17T08:07:31Z")
        self.assertEqual(record.title, "Imported title")

    def test_parse_rollout_extracts_messages_and_tools(self) -> None:
        session_memory = load_module("session_memory")

        record = session_memory.parse_rollout(FIXTURE_DIR / "minimal_rollout.jsonl")

        self.assertEqual(record.session_id, "session-test-123")
        self.assertEqual(record.cwd, "/workspace/demo")
        self.assertEqual(record.first_user_message, "Investigate why the parser misses tool output.")
        self.assertEqual(record.final_message, "Final answer: fixed the parser bug and added regression tests.")
        self.assertEqual([message.role for message in record.messages], ["user", "assistant", "assistant"])
        self.assertEqual(len(record.tool_calls), 1)
        self.assertEqual(record.tool_calls[0].name, "exec_command")
        self.assertIn("git status --short", record.tool_calls[0].arguments)
        self.assertIn("M main.py", record.tool_calls[0].output)

    def test_render_note_contains_metadata_timeline_and_tools(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.parse_rollout(FIXTURE_DIR / "minimal_rollout.jsonl")

        note_text = session_memory.render_session_note(record)

        self.assertIn("session_id: session-test-123", note_text)
        self.assertIn("## Outcome", note_text)
        self.assertIn("Final answer: fixed the parser bug and added regression tests.", note_text)
        self.assertIn("## Tool Activity", note_text)
        self.assertIn("exec_command", note_text)
        self.assertIn("```text", note_text)

    def test_render_note_highlights_terminal_command_details(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.parse_rollout(FIXTURE_DIR / "minimal_rollout.jsonl")

        note_text = session_memory.render_session_note(record)

        self.assertIn("Terminal Command", note_text)
        self.assertIn("Command: `git status --short`", note_text)

    def test_render_note_shows_immediate_commands_under_assistant_messages(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.parse_rollout(FIXTURE_DIR / "minimal_rollout.jsonl")

        note_text = session_memory.render_session_note(record)

        self.assertIn("Immediate Commands", note_text)
        self.assertIn("- `git status --short`", note_text)

    def test_render_note_scopes_immediate_commands_to_the_nearest_assistant_message(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.SessionRecord(
            session_id="session-assistant-commands",
            rollout_path="/tmp/assistant-commands.jsonl",
            created_at="2026-03-20T01:00:00Z",
            updated_at="2026-03-20T01:00:10Z",
            cwd="/workspace/demo",
            title="assistant command scoping",
            first_user_message="show the actual commands",
            final_message="done",
            messages=[
                session_memory.Message(
                    timestamp="2026-03-20T01:00:01Z",
                    role="assistant",
                    text="First I will inspect the tree.",
                ),
                session_memory.Message(
                    timestamp="2026-03-20T01:00:05Z",
                    role="assistant",
                    text="Then I will inspect the logs.",
                ),
            ],
            tool_calls=[
                session_memory.ToolCall(
                    timestamp="2026-03-20T01:00:02Z",
                    name="exec_command",
                    arguments='{"cmd":"tree -L 1"}',
                    output=".",
                ),
                session_memory.ToolCall(
                    timestamp="2026-03-20T01:00:06Z",
                    name="exec_command",
                    arguments='{"cmd":"tail -n 20 app.log"}',
                    output="log line",
                ),
            ],
        )

        note_text = session_memory.render_session_note(record)

        self.assertIn("First I will inspect the tree.", note_text)
        self.assertIn("Then I will inspect the logs.", note_text)
        self.assertIn("- `tree -L 1`", note_text)
        self.assertIn("- `tail -n 20 app.log`", note_text)
        self.assertNotIn("First I will inspect the tree.\n\n**Immediate Commands**\n\n- `tail -n 20 app.log`", note_text)

    def test_render_note_strips_tool_wrapper_noise_from_output_preview(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.parse_rollout(FIXTURE_DIR / "minimal_rollout.jsonl")

        note_text = session_memory.render_session_note(record)

        self.assertNotIn("Chunk ID: demo", note_text)
        self.assertNotIn("Wall time: 0.001 seconds", note_text)
        self.assertNotIn("Process exited with code 0", note_text)
        self.assertNotIn("Output:\n M main.py", note_text)
        self.assertIn("M main.py", note_text)

    def test_render_note_omits_redundant_exec_command_arguments(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.parse_rollout(FIXTURE_DIR / "minimal_rollout.jsonl")

        note_text = session_memory.render_session_note(record)

        self.assertNotIn('"cmd": "git status --short"', note_text)
        self.assertNotIn("**Arguments**", note_text)

    def test_render_note_highlights_terminal_input_details(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.parse_rollout(FIXTURE_DIR / "terminal_input_rollout.jsonl")

        note_text = session_memory.render_session_note(record)

        self.assertIn("Terminal Input", note_text)
        self.assertIn("Session ID: `9001`", note_text)
        self.assertIn("Input Preview", note_text)
        self.assertIn("status", note_text)
        self.assertIn("Input: `(empty poll)`", note_text)
        self.assertNotIn('"session_id": 9001', note_text)
        self.assertNotIn('"chars": "status\\n"', note_text)

    def test_render_note_keeps_arguments_for_non_terminal_tools(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.SessionRecord(
            session_id="session-non-terminal-tool",
            rollout_path="/tmp/non-terminal.jsonl",
            created_at="2026-03-18T09:00:00Z",
            updated_at="2026-03-18T09:01:00Z",
            cwd="/workspace/demo",
            title="non terminal tool arguments",
            first_user_message="keep non-terminal arguments",
            final_message="done",
            tool_calls=[
                session_memory.ToolCall(
                    timestamp="2026-03-18T09:00:30Z",
                    name="apply_patch",
                    arguments='{"path":"demo.txt","mode":"replace"}',
                    output="patched",
                )
            ],
        )

        note_text = session_memory.render_session_note(record)

        self.assertIn("**Arguments**", note_text)
        self.assertIn('"path": "demo.txt"', note_text)
        self.assertIn('"mode": "replace"', note_text)

    def test_render_note_strips_nul_and_control_characters(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.SessionRecord(
            session_id="session-binary-output",
            rollout_path="/tmp/binary.jsonl",
            created_at="2026-03-18T03:15:00Z",
            updated_at="2026-03-18T03:15:30Z",
            cwd="/workspace/demo",
            title="binary output reproduction",
            first_user_message="please inspect binary output \x00 safely",
            final_message="done \x1b with guardrails",
            messages=[
                session_memory.Message(
                    timestamp="2026-03-18T03:15:01Z",
                    role="user",
                    text="line before\x00line after",
                ),
            ],
            tool_calls=[
                session_memory.ToolCall(
                    timestamp="2026-03-18T03:15:02Z",
                    name="exec_command",
                    arguments='{"cmd":"cat binary.bin"}',
                    output="prefix\x00middle\x1b[31mred",
                )
            ],
        )

        note_text = session_memory.render_session_note(record)

        self.assertNotIn("\x00", note_text)
        self.assertNotIn("\x1b", note_text)
        self.assertIn("line before", note_text)
        self.assertIn("line after", note_text)
        self.assertIn("prefix", note_text)
        self.assertIn("middle", note_text)

    def test_render_note_truncates_large_sessions_to_keep_note_readable(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.SessionRecord(
            session_id="session-large-note",
            rollout_path="/tmp/large.jsonl",
            created_at="2026-03-18T09:00:00Z",
            updated_at="2026-03-18T09:30:00Z",
            cwd="/workspace/demo",
            title="large note reproduction",
            first_user_message="request " + ("r" * 120000),
            final_message="outcome " + ("o" * 120000),
            messages=[
                session_memory.Message(
                    timestamp=f"2026-03-18T09:{index:02d}:00Z",
                    role="assistant" if index % 2 else "user",
                    text=f"message-{index} " + ("x" * 5000),
                )
                for index in range(120)
            ],
            tool_calls=[
                session_memory.ToolCall(
                    timestamp=f"2026-03-18T09:{index:02d}:30Z",
                    name="exec_command",
                    arguments=json.dumps(
                        {
                            "cmd": f"echo tool-{index} " + ("y" * 4000),
                            "workdir": "/workspace/demo",
                        },
                        ensure_ascii=False,
                    ),
                    output=("output-line\n" * 200) + ("z" * 6000),
                )
                for index in range(120)
            ],
        )

        note_text = session_memory.render_session_note(record)

        self.assertLess(len(note_text), 200_000)
        self.assertIn("Request truncated", note_text)
        self.assertIn("Outcome truncated", note_text)
        self.assertIn("Conversation timeline truncated", note_text)
        self.assertIn("Tool activity truncated", note_text)
        self.assertIn("Full structured session data lives in", note_text)

    def test_note_rel_path_limits_long_slug_length(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.SessionRecord(
            session_id="session-test-very-long",
            rollout_path="/tmp/demo.jsonl",
            created_at="2026-03-17T08:30:00Z",
            title="x" * 400,
        )

        rel_path = session_memory.note_rel_path(record)

        self.assertLessEqual(len(rel_path.name), 140)

    def test_export_writes_note_artifact_and_manifest(self) -> None:
        session_memory = load_module("session_memory")
        record = session_memory.parse_rollout(FIXTURE_DIR / "minimal_rollout.jsonl")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = session_memory.export_session_record(record, Path(tmpdir))
            manifest_path = Path(tmpdir) / ".codex-session-memory" / "manifest.json"
            index_path = Path(tmpdir) / "Session Index.md"

            self.assertTrue(Path(result["note_path"]).exists())
            self.assertTrue(Path(result["artifact_path"]).exists())
            self.assertTrue(manifest_path.exists())
            self.assertTrue(index_path.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("session-test-123", manifest["sessions"])
            self.assertEqual(manifest["sessions"]["session-test-123"]["note_path"], result["note_rel_path"])
            self.assertIn(str(FIXTURE_DIR / "minimal_rollout.jsonl"), manifest["rollouts"])

    def test_manifest_tracks_rollout_path_for_skip_checks(self) -> None:
        session_memory = load_module("session_memory")
        auto_sync = load_module("auto_sync")
        rollout_path = FIXTURE_DIR / "minimal_rollout.jsonl"
        record = session_memory.parse_rollout(rollout_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            session_memory.export_session_record(record, Path(tmpdir))
            manifest = session_memory.load_manifest(tmpdir)

            self.assertTrue(auto_sync.should_skip_rollout(rollout_path, manifest))

    def test_load_manifest_retries_on_transient_json_decode_error(self) -> None:
        session_memory = load_module("session_memory")
        valid_manifest = json.dumps({"generated_at": "", "sessions": {}, "rollouts": {}})

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_file = Path(tmpdir) / ".codex-session-memory" / "manifest.json"
            manifest_file.parent.mkdir(parents=True, exist_ok=True)
            manifest_file.write_text(valid_manifest, encoding="utf-8")

            with mock.patch.object(Path, "read_text", side_effect=["{", valid_manifest]) as read_mock:
                manifest = session_memory.load_manifest(tmpdir)

            self.assertEqual(manifest["sessions"], {})
            self.assertEqual(read_mock.call_count, 2)

    def test_concurrent_exports_preserve_both_manifest_entries(self) -> None:
        session_memory = load_module("session_memory")

        record_a = session_memory.SessionRecord(
            session_id="session-race-a",
            rollout_path="/tmp/session-race-a.jsonl",
            created_at="2026-03-20T02:00:00Z",
            updated_at="2026-03-20T02:00:01Z",
            cwd="/workspace/demo",
            title="race a",
            first_user_message="race a",
            final_message="done a",
        )
        record_b = session_memory.SessionRecord(
            session_id="session-race-b",
            rollout_path="/tmp/session-race-b.jsonl",
            created_at="2026-03-20T02:00:02Z",
            updated_at="2026-03-20T02:00:03Z",
            cwd="/workspace/demo",
            title="race b",
            first_user_message="race b",
            final_message="done b",
        )

        first_loaded = threading.Event()
        allow_first_to_continue = threading.Event()
        original_load_manifest = session_memory.load_manifest
        failures: list[BaseException] = []

        def wrapped_load_manifest(out_dir: str | Path):
            manifest = original_load_manifest(out_dir)
            if threading.current_thread().name == "export-a":
                first_loaded.set()
                allow_first_to_continue.wait(timeout=2)
            return manifest

        def export_record(record):
            try:
                session_memory.export_session_record(record, out_dir)
            except BaseException as exc:  # pragma: no cover - surfaced below
                failures.append(exc)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            with mock.patch.object(session_memory, "load_manifest", side_effect=wrapped_load_manifest):
                thread_a = threading.Thread(target=export_record, args=(record_a,), name="export-a")
                thread_b = threading.Thread(target=export_record, args=(record_b,), name="export-b")
                thread_a.start()
                self.assertTrue(first_loaded.wait(timeout=2))
                thread_b.start()
                time.sleep(0.1)
                allow_first_to_continue.set()
                thread_a.join(timeout=5)
                thread_b.join(timeout=5)

            self.assertFalse(thread_a.is_alive())
            self.assertFalse(thread_b.is_alive())
            self.assertEqual([], failures)

            manifest = json.loads((out_dir / ".codex-session-memory" / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("session-race-a", manifest["sessions"])
            self.assertIn("session-race-b", manifest["sessions"])


class LessonMemoryTests(unittest.TestCase):
    def test_scope_path_resolution(self) -> None:
        memory_scopes = load_module("memory_scopes")

        global_store = memory_scopes.scope_store(scope="global", codex_root=Path("/tmp/codex-root"))
        project_store = memory_scopes.scope_store(
            scope="project",
            cwd="/tmp/example/openubmc",
            codex_root=Path("/tmp/codex-root"),
        )
        domain_store = memory_scopes.scope_store(
            scope="domain",
            domain="openubmc-debug",
            skills_root=Path("/tmp/skills-root"),
        )

        self.assertEqual(global_store.path, Path("/tmp/codex-root/memories/global/lessons"))
        self.assertEqual(project_store.project_slug, "tmp-example-openubmc")
        self.assertEqual(project_store.path, Path("/tmp/codex-root/memories/projects/tmp-example-openubmc/lessons"))
        self.assertEqual(domain_store.path, Path("/tmp/skills-root/openubmc-debug/references/lessons"))

    def test_scope_path_resolution_prefers_git_root_and_realpath(self) -> None:
        memory_scopes = load_module("memory_scopes")
        session_memory = load_module("session_memory")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            repo_root = tmp_path / "repo"
            nested_dir = repo_root / "src" / "module"
            nested_dir.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=repo_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            repo_link = tmp_path / "repo-link"
            repo_link.symlink_to(repo_root, target_is_directory=True)
            linked_nested_dir = repo_link / "src" / "module"

            project_store = memory_scopes.scope_store(
                scope="project",
                cwd=linked_nested_dir,
                codex_root=tmp_path / ".codex",
            )

            resolved_root = str(repo_root.resolve())
            expected_slug = session_memory.slugify(resolved_root.strip("/"), fallback="project")

            self.assertEqual(project_store.project_root, resolved_root)
            self.assertEqual(project_store.project_slug, expected_slug)
            self.assertEqual(project_store.path, tmp_path / ".codex" / "memories" / "projects" / expected_slug / "lessons")

    def test_record_and_find_lesson(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            skills_root = Path(tmpdir) / "skills"
            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root)
            project_store = memory_scopes.scope_store(
                scope="project",
                cwd="/home/workspace/source/openubmc",
                codex_root=codex_root,
            )
            domain_store = memory_scopes.scope_store(
                scope="domain",
                domain="openubmc-debug",
                skills_root=skills_root,
            )
            global_entry = lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Reuse failing-test-first workflow",
                domain="",
                problem="Fixes were attempted before reproducing the bug in an automated test.",
                rule="Write the failing test first, then change production code.",
                evidence="Repeated manual retries hid the real regression boundary.",
                keywords=["tdd", "failing-test", "workflow"],
                applies_when="A change request sounds like a bugfix or behavior correction.",
                anti_pattern="Do not patch first and test later.",
                next_check="Run the new regression test before touching implementation code.",
                session_id="session-global-1",
                source_note="/mnt/e/obsidian/Codex Sessions/global.md",
            )
            project_entry = lesson_memory.record_lesson(
                store=project_store.path,
                scope=project_store.scope,
                project_root="/home/workspace/source/openubmc",
                project_slug=project_store.project_slug,
                title="Project paths live under /home/workspace/source",
                domain="",
                problem="Commands were run from the wrong workspace root.",
                rule="Treat /home/workspace/source as the default project root for this repo.",
                evidence="Relative paths failed until the session moved back into the main source tree.",
                keywords=["workspace", "cwd", "project-root"],
                applies_when="The session is working in this repository.",
                anti_pattern="Do not assume / is the project root.",
                next_check="Confirm pwd before running repo-scoped searches.",
                session_id="session-project-1",
                source_note="/mnt/e/obsidian/Codex Sessions/project.md",
            )
            domain_entry = lesson_memory.record_lesson(
                store=domain_store.path,
                scope=domain_store.scope,
                title="Prefer SSH for DBus object queries",
                domain="openubmc-debug",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use SSH for busctl and mdbctl queries; keep Telnet for log access.",
                evidence="Telnet shell access was available, but DBus inspection remained unstable.",
                keywords=["ssh", "telnet", "dbus", "busctl", "mdbctl"],
                applies_when="User asks for DBus object paths, services, or properties.",
                anti_pattern="Do not read /var/log over SSH or use Telnet as the default DBus entrypoint.",
                next_check="Run preflight_remote.py and then use mdbctl_remote.py over SSH.",
                session_id="session-test-123",
                source_note="/mnt/e/obsidian/Codex Sessions/demo.md",
            )

            self.assertTrue((global_store.path / global_entry.note_path).exists())
            self.assertTrue((project_store.path / project_entry.note_path).exists())
            self.assertTrue((domain_store.path / domain_entry.note_path).exists())
            self.assertTrue((global_store.path / "INDEX.md").exists())
            self.assertTrue((project_store.path / "INDEX.md").exists())
            self.assertTrue((domain_store.path / "INDEX.md").exists())

            matches = lesson_memory.find_lessons_across_scopes(
                query="dbus ssh telnet project-root workflow",
                stores=[
                    global_store,
                    project_store,
                    domain_store,
                ],
                domain="openubmc-debug",
                limit=6,
            )

            self.assertEqual([match.scope for match in matches[:3]], ["domain", "global", "project"])
            self.assertEqual(matches[0].title, "Prefer SSH for DBus object queries")
            self.assertEqual(matches[1].title, "Reuse failing-test-first workflow")
            self.assertEqual(matches[2].title, "Project paths live under /home/workspace/source")
            self.assertIn("busctl", matches[0].keywords)

    def test_find_lessons_across_scopes_merges_before_applying_limit(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            skills_root = Path(tmpdir) / "skills"
            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root)
            project_store = memory_scopes.scope_store(
                scope="project",
                cwd="/home/workspace/source/openubmc",
                codex_root=codex_root,
            )
            domain_store = memory_scopes.scope_store(
                scope="domain",
                domain="openubmc-debug",
                skills_root=skills_root,
            )

            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Verify SSH access before deeper debugging",
                domain="",
                problem="Sessions sometimes continue without checking connectivity first.",
                rule="Verify SSH access before moving into deeper debugging.",
                evidence="A quick SSH check catches access issues early.",
                keywords=["ssh", "verification"],
            )
            lesson_memory.record_lesson(
                store=project_store.path,
                scope=project_store.scope,
                project_root="/home/workspace/source/openubmc",
                project_slug=project_store.project_slug,
                title="Keep workspace commands under the openUBMC source tree",
                domain="",
                problem="Workspace commands run from the wrong root.",
                rule="Use the main workspace tree before invoking repo-scoped commands.",
                evidence="Command lookup stabilized after returning to the workspace root.",
                keywords=["workspace", "cwd"],
            )
            lesson_memory.record_lesson(
                store=domain_store.path,
                scope=domain_store.scope,
                title="Prefer SSH for DBus object queries",
                domain="openubmc-debug",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use SSH for busctl and mdbctl queries; keep Telnet for log access.",
                evidence="DBus inspection is more stable over SSH.",
                keywords=["ssh", "telnet", "dbus", "busctl", "mdbctl"],
            )

            matches = lesson_memory.find_lessons_across_scopes(
                query="ssh telnet dbus workspace",
                stores=[global_store, project_store, domain_store],
                domain="openubmc-debug",
                limit=2,
            )

            self.assertEqual(len(matches), 2)
            self.assertEqual(matches[0].scope, "domain")
            self.assertEqual(matches[0].title, "Prefer SSH for DBus object queries")
            self.assertIn(matches[1].scope, {"global", "project"})

    def test_record_lesson_merges_duplicate_rule_identity(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root)

            first = lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Prefer SSH for DBus object queries",
                domain="",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use SSH for busctl and mdbctl queries.",
                evidence="First session showed SSH was stable.",
                keywords=["ssh", "dbus"],
                applies_when="When DBus object queries are needed.",
                session_id="session-merge-1",
                source_note="/tmp/session-merge-1.md",
            )
            second = lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Use SSH for DBus inspection",
                domain="",
                problem="DBObject checks were attempted over Telnet again.",
                rule="Use SSH for busctl and mdbctl queries.",
                evidence="Second session confirmed the same routing rule.",
                keywords=["busctl", "mdbctl"],
                applies_when="When DBus object queries are needed.",
                session_id="session-merge-2",
                source_note="/tmp/session-merge-2.md",
            )

            entries = lesson_memory.load_entries(global_store.path)

            self.assertEqual(len(entries), 1)
            self.assertEqual(first.note_path, second.note_path)
            self.assertEqual(entries[0].merge_count, 2)
            self.assertEqual(entries[0].conflict_status, "none")
            self.assertEqual(sorted(entries[0].source_sessions), ["session-merge-1", "session-merge-2"])
            self.assertIn("First session showed SSH was stable.", entries[0].evidence_history)
            self.assertIn("Second session confirmed the same routing rule.", entries[0].evidence_history)
            self.assertTrue(entries[0].lesson_id)
            self.assertTrue(entries[0].rule_key)

    def test_record_lesson_flags_conflicting_rules_for_same_trigger(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root)

            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Prefer SSH for DBus object queries",
                domain="",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use SSH for busctl and mdbctl queries.",
                evidence="SSH handled DBus inspection reliably.",
                keywords=["ssh", "dbus"],
                applies_when="When DBus object queries are needed.",
                session_id="session-conflict-1",
                source_note="/tmp/session-conflict-1.md",
            )
            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Prefer Telnet for DBus object queries",
                domain="",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use Telnet as the default DBus entrypoint.",
                evidence="A later session proposed the opposite route.",
                keywords=["telnet", "dbus"],
                applies_when="When DBus object queries are needed.",
                session_id="session-conflict-2",
                source_note="/tmp/session-conflict-2.md",
            )

            entries = lesson_memory.load_entries(global_store.path)

            self.assertEqual(len(entries), 2)
            self.assertEqual({entry.conflict_status for entry in entries}, {"conflict"})
            self.assertEqual(len({entry.lesson_id for entry in entries}), 2)

    def test_record_lesson_writes_canonical_metadata_to_index_and_note(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root)

            entry = lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Write the failing test first",
                domain="",
                problem="A bugfix started before reproducing the issue.",
                rule="Write the failing test before touching production code.",
                evidence="The regression boundary stayed unclear until a test existed.",
                keywords=["tdd", "bugfix"],
                applies_when="When a request is a bugfix.",
                session_id="session-canonical-1",
                source_note="/tmp/session-canonical-1.md",
            )

            index_payload = json.loads((global_store.path / "index.json").read_text(encoding="utf-8"))
            indexed = index_payload["entries"][0]
            note_text = (global_store.path / entry.note_path).read_text(encoding="utf-8")

            self.assertEqual(indexed["lesson_id"], entry.lesson_id)
            self.assertEqual(indexed["rule_key"], entry.rule_key)
            self.assertEqual(indexed["merge_count"], 1)
            self.assertEqual(indexed["source_sessions"], ["session-canonical-1"])
            self.assertEqual(indexed["conflict_status"], "none")
            self.assertIn("lesson_id:", note_text)
            self.assertIn("source_sessions:", note_text)

    def test_find_lessons_cli_surfaces_merge_and_conflict_metadata(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root)

            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Prefer SSH for DBus object queries",
                domain="",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use SSH for busctl and mdbctl queries.",
                evidence="SSH handled DBus inspection reliably.",
                keywords=["ssh", "dbus"],
                applies_when="When DBus object queries are needed.",
                session_id="session-cli-1",
                source_note="/tmp/session-cli-1.md",
            )
            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Use SSH for DBus inspection",
                domain="",
                problem="DBObject checks were attempted over Telnet again.",
                rule="Use SSH for busctl and mdbctl queries.",
                evidence="A follow-up session confirmed the same routing rule.",
                keywords=["busctl", "mdbctl"],
                applies_when="When DBus object queries are needed.",
                session_id="session-cli-2",
                source_note="/tmp/session-cli-2.md",
            )
            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Prefer Telnet for DBus object queries",
                domain="",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use Telnet as the default DBus entrypoint.",
                evidence="A later session proposed the opposite route.",
                keywords=["telnet", "dbus"],
                applies_when="When DBus object queries are needed.",
                session_id="session-cli-3",
                source_note="/tmp/session-cli-3.md",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "find_lessons.py"),
                    "--store",
                    str(global_store.path),
                    "--query",
                    "dbus busctl telnet",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("merge=2", result.stdout)
            self.assertIn("conflict=conflict", result.stdout)
            self.assertIn("sources=2", result.stdout)

    def test_find_lessons_ranks_repeated_lessons_above_one_off_hits(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root)

            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Use SSH for DBus queries",
                domain="",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use SSH for busctl and mdbctl queries.",
                evidence="The first session confirmed SSH was stable.",
                keywords=["ssh", "dbus"],
                session_id="session-rank-1",
            )
            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Use SSH for DBus inspection",
                domain="",
                problem="DBObject checks were attempted over Telnet again.",
                rule="Use SSH for busctl and mdbctl queries.",
                evidence="The second session confirmed the same routing rule.",
                keywords=["ssh", "dbus"],
                session_id="session-rank-2",
            )
            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Use SSH for DBus diagnostics",
                domain="",
                problem="DBObject checks started in the wrong shell.",
                rule="Use SSH for DBus diagnostics before other shells.",
                evidence="A single session suggested the same direction once.",
                keywords=["ssh", "dbus"],
                session_id="session-rank-3",
            )

            matches = lesson_memory.find_lessons(global_store.path, "ssh dbus", limit=2)

            self.assertEqual(matches[0].merge_count, 2)
            self.assertGreater(matches[0].score_components["merge"], 0)
            self.assertGreater(matches[0].score_components["source_sessions"], 0)
            self.assertGreater(matches[0].score, matches[1].score)

    def test_find_lessons_uses_recency_bonus_for_close_matches(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root)

            old_entry = lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Verify SSH access before deeper debugging",
                domain="",
                problem="Sessions sometimes continue without checking connectivity first.",
                rule="Verify SSH access before moving into deeper debugging.",
                evidence="An older session used this as the initial gate.",
                keywords=["ssh", "verification"],
                session_id="session-old",
            )
            recent_entry = lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Verify SSH access before deep debugging",
                domain="",
                problem="Sessions sometimes continue without checking connectivity first.",
                rule="Verify SSH access before moving into deep debugging.",
                evidence="A newer session used the same guardrail.",
                keywords=["ssh", "verification"],
                session_id="session-recent",
            )

            entries = lesson_memory.load_entries(global_store.path)
            old_indexed = next(entry for entry in entries if entry.lesson_id == old_entry.lesson_id)
            old_indexed.created = "2024-01-01T00:00:00Z"
            old_indexed.updated = "2024-01-01T00:00:00Z"
            lesson_memory.write_lesson_entry(global_store.path, old_indexed)
            lesson_memory.rebuild_index(global_store.path)

            matches = lesson_memory.find_lessons(global_store.path, "verify ssh access", limit=2)

            self.assertEqual(matches[0].lesson_id, recent_entry.lesson_id)
            self.assertGreater(matches[0].score_components["recency"], matches[1].score_components["recency"])

    def test_find_lessons_expands_openubmc_domain_synonyms(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_root = Path(tmpdir) / "skills"
            domain_store = memory_scopes.scope_store(
                scope="domain",
                domain="openubmc-debug",
                skills_root=skills_root,
            )

            lesson_memory.record_lesson(
                store=domain_store.path,
                scope=domain_store.scope,
                title="Prefer mdbctl first for object-side debugging",
                domain="openubmc-debug",
                problem="Object-side inspection started in the wrong tool.",
                rule="Default to mdbctl_remote.py first for object exploration.",
                evidence="A successful session started with mdbctl_remote.py.",
                keywords=["mdbctl", "object-debug"],
                session_id="session-synonym",
            )

            matches = lesson_memory.find_lessons(
                domain_store.path,
                "dbus",
                domain="openubmc-debug",
                limit=1,
            )

            self.assertEqual(matches[0].title, "Prefer mdbctl first for object-side debugging")
            self.assertGreater(matches[0].score_components["synonyms"], 0)

    def test_find_lessons_cli_explain_shows_score_factors(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root)

            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Use SSH for DBus queries",
                domain="",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use SSH for busctl and mdbctl queries.",
                evidence="The session showed SSH was stable.",
                keywords=["ssh", "dbus"],
                session_id="session-explain",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "find_lessons.py"),
                    "--store",
                    str(global_store.path),
                    "--query",
                    "ssh dbus",
                    "--explain",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("score components:", result.stdout)
            self.assertIn("lexical=", result.stdout)
            self.assertIn("recency=", result.stdout)


class AutoSyncTests(unittest.TestCase):
    def test_cleanup_stale_pid_file_removes_mismatched_metadata(self) -> None:
        auto_sync = load_module("auto_sync")

        with tempfile.TemporaryDirectory() as tmpdir:
            pid_file = Path(tmpdir) / "daemon.pid"
            payload = auto_sync.current_process_metadata()
            payload["cmdline"] = "python some-other-daemon.py --loop"
            pid_file.write_text(json.dumps(payload), encoding="utf-8")

            cleaned = auto_sync.cleanup_stale_pid_file(pid_file)

            self.assertTrue(cleaned)
            self.assertFalse(pid_file.exists())

    def test_next_sleep_seconds_applies_bounded_backoff(self) -> None:
        auto_sync = load_module("auto_sync")

        self.assertEqual(auto_sync.next_sleep_seconds(interval=45, consecutive_errors=0), 45)
        self.assertEqual(auto_sync.next_sleep_seconds(interval=45, consecutive_errors=1), 90)
        self.assertEqual(auto_sync.next_sleep_seconds(interval=45, consecutive_errors=4), auto_sync.MAX_ERROR_BACKOFF_SECONDS)

    def test_status_payload_accepts_matching_process_metadata(self) -> None:
        auto_sync = load_module("auto_sync")

        with tempfile.TemporaryDirectory() as tmpdir:
            pid_file = Path(tmpdir) / "daemon.pid"
            pid_file.write_text(json.dumps(auto_sync.current_process_metadata()), encoding="utf-8")

            status = auto_sync.status_payload(pid_file)

            self.assertTrue(status["running"])
            self.assertEqual(status["pid"], auto_sync.current_process_metadata()["pid"])

    def test_status_payload_rejects_mismatched_process_metadata(self) -> None:
        auto_sync = load_module("auto_sync")

        with tempfile.TemporaryDirectory() as tmpdir:
            pid_file = Path(tmpdir) / "daemon.pid"
            payload = auto_sync.current_process_metadata()
            payload["cmdline"] = "python some-other-daemon.py --loop"
            pid_file.write_text(json.dumps(payload), encoding="utf-8")

            status = auto_sync.status_payload(pid_file)

            self.assertFalse(status["running"])
            self.assertEqual(status["pid"], payload["pid"])

    def test_classify_domains_detects_openubmc_debug(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-test-123",
            rollout_path="/tmp/demo.jsonl",
            first_user_message="Check DBus object path and app.log behavior on the BMC",
            final_message="Use SSH for busctl and mdbctl. Do not use Telnet for DBus queries.",
        )

        self.assertIn("openubmc-debug", auto_sync.classify_domains(record))

    def test_extract_rule_candidates_merges_sources_and_dedupes(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-test-789",
            rollout_path="/tmp/demo.jsonl",
            first_user_message="Summarize the DBus debugging takeaways",
            final_message=(
                "Use SSH for busctl and mdbctl queries.\n"
                "Use Telnet for app.log and framework.log.\n"
            ),
            messages=[
                session_memory.Message(
                    timestamp="2026-03-18T02:00:00Z",
                    role="assistant",
                    text="Use SSH for busctl and mdbctl queries.\nPrefer mdbctl before raw busctl when object-side debugging.",
                    phase="final_answer",
                ),
                session_memory.Message(
                    timestamp="2026-03-18T02:01:00Z",
                    role="user",
                    text="不要用 Telnet 查 DBus。",
                ),
            ],
        )

        candidates = auto_sync.extract_rule_candidates(record)

        texts = [candidate.text for candidate in candidates]
        self.assertEqual(texts[0], "Use SSH for busctl and mdbctl queries.")
        self.assertIn("Use Telnet for app.log and framework.log.", texts)
        self.assertIn("Prefer mdbctl before raw busctl when object-side debugging.", texts)
        self.assertEqual(texts.count("Use SSH for busctl and mdbctl queries."), 1)
        self.assertIn("final_message", candidates[0].sources)
        self.assertTrue(any(source.startswith("assistant") for source in candidates[0].sources))
        self.assertGreater(candidates[0].confidence, candidates[-1].confidence)

    def test_extract_rule_candidates_ignores_nonfinal_assistant_planning_lines(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-noise-1",
            rollout_path="/tmp/noise.jsonl",
            first_user_message="continue",
            messages=[
                session_memory.Message(
                    timestamp="2026-03-18T06:00:00Z",
                    role="assistant",
                    text="先跑一遍 RED，确认刚才日志里的 bug 现在能被测试稳定复现。",
                )
            ],
        )

        candidates = auto_sync.extract_rule_candidates(record)

        self.assertEqual(candidates, [])

    def test_extract_rule_candidates_ignores_question_like_rules(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-noise-2",
            rollout_path="/tmp/noise2.jsonl",
            first_user_message="continue",
            final_message="先定一个关键约束：你希望“会话归档”和“经验沉淀”存在哪里？",
        )

        candidates = auto_sync.extract_rule_candidates(record)

        self.assertEqual(candidates, [])

    def test_extract_rule_candidates_uses_selected_user_corrections(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-user-correction-1",
            rollout_path="/tmp/correction.jsonl",
            first_user_message="记住这条经验",
            messages=[
                session_memory.Message(
                    timestamp="2026-03-18T06:05:00Z",
                    role="user",
                    text="不要用 Telnet 查 DBus。",
                )
            ],
        )

        candidates = auto_sync.extract_rule_candidates(record)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].text, "不要用 Telnet 查 DBus。")
        self.assertEqual(candidates[0].sources, ("user:0",))

    def test_extract_rule_candidates_ignores_short_fragmentary_lines(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-fragment-1",
            rollout_path="/tmp/fragment.jsonl",
            first_user_message="continue",
            messages=[
                session_memory.Message(
                    timestamp="2026-03-18T06:18:00Z",
                    role="assistant",
                    text="先读哪一层记忆",
                    phase="final_answer",
                )
            ],
            final_message="先读哪一层记忆",
        )

        candidates = auto_sync.extract_rule_candidates(record)

        self.assertEqual(candidates, [])

    def test_generate_lesson_candidates_writes_inbox_note(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir) / "workspace" / "openubmc"
            workspace_root.mkdir(parents=True)
            expected_project_slug = session_memory.slugify(str(workspace_root.resolve()).strip("/"), fallback="project")
            record = session_memory.SessionRecord(
                session_id="session-test-456",
                rollout_path="/tmp/demo.jsonl",
                created_at="2026-03-17T08:30:00Z",
                cwd=str(workspace_root),
                first_user_message="Diagnose DBus property lookup failures on openUBMC",
                final_message=(
                    "结论：\n"
                    "- Use SSH for busctl and mdbctl queries.\n"
                    "- Do not use Telnet as the default DBus entrypoint.\n"
                    "- Use Telnet for app.log and framework.log.\n"
                ),
            )
            created = auto_sync.generate_lesson_candidates(
                record,
                codex_root=Path(tmpdir) / ".codex",
                skills_root=Path(tmpdir),
                source_note="/mnt/e/obsidian/Codex Sessions/demo.md",
            )

            self.assertEqual(len(created), 9)
            for candidate in created:
                self.assertTrue(Path(candidate).exists())

            combined_content = "\n".join(Path(candidate).read_text(encoding="utf-8") for candidate in created)
            self.assertIn("Use SSH for busctl and mdbctl queries.", combined_content)
            self.assertIn("Use Telnet for app.log and framework.log.", combined_content)
            self.assertIn("candidate_id:", combined_content)
            self.assertIn("confidence:", combined_content)
            self.assertIn("sources:", combined_content)
            self.assertTrue((Path(tmpdir) / ".codex" / "memories" / "global" / "lessons" / "inbox" / "INBOX.md").exists())
            self.assertTrue(
                (Path(tmpdir) / ".codex" / "memories" / "projects" / expected_project_slug / "lessons" / "inbox" / "INBOX.md").exists()
            )
            self.assertTrue((Path(tmpdir) / "openubmc-debug" / "references" / "lessons" / "inbox" / "INBOX.md").exists())

    def test_generate_lesson_candidates_skips_project_store_without_cwd(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-test-999",
            rollout_path="/tmp/demo.jsonl",
            first_user_message="Summarize the main debugging rule",
            final_message="Use SSH for busctl and mdbctl queries.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            created = auto_sync.generate_lesson_candidates(
                record,
                codex_root=Path(tmpdir) / ".codex",
                skills_root=Path(tmpdir),
                source_note="/mnt/e/obsidian/Codex Sessions/demo.md",
            )

            self.assertEqual(len(created), 2)
            self.assertTrue((Path(tmpdir) / ".codex" / "memories" / "global" / "lessons" / "inbox" / "INBOX.md").exists())
            self.assertFalse(any((Path(tmpdir) / ".codex" / "memories" / "projects").glob("*/lessons/inbox/INBOX.md")))

    def test_generate_lesson_candidates_does_not_create_openubmc_domain_entries_for_generic_rules(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-generic-memory-1",
            rollout_path="/tmp/generic-memory.jsonl",
            first_user_message="设计 Codex 记忆系统",
            final_message="应该把经验沉淀到单独的 references/lessons 目录。",
            messages=[
                session_memory.Message(
                    timestamp="2026-03-18T06:15:00Z",
                    role="assistant",
                    text="openubmc-debug 只是其中一个 domain 入口。",
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            skills_root = Path(tmpdir) / "skills"
            created = auto_sync.generate_lesson_candidates(
                record,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note="/mnt/e/obsidian/Codex Sessions/generic-memory.md",
            )

            self.assertEqual(len(created), 1)
            self.assertTrue((codex_root / "memories" / "global" / "lessons" / "inbox" / "INBOX.md").exists())
            self.assertFalse((skills_root / "openubmc-debug" / "references" / "lessons" / "inbox" / "INBOX.md").exists())

    def test_generate_lesson_candidates_groups_duplicate_rules_by_candidate_id(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record_one = session_memory.SessionRecord(
            session_id="session-candidate-1",
            rollout_path="/tmp/demo-1.jsonl",
            first_user_message="Summarize the reusable workflow rule",
            final_message="Use regression tests before implementation.",
        )
        record_two = session_memory.SessionRecord(
            session_id="session-candidate-2",
            rollout_path="/tmp/demo-2.jsonl",
            first_user_message="Summarize the reusable workflow rule again",
            final_message="Use regression tests before implementation.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            skills_root = Path(tmpdir) / "skills"
            first = auto_sync.generate_lesson_candidates(
                record_one,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note="/mnt/e/obsidian/Codex Sessions/one.md",
            )
            second = auto_sync.generate_lesson_candidates(
                record_two,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note="/mnt/e/obsidian/Codex Sessions/two.md",
            )

            inbox_dir = codex_root / "memories" / "global" / "lessons" / "inbox"
            active_candidates = sorted(path for path in inbox_dir.glob("*.md") if path.name != "INBOX.md")

            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 1)
            self.assertEqual(first[0], second[0])
            self.assertEqual(len(active_candidates), 1)

            content = active_candidates[0].read_text(encoding="utf-8")
            self.assertIn("candidate_id:", content)
            self.assertIn("session-candidate-1", content)
            self.assertIn("session-candidate-2", content)

    def test_generate_lesson_candidates_prunes_stale_occurrences_for_the_same_session(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-prune-1",
            rollout_path="/tmp/prune.jsonl",
            first_user_message="设计 Codex 记忆系统",
            final_message="应该把经验沉淀到单独的 references/lessons 目录。",
            messages=[
                session_memory.Message(
                    timestamp="2026-03-18T06:20:00Z",
                    role="assistant",
                    text="应该把经验沉淀到单独的 references/lessons 目录。",
                    phase="final_answer",
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            skills_root = Path(tmpdir) / "skills"
            global_store = auto_sync.scope_store(scope="global", codex_root=codex_root, skills_root=skills_root)
            domain_store = auto_sync.scope_store(scope="domain", domain="openubmc-debug", codex_root=codex_root, skills_root=skills_root)
            stale_rule = "先读哪一层记忆"

            for store in (global_store, domain_store):
                stale_path = auto_sync.candidate_path(auto_sync.candidate_inbox_dir(store), store, stale_rule)
                entry = auto_sync.CandidateEntry(
                    candidate_id=auto_sync.candidate_id_for_rule(store, stale_rule),
                    note_path=str(stale_path),
                    created="2026-03-18T06:00:00Z",
                    updated="2026-03-18T06:00:00Z",
                    first_seen="2026-03-18T06:00:00Z",
                    last_seen="2026-03-18T06:00:00Z",
                    status="active",
                    rule=stale_rule,
                    normalized_rule_key=auto_sync.normalize_rule_key(stale_rule),
                    confidence=3,
                    scope=store.scope,
                    domain=store.domain,
                    project_root=store.project_root,
                    project_slug=store.project_slug,
                    source_note="/mnt/e/obsidian/Codex Sessions/prune.md",
                    store_path=str(store.path),
                    occurrences=[
                        auto_sync.CandidateOccurrence(
                            session_id="session-prune-1",
                            source_note="/mnt/e/obsidian/Codex Sessions/prune.md",
                            request="old noisy request",
                            confidence=3,
                            sources=("assistant:9",),
                            captured_at="2026-03-18T06:00:00Z",
                        )
                    ],
                )
                auto_sync.write_candidate_entry(stale_path, entry)
                auto_sync.write_inbox_index(auto_sync.candidate_inbox_dir(store))

            created = auto_sync.generate_lesson_candidates(
                record,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note="/mnt/e/obsidian/Codex Sessions/prune.md",
            )

            self.assertEqual(len(created), 1)
            self.assertFalse((global_store.path / "inbox" / f"{auto_sync.candidate_id_for_rule(global_store, stale_rule)}.md").exists())
            self.assertFalse((domain_store.path / "inbox" / f"{auto_sync.candidate_id_for_rule(domain_store, stale_rule)}.md").exists())

    def test_generate_lesson_candidates_replaces_occurrence_metadata_when_reprocessing_same_session(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-refresh-1",
            rollout_path="/tmp/refresh.jsonl",
            first_user_message="设计 Codex 记忆系统",
            final_message="应该把经验沉淀到单独的 references/lessons 目录。",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            skills_root = Path(tmpdir) / "skills"
            store = auto_sync.scope_store(scope="global", codex_root=codex_root, skills_root=skills_root)
            rule = "应该把经验沉淀到单独的 references/lessons 目录。"
            path = auto_sync.candidate_path(auto_sync.candidate_inbox_dir(store), store, rule)
            entry = auto_sync.CandidateEntry(
                candidate_id=auto_sync.candidate_id_for_rule(store, rule),
                note_path=str(path),
                created="2026-03-18T06:00:00Z",
                updated="2026-03-18T06:00:00Z",
                first_seen="2026-03-18T06:00:00Z",
                last_seen="2026-03-18T06:00:00Z",
                status="active",
                rule=rule,
                normalized_rule_key=auto_sync.normalize_rule_key(rule),
                confidence=3,
                scope=store.scope,
                domain=store.domain,
                project_root=store.project_root,
                project_slug=store.project_slug,
                source_note="/mnt/e/obsidian/Codex Sessions/refresh.md",
                store_path=str(store.path),
                occurrences=[
                    auto_sync.CandidateOccurrence(
                        session_id="session-refresh-1",
                        source_note="/mnt/e/obsidian/Codex Sessions/refresh.md",
                        request="old request",
                        confidence=3,
                        sources=("assistant:1",),
                        captured_at="2026-03-18T06:00:00Z",
                        command_contexts=("rg -n \"references/lessons\" /root/.codex/skills",),
                    )
                ],
            )
            auto_sync.write_candidate_entry(path, entry)

            auto_sync.generate_lesson_candidates(
                record,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note="/mnt/e/obsidian/Codex Sessions/refresh.md",
            )

            content = path.read_text(encoding="utf-8")
            self.assertIn("_No command context captured._", content)
            self.assertNotIn("rg -n \"references/lessons\" /root/.codex/skills", content)

    def test_generate_lesson_candidates_records_evidence_and_command_context(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-evidence-1",
            rollout_path="/tmp/evidence.jsonl",
            first_user_message="Summarize the DBus debugging rule",
            final_message="Use SSH for busctl and mdbctl queries.",
            messages=[
                session_memory.Message(
                    timestamp="2026-03-18T06:10:00Z",
                    role="assistant",
                    text="Use SSH for busctl and mdbctl queries.",
                    phase="final_answer",
                )
            ],
            tool_calls=[
                session_memory.ToolCall(
                    timestamp="2026-03-18T06:09:30Z",
                    name="exec_command",
                    arguments=json.dumps({"cmd": "busctl tree xyz.openbmc_project.Inventory"}),
                    output="xyz.openbmc_project.Inventory\n",
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            skills_root = Path(tmpdir) / "skills"
            created = auto_sync.generate_lesson_candidates(
                record,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note="/mnt/e/obsidian/Codex Sessions/evidence.md",
            )

            content = Path(created[0]).read_text(encoding="utf-8")

            self.assertIn("## Evidence", content)
            self.assertIn("final_message @ 2026-03-18T06:10:00Z", content)
            self.assertIn("Use SSH for busctl and mdbctl queries.", content)
            self.assertIn("## Command Context", content)
            self.assertIn("busctl tree xyz.openbmc_project.Inventory", content)

    def test_generate_lesson_candidates_does_not_attach_spurious_command_contexts_to_abstract_rules(self) -> None:
        auto_sync = load_module("auto_sync")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-command-noise-1",
            rollout_path="/tmp/command-noise.jsonl",
            first_user_message="continue",
            final_message="应该把经验沉淀到单独的 references/lessons 目录。",
            tool_calls=[
                session_memory.ToolCall(
                    timestamp="2026-03-18T06:19:00Z",
                    name="exec_command",
                    arguments=json.dumps({"cmd": "rg -n \"references/lessons\" /root/.codex/skills"}),
                    output="...",
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            created = auto_sync.generate_lesson_candidates(
                record,
                codex_root=Path(tmpdir) / ".codex",
                skills_root=Path(tmpdir) / "skills",
                source_note="/mnt/e/obsidian/Codex Sessions/command-noise.md",
            )

            content = Path(created[0]).read_text(encoding="utf-8")

            self.assertIn("## Command Context", content)
            self.assertIn("_No command context captured._", content)


class CandidateReviewTests(unittest.TestCase):
    def test_promote_candidate_creates_lesson_and_removes_inbox_entry(self) -> None:
        auto_sync = load_module("auto_sync")
        review_candidates = load_module("review_candidates")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-promote-1",
            rollout_path="/tmp/promote.jsonl",
            first_user_message="Summarize the workflow rule",
            final_message="Use regression tests before implementation.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            skills_root = Path(tmpdir) / "skills"
            auto_sync.generate_lesson_candidates(
                record,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note="/mnt/e/obsidian/Codex Sessions/promote.md",
            )

            candidates = review_candidates.list_candidates(
                scope="global",
                codex_root=codex_root,
                skills_root=skills_root,
            )
            self.assertEqual(len(candidates), 1)

            result = review_candidates.promote_candidate(
                candidate_id=candidates[0].candidate_id,
                scope="global",
                codex_root=codex_root,
                skills_root=skills_root,
            )

            lesson_path = Path(result["lesson_path"])
            self.assertTrue(lesson_path.exists())
            self.assertEqual(result["candidate"]["status"], "promoted")
            self.assertEqual(review_candidates.list_candidates(scope="global", codex_root=codex_root, skills_root=skills_root), [])
            self.assertTrue((codex_root / "memories" / "global" / "lessons" / "inbox" / "archive" / "promoted").exists())

    def test_reject_candidate_removes_it_from_active_inbox(self) -> None:
        auto_sync = load_module("auto_sync")
        review_candidates = load_module("review_candidates")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-reject-1",
            rollout_path="/tmp/reject.jsonl",
            first_user_message="Summarize the workflow rule",
            final_message="Use regression tests before implementation.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            skills_root = Path(tmpdir) / "skills"
            auto_sync.generate_lesson_candidates(
                record,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note="/mnt/e/obsidian/Codex Sessions/reject.md",
            )

            candidates = review_candidates.list_candidates(
                scope="global",
                codex_root=codex_root,
                skills_root=skills_root,
            )
            self.assertEqual(len(candidates), 1)

            result = review_candidates.reject_candidate(
                candidate_id=candidates[0].candidate_id,
                scope="global",
                codex_root=codex_root,
                skills_root=skills_root,
                reason="too generic",
            )

            self.assertEqual(result["candidate"]["status"], "rejected")
            self.assertEqual(review_candidates.list_candidates(scope="global", codex_root=codex_root, skills_root=skills_root), [])
            self.assertTrue((codex_root / "memories" / "global" / "lessons" / "inbox" / "archive" / "rejected").exists())


class DashboardTests(unittest.TestCase):
    def test_rebuild_dashboards_writes_memory_dashboard_counts(self) -> None:
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")
        rebuild_dashboards = load_module("rebuild_dashboards")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            codex_root = tmp_path / ".codex"
            skills_root = tmp_path / "skills"
            out_dir = tmp_path / "vault"

            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root, skills_root=skills_root)
            project_store = memory_scopes.scope_store(
                scope="project",
                cwd="/home/workspace/source/openubmc",
                codex_root=codex_root,
                skills_root=skills_root,
            )
            domain_store = memory_scopes.scope_store(
                scope="domain",
                domain="openubmc-debug",
                codex_root=codex_root,
                skills_root=skills_root,
            )

            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Global workflow rule",
                domain="",
                problem="Global workflow drifted.",
                rule="Keep global workflow rules in global memory.",
                evidence="Observed in a global session.",
                keywords=["global", "workflow"],
            )
            lesson_memory.record_lesson(
                store=project_store.path,
                scope=project_store.scope,
                project_root=project_store.project_root,
                project_slug=project_store.project_slug,
                title="Project workspace rule",
                domain="",
                problem="Project commands ran from the wrong cwd.",
                rule="Use the project root before repo-scoped commands.",
                evidence="Observed in a project session.",
                keywords=["project", "cwd"],
            )
            lesson_memory.record_lesson(
                store=domain_store.path,
                scope=domain_store.scope,
                title="Domain DBus rule",
                domain="openubmc-debug",
                problem="DBus inspection started from the wrong shell.",
                rule="Use SSH for busctl and mdbctl queries.",
                evidence="Observed in an openUBMC session.",
                keywords=["domain", "dbus"],
            )

            paths = rebuild_dashboards.rebuild_dashboards(
                out_dir=out_dir,
                codex_root=codex_root,
                skills_root=skills_root,
            )

            dashboard_path = Path(paths["dashboard"])
            self.assertTrue(dashboard_path.exists())
            content = dashboard_path.read_text(encoding="utf-8")
            self.assertIn("| Global Lessons | 1 |", content)
            self.assertIn("| Project Lessons | 1 |", content)
            self.assertIn("| Domain Lessons | 1 |", content)

    def test_rebuild_dashboards_writes_pending_promoted_and_conflict_views(self) -> None:
        auto_sync = load_module("auto_sync")
        lesson_memory = load_module("lesson_memory")
        memory_scopes = load_module("memory_scopes")
        rebuild_dashboards = load_module("rebuild_dashboards")
        review_candidates = load_module("review_candidates")
        session_memory = load_module("session_memory")

        record_one = session_memory.SessionRecord(
            session_id="session-dashboard-1",
            rollout_path="/tmp/dashboard-1.jsonl",
            first_user_message="Summarize the workflow rule",
            final_message="Use regression tests before implementation.",
        )
        record_two = session_memory.SessionRecord(
            session_id="session-dashboard-2",
            rollout_path="/tmp/dashboard-2.jsonl",
            first_user_message="Summarize the memory architecture rule",
            final_message="Keep Codex memory dashboards under the Obsidian export root.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            codex_root = tmp_path / ".codex"
            skills_root = tmp_path / "skills"
            out_dir = tmp_path / "vault"
            global_store = memory_scopes.scope_store(scope="global", codex_root=codex_root, skills_root=skills_root)

            auto_sync.generate_lesson_candidates(
                record_one,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note="/mnt/e/obsidian/Codex Sessions/dashboard-1.md",
            )
            auto_sync.generate_lesson_candidates(
                record_two,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note="/mnt/e/obsidian/Codex Sessions/dashboard-2.md",
            )

            candidates = review_candidates.list_candidates(scope="global", codex_root=codex_root, skills_root=skills_root)
            promoted = review_candidates.promote_candidate(
                candidate_id=candidates[0].candidate_id,
                scope="global",
                codex_root=codex_root,
                skills_root=skills_root,
            )

            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Prefer SSH for DBus object queries",
                domain="",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use SSH for busctl and mdbctl queries.",
                evidence="SSH handled DBus inspection reliably.",
                keywords=["ssh", "dbus"],
                applies_when="When DBus object queries are needed.",
            )
            lesson_memory.record_lesson(
                store=global_store.path,
                scope=global_store.scope,
                title="Prefer Telnet for DBus object queries",
                domain="",
                problem="DBObject checks were attempted over Telnet.",
                rule="Use Telnet as the default DBus entrypoint.",
                evidence="A later session proposed the opposite route.",
                keywords=["telnet", "dbus"],
                applies_when="When DBus object queries are needed.",
            )

            paths = rebuild_dashboards.rebuild_dashboards(
                out_dir=out_dir,
                codex_root=codex_root,
                skills_root=skills_root,
            )

            pending_content = Path(paths["pending"]).read_text(encoding="utf-8")
            promoted_content = Path(paths["promoted"]).read_text(encoding="utf-8")
            conflicts_content = Path(paths["conflicts"]).read_text(encoding="utf-8")

            self.assertIn("Use regression tests before implementation.", pending_content)
            self.assertIn(Path(promoted["lesson_path"]).stem, promoted_content)
            self.assertIn("Prefer Telnet for DBus object queries", conflicts_content)

    def test_promoted_lesson_links_back_to_source_session_and_candidate(self) -> None:
        auto_sync = load_module("auto_sync")
        review_candidates = load_module("review_candidates")
        session_memory = load_module("session_memory")

        record = session_memory.SessionRecord(
            session_id="session-dashboard-promote-1",
            rollout_path="/tmp/dashboard-promote.jsonl",
            first_user_message="Summarize the workflow rule",
            final_message="Use regression tests before implementation.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_root = Path(tmpdir) / ".codex"
            skills_root = Path(tmpdir) / "skills"
            source_note = "/mnt/e/obsidian/Codex Sessions/dashboard-promote.md"

            auto_sync.generate_lesson_candidates(
                record,
                codex_root=codex_root,
                skills_root=skills_root,
                source_note=source_note,
            )
            candidates = review_candidates.list_candidates(scope="global", codex_root=codex_root, skills_root=skills_root)
            result = review_candidates.promote_candidate(
                candidate_id=candidates[0].candidate_id,
                scope="global",
                codex_root=codex_root,
                skills_root=skills_root,
            )

            lesson_note = Path(result["lesson_path"]).read_text(encoding="utf-8")

            self.assertIn(f"]({source_note})", lesson_note)
            self.assertIn(f"]({result['archive_path']})", lesson_note)


class DoctorTests(unittest.TestCase):
    def test_collect_checks_reports_healthy_state(self) -> None:
        auto_sync = load_module("auto_sync")
        doctor = load_module("doctor")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            codex_root = tmp_path / ".codex"
            out_dir = tmp_path / "vault"
            pid_file = codex_root / "daemon.pid"
            (codex_root / "memories" / "global" / "lessons").mkdir(parents=True)
            (out_dir / ".codex-session-memory").mkdir(parents=True)
            (out_dir / ".codex-session-memory" / "manifest.json").write_text(
                json.dumps({"generated_at": "", "sessions": {}, "rollouts": {}}),
                encoding="utf-8",
            )
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(json.dumps(auto_sync.current_process_metadata()), encoding="utf-8")

            checks = doctor.collect_checks(codex_root=codex_root, out_dir=out_dir, pid_file=pid_file)

            self.assertTrue(all(check["status"] == "ok" for check in checks))

    def test_collect_checks_detects_stale_pid_metadata(self) -> None:
        auto_sync = load_module("auto_sync")
        doctor = load_module("doctor")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            codex_root = tmp_path / ".codex"
            out_dir = tmp_path / "vault"
            pid_file = codex_root / "daemon.pid"
            (codex_root / "memories" / "global" / "lessons").mkdir(parents=True)
            (out_dir / ".codex-session-memory").mkdir(parents=True)
            (out_dir / ".codex-session-memory" / "manifest.json").write_text(
                json.dumps({"generated_at": "", "sessions": {}, "rollouts": {}}),
                encoding="utf-8",
            )
            payload = auto_sync.current_process_metadata()
            payload["cmdline"] = "python stale-process.py"
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(json.dumps(payload), encoding="utf-8")

            checks = doctor.collect_checks(codex_root=codex_root, out_dir=out_dir, pid_file=pid_file)

            daemon_check = next(check for check in checks if check["name"] == "daemon_status")
            self.assertEqual(daemon_check["status"], "fail")


if __name__ == "__main__":
    unittest.main()
