---
name: openubmc-log-analyzer
description: Use when diagnosing openUBMC/BMC issues from a one-click log bundle (.tar/.tar.gz) or log directory, especially when the user provides a log path plus a problem statement and expects you to unpack, select relevant logs, and analyze them without repeatedly querying NotebookLM.
---

# OpenUBMC Log Analyzer

## Overview
This skill analyzes openUBMC one-click log bundles by selecting logs based on the user’s problem statement, using a local log reference cache, and only querying NotebookLM for unknown log types.

## Workflow (Problem-Driven)

1. Collect inputs. Required: log bundle path or directory path plus the problem statement. Optional: time range, component name, or known keywords.
2. Unpack and inventory. If a `.tar` or `.tar.gz` is provided, extract into a temp directory. List log files and directories; focus on `dump_info/LogDump`, `dump_info/AppDump`, `dump_info/RTOSDump`.
3. Select logs based on the question. Load `references/logs.json` and apply keyword rules first. If matches are empty or too few, use rule fallback (topic → log files). Do NOT default to “priority logs” if they are unrelated to the question.
4. Analyze selected logs. Extract errors/warnings and timestamps. Correlate with `app.log` and `framework.log` only when the question implies component or service failures. For data-not-updating or object-missing issues, use AppDump logs (`mdb_info.log`, `sync_property_trace.log`, `rpc_records.log`).
5. Synthesize findings. Output: problem summary, evidence blocks (command + lines), likely cause, and next verification steps.
6. Only query NotebookLM for unknowns. If a log file is unknown or missing in `logs.md/logs.json`, query NotebookLM once. Append the result to `references/logs.md` and `references/logs.json` so future runs don’t query again.

## Quick Reference (Table)

| Task | File |
| --- | --- |
| Log meanings | `references/logs.md` |
| Keyword mapping | `references/logs.json` |
| Core directories | `dump_info/LogDump`, `dump_info/AppDump`, `dump_info/RTOSDump` |

## Example (Single Bundle)

User: “BMC 登录失败，日志在 `/path/openUBMC_20260204-0112.tar`。”

Process:
- Extract bundle → inventory files.
- From `logs.json` match keywords: login/auth → `security.log`, `operation.log`.
- Scan those files for failure timestamps and reasons.
- If additional system issues are suspected, consult `framework.log` and `journalctl.log`.

## Rationalization Table

| Excuse | Reality |
| --- | --- |
| “Start with app.log/framework.log anyway” | Use question-driven selection; unrelated logs waste time. |
| “Query NotebookLM for every file just in case” | Only query for unknowns; cache results locally. |

## Red Flags

- Defaulting to unrelated “priority logs”.
- Querying NotebookLM repeatedly for known log types.
- Skipping `logs.json` mapping.

## Common Mistakes

- Ignoring the problem statement and scanning the entire bundle.
- Failing to update `logs.md/logs.json` after discovering a new log type.
- Mixing unrelated time ranges without stating assumptions.

## Resources

### references/
- `references/logs.md` – human-readable log meanings and usage.
- `references/logs.json` – keyword rules for mapping problems to logs.
