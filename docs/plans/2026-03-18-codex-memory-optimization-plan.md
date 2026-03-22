# Codex Memory Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve Codex memory quality so session capture stays reliable, lesson candidates become easier to promote, and recalled lessons are more relevant and less duplicated.

**Architecture:** Keep native rollout JSONL as the source of truth, but make the lesson pipeline more explicit: extract richer candidates, triage them through a reviewable queue, merge them into canonical lessons, and score recall across `global`, `project`, and `domain` stores with stronger ranking signals. Reliability work on the daemon stays separate from retrieval quality work so failures are easier to isolate.

**Tech Stack:** Python 3, local JSON/Markdown stores, Obsidian Markdown export, unittest

### Task 1: Candidate Lifecycle And Promotion Queue

**Files:**
- Modify: `/root/.codex/skills/codex-session-memory/scripts/auto_sync.py`
- Modify: `/root/.codex/skills/codex-session-memory/scripts/lesson_memory.py`
- Modify: `/root/.codex/skills/codex-session-memory/scripts/record_lesson.py`
- Create: `/root/.codex/skills/codex-session-memory/scripts/review_candidates.py`
- Test: `/root/.codex/skills/codex-session-memory/tests/test_session_memory.py`

**Step 1: Write the failing tests**

Add tests for:
- candidate notes carrying stable candidate ids
- candidate promotion converting a candidate into a formal lesson
- promoted/rejected candidates disappearing from `INBOX.md`
- duplicate candidate rules being grouped instead of listed as separate pending items

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v
```

Expected: FAIL on missing promotion workflow and candidate ids.

**Step 3: Write minimal implementation**

Implement:
- candidate metadata model with `candidate_id`, `normalized_rule_key`, `sources`, `confidence`, `first_seen`, `last_seen`
- `review_candidates.py` commands for `list`, `promote`, `reject`
- promotion path that calls shared lesson-writing logic instead of duplicating note creation
- inbox rebuild logic that removes promoted/rejected items from active queue pages

**Step 4: Run test to verify it passes**

Run:
```bash
python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v
```

Expected: PASS with new candidate lifecycle coverage.

**Step 5: Commit**

```bash
git -C /root/.codex/skills add codex-session-memory/scripts/auto_sync.py codex-session-memory/scripts/lesson_memory.py codex-session-memory/scripts/record_lesson.py codex-session-memory/scripts/review_candidates.py codex-session-memory/tests/test_session_memory.py
git -C /root/.codex/skills commit -m "feat: add candidate review and promotion flow"
```

### Task 2: Canonical Lesson Identity And Merge Rules

**Files:**
- Modify: `/root/.codex/skills/codex-session-memory/scripts/lesson_memory.py`
- Modify: `/root/.codex/skills/codex-session-memory/scripts/find_lessons.py`
- Modify: `/root/.codex/skills/codex-session-memory/references/lesson-schema.md`
- Test: `/root/.codex/skills/codex-session-memory/tests/test_session_memory.py`

**Step 1: Write the failing tests**

Add tests for:
- promoting the same rule twice updates one lesson instead of creating duplicates
- merged lessons accumulate source sessions and evidence history
- conflicting rules with the same trigger are flagged instead of silently merged

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v
```

Expected: FAIL because lessons currently append duplicate Markdown files.

**Step 3: Write minimal implementation**

Implement:
- canonical lesson key from `scope + domain + project_slug + normalized_rule_key`
- merge strategy for evidence, source sessions, and keywords
- conflict marker when normalized trigger overlaps but rule text materially differs
- index fields for `lesson_id`, `rule_key`, `source_sessions`, `merge_count`, `conflict_status`

**Step 4: Run test to verify it passes**

Run the same unittest command and confirm duplicate-promotion tests pass.

**Step 5: Commit**

