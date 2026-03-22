---
title: Check CPUMetrics and MemoryMetrics before assuming CPU/MEM power sensors exist
scope: domain
domain: openubmc-debug
lesson_id: domain-openubmc-debug-first-query-bmc-kepler-systems-id-processors-cpu-62239d0a83
rule_key: first query /bmc/kepler/systems/<id>/processors/cpu and /bmc/kepler/systems/<id>/memory
  for consumedpowerwatt, then enumerate thresholdsensor/getthresholdsensorlist to
  verify whether cpu power or mem power sensors are actually exposed. do not assume
  metrics imply sensor objects
trigger_key: on live systems, users ask where currentcpupowerwatts and currentmemorypowerwatts
  come from and whether matching sensors exist
created: '2026-03-19T10:30:38Z'
updated: '2026-03-19T10:30:38Z'
keywords:
- openubmc
- cpu-power
- memory-power
- metrics
- sensor
- thresholdsensor
- mdbctl
project_root: ''
project_slug: ''
applies_when: ''
session_id: ''
source_note: ''
source_sessions: []
source_notes: []
candidate_notes: []
evidence_history:
- 10.121.177.40 exposed CPUMetrics_1_010101 and MemoryMetrics_1_010101 with non-zero
  ConsumedPowerWatt, but ThresholdSensor/GetThresholdSensorList only showed FAN/PSU/System
  power sensors and no CPU Power or MEM Power.
confidence: 0
merge_count: 1
conflict_status: none
tags:
- codex/lesson
- memory/domain
- lessons/openubmc-debug
---

# Check CPUMetrics and MemoryMetrics before assuming CPU/MEM power sensors exist

## Trigger

On live systems, users ask where CurrentCPUPowerWatts and CurrentMemoryPowerWatts come from and whether matching sensors exist.

## Rule

First query /bmc/kepler/Systems/<id>/Processors/CPU and /bmc/kepler/Systems/<id>/Memory for ConsumedPowerWatt, then enumerate ThresholdSensor/GetThresholdSensorList to verify whether CPU Power or MEM Power sensors are actually exposed. Do not assume metrics imply sensor objects.

## Evidence

10.121.177.40 exposed CPUMetrics_1_010101 and MemoryMetrics_1_010101 with non-zero ConsumedPowerWatt, but ThresholdSensor/GetThresholdSensorList only showed FAN/PSU/System power sensors and no CPU Power or MEM Power.

## Anti-Pattern

_No anti-pattern recorded._

## Verification

_No verification step recorded._

## Source

- Lesson ID: `domain-openubmc-debug-first-query-bmc-kepler-systems-id-processors-cpu-62239d0a83`
- Merge Count: `1`
- Conflict Status: `none`
- Session ID: `unknown`
- Source Note: not linked
- Source Sessions: none
- Source Notes: none
- Candidate Notes: none
- Confidence: `0`
