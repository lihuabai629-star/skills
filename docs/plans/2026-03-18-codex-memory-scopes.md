# Codex Memory Scopes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor `codex-session-memory` from domain-only lessons into a three-layer memory system: `global`, `project`, and `domain`.

**Architecture:** Keep native Codex sessions as the fact source, but resolve lesson stores by scope. `global` lessons live under `~/.codex/memories/global/`, `project` lessons live under `~/.codex/memories/projects/<slug>/`, and `domain` lessons keep using skill-local stores such as `openubmc-debug/references/lessons/`. Recall aggregates these layers in the order `global -> project -> domain`.

**Tech Stack:** Python 3 standard library, markdown note stores, existing session export + lesson indexing scripts.

### Task 1: Add failing tests for scoped memory behavior

**Files:**
- Modify: `codex-session-memory/tests/test_session_memory.py`

**Step 1: Write failing tests**

Cover:
- scope path resolution for `global`, `project`, and `domain`
- scoped lesson metadata and multi-store recall
- auto candidate generation into `global`, `project`, and `domain` inboxes

**Step 2: Run tests to verify failure**

Run: `python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v`
Expected: FAIL because scoped store utilities and multi-scope candidate generation do not exist yet.

### Task 2: Implement scope resolution utilities

**Files:**
- Create: `codex-session-memory/scripts/memory_scopes.py`
- Modify: `codex-session-memory/scripts/lesson_memory.py`

**Step 1: Implement path rules**

Add helpers for:
- `global` store path
- `project` store path from `cwd`
- `domain` store path from skill name

**Step 2: Extend lesson metadata**

Persist:
- `scope`
- `project_root`
- `project_slug`

### Task 3: Update lesson read/write CLIs

**Files:**
- Modify: `codex-session-memory/scripts/record_lesson.py`
- Modify: `codex-session-memory/scripts/find_lessons.py`

**Step 1: Add scoped write arguments**

Support:
- `--scope`
- `--cwd`
- optional `--domain`

**Step 2: Add aggregated recall**

Default recall order:
- `global`
- `project` when `cwd` is meaningful
- `domain` when provided

### Task 4: Update automation and candidate inboxes

**Files:**
- Modify: `codex-session-memory/scripts/auto_sync.py`

**Step 1: Generate multi-scope candidate inbox entries**

For a session with reusable rule lines:
- always consider `global`
- consider `project` when `cwd` is project-like
- consider classified `domain` scopes

**Step 2: Keep candidate inboxes separate from formal indexes**

No automatic promotion into official lesson indexes.

### Task 5: Update skill docs and re-enable automation

**Files:**
- Modify: `codex-session-memory/SKILL.md`
- Modify: `codex-session-memory/references/lesson-schema.md`
- Modify: `openubmc-debug/SKILL.md`

**Step 1: Document the three scopes**

Explain:
- where each scope lives
- when to read each scope
- when to write each scope

**Step 2: Re-enable daemon**

Run:
- `python /root/.codex/skills/codex-session-memory/scripts/auto_sync.py --once --json`
- start daemon after tests pass
