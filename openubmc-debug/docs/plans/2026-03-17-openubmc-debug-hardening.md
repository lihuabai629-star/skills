# openUBMC Debug Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden `openubmc-debug` so its JSON outputs share a stable contract, debug dumps redact more sensitive shapes and carry richer manifests, routing/fixture coverage reflects real failures, and skill packaging is automated again.

**Architecture:** Add a shared JSON payload helper for the four runtime scripts while preserving existing script-specific fields for compatibility. Extend the existing debug dumper instead of inventing a second artifact system, then lock the new behavior with regression fixtures before adding a generic packaging script under `skill-creator`.

**Tech Stack:** Python 3, unittest, zipfile, existing openUBMC debug helper scripts.

### Task 1: Unified JSON Contract

**Files:**
- Create: `/root/.codex/skills/openubmc-debug/scripts/_json_common.py`
- Modify: `/root/.codex/skills/openubmc-debug/scripts/preflight_remote.py`
- Modify: `/root/.codex/skills/openubmc-debug/scripts/busctl_remote.py`
- Modify: `/root/.codex/skills/openubmc-debug/scripts/mdbctl_remote.py`
- Modify: `/root/.codex/skills/openubmc-debug/scripts/collect_logs.py`
- Test: `/root/.codex/skills/openubmc-debug/tests/test_regressions.py`

**Steps:**
1. Write failing regression tests that require `schema_version`, `tool`, `request`, `result`, `warnings` on all four JSON outputs.
2. Run regression to verify those tests fail for the expected reason.
3. Implement a shared payload builder and wire it into all four scripts with minimal behavior change.
4. Re-run regression until green.

### Task 2: Debug Dump Hardening

**Files:**
- Modify: `/root/.codex/skills/openubmc-debug/scripts/_debug_dump.py`
- Modify: `/root/.codex/skills/openubmc-debug/scripts/_remote_common.py`
- Modify: `/root/.codex/skills/openubmc-debug/scripts/_telnet_common.py`
- Test: `/root/.codex/skills/openubmc-debug/tests/test_regressions.py`
- Create: `/root/.codex/skills/openubmc-debug/tests/fixtures/ssh_auth_failed.txt`
- Create: `/root/.codex/skills/openubmc-debug/tests/fixtures/ssh_timeout.txt`
- Create: `/root/.codex/skills/openubmc-debug/tests/fixtures/telnet_login_stuck.txt`

**Steps:**
1. Write failing tests for token/cookie/session/private-key redaction and richer `summary.json` metadata.
2. Add fixture-driven tests for timeout/auth/login-stuck failure shapes.
3. Implement regex-based redaction and manifest metadata plumbing.
4. Re-run regression until green.

### Task 3: Routing Acceptance

**Files:**
- Modify: `/root/.codex/skills/openubmc-debug/tests/fixtures/routing_cases.json`
- Modify: `/root/.codex/skills/openubmc-debug/tests/test_regressions.py`
- Modify: `/root/.codex/skills/openubmc-debug/references/routing-cases.md`
- Modify: `/root/.codex/skills/openubmc-debug/SKILL.md`

**Steps:**
1. Add failing tests for stronger routing expectations like channels, preferred scripts, and forbidden scripts.
2. Enrich the fixture and reference doc to encode those expectations.
3. Re-run regression until green.

### Task 4: Packaging Tool

**Files:**
- Create: `/root/.codex/skills/skill-creator/scripts/package_skill.py`
- Create: `/root/.codex/skills/skill-creator/tests/test_package_skill.py`

**Steps:**
1. Write a failing unit test that packages `openubmc-debug` into a `.skill` zip and asserts exclusions like `__pycache__`.
2. Implement a small packaging CLI on top of `quick_validate.py` and `zipfile`.
3. Run the packaging tests, then package `openubmc-debug` as a live verification step.

### Task 5: Final Verification

**Files:**
- Modify: `/root/.codex/skills/openubmc-debug/references/env-access.md`
- Modify: `/root/.codex/skills/openubmc-debug/references/logs.md`
- Modify: `/root/.codex/skills/openubmc-debug/SKILL.md`

**Steps:**
1. Refresh docs for the unified JSON contract and richer dump manifest.
2. Run:
   - `python /root/.codex/skills/openubmc-debug/tests/test_regressions.py`
   - `python -m py_compile ...`
   - `python /root/.codex/skills/skill-creator/tests/test_package_skill.py`
   - `python /root/.codex/skills/skill-creator/scripts/quick_validate.py /root/.codex/skills/openubmc-debug`
3. Live-verify `preflight_remote.py --json`, `busctl_remote.py --json`, `mdbctl_remote.py --json`, `collect_logs.py --json` on `10.121.177.97`.
4. Package `/root/.codex/skills/openubmc-debug` into a fresh `.skill` file.
