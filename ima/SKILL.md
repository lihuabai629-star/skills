---
name: ima-agent-skill
description: Use when querying ima.qq.com for public answers or private knowledge-base answers through browser automation, especially when persistent web login and knowledge-base selection are needed from Codex.
---

# IMA Skill

Control **ima.qq.com** through browser automation for public search and private knowledge-base retrieval.

## Tools

### ima_search
Asks IMA a question through the web app. Supports private knowledge-base mode via special tags.

- **query** (required): The search query. Prefix with `@个人知识库` or `@knowledge` to search your private knowledge base.
- **autoclose** (optional): Kept only for backward compatibility. Ignored in web mode.
- **show-browser** (optional): If supported by the caller, shows the browser for debugging.

**Implementation:**
```bash
/usr/bin/python3 /root/.codex/skills/ima/scripts/ima.py "{query}" --autoclose="{autoclose}"
```

## First-Time Setup

Always use the `run.py` wrapper for direct script calls:

```bash
python scripts/run.py auth_manager.py status
python scripts/run.py auth_manager.py setup
python scripts/run.py knowledge_manager.py list --refresh
python scripts/run.py ask_knowledge.py --question "你好"
```

The first visible login stores cookies in `data/browser_state/state.json`. Later headless runs reuse that state.
Knowledge-base discovery now goes directly through `https://ima.qq.com/wikis` and caches names in `data/knowledge_library.json`.

## Knowledge Base Workflow

```bash
# 1. Authenticate once
python scripts/run.py auth_manager.py setup

# 2. Discover and cache knowledge bases
python scripts/run.py knowledge_manager.py list --refresh

# 3. Activate one knowledge base
python scripts/run.py knowledge_manager.py activate --query "你的知识库名称"

# 4. Ask inside the active knowledge base
python scripts/run.py ask_knowledge.py --scope knowledge --question "帮我总结这份资料"
```

## Platform Notes

- This local copy no longer depends on the Windows/macOS desktop client CDP port.
- It uses Patchright plus a persistent browser profile, similar to the working `notebooklm-skill`.
- On first run, `run.py` creates `.venv/`, installs dependencies, and installs Chrome for Patchright.

## Examples

- **Public:** `clawdbot ima_search query="DeepSeek analysis"`
- **Private:** `clawdbot ima_search query="@knowledge project update"`
