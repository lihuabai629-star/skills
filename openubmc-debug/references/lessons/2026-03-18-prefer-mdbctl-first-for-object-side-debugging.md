---
title: Prefer mdbctl first for object-side debugging
scope: domain
domain: openubmc-debug
created: '2026-03-18T02:01:29Z'
updated: '2026-03-18T02:01:29Z'
keywords:
- openubmc
- mdbctl
- busctl
- dbus
- object-debug
- ssh
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

# Prefer mdbctl first for object-side debugging

## Trigger

The skill was steering object queries to busctl too early, which did not match the user normal openUBMC workflow.

## Rule

Default to mdbctl or mdbctl_remote.py first for openUBMC object exploration; switch to busctl_remote.py only for raw D-Bus, exact signatures, monitor, or when mdbctl fails.

## Evidence

Quickstart and overview now make mdbctl the first object-side command and busctl the precise or fallback path.

## Anti-Pattern

_No anti-pattern recorded._

## Verification

_No verification step recorded._

## Source

- Session ID: `unknown`
- Source Note: `not linked`
