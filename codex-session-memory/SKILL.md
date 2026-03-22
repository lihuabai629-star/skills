---
name: codex-session-memory
description: "Use when the user wants to save Codex conversations, export native Codex sessions into Obsidian notes, sync archived sessions, search prior lessons, or capture reusable debugging and workflow rules from a session for future recall."
---

# codex-session-memory

## Overview
Use native Codex session files under `~/.codex/` as the source of truth. Export conversations into Obsidian notes, keep a machine-readable artifact/manifest for incremental sync, and capture reusable lessons into three scopes: `global`, `project`, and `domain`.

## Quick Start
- Export the latest completed session:
  - `python /root/.codex/skills/codex-session-memory/scripts/export_sessions.py --latest`
- Backfill all missing sessions into Obsidian:
  - `python /root/.codex/skills/codex-session-memory/scripts/export_sessions.py --sync-all`
- Run the automation loop once:
  - `python /root/.codex/skills/codex-session-memory/scripts/auto_sync.py --once --json`
- Check whether the automation daemon is running:
  - `python /root/.codex/skills/codex-session-memory/scripts/auto_sync.py --status --json`
- Export one known rollout:
  - `python /root/.codex/skills/codex-session-memory/scripts/export_sessions.py --rollout /root/.codex/sessions/2026/03/17/rollout-....jsonl`
- Record a global Codex workflow lesson:
  - `python /root/.codex/skills/codex-session-memory/scripts/record_lesson.py --scope global --title "Write the failing test first" --problem "A bugfix was attempted before reproducing it." --rule "Write the failing test before touching production code." --keywords tdd bugfix regression`
- Record a project lesson:
  - `python /root/.codex/skills/codex-session-memory/scripts/record_lesson.py --scope project --cwd /home/workspace/source --title "Use /home/workspace/source as repo root" --problem "Commands ran from the wrong cwd." --rule "Treat /home/workspace/source as the default repo root." --keywords cwd workspace repo-root`
- Record a domain lesson:
  - `python /root/.codex/skills/codex-session-memory/scripts/record_lesson.py --scope domain --domain openubmc-debug --title "Prefer SSH for DBus object queries" --problem "Telnet was used for DBus inspection." --rule "Use SSH for busctl/mdbctl and reserve Telnet for logs." --keywords ssh telnet dbus busctl mdbctl`
- Recall lessons in default order `global -> project -> domain`:
  - `python /root/.codex/skills/codex-session-memory/scripts/find_lessons.py --scope auto --cwd /home/workspace/source --domain openubmc-debug --query "dbus telnet app.log"`

## Default Paths
- Codex source data: `/root/.codex/`
- Obsidian session archive: `/mnt/e/obsidian-codex-sessions-vault/`
- Per-session machine artifacts: `/mnt/e/obsidian-codex-sessions-vault/.codex-session-memory/artifacts/`
- Global lessons: `/root/.codex/memories/global/lessons/`
- Project lessons: `/root/.codex/memories/projects/<project-slug>/lessons/`
- Domain lessons for `openubmc-debug`: `/root/.codex/skills/openubmc-debug/references/lessons/`

## Workflow

### 1. Export Sessions
Use `scripts/export_sessions.py`.

Choose one of:
- `--latest`: export the most recent rollout
- `--sync-all`: import all rollouts and skip unchanged sessions using the manifest
- `--session-id <id>`: locate a rollout by Codex session id
- `--rollout <path>`: export a specific rollout file directly

Useful flags:
- `--out-dir <path>`: override the Obsidian vault destination
- `--codex-root <path>`: override the Codex state root
- `--force`: rewrite notes even if the manifest says nothing changed
- `--limit <n>`: cap how many rollouts `--sync-all` processes
- `--json`: print machine-readable results

The exporter:
- parses rollout JSONL for user messages, assistant messages, and tool activity
- enriches metadata from `state_*.sqlite` when available
- writes an Obsidian note per session
- writes a JSON artifact with the full parsed record
- updates `.codex-session-memory/manifest.json`
- rebuilds `Session Index.md`

