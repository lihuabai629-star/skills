# Session Note Schema

## Frontmatter
- `title`: human-friendly session title
- `session_id`: Codex session id from rollout `session_meta`
- `created`: first known timestamp for the session
- `updated`: latest known timestamp or thread update time
- `cwd`: session working directory
- `source_rollout`: rollout JSONL path
- `model`: model name when present
- `approval_policy`: Codex approval mode
- `sandbox_policy`: Codex sandbox mode
- `git_branch`: optional thread metadata
- `git_origin_url`: optional thread metadata
- `aliases`: include the raw session id
- `tags`: at least `codex/session` and `codex/exported`

## Body Sections
- `# <title>`
- metadata callout
- `## Request`
- `## Outcome`
- `## Conversation Timeline`
  - assistant timeline entries may include an `Immediate Commands` block showing the concrete terminal commands that followed that message before the next message
- `## Tool Activity`
  - when a tool call is `exec_command` or `write_stdin`, render a terminal-oriented summary first and omit redundant argument keys that are already visible in that summary

## Export Rules
- Keep the note readable; preview tool output instead of dumping everything, and strip tool-wrapper noise such as `Chunk ID`, `Wall time`, and `Process exited` when a cleaner terminal preview is available
- Prefer readable terminal records such as command, workdir, session id, and input preview over raw tool JSON alone
- For `exec_command` and `write_stdin`, only show leftover arguments after removing duplicate terminal-summary fields; keep the full raw arguments in the JSON artifact
- Preserve full parsed data in the JSON artifact
- Prefer stable date-based paths so old links do not churn
