---
title: Candidate - 优先按平台维护流程重导入/重载正确的 `MYK` CSR，而不是直接改 `/opt/bmc/sr/*.sr`。
candidate_id: domain-openubmc-debug-myk-csr-opt-bmc-sr-sr-06d964baa0
scope: domain
domain: openubmc-debug
project_root: ''
project_slug: ''
status: active
rule: 优先按平台维护流程重导入/重载正确的 `MYK` CSR，而不是直接改 `/opt/bmc/sr/*.sr`。
normalized_rule_key: 优先按平台维护流程重导入/重载正确的 `myk` csr，而不是直接改 `/opt/bmc/sr/*.sr`
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
  - assistant:83
  captured_at: '2026-03-20T02:46:26Z'
  evidence:
  - source: assistant:83
    timestamp: '2026-03-19T11:13:12.325Z'
    excerpt: 优先按平台维护流程重导入/重载正确的 `MYK` CSR，而不是直接改 `/opt/bmc/sr/*.sr`。
  command_contexts: []
tags:
- codex/lesson-candidate
- memory/domain
- candidate/active
- lessons/openubmc-debug/inbox
---

# Candidate - 优先按平台维护流程重导入/重载正确的 `MYK` CSR，而不是直接改 `/opt/bmc/sr/*.sr`。

## Rule

优先按平台维护流程重导入/重载正确的 `MYK` CSR，而不是直接改 `/opt/bmc/sr/*.sr`。

## Request Signals

- 10.121.177.40这台机器风扇转速设置了手动100%但是实际占空比没达到，风扇转速也没达到，分析一下为什么

## Evidence

- assistant:83 @ 2026-03-19T11:13:12.325Z: 优先按平台维护流程重导入/重载正确的 `MYK` CSR，而不是直接改 `/opt/bmc/sr/*.sr`。

## Command Context

- _No command context captured._

## Supporting Sessions

| Session ID | Confidence | Sources | Note |
| --- | --- | --- | --- |
| 019d05a2-f350-79e0-a510-9f941db417f6 | 3 | assistant:83 | /mnt/e/obsidian-codex-sessions-vault/2026/03/2026-03-19-102738-10-121-177-40100.md |

## Next Step

Promote with `review_candidates.py promote --candidate-id ...` when the rule is stable and reusable.
