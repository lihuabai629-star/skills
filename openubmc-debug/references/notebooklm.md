# NotebookLM 使用原则（openubmc-debug）

本文件承载 openUBMC 排障场景下的 NotebookLM 使用策略与“快速失败”规则。NotebookLM 的具体操作细节（登录、库管理、脚本用法等）以 `notebooklm-skill` 为准。

## 定位（What / Why）

- 目的：补齐背景/术语/流程/规范，帮助你更快选对现场采集手段（SSH DBus / Telnet 日志 / 本地代码定位）。
- 边界：NotebookLM 不替代现场证据。最终结论以日志/对象/代码为准。

## 使用策略（Conditional Doc-first + Fast-fail）

- 默认先判断：本地代码、现场证据、日志是否已经足以闭环；只有不足以解释架构、术语、流程、责任边界时再问 NotebookLM。
- 触发 `openubmc-debug` 不等于必须先问 NotebookLM；只有已经确认这是运行时排障问题，且本地代码/现场证据仍不足时才加载。
- 本地代码快路径可跳过：如果用户只有告警文案、SEL 字段、错误串、对象路径，且仓库代码能较快定位定义与触发逻辑，则不要为了“doc-first”先卡在 NotebookLM。
- 若本地 `env-access.md` 里对 `mdbctl`、`busctl` 的命令语义、对象模型背景、典型参数仍解释不够，可向 NotebookLM 补问“命令职责边界 / 典型命令形式 / 什么时候优先用哪个”，但这属于补背景，不应阻塞主路径。
- 若问题本质是编译失败、实现方案、代码 review、CSR/MDS/Redfish 修改：不要走 NotebookLM 背景问答，直接切 `openubmc-developer`。
- 信息不足再追问：当现场证据或概念有缺口时继续提问（而不是反复猜测）。
- 本地环境一次配置：每台机器第一次需要提供 NotebookLM URL 并加入库；之后用 notebook-id 直接问。
- 推荐默认笔记本：`openUBMC 架构设计与特性参考指南`（如果库里已添加）。

## 并行使用（Background lane）

- NotebookLM 是后台文档通道，不是主路径 gate。
- 需要它时，先发一个边界清晰的问题，然后立即继续本地代码检索、`preflight_remote.py`、`busctl_remote.py` 或 `collect_logs.py`。
- 不要等待 NotebookLM 返回才开始主路径；它返回后再把背景结论折回分析。
- 如果已经有 `SSH`、`Telnet`、本地代码 3 个终端，NotebookLM 放到可选第 4 个终端；没有第 4 个终端也可以单独起一个后台会话。
- NotebookLM 只负责术语、架构、流程补充，不负责替代日志、对象树、属性值和 SEL 触发证据。
- 典型适用问题：
  - `mdbctl` 和 `busctl` 的职责边界是什么
  - 某类 `busctl --user` / `mdbctl getprop` 命令在 openUBMC 里的推荐使用顺序是什么
  - 某个对象/接口/属性的命名习惯、上下文参数、模型归属是什么

## 预检（Precheck）

按 `notebooklm-skill` 使用 `run.py` 包装器先确认可用性：

```bash
python /root/.codex/skills/notebooklm-skill/scripts/run.py auth_manager.py status
python /root/.codex/skills/notebooklm-skill/scripts/run.py notebook_manager.py list
```

## 快速失败规则（必须执行）

- 若 `auth_manager.py status` 显示未认证或 `notebook_manager.py list` 失败：立即停止并提示用户登录/修复环境（不要卡住现场采集）。
- 若提问时 20s 内无法进入输入框（未出现 “Found input”）：视为登录/权限/页面异常，立刻中止并转入现场采集。
- 若已进入输入框但 90s 内无回答或返回“系统无法回答”：记录原因后跳过，结论中注明“NotebookLM 未就绪/未能返回”，稍后补问。
- 统一策略：仅重试 1 次；仍失败则进入现场采集。
- 不要把“skill 里提到 NotebookLM”理解成必须前置；会话里已多次出现 `ask_question.py` 超时，这类失败不能阻塞主路径。
- 不要等待 NotebookLM 返回再去跑本地代码、SSH 预检或 Telnet 日志抓取；这些步骤应与 NotebookLM 并行。

## 提问模板（建议）

把问题写成三段，便于 NotebookLM 给到可落地的信息：

- 背景：设备/模块/版本
- 现象：错误日志/告警/字段缺失（尽量带原始片段）
- 想要知道：相关字段/对象/接口的来源、更新时机或处理逻辑
