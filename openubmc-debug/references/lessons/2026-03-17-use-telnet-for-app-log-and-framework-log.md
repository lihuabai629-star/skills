---
title: Use Telnet for app.log and framework.log
domain: openubmc-debug
created: '2026-03-17T08:08:24Z'
updated: '2026-03-17T08:08:24Z'
keywords:
- telnet
- app.log
- framework.log
- var/log
- rotated-log
- grep
- logs
applies_when: The user asks for app.log, framework.log, /var/log, grep on logs, or
  rotated .gz logs.
session_id: ''
source_note: ''
tags:
- codex/lesson
- lessons/openubmc-debug
---

# Use Telnet for app.log and framework.log

## Trigger

Runtime log collection started from the wrong shell path.

## Rule

Use Telnet for app.log, framework.log, rotated log files, and keyword log grep.

## Evidence

This skill keeps the log plane on Telnet and the object plane on SSH to avoid mixed evidence collection.

## Anti-Pattern

Do not read /var/log over SSH when the question is log-oriented.

## Verification

Use collect_logs.py or a focused Telnet grep before switching to code search.

## Source

- Session ID: `unknown`
- Source Note: `not linked`
