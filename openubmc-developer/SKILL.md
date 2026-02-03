---
name: openubmc-developer
description: 面向 openUBMC 开发/实现需求的全流程技能，覆盖属性/MDS/MDB、Lua 业务逻辑、Redfish 映射、构建与测试。适用于用户提出实现需求且可提供 SSH/Telnet 环境 IP 进行验证的场景。默认先用 NotebookLM 获取架构上下文，完成后输出详细设计到 /mnt/e/obsidian/（Obsidian Markdown）。
---

# OpenUBMC Developer（开发流程）

## 概述
Doc-first：先 NotebookLM 查架构与术语，再用 SSH/Telnet 验证环境，最后实现代码并产出 Obsidian 详细设计。
先分析，后改代码；NotebookLM 采用快速失败策略，失败则转入本地/现场验证并在结论中说明。
要求最少打断用户，问题集中、清晰、可执行。
强调可复现：输出中保留关键命令与原始输出摘要。

## 流程（Doc-first → Verify → Plan → Develop → Confirm → Design）

### 1) 需求澄清
- 复述需求，确认目标与边界。
- 只问最少且必要的问题（组件/仓库/API/期望行为）。
- 确认环境 IP、访问方式与仓库路径。
- 若用户无法提供环境，明确说明验证能力受限。
完成标准：目标行为 + 影响范围 + 验证方式已明确。

澄清问题清单（按需问 2~4 个）:
- 目标模块/仓库路径？是否已有分支/变更基线？
- 期望行为/输入输出/边界条件？
- 关联接口（DBus/Redfish/CLI）与兼容性要求？
- 是否需要运行测试或仅提供补丁？

最小输入集（用于减少反复追问）:
- 必填：问题现象 + 环境 IP + 复现时间点（或“最近一次重启后”）
- 选填：组件/服务名、固件版本、已有日志片段

### 2) NotebookLM 上下文优先
- 在改代码前先用 NotebookLM 查询架构/术语/流程。
- 优先关注：模块架构、DBus/MDB/MDS 术语、Redfish 映射约定。
- 后续若仍有空白再补查。
- 若 NotebookLM 不可用，则使用本地仓库文档并说明局限。
- 预检（按 notebooklm skill 使用 `run.py` 包装器）：
  ```
  python /root/.codex/skills/notebooklm-skill/scripts/run.py auth_manager.py status
  python /root/.codex/skills/notebooklm-skill/scripts/run.py notebook_manager.py list
  ```
- 快速失败：20s 内无法进入输入框或 90s 内无回答，仅重试 1 次；仍失败则记录原因并转入现场验证。
完成标准：已获得关键术语/流程要点，或记录失败原因并转入现场验证。

### 3) 环境验证（SSH/Telnet）
- SSH 仅用于对象/DBus 查询与服务路径核对；Telnet 用于日志。
- 修改前确认仓库路径，避免与环境不一致。
- 默认凭据：SSH `Administrator / Admin@9000`，Telnet 无密码（如用户未另行提供）。
- 记录精确的 DBus 对象路径、接口与属性。
- 需要日志/DBus 细节时优先使用本技能脚本：
  - `/root/.codex/skills/openubmc-developer/scripts/collect_logs.py` / `/root/.codex/skills/openubmc-developer/scripts/busctl_remote.py`
- 相关环境/日志细节参考本技能文档：
  - `references/env-access.md` / `references/logs.md`
- 环境连通性快检（可选）：
  - `ssh -o ConnectTimeout=5 Administrator@<ip> exit`
  - `telnet <ip> 23`
常见失败分支处理:
- NotebookLM 不可用：记录原因 → 转入现场采集 → 结论标注“未就绪/未返回”
- SSH 失败：确认网络/账号 → 尝试 `telnet` 或请求用户提供日志片段
- Telnet 失败：请求用户提供日志/时间戳 → 先做本地代码定位
- DBUS 变量缺失：改用 `busctl list`/`mdbctl lsclass` 或请求用户提供环境变量
完成标准：拿到关键对象/属性/日志证据，或明确说明无法获取的原因。

