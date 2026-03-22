---
title: Check CoolingConfig.MaxLimitLevel when manual 100% fan speed does not reach
  full PWM
scope: domain
domain: openubmc-debug
lesson_id: domain-openubmc-debug-when-manual-fan-speed-is-set-to-100-but-actual-d-c385788f9a
rule_key: when manual fan speed is set to 100% but actual duty remains lower, query
  coolingconfig private maxlimitlevel first and compare coolingfan hardwarepwm against
  maxsupportedpwm. the runtime clamps both manual and automatic fan tables through
  cooling_check_fan_level_range using maxlimitlevel
trigger_key: a live bmc showed aircoolingconfig/coolingconfig manual level at 100
  but actual fan hardwarepwm stayed below full scale
created: '2026-03-19T10:38:55Z'
updated: '2026-03-19T10:38:55Z'
keywords:
- openubmc
- fan
- manual
- pwm
- maxlimitlevel
- coolingconfig
- thermal_mgmt
project_root: ''
project_slug: ''
applies_when: ''
session_id: ''
source_note: ''
source_sessions: []
source_notes: []
candidate_notes: []
evidence_history:
- Live system 10.121.177.40 had ManualLevel=100, MaxLimitLevel=92, and all CoolingFan
  objects showed HardwarePWM=235 with MaxSupportedPWM=255.
confidence: 0
merge_count: 1
conflict_status: none
tags:
- codex/lesson
- memory/domain
- lessons/openubmc-debug
---

# Check CoolingConfig.MaxLimitLevel when manual 100% fan speed does not reach full PWM

## Trigger

A live BMC showed AirCoolingConfig/CoolingConfig manual level at 100 but actual fan HardwarePWM stayed below full scale.

## Rule

When manual fan speed is set to 100% but actual duty remains lower, query CoolingConfig private MaxLimitLevel first and compare CoolingFan HardwarePWM against MaxSupportedPWM. The runtime clamps both manual and automatic fan tables through cooling_check_fan_level_range using MaxLimitLevel.

## Evidence

Live system 10.121.177.40 had ManualLevel=100, MaxLimitLevel=92, and all CoolingFan objects showed HardwarePWM=235 with MaxSupportedPWM=255.

## Anti-Pattern

_No anti-pattern recorded._

## Verification

_No verification step recorded._

## Source

- Lesson ID: `domain-openubmc-debug-when-manual-fan-speed-is-set-to-100-but-actual-d-c385788f9a`
- Merge Count: `1`
- Conflict Status: `none`
- Session ID: `unknown`
- Source Note: not linked
- Source Sessions: none
- Source Notes: none
- Candidate Notes: none
- Confidence: `0`
