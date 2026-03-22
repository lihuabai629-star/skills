# Lesson Schema

## Store Files
- `INDEX.md`: human-readable table of lessons
- `index.json`: machine-readable list used by `find_lessons.py`
- `YYYY-MM-DD-<slug>.md`: one note per lesson
- `inbox/INBOX.md`: candidate lesson queue generated automatically

Canonical lesson identity:
- One formal lesson per canonical `lesson_id`
- Re-promoting the same normalized rule updates the existing lesson instead of creating a new note
- Conflicting rules with the same normalized trigger stay as separate notes and are marked with `conflict_status: conflict`

## Memory Scopes
- `global`: `/root/.codex/memories/global/lessons/`
- `project`: `/root/.codex/memories/projects/<project-slug>/lessons/`
- `domain`: `/root/.codex/skills/<domain>/references/lessons/`

Default recall order:
1. `global`
2. `project`
3. `domain`

## Lesson Frontmatter
- `title`
- `scope`
- `domain`
- `lesson_id`
- `rule_key`
- `trigger_key`
- `project_root`
- `project_slug`
- `created`
- `updated`
- `keywords`
- `applies_when`
- `session_id`
- `source_note`
- `source_sessions`
- `source_notes`
- `evidence_history`
- `merge_count`
- `conflict_status`
- `tags`

## Lesson Body
- `# <title>`
- `## Trigger`
- `## Rule`
- `## Evidence`
- `## Anti-Pattern`
- `## Verification`
- `## Source`

`## Source` should expose:
- canonical `lesson_id`
- `merge_count`
- `conflict_status`
- latest `session_id`
- latest `source_note`
- accumulated `source_sessions`
- accumulated `source_notes`

## Writing Rules
- One reusable lesson per note
- Include concrete trigger keywords
- State the action rule explicitly
- Capture the anti-pattern that caused the mistake
- Include the quickest verification step for next time
- Choose scope deliberately:
  - use `global` for Codex-wide workflow rules
  - use `project` for repository/workspace-specific rules
  - use `domain` for skill-specific rules

## Merge Rules
- Canonical identity is `scope + domain + project_slug + normalized_rule_key`
- Merge duplicate promotions into the same note
- Union keywords, source sessions, source notes, and evidence history
- Prefer richer text when later promotions add more detailed trigger/problem/rule/verification wording
- Keep the original note path stable when a lesson merges

## Conflict Rules
- Detect conflicts when normalized triggers match but normalized rule keys differ
- Mark both the existing lesson and the new lesson with `conflict_status: conflict`
- Keep both notes visible in `INDEX.md`, `index.json`, and `find_lessons.py` output so the conflict can be resolved deliberately

## Index Expectations
- `index.json` entries include canonical metadata plus `merge_count`, `conflict_status`, `source_sessions`, and `source_notes`
- `INDEX.md` shows `Updated`, `Scope`, `Merge`, `Conflict`, `Title`, `Keywords`, and `Note`
- `find_lessons.py` plain-text output should surface `merge`, `conflict`, and source count for each hit
