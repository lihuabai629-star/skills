---
name: openubmc-debug
description: Use when diagnosing openUBMC runtime issues from a BMC IP, DBus object/path query, app.log/framework.log content, or concrete SEL/alarm text tied to live behavior. Not for build failures, feature implementation, CSR/MDS design, or generic repository/code review.
---

# openubmc-debug

## 概述 (Overview)
优先选择能最快闭环的问题路径，而不是固定先跑所有采集手段。

- 只有告警、SEL、字段、错误串含义：先走本地代码快路径
- 有 BMC IP 且需要现场状态：SSH 查 DBus，Telnet 查日志
- 只有日志包或日志目录：先用 `openubmc-log-analyzer`
- 构建失败、代码实现、CSR/MDS/Redfish 设计、仓库静态分析：不要用本 skill，改用 `openubmc-developer`

> 先分析，后改代码。未得到用户明确指令前不要改代码。

NotebookLM 和 Context7 只用于补架构、术语、流程背景；本地代码或现场证据足以闭环时，不要因 NotebookLM 卡住而阻塞分析。不要等待 NotebookLM 返回再开始本地代码检索、`preflight_remote.py` 或 `collect_logs.py`。NotebookLM 的操作细节与快速失败规则见 `references/notebooklm.md`。

## 技能分流 (Routing)
- 只有 BMC IP、需要 SSH 或 Telnet 现场采集：用 `openubmc-debug`
- 只有日志包或日志目录：用 `openubmc-log-analyzer`
- 日志包 + BMC IP：先 `openubmc-log-analyzer` 缩小范围，再用 `openubmc-debug` 补现场证据
- 只有告警文案、SEL 字段、关键词、对象路径，没有 IP 和日志：仍可用 `openubmc-debug`，直接走本地代码快路径
- 编译报错、实现需求、接口映射、CSR/MDS 修改、代码 review：用 `openubmc-developer`

## Quickstart（最短路径）
- 最小输入：问题现象 + 下列任一项
  - BMC IP
  - 日志包或日志目录
  - 告警、SEL 文案、对象路径、错误串、关键词
- 选填：复现时间点、最近一次启动、组件或服务名、固件版本、已有日志片段
- 本地代码快检：`rg -n "<keyword>" /home/workspace/source/`
- 连通性快检：`ssh -o ConnectTimeout=5 Administrator@<ip> exit`；`telnet <ip> 23`
- 远端预检：`python scripts/preflight_remote.py --ip <ip>`；需要机器可读结果时加 `--json`；脚本内部会并行跑独立的 SSH/Telnet 检查
- 需要把本地、SSH、Telnet、NotebookLM 一次拆成并行 lane 时：`python scripts/triage_parallel.py --ip <ip> --keyword <keyword>`
- 远端对象查询：默认先试 `python scripts/mdbctl_remote.py --ip <ip> lsclass`
- 需要原始 D-Bus、精确接口签名、`monitor` 或机器可读对象树时，再用 `python scripts/busctl_remote.py --ip <ip> --action tree --service <service> --json`
- 远端 `mdbctl` / 日志抓取：需要机器可读结果时，分别用 `python scripts/mdbctl_remote.py --ip <ip> --json <command>` 和 `python scripts/collect_logs.py --ip <ip> --json ...`
- 机器可读输出统一优先读：`schema_version`、`tool`、`request`、`result`、`warnings`
- 非默认端口或不想在命令行明文带账号密码时，优先用 `--ssh-port` / `--telnet-port` 和 `--*-user-env` / `--*-password-env`
- 需要保留原始 SSH/Telnet 证据时，给相关脚本加 `--debug-dump <dir>`；目录里会带脱敏后的原始产物和 `summary.json`
- 采证据：DBus 见 `references/env-access.md`；日志见 `references/logs.md`；组件职责见 `references/components.md`