### 4) 本地代码定位
- 在 `/home/workspace/source/` 使用 `rg` 搜索关键字/错误串/对象路径。
- 结合现有模块目录判断影响面，缩小修改范围。
- 组件职责可参考 `references/components.md`。

### 5) 代码影响面梳理
- 确定属性与业务逻辑的落点：
  - **Properties/DBus model**: `mdb_interface` (MDS, schema, interfaces).
  - **Lua business logic**: commonly `general_hardware/` (or module-specific repo).
  - **Northbound mapping**: `rackmount/` for Redfish/CLI mappings.
  - **Platform data**: `manifest/`, `profile_schema/`, `vpd/` as needed.
- 影响面三问：
  - 是否涉及 MDS/MDB 变更（需生成代码）？
  - 是否影响北向接口行为（Redfish/CLI/SNMP）？
  - 是否涉及持久化/配置导入导出（profile_schema/manifest）？
- 修改前阅读 `/home/workspace/source/AGENTS.md`。
- 维护一份精简的“文件清单 + 修改原因”。
Plan 模板（确认前输出）：
- 文件清单：
- 变更点：
- 生成/构建：
- 验证与回滚：

### 6) 方案确认
- 给出具体方案（涉及文件、新增属性、流程、测试）。
- 变更 schema 或北向行为时，必须写回滚/兼容说明。
- 未经用户确认，不进行代码修改。
确认点清单（最少三项）：
- 目标行为与边界
- 影响范围与兼容性
- 测试/验证方式与回滚
完成标准：用户明确允许修改/测试并确认关键影响面。

### 7) 开发与验证
- 实施修改；如涉及 MDS 变更需重新生成代码（禁止手改 `gen/`）。
- 构建/测试：`make -C <module>` 或 `cmake`，必要时 `bingo gen/build/test`。
- 如需，验证 DBus 路径与北向 API 映射。
- 若跳过测试，必须说明原因并给出手工验证清单。
完成标准：至少完成一项验证，或明确说明跳过原因与替代手工验证。
最小验证清单（可选模板）：
- DBus 路径/属性读取正常
- 北向接口调用返回符合预期
- 关键日志无新增错误

### 8) 详细设计笔记（Obsidian）
- 用户确认实现正确后，输出详细设计到 `/mnt/e/obsidian/`。
- 使用 Obsidian Markdown（wikilinks、callouts、frontmatter）。
- 若流程复杂，可补 `.canvas` 图。
最小笔记模板：
- 需求与背景
- 关键接口（DBus/Redfish）
- 变更点（文件/属性/流程）
- 测试与验证
- 回滚与兼容性

## 输出结构
- 现象/需求摘要
- 证据与环境快照（关键命令 + 原始输出摘要）
- 上下文摘要（NotebookLM 结论 + 现场验证）
- 实施方案（文件、属性、流程）
- 等待用户确认的问题
- 确认后：开发摘要 + 测试状态 + Obsidian 笔记路径

证据块格式建议：
```
命令：<ssh/telnet/busctl/mdbctl>
输出：<关键行，带时间戳>
```

## 注意事项
- 生成代码禁止手改，必须通过生成器更新。
- 未经用户明确确认，不得修改 schema 或北向行为。
- 变更应最小化、可回滚，并与目标平台 profile 保持一致。

## Obsidian 笔记要求
- 设计笔记直接保存到 `/mnt/e/obsidian/`。
- 标题清晰、与功能名一致（如 `SwitchMode-Design.md`）。

## 资源/参考
- `references/components.md`：仓库顶层组件职责速览
- `references/overview.md`：skill 使用概览与流程速览
- `references/env-access.md`：SSH/Telnet 与 DBus 环境变量
- `references/logs.md`：日志路径与轮转
- `references/context7.md`：Context7 openUBMC 文档入口
