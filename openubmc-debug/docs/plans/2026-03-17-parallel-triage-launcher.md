# Parallel Triage Launcher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a reusable launcher that turns the skill's parallel evidence-collection guidance into executable sessions.

**Architecture:** Add a small Python script that builds lane-specific commands for local code search, SSH object queries, Telnet log queries, and optional NotebookLM background questions. When `tmux` is available it should create a detached multi-window session; otherwise it should emit a machine-readable and human-readable plan so the lanes can be opened manually without losing the recommended command split.

**Tech Stack:** Python 3, argparse, json, subprocess, shutil, existing openubmc-debug helper scripts.

### Task 1: Regression coverage for launcher behavior

**Files:**
- Modify: `/root/.codex/skills/openubmc-debug/tests/test_regressions.py`

**Step 1: Write the failing tests**

Add tests that require:
- `triage_parallel.py` to exist and parse lane-related flags
- plan building to include `local`, `ssh`, `telnet`, and optional `notebooklm`
- `tmux` launch mode to emit expected `tmux` commands when mocked
- docs to reference the launcher

**Step 2: Run tests to verify they fail**

Run: `python /root/.codex/skills/openubmc-debug/tests/test_regressions.py`
Expected: FAIL because `triage_parallel.py` and its doc references do not exist yet

### Task 2: Implement the launcher

**Files:**
- Create: `/root/.codex/skills/openubmc-debug/scripts/triage_parallel.py`

**Step 1: Write minimal implementation**

Implement:
- argument parsing for `--ip`, `--keyword`, `--service`, `--log`, `--grep`, `--notebooklm-question`, `--json`, `--launch-tmux`, `--tmux-session`
- `build_session_plan()` returning ordered lanes and commands
- `launch_tmux_session()` that creates a detached session only when `tmux` exists
- text and JSON output paths for non-`tmux` use

**Step 2: Run tests to verify they pass**

Run: `python /root/.codex/skills/openubmc-debug/tests/test_regressions.py`
Expected: PASS for launcher behavior tests

### Task 3: Wire docs to the launcher

**Files:**
- Modify: `/root/.codex/skills/openubmc-debug/SKILL.md`
- Modify: `/root/.codex/skills/openubmc-debug/references/env-access.md`
- Modify: `/root/.codex/skills/openubmc-debug/references/notebooklm.md`

**Step 1: Update docs**

Add:
- where to use `triage_parallel.py`
- tmux-first / manual fallback rule
- how NotebookLM fits as an optional background lane

**Step 2: Re-run tests**

Run: `python /root/.codex/skills/openubmc-debug/tests/test_regressions.py`
Expected: PASS and doc-reference checks green

### Task 4: Verification

**Files:**
- Verify only

**Step 1: Syntax verification**

Run: `python -m py_compile /root/.codex/skills/openubmc-debug/scripts/triage_parallel.py /root/.codex/skills/openubmc-debug/tests/test_regressions.py`
Expected: PASS

**Step 2: Basic runtime verification**

Run: `python /root/.codex/skills/openubmc-debug/scripts/triage_parallel.py --ip 10.121.177.97 --keyword SensorSelInfo --notebooklm-question "SensorSelInfo belongs to which component?" --json`
Expected: JSON with lane plan and no launch failure