## 经验回忆（Lessons recall）
- 开始前先用告警文案、对象路径、service 名、日志关键词或错误串查已有 lessons：
  - `python /root/.codex/skills/codex-session-memory/scripts/find_lessons.py --scope auto --cwd /home/workspace/source --domain openubmc-debug --query "<keyword or symptom>" --limit 5`
- 这条命令默认会按 `global -> project -> domain` 三层回忆：
  - `global`：Codex 通用工作流经验
  - `project`：当前仓库经验
  - `domain`：`openubmc-debug` 专项经验
- 命中后只读取最相关的 `1-3` 条，不要整目录全读
- lessons 只用来提醒分流、捷径和 anti-pattern；不能替代现场证据、本地代码或日志
- 如果这次排障总结出了可复用规则，结束后写回 lesson store，而不是继续堆进 `SKILL.md`

## SSH vs Telnet（先判断这个）

| 你要拿什么证据 | 首选 | 不要先用什么 | 原因 |
|------|------|------|------|
| DBus 对象、属性、接口、方法、对象树、service 是否存在 | SSH | Telnet | `busctl` / `mdbctl` 查询属于对象面，SSH 更稳定、输出更适合复现 |
| `app.log`、`framework.log`、轮转 `.gz`、按时间 grep 日志 | Telnet | SSH | 本 skill 约定日志面统一走 Telnet，避免把 SSH 混成通用 shell |
| 告警/SEL 文案含义、字段来源、触发逻辑 | 本地代码快路径 | 先上环境 | 很多问题本地代码就能闭环，不需要现场连接 |
| 既要当前对象状态，又要对应错误日志 | SSH + Telnet | 只靠其中一种 | 这是“对象面 + 日志面”联合取证场景 |

硬规则：
- 问题里出现 `app.log`、`framework.log`、`/var/log`、`grep 某条日志`：先走 Telnet
- 问题里出现 `busctl`、`mdbctl`、`DBus`、对象路径、属性名、service 名：先走 SSH
- 问题里只有告警、SEL、错误串，没有要求现场状态：先走本地代码快路径
- 不要在 SSH 里读 `/var/log`
- 不要把 Telnet 当成 `busctl` / `mdbctl` 的默认入口

对象面入口短语统一按这一套：
- `mdbctl` 更适合 openUBMC 微组件对象调试。
- `busctl` 更适合原始 D-Bus 观察和精确调用。
- `mdbctl` 失败不代表对象面不可查，优先切 `busctl_remote.py`。

## 并行采证（3-terminal pattern）

推荐默认开 3 个终端，而不是在一个会话里来回切：

- 终端 1：本地代码面
  - `rg`、源码阅读、字段/告警/SEL 触发链路定位
- 终端 2：SSH 对象面
  - `preflight_remote.py`
  - `mdbctl_remote.py`
  - `busctl_remote.py`
- 终端 3：Telnet 日志面
  - `collect_logs.py`
  - 手工 `grep` / `tail` / `zcat`

适用：
- 需要把“当前对象状态”和“对应时间点日志”对上
- 需要边查代码边确认现场表现

限制：
- 不要并行执行会改状态的命令，如 `setprop`、控制类方法、模拟告警、上下电
- 不要同时开多个长时间 `monitor` / `tail -f` 会话把输出搅在一起
- 默认就是 `1 个本地 + 1 个 SSH + 1 个 Telnet`，不要一开始就开很多远端终端

如果不想手工分配命令，优先用：
- `python scripts/triage_parallel.py --ip <ip> --keyword <keyword>`
- 有 `tmux` 时可直接：`python scripts/triage_parallel.py --ip <ip> --keyword <keyword> --launch-tmux`
- 没有 `tmux` 时，脚本会退回为人工可执行的 lane 计划，不会卡死

需要 NotebookLM 时，加一个可选后台文档通道，而不是让主路径等待：
- 可选终端 4：NotebookLM 背景面
  - 只发一个有边界的问题
  - 发出后立即继续终端 1-3 的本地代码、`preflight_remote.py`、`busctl_remote.py`、`collect_logs.py`
  - NotebookLM 返回后再把背景信息折回结论，不要等待 NotebookLM 返回才开始采证

