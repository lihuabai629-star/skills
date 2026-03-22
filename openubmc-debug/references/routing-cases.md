# Routing Pressure Cases

用这组 case 反复压 `openubmc-debug` 的分流边界。  
如果未来 agent 对这些 case 选了别的路径，优先视为 skill 回归，而不是“灵活发挥”。

### Routing Pressure Cases

## 使用方式

- 改 `SKILL.md` 的分流、`SSH vs Telnet`、`Route away` 前后，都重新对照这组 case。
- 新增规则时，先补 case，再改文档。
- 如果问题触发了 `openUBMC` 关键词，但命中了 `route-away-developer`，说明分流比关键词优先级更高。

## Case Matrix

| id | 用户问题形态 | 期望 skill | 期望路径 | 期望通道 | 首选脚本 | 禁止脚本 | 为什么 |
|----|--------------|-----------|---------|---------|---------|---------|--------|
| `local-only-sel-meaning` | 只问告警 / SEL 含义 | `openubmc-debug` | `local-only` | `local` | `local-code-search` | `busctl_remote.py`, `mdbctl_remote.py`, `collect_logs.py` | 本地代码快路径即可闭环，不先追环境 |
| `telnet-app-log-grep` | 点名 `app.log` / `grep` | `openubmc-debug` | `telnet` | `telnet` | `collect_logs.py` | `busctl_remote.py`, `mdbctl_remote.py` | 日志面统一走 Telnet |
| `ssh-busctl-tree` | 点名 `busctl` / 对象树 | `openubmc-debug` | `ssh` | `ssh` | `busctl_remote.py` | `collect_logs.py` | 对象面统一走 SSH |
| `ssh-telnet-correlate` | 同时要对象状态和日志 | `openubmc-debug` | `ssh+telnet` | `ssh + telnet` | `busctl_remote.py`, `collect_logs.py` | 无 | 联合取证，不要只走一种 |
| `log-bundle-only` | 只有日志包 | `openubmc-log-analyzer` | `log-analyzer` | `log-bundle` | `openubmc-log-analyzer` | `busctl_remote.py`, `mdbctl_remote.py`, `collect_logs.py` | 先离线缩小范围 |
| `log-bundle-plus-ip` | 日志包 + BMC IP | `openubmc-log-analyzer` | `log-analyzer+debug` | `log-bundle + ssh` | `openubmc-log-analyzer`, `busctl_remote.py` | 无 | 先日志，再现场补证据 |
| `build-failure-route-away` | 编译失败 / `bingo build` | `openubmc-developer` | `route-away-developer` | `developer` | `openubmc-developer` | `busctl_remote.py`, `mdbctl_remote.py`, `collect_logs.py` | 开发问题，不是运行时排障 |
| `design-review-route-away` | 设计评审 / CSR / MDS / Redfish | `openubmc-developer` | `route-away-developer` | `developer` | `openubmc-developer` | `busctl_remote.py`, `mdbctl_remote.py`, `collect_logs.py` | 静态设计问题，不是 debug |

## 回归信号

- `local-only-sel-meaning` 被追着要 IP，再做现场采集。
- `telnet-app-log-grep` 先跑 SSH。
- `ssh-busctl-tree` 先跑 Telnet。
- `log-bundle-only` 还没看日志包就要求现场 IP。
- `build-failure-route-away` 仍然触发 `openubmc-debug`。

这些都应该视为 skill 退化。
