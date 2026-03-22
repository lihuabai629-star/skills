---
title: Verify live board UID before editing platform SR or soft.sr
scope: domain
domain: openubmc-debug
lesson_id: domain-openubmc-debug-before-editing-a-platform-sr-soft-sr-for-a-live--f1427d50b7
rule_key: before editing a platform sr/soft.sr for a live system, first query the
  board uid from dbus (for example cpuboard_1_010101 bmc.kepler.systems.board.unit
  uid) and verify it matches the target file uniqueid/uid. do not pick the platform
  file by similar name alone
trigger_key: a sensor change looked correct in source but had no effect on the live
  bmc because the edited platform file uid did not match the board uid loaded on the
  system
created: '2026-03-19T10:56:25Z'
updated: '2026-03-19T10:56:25Z'
keywords:
- openubmc
- uid
- platform
- sr
- soft-sr
- sensor
- vpd
project_root: ''
project_slug: ''
applies_when: ''
session_id: ''
source_note: ''
source_sessions: []
source_notes: []
candidate_notes: []
evidence_history:
- 10.121.177.40 reported CpuBoard UID 00000001020302083825, while the edited source
  file was 14060876_00000001020302031825_soft.sr. CPUMetrics and MemoryMetrics still
  had live power values, but CPU Power and MEM Power sensors did not appear because
  the modified file was not the platform actually loaded.
confidence: 0
merge_count: 1
conflict_status: none
tags:
- codex/lesson
- memory/domain
- lessons/openubmc-debug
---

# Verify live board UID before editing platform SR or soft.sr

## Trigger

A sensor change looked correct in source but had no effect on the live BMC because the edited platform file UID did not match the board UID loaded on the system.

## Rule

Before editing a platform SR/soft.sr for a live system, first query the board UID from DBus (for example CpuBoard_1_010101 bmc.kepler.Systems.Board.Unit UID) and verify it matches the target file UniqueId/UID. Do not pick the platform file by similar name alone.

## Evidence

10.121.177.40 reported CpuBoard UID 00000001020302083825, while the edited source file was 14060876_00000001020302031825_soft.sr. CPUMetrics and MemoryMetrics still had live power values, but CPU Power and MEM Power sensors did not appear because the modified file was not the platform actually loaded.

## Anti-Pattern

_No anti-pattern recorded._

## Verification

_No verification step recorded._

## Source

- Lesson ID: `domain-openubmc-debug-before-editing-a-platform-sr-soft-sr-for-a-live--f1427d50b7`
- Merge Count: `1`
- Conflict Status: `none`
- Session ID: `unknown`
- Source Note: not linked
- Source Sessions: none
- Source Notes: none
- Candidate Notes: none
- Confidence: `0`