## 快速决策表 (Quick Reference)

| 场景 | 首选路径 | 必要证据 |
|------|----------|----------|
| 告警或 SEL 含义、字段来源、对象归属 | 本地代码快路径 | 文案、字段或关键词 |
| 需要确认当前对象、属性、服务状态 | SSH + `mdbctl_remote.py`/`busctl_remote.py` | BMC IP |
| 需要看 `app.log` 或 `framework.log` | Telnet 或日志包 | BMC IP 或日志目录 |
| 只有日志包、无现场权限 | `openubmc-log-analyzer` | 日志包或目录 |
| 构建失败、功能实现、SR/CSR/MDS/Redfish 设计 | `openubmc-developer` | 代码路径、报错日志或需求描述 |

## 推荐流程 (Workflow)

### 1) 确认输入 (Inputs)
- 必选：问题描述 + 任一证据种子（IP、日志路径、告警文案、关键词）
- 选填：时间范围、组件名、服务名、固件版本、最近一次启动、已有命令输出
- 如果用户只有一句告警文案，不要先追问 IP；先判断本地代码能否闭环

### 2) 回忆已有 lessons (Recall)
- 用最短的可复用 clue 组成 query：
  - 告警/SEL 文案
  - 对象路径、属性名、service 名
  - `app.log` / `framework.log` 错误串
  - `mdbctl` / `busctl` 失败形态
- 推荐命令：
  - `python /root/.codex/skills/codex-session-memory/scripts/find_lessons.py --scope auto --cwd /home/workspace/source --domain openubmc-debug --query "<clue>" --limit 5`
- 命中时优先吸收以下信息：
  - 上次是怎么分流的
  - 哪条命令最快闭环
  - 哪个 anti-pattern 要避免
- 没命中就直接继续，不要因为“先找历史经验”而阻塞现场分析

### 3) 选择路径 (Choose Path)
#### A. 本地代码快路径（Local-only fast path）
适用：
- 没有 IP 或没有日志
- 用户只问告警、SEL、DBus 对象、字段来源、错误串含义
- 预期能通过本地代码和样例日志解释触发条件

执行：
- 在 `/home/workspace/source/` 用 `rg` 搜索字符串、对象、字段
- 沿“定义 -> 触发逻辑 -> 样例测试或样例日志 -> 可能组件”串联证据
- 对告警或 SEL 优先按以下链路排查：
  - `文案或字段` -> `proto/datas.yaml` 或 MIB、接口映射
  - `SensorType`、`EventData`、`SelData` -> 生成 SEL 的代码
  - `样例 test`、`app.log` -> 字段含义、真实记录格式
- 给出“代码上精确触发条件”与“常见上游原因”，并明确还缺哪些现场证据才能指到具体器件

#### B. 现场采集路径（Live evidence path）
适用：
- 用户给了 BMC IP
- 需要确认当前 DBus 对象、属性、服务状态
- 需要现场日志、对象树、属性值、方法返回值

执行：
- 先做 SSH 和 Telnet 连通性快检
- 需要快速判断环境是否可查时，先跑：`python scripts/preflight_remote.py --ip <ip>`
- 先判定证据面：
  - 对象面：SSH
  - 日志面：Telnet
  - 两者都缺：SSH + Telnet
- SSH 只做 DBus 和对象查询，不读 `/var/log`
- 日志读取走 Telnet 或用户提供的日志目录
- 对象、属性一致性优先 `scripts/mdbctl_remote.py`；接口、方法、信号优先 `scripts/busctl_remote.py`
- 细节与默认登录方式见 `references/env-access.md`

#### C. 文档补充路径（NotebookLM 或 Context7）
适用：
- 本地代码或现场证据不足以解释术语、架构边界、责任组件、流程规范
- 用户明确要求文档或架构解释

执行：
- 先按 `references/notebooklm.md` 做预检
- 把 NotebookLM 当成后台补充通道：发出问题后，继续本地代码定位或现场采集
- 只把 NotebookLM 当成背景来源，不替代代码、日志、对象证据

