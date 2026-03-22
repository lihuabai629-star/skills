# WIKIS Knowledge Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Route IMA knowledge-base discovery and questioning through `https://ima.qq.com/wikis` instead of the homepage sidebar.

**Architecture:** Keep the existing persistent-browser auth flow, but make knowledge operations navigate directly to the knowledge-base page. Parse lightweight names from `/wikis` body text for cache refresh, then select a target knowledge base by exact visible text before asking a question.

**Tech Stack:** Python 3, Patchright, unittest

### Task 1: Lock the `/wikis` behavior in tests

**Files:**
- Create: `docs/plans/2026-03-21-wikis-knowledge-routing.md`
- Modify: `tests/test_browser_utils.py`
- Modify: `tests/test_knowledge_manager.py`
- Modify: `tests/test_ask_knowledge.py`

**Step 1: Write the failing tests**

Add tests for:
- `IMAUi.open_wikis()` navigating to `https://ima.qq.com/wikis`
- knowledge-base name extraction from `/wikis` body text
- knowledge-mode navigation selecting a named knowledge base from `/wikis`

**Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test_browser_utils.py test_knowledge_manager.py test_ask_knowledge.py`

Expected: failures because `/wikis` helpers and extraction logic do not exist yet.

### Task 2: Implement direct `/wikis` support

**Files:**
- Modify: `scripts/config.py`
- Modify: `scripts/browser_utils.py`
- Modify: `scripts/knowledge_manager.py`
- Modify: `scripts/ask_knowledge.py`

**Step 1: Write the minimal implementation**

Add:
- `WIKIS_URL`
- browser helper for `/wikis`
- body-text extraction logic for knowledge-base names
- knowledge-mode navigation that opens `/wikis` directly

**Step 2: Run targeted tests to verify they pass**

Run: `python3 -m unittest test_browser_utils.py test_knowledge_manager.py test_ask_knowledge.py`

Expected: PASS

### Task 3: Verify the skill end to end

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`

**Step 1: Run the full test suite**

Run: `python3 -m unittest discover -s /root/.codex/skills/ima/tests -p 'test_*.py'`

Expected: PASS

**Step 2: Refresh the live knowledge-base cache**

Run: `python3 /root/.codex/skills/ima/scripts/run.py knowledge_manager.py list --refresh`

Expected: real knowledge-base names printed from the authenticated session.

**Step 3: Ask a real knowledge-base question**

Run: `python3 /root/.codex/skills/ima/scripts/run.py ask_knowledge.py --scope knowledge --knowledge-query "openUBMC" --question "这个知识库主要包含什么，请用一句话回答" --timeout 60`

Expected: a scoped answer from the selected knowledge base.
