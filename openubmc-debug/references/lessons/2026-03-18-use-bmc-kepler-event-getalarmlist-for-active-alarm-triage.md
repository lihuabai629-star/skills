---
title: Use bmc.kepler.event GetAlarmList for active alarm triage
scope: domain
domain: openubmc-debug
lesson_id: domain-openubmc-debug-on-live-systems-introspect-bmc-kepler-systems-1--c5eb46fb1f
rule_key: on live systems, introspect /bmc/kepler/systems/1/events on bmc.kepler.event
  first, then call getalarmlist to retrieve active alarms before broad log scraping
  or tree enumeration
trigger_key: when analyzing a live openubmc alarm by event code, service ownership
  of /bmc/kepler/systems/1/events is not obvious and generic mdbctl enumeration may
  time out
created: '2026-03-18T07:49:29Z'
updated: '2026-03-18T07:49:29Z'
keywords:
- openubmc
- alarm
- dbus
- busctl
- getalarmlist
- event-service
project_root: ''
project_slug: ''
applies_when: ''
session_id: ''
source_note: ''
source_sessions: []
source_notes: []
candidate_notes: []
evidence_history:
- On 10.121.177.159, bmc.kepler.event owned /bmc/kepler/Systems/1/Events and GetAlarmList
  immediately returned the three active 0x5D000001 alarms while preflight mdbctl timed
  out.
confidence: 0
merge_count: 1
conflict_status: none
tags:
- codex/lesson
- memory/domain
- lessons/openubmc-debug
---

# Use bmc.kepler.event GetAlarmList for active alarm triage

## Trigger

When analyzing a live openUBMC alarm by event code, service ownership of /bmc/kepler/Systems/1/Events is not obvious and generic mdbctl enumeration may time out.

## Rule

On live systems, introspect /bmc/kepler/Systems/1/Events on bmc.kepler.event first, then call GetAlarmList to retrieve active alarms before broad log scraping or tree enumeration.

## Evidence

On 10.121.177.159, bmc.kepler.event owned /bmc/kepler/Systems/1/Events and GetAlarmList immediately returned the three active 0x5D000001 alarms while preflight mdbctl timed out.

## Anti-Pattern

_No anti-pattern recorded._

## Verification

_No verification step recorded._

## Source

- Lesson ID: `domain-openubmc-debug-on-live-systems-introspect-bmc-kepler-systems-1--c5eb46fb1f`
- Merge Count: `1`
- Conflict Status: `none`
- Session ID: `unknown`
- Source Note: not linked
- Source Sessions: none
- Source Notes: none
- Candidate Notes: none
- Confidence: `0`