```bash
git -C /root/.codex/skills add codex-session-memory/scripts/lesson_memory.py codex-session-memory/scripts/find_lessons.py codex-session-memory/references/lesson-schema.md codex-session-memory/tests/test_session_memory.py
git -C /root/.codex/skills commit -m "feat: add canonical lesson identity and merge rules"
```

### Task 3: Recall Ranking Quality

**Files:**
- Modify: `/root/.codex/skills/codex-session-memory/scripts/lesson_memory.py`
- Modify: `/root/.codex/skills/codex-session-memory/scripts/find_lessons.py`
- Create: `/root/.codex/skills/codex-session-memory/references/domain-synonyms.json`
- Test: `/root/.codex/skills/codex-session-memory/tests/test_session_memory.py`

**Step 1: Write the failing tests**

Add tests for:
- repeated lessons ranking higher than one-off lessons
- recent lessons outranking stale lessons when scores are close
- domain synonyms such as `dbus` and `mdbctl` improving query recall
- recall output including why each match ranked highly

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v
```

Expected: FAIL because current scoring only uses token overlap and time.

**Step 3: Write minimal implementation**

Implement:
- scoring inputs for `confidence`, `merge_count`, `source_session_count`, `recency`, and exact-trigger hits
- optional synonym expansion loaded from `references/domain-synonyms.json`
- `find_lessons.py --explain` output showing score components
- tie-break rules that still respect `domain > project > global` when scores are materially equal

**Step 4: Run test to verify it passes**

Run the same unittest command and a targeted CLI check:
```bash
python /root/.codex/skills/codex-session-memory/scripts/find_lessons.py --scope auto --cwd /root/.codex/skills --domain openubmc-debug --query "dbus mdbctl" --explain
```

Expected: PASS and explanation output showing score factors.

**Step 5: Commit**

```bash
git -C /root/.codex/skills add codex-session-memory/scripts/lesson_memory.py codex-session-memory/scripts/find_lessons.py codex-session-memory/references/domain-synonyms.json codex-session-memory/tests/test_session_memory.py
git -C /root/.codex/skills commit -m "feat: improve lesson recall ranking"
```

### Task 4: Better Candidate Extraction And Evidence Capture

**Files:**
- Modify: `/root/.codex/skills/codex-session-memory/scripts/auto_sync.py`
- Modify: `/root/.codex/skills/codex-session-memory/scripts/session_memory.py`
- Modify: `/root/.codex/skills/codex-session-memory/references/note-schema.md`
- Test: `/root/.codex/skills/codex-session-memory/tests/test_session_memory.py`

**Step 1: Write the failing tests**

Add tests for:
- extracting candidates from assistant summaries, user corrections, and final answers
- candidate evidence including the originating message timestamp or source label
- terminal-command context appearing in exported notes when the rule came from shell activity
- low-confidence noise being filtered out

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v
```

Expected: FAIL because current extraction is still prefix-driven and context-light.

**Step 3: Write minimal implementation**

Implement:
- weighted extraction from `final_message`, `assistant` messages, selected `user` corrections, and tool summaries
- evidence blocks with source type and short excerpt
- optional context line for commands such as `busctl`, `mdbctl`, `grep`, `rg`, `pytest`
- minimum confidence threshold and source diversity threshold before candidate creation

**Step 4: Run test to verify it passes**

Run the unittest command and:
```bash
python /root/.codex/skills/codex-session-memory/scripts/auto_sync.py --once --json
```

Expected: PASS and candidate notes showing evidence plus confidence.

**Step 5: Commit**

```bash
git -C /root/.codex/skills add codex-session-memory/scripts/auto_sync.py codex-session-memory/scripts/session_memory.py codex-session-memory/references/note-schema.md codex-session-memory/tests/test_session_memory.py
git -C /root/.codex/skills commit -m "feat: improve candidate extraction and evidence capture"
```

### Task 5: Daemon Reliability And Recovery

