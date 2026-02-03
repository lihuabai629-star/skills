---
name: openubmc-debug
description: openUBMC 排障与适配分析。用于用户提供 BMC IP、要求查看 app.log/framework.log（telnet 日志）、或需要 busctl/mdbctl(DBus) 对象查询时；需要结合本地代码 + 环境日志/对象给出分析结论，并在用户指令后再修改代码。关键词：openUBMC, busctl, mdbctl, DBUS, app.log, framework.log, telnet, ssh, bmc.kepler。
---

# openubmc-debug

## 概述 (Overview)
先用 **NotebookLM 查文档** 获得背景/术语/流程，再用 **SSH 做对象查询**（busctl/mdbctl）与 **Telnet 看日志** 验证；信息不足时再追问 NotebookLM。默认账号密码：SSH `Administrator / Admin@9000`（优先使用 Windows OpenSSH），Telnet 如提示登录则使用 `Administrator / Admin@9000`。本地代码目录：`/home/workspace/source/`。

> 先分析，后改代码。未得到用户明确指令前不要改代码。

## NotebookLM 使用原则
- **默认先问**：用户描述问题后，先向 NotebookLM 提问获取架构/术语/流程/规范背景。
- **信息不足再追问**：现场证据或概念缺口时继续提问。
- **本地环境一次配置**：每台机器第一次需要提供 NotebookLM URL 并加入库；之后用 notebook-id 直接问，不再重复询问。
  - 参考默认笔记本：`openUBMC 架构设计与特性参考指南`（如果库里已添加）。
- **必须尝试，但允许快速失败**：
  - 若 `auth_manager.py status` 显示未认证或 `notebook_manager.py list` 失败，立即停止并提示用户登录/修复环境（不要卡住现场采集）。
  - 若提问时 20s 内无法进入输入框（未出现 “Found input”），视为登录/权限/页面异常，立刻中止并转入现场采集。
  - 若已进入输入框但 90s 内无回答或返回“系统无法回答”，记录原因后跳过，结论中注明“NotebookLM 未就绪/未能返回”，稍后补问。
  - 统一策略：仅重试 1 次；仍失败则进入现场采集。
  - 提问模板（建议）：
    - 背景：设备/模块/版本
    - 现象：错误日志/告警/字段缺失
    - 想要知道：相关字段/对象/接口的来源、更新时机或处理逻辑

## 推荐流程 (Workflow)

### 1) 确认输入 (Inputs)
- 必选：问题描述 + 环境 IP
- 可选：组件/服务名、关键词、时间范围（最近一次启动/历史日志）
最小输入集（用于减少反复追问）:
- 必填：问题现象 + 环境 IP + 复现时间点（或“最近一次重启后”）
- 选填：组件/服务名、固件版本、已有日志片段

### 2) 预检 (Precheck)
- NotebookLM 可用性：先跑 `auth_manager.py status` 与 `notebook_manager.py list`（按 notebooklm skill 使用 `run.py` 包装器）
  - 未认证需提示用户浏览器登录（见 notebooklm skill）
  - 预检命令（可直接复制）：
    ```
    python /root/.codex/skills/notebooklm-skill/scripts/run.py auth_manager.py status
    python /root/.codex/skills/notebooklm-skill/scripts/run.py notebook_manager.py list
    ```
- SSH/Telnet 连通性与权限是否允许
- 连通性快检（可选）：
  - `ssh -o ConnectTimeout=5 Administrator@<ip> exit`
  - `telnet <ip> 23`（应看到提示符；若提示登录说明非免登录）
- 脚本依赖：`sshpass` 是否存在（仅脚本化 SSH 需要）

### 2.1) 常见失败分支处理 (Failure Branches)
- NotebookLM 不可用：记录原因 → 转入现场采集 → 结论中标注“未就绪/未返回”
- SSH 失败：确认网络/账号 → 尝试 `telnet` 或请求用户提供日志片段
- Telnet 失败：请求用户提供日志/时间戳 → 优先用本地代码定位缩小范围
- DBUS 变量缺失：改用 `busctl list`/`mdbctl lsclass` 或请求用户提供环境变量

### 3) NotebookLM 预查询 (Doc-first)
- 基于用户问题先问 NotebookLM，拿到架构/术语/流程/规范要点。
- 若未配置 NotebookLM 库，先添加 notebook URL 并设置为默认后再问。
- 若触发“快速失败”或超时，记录原因后进入现场采集，待证据齐全再补问。

### 4) 本地代码定位 (Local code search)
- 在 `/home/workspace/source/` 使用 `rg` 搜索关键词/错误串
- 识别涉及组件（如 `hwproxy` / `general_hardware` / `hwdiscovery` / `pcie` / `gpu`）
- 组件职责可参考 `references/components.md`

### 5) SSH 对象查询 (busctl/mdbctl)
- **SSH 仅做对象/DBus 查询**，不要读 `/var/log`
- 工具选择：对象/属性一致性优先 `mdbctl`；接口/方法/信号优先 `busctl`
- `busctl --user tree <service>` 输出很多，需要等待完整输出
- DBUS/XDG 变量以 **当前交互 SSH** 的 `printenv` 为准
- 细节见 `references/env-access.md`
  - 无参方法调用时，用 `--signature ''`（空签名）

### 6) Telnet 日志分析 (app.log / framework.log)
- 使用 Telnet 读 `/var/log`，包含 `.gz` 轮转
- 推荐用 `scripts/collect_logs.py` 统一抓取
- 如果用户说“最近一次启动”，使用 `--since-boot`
- 轮转日志可能很大，`--include-rotated` 建议搭配 `--rotated-limit`（默认 3）

### 7) 信息不足再问 NotebookLM
- 现场证据缺口、术语不一致、流程不清晰时，继续向 NotebookLM 追问补全。

### 8) 输出分析结论 (Analysis)
输出结构建议：
- 现象总结
- 证据日志（时间戳）与证据块（命令 + 原始输出）
- 环境快照（BMC 时间/uptime/固件版本，输出中展示）
- NotebookLM 要点（作为背景/规范）
- 可能涉及组件 + 代码路径
- 初步结论 + 下一步验证建议
- 等待用户指令再改代码

证据块格式建议：
```
命令：<ssh/telnet/busctl/mdbctl>
输出：<关键行，带时间戳>
```

## 资源 (Resources)

### scripts/
- `collect_logs.py`：Telnet 拉日志（过滤关键字/按启动时间/包含轮转，支持 `--rotated-limit`）
- `busctl_remote.py`：SSH 自动读取 DBUS/XDG 并执行 `busctl --user`

### references/
- `env-access.md`：SSH/Telnet、busctl/mdbctl、DBUS/XDG 变量
- `logs.md`：日志路径与轮转
- `components.md`：仓库顶层组件职责速览
- `overview.md`：skill 使用概览与输出要点
- `context7.md`：Context7 openUBMC 文档入口

## 备注 (Notes)
- 信息不足时可用 Context7 查询官方文档（见 `references/context7.md`）
- 服务名未知时先 `busctl list` 或 `mdbctl lsclass`
- 输出中保留命令，方便复现
- Scripts 为纯 Python，可复用到其他 AI 工具
- 完整命令示例见 `references/env-access.md` 与 `references/logs.md`