#### D. 不适用路径（Route away）
遇到以下场景，不要继续使用 `openubmc-debug`：
- 用户主要要的是实现方案、代码修改、编译报错分析、仓库设计评审
- 主要证据是源码、构建日志、MDS/CSR/Redfish 配置，而不是现场对象或运行时日志
- 用户没有要求现场采集，问题也不是告警/SEL/对象/日志语义

执行：
- 改用 `openubmc-developer`
- 若只有日志包而无现场权限，改用 `openubmc-log-analyzer`

### 4) 预检与快速失败 (Precheck / Fast-fail)
- NotebookLM 预检：
  - `python /root/.codex/skills/notebooklm-skill/scripts/run.py auth_manager.py status`
  - `python /root/.codex/skills/notebooklm-skill/scripts/run.py notebook_manager.py list`
- 快速失败规则：
  - 若本地代码已能在短路径内闭环，不要为了“doc-first”强行阻塞在 NotebookLM
  - 若需要 NotebookLM，先发起提问，再继续本地代码、`preflight_remote.py`、`busctl_remote.py` 或 `collect_logs.py`；不要等待 NotebookLM 返回才开始主路径
  - 若 NotebookLM 未认证、列表失败、页面超时或单次提问超时：按 `references/notebooklm.md` 记录原因后继续本地或现场采集
  - NotebookLM 最多重试 1 次；仍失败则继续，不要卡住整个排障
- SSH 失败：改用 Telnet 或请求日志片段；同时先做本地代码定位
- Telnet 失败：请求日志或时间戳；同时先做本地代码定位
- DBUS 环境异常：改用 `busctl list`、`mdbctl lsclass`，必要时回到交互 SSH 重新 `printenv`
- `mdbctl` 执行失败、无输出、卡住或 `ServiceUnknown`：不要反复重试同一种方式；优先切 `scripts/mdbctl_remote.py`，再切 `scripts/busctl_remote.py`

### 5) 本地代码定位 (Local code search)
- 优先搜索：
  - 告警文案、错误串、对象路径、字段名、service 名
  - `SensorType`、`SelData`、`EventData`、`AlarmLevel`、`ReadingStatus`
- 识别涉及组件：
  - `sensor`, `hwproxy`, `general_hardware`, `hwdiscovery`, `pcie_device`, `network_adapter`, `bios` 等
- 组件职责参考 `references/components.md`

### 6) SSH 对象查询 (busctl/mdbctl)
- SSH 仅做对象、DBus 查询，不读 `/var/log`
- `scripts/mdbctl_remote.py` 适合远程对象、属性一致性；默认走登录 shell，并在失败时自动切换 fallback
- `scripts/busctl_remote.py` 适合远程接口、方法、信号、对象树，并会清洗 SSH banner 噪音；支持 `--grep`、`--head`、`--tail`
- 原生命令 `mdbctl`、`busctl` 只在脚本不足以表达时再手工使用
- `busctl --user tree <service>` 输出较大，需要等待完整输出
- DBUS、XDG 变量以当前交互 SSH 的 `printenv` 为准
- 无参方法调用时，用 `--signature ''`
- 远程 `mdbctl` 的推荐顺序：
- 先试：`python scripts/mdbctl_remote.py --ip <ip> lsclass`
  - 若需要更细命令：`python scripts/mdbctl_remote.py --ip <ip> lsobj DiscreteSensor`
  - 若仍无法稳定执行，则改用 `python scripts/busctl_remote.py ...`
- `mdbctl_remote.py` 失败时要看分类与退出码，优先区分 `command-not-found`、`service-unknown`、`empty-output`
- 详细命令见 `references/env-access.md`

### 7) 日志分析 (Telnet / logs)
- 现场日志优先走 Telnet；离线日志优先走 `openubmc-log-analyzer`
- 读取 `/var/log/app.log`、`framework.log` 及其轮转 `.gz`
- `scripts/collect_logs.py` 适合批量抓取、关键词过滤、按启动时间裁剪；Telnet 出现登录提示时可直接传用户密码
- 用户说“最近一次启动”时，优先 `--since-boot`
- 大量轮转日志需要搭配 `--rotated-limit`

