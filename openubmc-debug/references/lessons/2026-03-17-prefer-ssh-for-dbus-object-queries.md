---
title: Prefer SSH for DBus object queries
domain: openubmc-debug
created: '2026-03-17T08:08:24Z'
updated: '2026-03-17T08:08:24Z'
keywords:
- ssh
- telnet
- dbus
- busctl
- mdbctl
- object-path
- service
- property
applies_when: The user asks about DBus object paths, services, interfaces, methods,
  or properties.
session_id: ''
source_note: ''
tags:
- codex/lesson
- lessons/openubmc-debug
---

# Prefer SSH for DBus object queries

## Trigger

DBus object or property inspection was attempted from the wrong interface.

## Rule

Use SSH for busctl and mdbctl queries; keep Telnet for log access.

## Evidence

Object trees, services, and properties are more stable and reproducible over SSH.

## Anti-Pattern

Do not use Telnet as the default entrypoint for busctl or mdbctl.

## Verification

Run preflight_remote.py and then use mdbctl_remote.py or busctl_remote.py over SSH.

## Source

- Session ID: `unknown`
- Source Note: `not linked`