For note layout and frontmatter fields, read `references/note-schema.md`.

### 2. Recall Lessons Before Repeating Work
If the task looks similar to something handled before, search the lesson store first instead of relying on memory.

Use:
- `python /root/.codex/skills/codex-session-memory/scripts/find_lessons.py --scope auto --cwd <project-root> --domain <skill-name> --query "<symptom keywords>"`

Scope behavior:
- `global`: Codex-wide workflow rules
- `project`: current repo/workspace conventions and shortcuts
- `domain`: skill-specific lessons such as `openubmc-debug`

Default recall order:
- `global`
- `project` when `cwd` is meaningful
- `domain` when provided

Good query inputs:
- a log signature
- an object path
- a service name
- an alarm or SEL phrase
- a workflow failure mode such as `wrong branch`, `timeout`, `ssh telnet dbus`

For lesson note structure and index fields, read `references/lesson-schema.md`.

### 3. Capture Lessons After Finishing
Create a lesson only when the rule is reusable across future sessions.

Good lessons:
- a routing rule
- a diagnostic shortcut
- a failure pattern with a reliable countermeasure
- a workflow guardrail that prevents repeated mistakes

Avoid storing:
- one-off incident details with no reusable rule
- raw chat transcripts
- vague advice with no trigger condition

Use:
- `python /root/.codex/skills/codex-session-memory/scripts/record_lesson.py --scope <global|project|domain> --cwd <project-root> --domain <skill-name> --title "<rule>" --problem "<what went wrong>" --rule "<what to do next time>" --evidence "<evidence shape>" --keywords key1 key2`

The recorder writes:
- a lesson note under the store
- `index.json` for machine lookup
- `INDEX.md` for human browsing in Obsidian or the repo

### 4. Use Automatic Mode
Use `scripts/auto_sync.py` when you want session export to happen without manual commands.

Modes:
- `--once`: one sync pass
- `--daemon`: long-running poller for new rollouts
- `--status`: inspect pid/running state
- `--stop`: stop the background daemon

The daemon also creates lesson **candidates** in `references/lessons/inbox/` for domains it can identify reliably enough. Candidates stay separate from the formal lesson index on purpose; review them before promoting them with `record_lesson.py`.
The daemon writes candidates into the appropriate `global`, `project`, and `domain` inboxes when it has enough evidence.

## Output Shape
- Session note:
  - date-based path under the vault
  - frontmatter with session id, timestamps, cwd, git info, tags
  - sections for request, outcome, conversation timeline, and tool activity
- Session artifact:
  - full parsed record in JSON
  - stable path keyed by session id
- Lesson note:
  - frontmatter with scope, optional domain/project metadata, keywords, source note, and session id
  - sections for trigger, rule, evidence, anti-pattern, and verification

## Common Mistakes
- Trying to rely on `history.jsonl` alone. Prefer rollout JSONL; it contains assistant messages and tool calls.
- Writing every discovered rule back into the skill body. Put reusable lessons into the lesson store.
- Writing every lesson into `domain` scope. Put cross-task workflow rules in `global`, repo-specific rules in `project`, and only specialized rules in `domain`.
- Exporting only the current session. Run `--sync-all` periodically so missed sessions are backfilled.
- Storing huge raw tool output in the Obsidian note. The note should stay readable; the JSON artifact keeps the full structure.
- Creating lessons without trigger keywords. Poor keywords make recall weak.

## Resources
### scripts/
- `session_memory.py`: parse rollouts, enrich metadata, render notes, and update the archive manifest
- `export_sessions.py`: CLI for latest, sync-all, session-id, and direct-rollout export
- `auto_sync.py`: background sync loop plus automatic lesson candidate inbox generation
- `lesson_memory.py`: lesson note model, indexing, and search
- `record_lesson.py`: CLI to persist one lesson
- `find_lessons.py`: CLI to search existing lessons

### references/
- `note-schema.md`: session note/frontmatter conventions
- `lesson-schema.md`: lesson note/index conventions