### 8) 输出结论并沉淀经验 (Analysis + Capture)
#### 本地代码快路径输出
- 现象总结
- 代码证据：定义位置、触发函数、字段含义
- 可能涉及组件 + 代码路径
- 代码上精确触发条件
- 常见上游原因
- 还缺哪些现场证据才能确认到器件或链路

#### 现场或日志路径输出
- 现象总结
- 环境快照：BMC 时间、uptime、固件版本
- 证据日志与证据块（命令 + 关键输出 + 时间戳）
- 排查思路
- 排查方法
- NotebookLM 要点（仅作为背景）
- 可能涉及组件 + 代码路径
- 初步结论 + 下一步验证建议

证据块格式建议：
```
命令：<ssh/telnet/busctl/mdbctl>
输出：<关键行，带时间戳>
```

是否开始写 Obsidian 笔记，由用户决定：
- 用户没有明确要求时，不主动写总结笔记
- 用户明确要求时，再按当前状态选择最终总结或阶段性总结
- 默认在任务完成后写最终总结；如果用户要求得更早，再写阶段性总结
- 目录：`/mnt/e/obsidian/openubmc/`
- 模板：`references/obsidian-debug-note-template.md`
- 必填章节：`现象`、`排查思路`、`排查方法`、`关键证据`、`结论`
- 目标不是写流水账，而是让用户能跟着你的排查顺序复盘和复用方法
- 如果主路径还在连续采证，不要为了“先把笔记写完整”打断分析

什么时候记一版阶段性总结：
- 只有用户明确要求先沉淀当前阶段结果时，才考虑写，而不是边排障边记
- 用户要求写且属于以下情况时，写阶段性总结而不是最终总结：
  - 已给出明确结论，需要先交付给用户
  - 形成稳定方法，后续只是在补充证据或验证细节
  - 被外部条件卡住，需要暂停或交接
- 不必等到 100% 根因闭环；只要这一阶段已经能交付思路、方法和下一步，就可以写

如果这次排障得出了“下次应该先怎么做”的稳定规则，结束前补一条 lesson：
- 推荐命令：
  - 领域规则写入 domain：
    `python /root/.codex/skills/codex-session-memory/scripts/record_lesson.py --scope domain --domain openubmc-debug --title "<reusable rule>" --problem "<what went wrong or what triggered recall>" --rule "<what to do next time>" --evidence "<error shape or evidence>" --keywords key1 key2 key3`
  - 仓库/路径规则写入 project：
    `python /root/.codex/skills/codex-session-memory/scripts/record_lesson.py --scope project --cwd /home/workspace/source --title "<project rule>" --problem "<what went wrong>" --rule "<what to do next time>" --keywords key1 key2`
  - 通用工作流规则写入 global：
    `python /root/.codex/skills/codex-session-memory/scripts/record_lesson.py --scope global --title "<codex rule>" --problem "<what went wrong>" --rule "<what to do next time>" --keywords key1 key2`
- 优先记录：
  - 分流规则
  - 失败模式和替代命令
  - 哪类问题应先走本地代码快路径
  - 哪类日志必须 Telnet，哪类对象必须 SSH
- 不要记录：
  - 只对一次事故有效的噪音细节
  - 没有 trigger 条件的泛泛建议

