# openubmc-debug 概览

## 适用场景
- 用户提供 BMC IP，需要 SSH 查 DBus 或 Telnet 看 `app.log`、`framework.log`
- 用户只有告警文案、SEL 字段、对象路径、错误串，需要先用本地代码解释触发条件
- 需要结合本地代码 + 现场证据给出分析结论

## SSH vs Telnet
- SSH：对象面。查 `busctl` / `mdbctl` / DBus 对象、属性、方法、service。
- Telnet：日志面。查 `app.log` / `framework.log` / `/var/log` 与轮转日志。
- 两者都要：当问题需要把“当前对象状态”和“对应时间点日志”对上时。
- 不要混用：不要在 SSH 里读日志，也不要把 Telnet 当默认 DBus 查询入口。
- 对象面默认先试 `mdbctl_remote.py`；需要原始 D-Bus、精确接口签名或 `monitor` 时再切 `busctl_remote.py`。

对象面入口短语统一按这一套：
- `mdbctl` 更适合 openUBMC 微组件对象调试。
- `busctl` 更适合原始 D-Bus 观察和精确调用。
- `mdbctl` 失败不代表对象面不可查，优先切 `busctl_remote.py`。

## 并行采证
- 终端 1：本地代码面，负责 `rg`、源码和字段映射定位。
- 终端 2：SSH 对象面，负责 `preflight_remote.py`、`mdbctl_remote.py`、`busctl_remote.py`。
- 终端 3：Telnet 日志面，负责 `collect_logs.py`、手工 `grep` / `tail` / `zcat`。
- 默认只建议这 3 个，不建议同时开很多远端终端。

## 不适用场景
- 编译报错、构建日志、实现方案、代码评审、CSR/MDS/Redfish 设计
- 主要问题不在运行时对象/日志/告警，而在源码实现本身
- 这类任务应改用 `openubmc-developer`

## 技能分流（Routing）
- 有 BMC IP、需要 SSH DBus + Telnet 日志：用 `openubmc-debug`
- 只有日志包或日志目录（`.tar`, `.tar.gz` 或已解压目录）、想离线分析：用 `openubmc-log-analyzer`
- 只有告警文案、SEL、关键词，没有 IP 和日志：仍可用 `openubmc-debug`，直接走本地代码快路径
- 如果用户要的是实现或改代码，而不是现场排障：用 `openubmc-developer`

## 目录结构
- `SKILL.md`：主流程与分流策略
- `scripts/`：日志与 DBus 采集脚本（含 `busctl_remote.py`、`mdbctl_remote.py`）
- `references/`：环境、日志、组件、NotebookLM 等参考

## 典型输出结构
- 本地代码快路径：现象总结、代码证据、精确触发条件、常见上游原因、仍需补的现场证据
- 现场路径：现象总结、环境快照、证据块、可能涉及组件、初步结论、下一步验证建议

## Quickstart（最短路径）

最小输入集（先拿到任一证据种子，减少来回追问）：
- 现象：错误、字段缺失、告警、对象路径、SEL 文案、关键词
- 证据种子：`BMC IP`、`日志路径`、`告警或错误串` 三选一
- 可选：复现时间点（或“最近一次重启后”）、组件或服务名（例如 `bmc.kepler.hwproxy`）、固件版本

连通性快检（有 IP 时再做）：
```bash
ssh -o ConnectTimeout=5 Administrator@<ip> exit
telnet <ip> 23
```

先采证据，再写结论（速查链接）：
- DBus（SSH）：见 `env-access.md`
- 日志（Telnet）：见 `logs.md`
- 本地代码定位：见 `components.md`（组件职责）+ 在 `/home/workspace/source/` 用 `rg` 搜索关键字

## 注意事项
- SSH 只用于对象、DBus 查询，Telnet 用于日志
- NotebookLM 是补充背景，不应阻塞本地代码或现场证据分析
- 信息不足时先补证据，再给结论
- 触发词里出现 `openUBMC` 不等于一定用本 skill；先判断是不是运行时排障
- 是否开始写这份笔记，由用户决定；用户没有明确要求时，不主动写总结
- 用户明确要求时，默认在任务完成后，把 `排查思路`、`排查方法`、`关键证据` 和 `结论` 写入 `/mnt/e/obsidian/openubmc/` 下的笔记
- 如果用户要求时主路径还在连续采证，不要为了保持笔记实时更新而打断分析；改写阶段性总结即可
- 用户明确要求阶段性沉淀，且已经能先交付结论、形成稳定方法或被外部条件卡住时，才写一版阶段性总结
