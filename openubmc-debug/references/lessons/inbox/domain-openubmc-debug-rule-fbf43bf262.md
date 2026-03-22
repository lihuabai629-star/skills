---
title: Candidate - 先去正常机器上查同样几个值，基本就能坐实：
candidate_id: domain-openubmc-debug-rule-fbf43bf262
scope: domain
domain: openubmc-debug
project_root: ''
project_slug: ''
status: active
rule: 先去正常机器上查同样几个值，基本就能坐实：
normalized_rule_key: 先去正常机器上查同样几个值，基本就能坐实：
confidence: 3
created: '2026-03-20T02:46:26Z'
updated: '2026-03-20T02:46:26Z'
first_seen: '2026-03-20T02:46:26Z'
last_seen: '2026-03-20T02:46:26Z'
source_note: /mnt/e/obsidian-codex-sessions-vault/2026/03/2026-03-19-102738-10-121-177-40100.md
rejection_reason: ''
promoted_lesson_path: ''
occurrences:
- session_id: 019d05a2-f350-79e0-a510-9f941db417f6
  source_note: /mnt/e/obsidian-codex-sessions-vault/2026/03/2026-03-19-102738-10-121-177-40100.md
  request: 10.121.177.40这台机器风扇转速设置了手动100%但是实际占空比没达到，风扇转速也没达到，分析一下为什么
  confidence: 3
  sources:
  - assistant:23
  captured_at: '2026-03-20T02:46:26Z'
  evidence:
  - source: assistant:23
    timestamp: '2026-03-19T10:47:39.820Z'
    excerpt: 先去正常机器上查同样几个值，基本就能坐实：
  command_contexts: []
tags:
- codex/lesson-candidate
- memory/domain
- candidate/active
- lessons/openubmc-debug/inbox
---

# Candidate - 先去正常机器上查同样几个值，基本就能坐实：

## Rule

先去正常机器上查同样几个值，基本就能坐实：

## Request Signals

- 10.121.177.40这台机器风扇转速设置了手动100%但是实际占空比没达到，风扇转速也没达到，分析一下为什么

## Evidence

- assistant:23 @ 2026-03-19T10:47:39.820Z: 先去正常机器上查同样几个值，基本就能坐实：

## Command Context

- _No command context captured._

## Supporting Sessions

| Session ID | Confidence | Sources | Note |
| --- | --- | --- | --- |
| 019d05a2-f350-79e0-a510-9f941db417f6 | 3 | assistant:23 | /mnt/e/obsidian-codex-sessions-vault/2026/03/2026-03-19-102738-10-121-177-40100.md |

## Next Step

Promote with `review_candidates.py promote --candidate-id ...` when the rule is stable and reusable.
