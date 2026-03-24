# IMA Agent Skill

[中文](#chinese) | [English](#english)

---

<a id="chinese"></a>

# IMA Skill (中文版)

通过浏览器自动化控制腾讯 **ima.qq.com**，实现公开问答与私有知识库问答。本地实现参考 `notebooklm-skill`，使用独立 `.venv`、持久化浏览器 profile，以及一次可见登录后复用 cookies 的方式工作。

这个 skill 不绑定某一个特定 agent。只要你的 agent 运行环境满足下面几个条件，就可以复用这套能力：

- 能读取本地 `skills/ima` 目录
- 能执行本地 Python 脚本
- 能保留本机浏览器登录态和本地文件

换句话说，Codex、Clawdbot 只是示例接入方，不是唯一使用方式。

## ✨ 核心特性

- **🌐 纯 Web 方案**：不再依赖桌面客户端 CDP 端口。
- **🔐 持久化登录**：首次可见浏览器扫码登录，后续通过 `state.json` 复用认证状态。
- **📚 知识库缓存**：支持刷新、缓存并激活一个知识库。
- **🧭 兼容旧入口**：`scripts/ima.py` 仍接受普通 query，`@knowledge` / `@个人知识库` 前缀会自动切到私有知识库模式。

## 📦 环境要求

- **操作系统**：
  - macOS（上游原始方案）
  - WSL + Windows（本地已适配到 Windows 安装路径发现）
- **Python 3**
- **Patchright**：在 skill 自己的 `.venv` 中自动安装
- **Google Chrome**：`setup_environment.py` 会通过 Patchright 安装

```bash
python3 scripts/setup_environment.py
```

## ⚙️ 配置说明

当前 Web 版默认不再依赖手工填写 `knowledge_id`。知识库由 `knowledge_manager.py` 从网页端发现并缓存到：

```text
data/knowledge_library.json
```

认证状态保存在：

```text
data/browser_state/state.json
```

## 🎯 如何选择具体知识库

这个 skill 当前管理的是 **知识库**，不是 IMA 个人笔记接口里的“笔记本”。如果你的账号下有多个知识库，可以用下面两种方式指定目标：

### 方式一：一次性指定

适合单次问答时临时指定某个知识库：

```bash
python3 scripts/run.py ask_knowledge.py --scope knowledge --knowledge-query "openUBMC" --question "帮我总结这份资料"
```

这里的 `--knowledge-query` 支持：

- 精确名称匹配
- 唯一的部分名称匹配

### 方式二：先激活，再连续使用

适合连续在同一个知识库里多轮提问：

```bash
python3 scripts/run.py knowledge_manager.py activate --query "openUBMC"
python3 scripts/run.py ask_knowledge.py --scope knowledge --question "帮我总结这份资料"
python3 scripts/run.py ask_knowledge.py --scope knowledge --question "这个知识库更适合哪些角色使用？"
```

激活后，后续不再传 `--knowledge-query` 时，默认使用当前激活的知识库。

## 🚀 使用方法

### 派发给同事

如果要把这个 skill 发给别的同事，现在除了 `git clone`，也可以直接给对方一条安装命令。

#### 方式零：远程一键安装

同事不需要先 `git clone`，直接执行：

```bash
curl -fsSL https://raw.githubusercontent.com/lihuabai629-star/skills/main/install.sh | bash -s -- ima
```

如果机器没有 `curl`，也可以用：

```bash
wget -qO- https://raw.githubusercontent.com/lihuabai629-star/skills/main/install.sh | bash -s -- ima
```

这个命令会：

- 下载仓库级安装脚本
- 从 `lihuabai629-star/skills` 拉取 `ima`
- 安装到 `${CODEX_HOME:-$HOME/.codex}/skills/ima`
- 如果已有旧版本则自动备份

如果你的同事一次要装多个 skill，也可以这样：

```bash
curl -fsSL https://raw.githubusercontent.com/lihuabai629-star/skills/main/install.sh | bash -s -- ima ima-note
```

下面两种方式仍然可用。

#### 方式一：从 skills 仓库安装

```bash
git clone https://github.com/lihuabai629-star/skills.git
cd skills/ima
bash install.sh
```

#### 方式二：只分发 `ima/` 目录

如果你只把 `ima/` 目录打包发给同事，对方进入目录后同样执行：

```bash
bash install.sh
```

默认会安装到：

```bash
${CODEX_HOME:-$HOME/.codex}/skills/ima
```

如果目标位置已经有旧版 `ima`，安装脚本会先自动备份成：

```bash
ima.backup.<timestamp>
```

#### 同事安装后需要做什么

安装完成不代表已经可用。每个同事都还需要自己完成一次认证初始化：

```bash
python3 ~/.codex/skills/ima/scripts/run.py auth_manager.py setup
python3 ~/.codex/skills/ima/scripts/run.py knowledge_manager.py list --refresh
```

> [!warning]
> 不要把 `.venv/`、`data/`、`__pycache__/` 一起分发给同事，尤其不要分发 `data/browser_state/state.json`。每个人都应该使用自己的浏览器登录态。

### 命令行调用

**首次认证：**
```bash
python3 scripts/run.py auth_manager.py setup
```

**刷新知识库缓存：**
```bash
python3 scripts/run.py knowledge_manager.py list --refresh
```

**激活一个知识库：**
```bash
python3 scripts/run.py knowledge_manager.py activate --query "你的知识库名称"
```

**公开问答：**
```bash
python3 scripts/run.py ask_knowledge.py --question "DeepSeek V3 分析"
```

**私有知识库问答：**
```bash
python3 scripts/run.py ask_knowledge.py --scope knowledge --question "帮我总结这份资料"
```

**指定某个知识库问答：**
```bash
python3 scripts/run.py ask_knowledge.py --scope knowledge --knowledge-query "openUBMC" --question "帮我总结这份资料"
```

**兼容旧入口：**
```bash
python3 scripts/ima.py "@knowledge 年度报告分析"
python3 scripts/ima.py "全网搜索一下 DeepSeek V3"
```

### 集成到任意 Agent

只要你的 agent 支持读取 skill 目录，或者至少能调用本地脚本，就可以使用这套能力。

有两种集成方式：

#### 方式一：作为原生 skill 集成

把目录放到 agent 约定的 skills 路径，例如：

```bash
~/.codex/skills/ima
```

之后让 agent 在合适的任务中加载这个 skill。

#### 方式二：直接调用 CLI

即使 agent 没有“skill 系统”，也可以直接调用这些脚本：

```bash
python3 scripts/run.py knowledge_manager.py list --refresh
python3 scripts/run.py ask_knowledge.py --scope knowledge --knowledge-query "openUBMC" --question "帮我总结这份资料"
```

因此，这个项目本质上是一个“可被 agent 调用的本地知识库查询工具”，而不只是某个单一 agent 平台的插件。

安装到对应目录后，你可以直接对 Agent 说：

> "用 IMA 搜一下最新的 AI 新闻"
> "去个人知识库查一下关于 Project X 的会议纪要"
> "在 openUBMC 知识库里总结一下 PCIe 加载流程"

如果你的 agent 支持把自然语言参数转成命令参数，推荐显式说出知识库名称。

## 🛠️ 工作原理

1.  `run.py` 负责创建 `.venv` 并安装依赖。
2.  `auth_manager.py` 用可见浏览器完成一次扫码登录，并导出 `state.json`。
3.  `knowledge_manager.py` 直接访问 `https://ima.qq.com/wikis` 发现知识库名称并缓存。
4.  `ask_knowledge.py` 通过网页编辑器提交问题并抓取返回内容。

## ⚠️ 当前已知限制

- 私有知识库页面的 DOM 结构比首页更动态，首次适配时可能需要根据你的账号页面再微调选择器。
- 首次认证必须用可见浏览器完成，纯 headless 不能扫码。
- `state.json` 依赖真实 Chrome；如果误退回到 bundled Chromium，`ima.qq.com` 会跳转到浏览器升级页。
- `scripts/ima.py` 的 `@knowledge` 兼容入口默认使用“当前激活的知识库”；如果要临时切换到别的知识库，优先使用 `--knowledge-query` 或先执行 `activate`。

---

<a id="english"></a>

# IMA Skill (English)

Control **ima.qq.com** via browser automation for public answers and private knowledge-base answers. This implementation follows the same persistent-browser approach that works for `notebooklm-skill`.

This skill is agent-agnostic. Any local agent runtime can reuse it as long as it can:

- read a local `skills/ima` directory
- execute local Python scripts
- persist browser auth state and local files

Codex and Clawdbot are only example integrations, not hard requirements.

## ✨ Features

- **🌐 Web-first**: No dependency on the desktop client's CDP port.
- **🔐 Persistent auth**: One visible login stores cookies for later headless reuse.
- **📚 Knowledge cache**: Refresh, cache, and activate a knowledge base before asking.
- **♻️ Backward-compatible entrypoint**: `scripts/ima.py` still accepts plain queries and `@knowledge` prefixes.

## 📦 Requirements

- **Python 3**
- **Patchright** in the skill-local `.venv`
- **Google Chrome** installed through Patchright

```bash
python3 scripts/setup_environment.py
```

## ⚙️ Configuration

The Web version no longer depends on a manually configured `knowledge_id`. It discovers knowledge bases from the site and stores them in `data/knowledge_library.json`. Authentication state is stored in `data/browser_state/state.json`.

## 🎯 How to choose a specific knowledge base

This skill targets **knowledge bases**, not the personal note notebooks exposed by the separate note API. If your account can access multiple knowledge bases, pick one in either of these ways.

### Option 1: select it for a single question

```bash
python3 scripts/run.py ask_knowledge.py --scope knowledge --knowledge-query "openUBMC" --question "Summarize this material"
```

`--knowledge-query` supports:

- exact name matches
- unique partial-name matches

### Option 2: activate one, then reuse it

```bash
python3 scripts/run.py knowledge_manager.py activate --query "openUBMC"
python3 scripts/run.py ask_knowledge.py --scope knowledge --question "Summarize this material"
python3 scripts/run.py ask_knowledge.py --scope knowledge --question "Who is this knowledge base for?"
```

Once activated, later knowledge-mode calls reuse the active knowledge base unless you override it with `--knowledge-query`.

## 🚀 Usage

### Install

Install directly from the repository without cloning it first:

```bash
curl -fsSL https://raw.githubusercontent.com/lihuabai629-star/skills/main/install.sh | bash -s -- ima
```

Or with `wget`:

```bash
wget -qO- https://raw.githubusercontent.com/lihuabai629-star/skills/main/install.sh | bash -s -- ima
```

This installs the skill into `${CODEX_HOME:-$HOME/.codex}/skills/ima` and backs up an existing install automatically.

### Command Line

**Authenticate once:**
```bash
python3 scripts/run.py auth_manager.py setup
```

**Refresh knowledge-base cache:**
```bash
python3 scripts/run.py knowledge_manager.py list --refresh
```

**Activate a knowledge base:**
```bash
python3 scripts/run.py knowledge_manager.py activate --query "Your Knowledge Base Name"
```

**Public question:**
```bash
python3 scripts/run.py ask_knowledge.py --question "Analysis of DeepSeek V3"
```

**Private knowledge-base question:**
```bash
python3 scripts/run.py ask_knowledge.py --scope knowledge --question "Summarize this material"
```

**Question a specific knowledge base:**
```bash
python3 scripts/run.py ask_knowledge.py --scope knowledge --knowledge-query "openUBMC" --question "Summarize this material"
```

**Legacy-compatible entrypoint:**
```bash
python3 scripts/ima.py "@knowledge Annual Report Analysis"
```

### Agent Integration

Any agent can use this project in one of two ways.

#### Option 1: native skill integration

Place the directory in the agent's skill path, for example:

```bash
~/.codex/skills/ima
```

Then let the agent load and use the skill in normal task routing.

#### Option 2: direct CLI integration

Even if your agent platform does not have a skill system, it can still call the scripts directly:

```bash
python3 scripts/run.py knowledge_manager.py list --refresh
python3 scripts/run.py ask_knowledge.py --scope knowledge --knowledge-query "openUBMC" --question "Summarize this material"
```

So this repository is better understood as a local knowledge-base automation tool that agents can call, not as a plugin tied to one agent platform.

Once installed, you can ask your agent:

> "Use IMA to search for the latest AI news"
> "Check my personal knowledge base for the meeting minutes about Project X"
> "Summarize the PCIe loading flow from the openUBMC knowledge base"

## 🛠️ How it Works

1.  `run.py` creates `.venv` and installs dependencies.
2.  `auth_manager.py` performs a one-time visible login and exports `state.json`.
3.  `knowledge_manager.py` goes directly to `https://ima.qq.com/wikis` to discover and cache knowledge-base names.
4.  `ask_knowledge.py` submits prompts through the web editor and extracts the response.

## ⚠️ Known Limitation

- Private knowledge-base DOM can still need selector tuning depending on your account's actual page shape.
- First authentication must be done with a visible browser.
- If automation falls back to bundled Chromium instead of full Chrome, `ima.qq.com` may redirect to the browser-upgrade page.
- The legacy `scripts/ima.py` `@knowledge` entrypoint uses the currently active knowledge base by default. For one-off targeting, prefer `--knowledge-query` or run `activate` first.

## License

MIT