## 常见错误 (Common Mistakes)
- 没有 IP 就停止：先判断能否走本地代码快路径
- 为了 `doc-first` 强行卡 NotebookLM：本地代码或现场证据能闭环时直接继续
- 发了 NotebookLM 问题后停下来等：NotebookLM 应该后台跑，主路径继续本地代码、SSH 或 Telnet 采证
- 用 SSH 读 `/var/log`：日志应该走 Telnet 或日志包
- 看到 Telnet 能进 root shell，就顺手拿它做对象查询：对象查询仍应优先 SSH
- 同一个问题只用 SSH 或只用 Telnet：很多运行时问题需要“对象面 + 日志面”联合取证
- 一口气开很多远端终端并行跑命令：默认只保留 1 个 SSH 对象面和 1 个 Telnet 日志面
- 只给泛泛原因，不解释字段含义：要把文案、字段、触发逻辑串起来
- 有日志包还直接上现场采集：先用 `openubmc-log-analyzer` 缩小范围
- 已经发现了稳定的排障规律，却没写进 lesson store：下次还会重复犯同一个错
- 只因为问题里出现 `openUBMC` 或仓库路径就套用本 skill：先判断是不是运行时排障
- 把编译报错、实现设计、SR/CSR/MDS 改动当成 debug 任务：这类应切 `openubmc-developer`

## 资源 (Resources)
### scripts/
- `collect_logs.py`：Telnet 拉日志（支持登录、过滤关键字、按启动时间、包含轮转，支持 `--rotated-limit`、`--telnet-port`、`--telnet-*-env`、`--debug-dump`、`--json`）
- `_minimal_telnet.py`：skill 自带的最小 Telnet 客户端，避免依赖已弃用的 `telnetlib`
- `busctl_remote.py`：SSH 自动读取 DBUS、XDG 并执行 `busctl --user`，支持 `--grep`、`--head`、`--tail`、`--ssh-port`、`--ssh-*-env`、`--debug-dump`、`--json`
- `mdbctl_remote.py`：SSH 自动用登录 shell 执行 `mdbctl`，并在失败时切换 fallback，返回失败分类退出码；支持 `--ssh-port`、`--ssh-*-env`、`--debug-dump`、`--json`
- `preflight_remote.py`：一条命令检查 SSH、Telnet、DBUS/XDG、`mdbctl`、`busctl` 是否可用，独立检查默认并行执行；支持 `--ssh-port`、`--telnet-port`、`--*-env`、`--debug-dump`、`--json`；JSON 输出带稳定 `overall_code`、`failed_checks`、`recommended_next_step`、`recommended_command` 和 per-check `code`
- `preflight_remote.py`：支持 `--debug-dump <dir>`，一次落完整预检链路的 SSH/Telnet 原始证据
- `triage_parallel.py`：把本地代码、SSH、Telnet 和可选 NotebookLM 拆成并行 lane；有 `tmux` 时可直接拉起 detached session，没有 `tmux` 时输出人工可执行计划；支持 `--json`

### tests/
- `tests/test_regressions.py`：离线回归测试，覆盖 SSH banner 清洗、对象树过滤、`mdbctl` 失败分类、Telnet 登录流和空日志提示
  - 同时覆盖统一 JSON contract、routing fixture contract，以及 `debug-dump` 对 token/cookie/private-key 的脱敏

### references/
- `env-access.md`：SSH、Telnet、busctl、mdbctl、DBUS、XDG 变量、默认登录方式
- `logs.md`：日志路径与轮转
- `components.md`：仓库顶层组件职责速览
- `overview.md`：skill 使用概览与最短路径
- `obsidian-debug-note-template.md`：Obsidian 排障记录模板；是否开始写由用户决定，用户要求后再按任务状态写最终总结或阶段性总结
- `routing-cases.md`：分流压力样例，维护 `local-only`、`SSH`、`Telnet`、`route-away` 边界时优先对照
- `notebooklm.md`：NotebookLM 预检、快速失败和提问模板
- `context7.md`：Context7 openUBMC 文档入口
- `lessons/INDEX.md`：`openubmc-debug` 的正式 domain 经验入口
- `lessons/inbox/INBOX.md`：自动生成的候选经验草稿；需要审核后再转正

## 备注 (Notes)
- 信息不足时可用 Context7 查询官方文档
- 服务名未知时先 `busctl list` 或 `mdbctl lsclass`
- 输出中保留命令，方便复现
- Scripts 为纯 Python，可复用到其他 AI 工具
