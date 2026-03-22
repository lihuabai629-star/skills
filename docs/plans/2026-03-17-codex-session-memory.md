# Codex Session Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a full Codex session archiving and lessons-learned system that exports native Codex sessions into Obsidian notes and lets skills such as `openubmc-debug` recall and capture reusable lessons.

**Architecture:** Parse Codex rollout JSONL files as the primary source of truth, enrich them with thread metadata from `state_*.sqlite`, render Obsidian-friendly notes plus machine-readable artifacts, and maintain a manifest/index for incremental sync. Keep lessons in per-domain stores with note files, `index.json`, and `INDEX.md`, then wire `openubmc-debug` to query and update that store.

**Tech Stack:** Python 3 standard library, `yaml`, Obsidian Markdown, Codex local state files under `~/.codex`.

### Task 1: Define export and lesson behaviors with failing tests

**Files:**
- Create: `codex-session-memory/tests/test_session_memory.py`
- Create: `codex-session-memory/tests/fixtures/minimal_rollout.jsonl`

**Step 1: Write the failing tests**

Cover:
- rollout parsing into messages, final answer, and tool calls
- note rendering and export manifest generation
- lesson note creation, index rebuild, and keyword search

**Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v`
Expected: FAIL because `session_memory` and `lesson_memory` modules do not exist yet.

### Task 2: Implement session export library and CLI

**Files:**
- Create: `codex-session-memory/scripts/session_memory.py`
- Create: `codex-session-memory/scripts/export_sessions.py`

**Step 1: Implement rollout parsing**

Read `session_meta`, `turn_context`, `event_msg`, `response_item` records and normalize them into a reusable session model.

**Step 2: Implement note/artifact export**

Write:
- per-session Obsidian note
- per-session JSON artifact
- `.codex-session-memory/manifest.json`
- `Session Index.md`

**Step 3: Add CLI modes**

Support:
- `--latest`
- `--sync-all`
- `--session-id`
- `--rollout`

### Task 3: Implement lesson store library and CLIs

**Files:**
- Create: `codex-session-memory/scripts/lesson_memory.py`
- Create: `codex-session-memory/scripts/record_lesson.py`
- Create: `codex-session-memory/scripts/find_lessons.py`

**Step 1: Implement lesson note writer**

Persist lessons as Obsidian notes with frontmatter, stable filenames, and source references.

**Step 2: Implement index maintenance**

Maintain:
- `index.json`
- `INDEX.md`

**Step 3: Implement search**

Tokenize query + keywords, score matches, and return the highest-signal lessons for recall.

### Task 4: Finish the skill package

**Files:**
- Modify: `codex-session-memory/SKILL.md`
- Create: `codex-session-memory/references/note-schema.md`
- Create: `codex-session-memory/references/lesson-schema.md`
- Create: `codex-session-memory/agents/openai.yaml`

**Step 1: Replace scaffold content with workflow instructions**

Document:
- when to use the skill
- session export workflow
- lesson capture workflow
- exact scripts to run

**Step 2: Add references**

Keep schema details and note conventions out of `SKILL.md`.

### Task 5: Integrate `openubmc-debug`

**Files:**
- Modify: `openubmc-debug/SKILL.md`
- Create: `openubmc-debug/references/lessons/INDEX.md`
- Create: `openubmc-debug/references/lessons/index.json`

**Step 1: Add recall step**

Before analysis, query the lesson store using the symptom/object/service/log clue.

**Step 2: Add capture step**

After analysis, record a lesson when a reusable debugging rule or anti-pattern emerges.

### Task 6: Validate and verify end to end

**Files:**
- Validate: `codex-session-memory/`
- Verify against: a real rollout under `~/.codex/sessions/`

**Step 1: Run unit tests**

Run: `python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v`

**Step 2: Validate skill**

Run: `python /root/.codex/skills/skill-creator/scripts/quick_validate.py /root/.codex/skills/codex-session-memory`

**Step 3: Verify real export**

Run `export_sessions.py` against a real completed rollout and confirm the note, artifact, and index are written under `/mnt/e/obsidian/Codex Sessions/`.
