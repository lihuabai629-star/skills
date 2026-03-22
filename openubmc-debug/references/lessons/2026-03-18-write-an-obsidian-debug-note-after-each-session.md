---
title: Write an Obsidian debug note only when the user explicitly asks
scope: domain
domain: openubmc-debug
created: '2026-03-18T02:01:29Z'
updated: '2026-03-20T00:30:00Z'
keywords:
- openubmc
- obsidian
- note
- template
- troubleshooting-method
- recap
project_root: ''
project_slug: ''
applies_when: ''
session_id: ''
source_note: ''
tags:
- codex/lesson
- memory/domain
- lessons/openubmc-debug
---

# Write an Obsidian debug note only when the user explicitly asks

## Trigger

The user explicitly asks for an openUBMC-debug note, summary, recap, handoff, or Obsidian record, and does not want note-taking to start automatically.

## Rule

Only write or update the Obsidian note when the user explicitly asks. If the user asks after task completion, write the final summary; if the user asks earlier while the main path is still active, write a stage summary instead. The note should still include at least 现象, 排查思路, 排查方法, 关键证据, and 结论, using the shared template when possible. The default timing, once requested, is after task completion.

## Evidence

SKILL.md, overview.md, and obsidian-debug-note-template.md now align on the same rule: whether to write is controlled by the user, and once the user explicitly asks, final summaries happen after task completion while stage summaries are reserved for stable conclusions or blocked handoff points.

## Anti-Pattern

- Writing or polishing the note before the user explicitly asks for it
- Treating every intermediate step as a session that must immediately produce a polished note

## Verification

- Re-run the openubmc-debug documentation regression tests and confirm they assert both "由用户决定" / "user explicitly asks" and the remaining "任务完成后" / "after task completion" timing guard across the skill, template, overview, and lesson text.

## Source

- Session ID: `unknown`
- Source Note: `not linked`