**Files:**
- Modify: `/root/.codex/skills/codex-session-memory/scripts/auto_sync.py`
- Modify: `/root/.zshrc`
- Create: `/root/.codex/skills/codex-session-memory/scripts/doctor.py`
- Test: `/root/.codex/skills/codex-session-memory/tests/test_session_memory.py`

**Step 1: Write the failing tests**

Add tests for:
- stale pid files being cleaned automatically
- daemon refusing to start only when metadata matches a real running process
- repeated sync failures backing off instead of hot-looping
- doctor command detecting broken stores, unreadable manifests, and daemon mismatch

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v
```

Expected: FAIL on missing backoff/doctor behavior.

**Step 3: Write minimal implementation**

Implement:
- stale-pid cleanup on startup and status checks
- error counter with bounded backoff in daemon mode
- `doctor.py` for manifest, store, daemon, and export-root health checks
- shell startup remaining idempotent after stale metadata cleanup

**Step 4: Run test to verify it passes**

Run:
```bash
python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v
python /root/.codex/skills/codex-session-memory/scripts/doctor.py
python /root/.codex/skills/codex-session-memory/scripts/auto_sync.py --status --json
```

Expected: PASS and doctor output showing clean state.

**Step 5: Commit**

```bash
git -C /root/.codex/skills add codex-session-memory/scripts/auto_sync.py codex-session-memory/scripts/doctor.py /root/.zshrc codex-session-memory/tests/test_session_memory.py
git -C /root/.codex/skills commit -m "feat: harden codex memory daemon lifecycle"
```

### Task 6: Obsidian UX And Review Surfaces

**Files:**
- Modify: `/root/.codex/skills/codex-session-memory/scripts/session_memory.py`
- Modify: `/root/.codex/skills/codex-session-memory/scripts/lesson_memory.py`
- Create: `/root/.codex/skills/codex-session-memory/scripts/rebuild_dashboards.py`
- Test: `/root/.codex/skills/codex-session-memory/tests/test_session_memory.py`

**Step 1: Write the failing tests**

Add tests for:
- a memory dashboard note listing global/project/domain lesson counts
- separate views for pending candidates, promoted lessons, and conflicts
- backlinks from lesson notes to source sessions and candidate notes

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v
```

Expected: FAIL because only raw indexes exist today.

**Step 3: Write minimal implementation**

Implement:
- dashboard notes under `/mnt/e/obsidian/Codex Sessions/.codex-session-memory/`
- grouped pages for `Pending Candidates`, `Conflicts`, and `Top Lessons`
- lightweight rebuild command that can be called after export or promotion

**Step 4: Run test to verify it passes**

Run:
```bash
python -m unittest discover -s /root/.codex/skills/codex-session-memory/tests -p 'test_session_memory.py' -v
python /root/.codex/skills/codex-session-memory/scripts/rebuild_dashboards.py
```

Expected: PASS and dashboard files generated in the Obsidian archive.

**Step 5: Commit**

```bash
git -C /root/.codex/skills add codex-session-memory/scripts/session_memory.py codex-session-memory/scripts/lesson_memory.py codex-session-memory/scripts/rebuild_dashboards.py codex-session-memory/tests/test_session_memory.py
git -C /root/.codex/skills commit -m "feat: add codex memory dashboards"
```

## Recommended Order

1. Task 5: Daemon reliability and recovery
2. Task 1: Candidate lifecycle and promotion queue
3. Task 2: Canonical lesson identity and merge rules
4. Task 3: Recall ranking quality
5. Task 4: Better candidate extraction and evidence capture
6. Task 6: Obsidian UX and review surfaces

## Success Criteria

- Daemon status can distinguish a real running process from a reused PID.
- Candidate inbox volume stays reviewable instead of growing as raw duplicates.
- Promoting a candidate updates canonical lessons rather than spraying new Markdown files.
- `find_lessons.py` returns more relevant results with visible ranking reasons.
- Obsidian exposes pending work, top lessons, and conflicts without manual digging.
