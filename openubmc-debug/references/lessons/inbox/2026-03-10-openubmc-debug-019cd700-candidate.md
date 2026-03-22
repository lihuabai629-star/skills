---
title: 'Candidate - bmcip 10.121.176.198


  Administrator

  Admin@9000


  OSip 10.121.177.165


  root

  @qwer1234!  ascend-dmi -p it 5     A2 GPU加压命令在os下执行加压命令发现功耗并没有变化分析一下'
domain: openubmc-debug
created: '2026-03-17T08:18:15Z'
session_id: 019cd700-95bd-7b00-91c5-8e377ca1fd4e
source_note: /mnt/e/obsidian/Codex Sessions/2026/03/2026-03-10-090745-bmcip-10-121-176-198-administrator-admin-9000-osip-10-121-177-165-root-qwer1234-ascend-dmi-p-it.md
tags:
- codex/lesson-candidate
- lessons/openubmc-debug/inbox
---

# Candidate - bmcip 10.121.176.198

Administrator
Admin@9000

OSip 10.121.177.165

root
@qwer1234!  ascend-dmi -p it 5     A2 GPU加压命令在os下执行加压命令发现功耗并没有变化分析一下

## Request

bmcip 10.121.176.198

Administrator
Admin@9000

OSip 10.121.177.165

root
@qwer1234!  ascend-dmi -p it 5     A2 GPU加压命令在os下执行加压命令发现功耗并没有变化分析一下

## Potential Rules

- 先在 OS 上补环境再测：`export LD_LIBRARY_PATH=/usr/local/Ascend/driver/lib64/driver:$LD_LIBRARY_PATH`
- 先用 `ascend-dmi -i` 验证工具恢复正常，再跑合法压测命令。

## Next Step

If these rules are stable and reusable, convert them into formal lessons with `record_lesson.py`.

## Source

- Session ID: `019cd700-95bd-7b00-91c5-8e377ca1fd4e`
- Source Note: `/mnt/e/obsidian/Codex Sessions/2026/03/2026-03-10-090745-bmcip-10-121-176-198-administrator-admin-9000-osip-10-121-177-165-root-qwer1234-ascend-dmi-p-it.md`
