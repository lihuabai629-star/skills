# 环境访问（SSH vs Telnet）

## 并行入口（Launcher）

如果你不想手工分配“本地代码面 / SSH 对象面 / Telnet 日志面 / 可选 NotebookLM 背景面”，优先先跑：

```
python scripts/triage_parallel.py --ip <ip> --keyword <keyword>
```

如果环境有 `tmux`，可直接让它拉起 detached session：

```
python scripts/triage_parallel.py --ip <ip> --keyword <keyword> --launch-tmux
```

如果没有 `tmux`，脚本会自动退回为手工可执行的 lane 计划，不会阻塞主路径。

## 先选通道（Decision Gate）

| 如果你要做的是 | 用什么 | 不要先用什么 |
|------|------|------|
| 查 `busctl` / `mdbctl` / DBus 对象树 / 属性 / 方法 / service | SSH | Telnet |
| 看 `app.log` / `framework.log` / `/var/log` / 轮转日志 | Telnet | SSH |
| 同时需要“当前对象状态 + 对应时间点日志” | SSH + Telnet | 只用一种 |

固定约束：
- SSH 在本 skill 里是“对象查询通道”，不是通用 shell
- Telnet 在本 skill 里是“日志通道”，不是默认 DBus 查询通道
- 即使 Telnet 登录后通常是 root，也不要把它当成 `busctl` / `mdbctl` 的默认入口
- 即使 SSH 能执行 shell，也不要在 SSH 里读 `/var/log`

一句话判断：
- 你想确认“现在对象是什么状态” -> SSH
- 你想确认“当时日志里发生了什么” -> Telnet
- 两个都想确认 -> 两条链都跑

## 预检脚本（推荐）

先跑一次：

```
python scripts/preflight_remote.py --ip <ip>
python scripts/preflight_remote.py --ip <ip> --json
python scripts/triage_parallel.py --ip <ip> --keyword SensorSelInfo
```

它会快速检查：
- SSH 是否可连
- DBUS/XDG 是否可读
- `mdbctl` 登录 shell 是否可用
- `busctl` 对象树是否可查
- Telnet 是否可进，以及日志文件是否可见

`preflight_remote.py` 会把互不依赖的 SSH/Telnet 检查并行跑完，再补依赖 DBUS 环境的 `busctl`，避免整条预检串行等待。

如果你要让 agent 或其他脚本自动消费对象查询结果，也可以直接用：

```
python scripts/busctl_remote.py --ip <ip> --action tree --service bmc.kepler.sensor --json
```

四个脚本的机器可读输出现在都共享同一层稳定外壳：
- `schema_version`
- `tool`
- `ip`
- `ok`
- `code`
- `returncode`
- `warnings`
- `error`
- `request`
- `result`

其中 `request` / `result` 是推荐给 agent 消费的稳定层；下面再保留原有顶层字段，方便兼容旧脚本和人手排查。

`busctl_remote.py --json` 的 `result` 会包含 `stdout`、`stdout_lines`、`stderr`、`stderr_lines` 和 `dbus_env`。默认机器码当前固定为：
- `ok`
- `dbus_env_missing`
- `remote_command_failed`

如果你要让 agent 自动消费 `mdbctl` 结果，也可以直接用：

```
python scripts/mdbctl_remote.py --ip <ip> --json lsclass
```

`mdbctl_remote.py --json` 的 `request` 会包含 `requested_mode` 和 `command_parts`；`result` 会包含 `selected_mode`、`stdout`、`stderr`、`attempts` 和 `hint`。默认机器码当前固定为：
- `ok`
- `remote-command-failed`
- `empty-output`
- `command-not-found`
- `service-unknown`
- `timeout`
- `unknown`

如果环境不是默认端口，或者不想把账号密码直接写进 shell history，统一优先用：

```
# SSH 类脚本
export BMC_USER=Administrator
export BMC_PASS='Admin@9000'
python scripts/busctl_remote.py --ip <ip> --ssh-port 22 --ssh-user-env BMC_USER --ssh-password-env BMC_PASS --action list

# Telnet 类脚本
export TEL_USER=Administrator
export TEL_PASS='Admin@9000'
python scripts/collect_logs.py --ip <ip> --telnet-port 23 --telnet-user-env TEL_USER --telnet-password-env TEL_PASS --logs app.log --lines 50
```

如果现场行为不稳定、banner 污染严重、认证偶发失败，或者你需要把“原始远端输出”留给后续复盘，给脚本再加一层：

```
python scripts/preflight_remote.py --ip <ip> --debug-dump /tmp/openubmc-preflight-dump
python scripts/busctl_remote.py --ip <ip> --debug-dump /tmp/openubmc-busctl-dump --action tree --service bmc.kepler.sensor
python scripts/mdbctl_remote.py --ip <ip> --debug-dump /tmp/openubmc-mdbctl-dump lsclass
python scripts/collect_logs.py --ip <ip> --debug-dump /tmp/openubmc-collect-dump --logs app.log --lines 50
```

典型产物：
- `*_command.txt`：脚本实际执行的命令
- `*_stdout.txt` / `*_stderr.txt`：原始 SSH 输出
- `*_raw.bin`：原始 Telnet 字节流
- `*_text.txt`：Telnet 命令解码后的文本
- `summary.json`：按顺序列出每个产物的阶段、时间戳、文件名、大小、脱敏状态和附加 metadata

当前实现会自动掩掉脚本已知的 SSH/Telnet 密码，并额外识别常见 token、cookie、session id 和 private key 片段；但外发前仍建议人工抽查 dump 内容。

如果你要让 agent 或其他脚本自动消费预检结果，优先用：

```
python scripts/preflight_remote.py --ip <ip> --json
```

`preflight_remote.py --json` 的 `result` 会包含 `overall_ok`、`overall_code`、`failure_count`、`failed_checks`、`recommended_next_step`、`recommended_command` 和 `checks`，其中：
- `overall_code` 当前固定为 `ok` 或 `preflight_failed`
- `failed_checks` 会按固定顺序列出失败阶段名，方便直接分流
- `recommended_next_step` 是优先执行的下一步；失败时默认跟随第一个失败检查
- `recommended_command` 是与 `recommended_next_step` 对应的首选命令；为避免泄露，不会回填密码明文
- `checks.<NAME>.code` 是稳定机器码，当前固定为 `ok`、`ssh_unavailable`、`dbus_env_missing`、`mdbctl_unavailable`、`busctl_unavailable`、`telnet_unavailable`
- `checks.<NAME>.recommended_next_step` 是该检查自己的建议动作
- `checks.<NAME>.recommended_command` 是该检查自己的建议命令
- `checks.<NAME>.lines` 是给人读的摘要
- `checks.DBUS_ENV.env` 会附带解析出的 `DBUS_SESSION_BUS_ADDRESS` 与 `XDG_RUNTIME_DIR`
## SSH（对象查询）
SSH 仅用于 busctl/mdbctl 对象查询；SSH 用户权限有限，**不要**在 SSH 里读 `/var/log`。

- 登录（默认账号密码可用）：
  - Linux 直连：`ssh Administrator@<ip>` 密码 `Admin@9000`
  - Windows OpenSSH：`/mnt/c/Windows/System32/OpenSSH/ssh.exe Administrator@<ip>`

非交互（脚本）示例：

```
sshpass -p 'Admin@9000' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null Administrator@<ip> "<command>"
```

如果缺少 `sshpass`：

```
apt-get install -y sshpass
```

### busctl vs mdbctl（职责边界）

如果你已经进入 SSH 对象面，但还不确定应该先用哪个命令，按这个原则判断：

- `mdbctl` 更适合 openUBMC 微组件对象调试。
  - 适合先快速浏览 class、object、property、method。
  - 适合直接 `getprop` / `lsprop` / `call`，不想手工查完整 DBus path、interface、signature 时优先用它。
  - 适合 attach 到模块后做组件级调试，例如 `mdbctl attach hwproxy`、`mdbctl lsmc`、动态调日志级别、trace 属性。
- `busctl` 更适合原始 D-Bus 观察和精确调用。
  - 适合已经知道 service、object path、interface，需要精确 `introspect`、`get-property`、`call`、`monitor` 时优先用它。
  - 适合看 `busctl --user monitor` 这类原始消息流。
  - 适合脚本化、机器可读、以及非 openUBMC 标准 Linux user bus 服务排查。

在本 skill 里的落地规则：

- 人工 SSH 探索 openUBMC 微组件对象时，先试 `mdbctl`。
- 需要稳定脚本化、精确接口签名、对象树、原始 D-Bus 语义时，先试 `busctl_remote.py` / `busctl --user`。
- `mdbctl` 失败不代表对象面不可查；很多场景直接切 `busctl_remote.py` 更稳。
- 如果你已经明确知道 service/path/interface，就不要为了“更友好”强行绕回 `mdbctl`。

代表命令：

```
# mdbctl：面向 openUBMC 对象模型
mdbctl lsclass
mdbctl lsobj DiscreteSensor
mdbctl lsprop CpuBoard_1_010101
mdbctl getprop CpuBoard_1_010101 Private BmcStartFlag
mdbctl attach hwproxy

# busctl：面向原始 D-Bus
busctl --user tree bmc.kepler.sensor
busctl --user introspect bmc.kepler.sensor /bmc/kepler/Chassis/1/SensorSelInfo
busctl --user get-property <service> <path> <interface> <property>
busctl --user call <service> <path> <interface> <method> <signature> [args...]
busctl --user monitor bmc.kepler.sensor
```

### busctl（DBus）
交互 SSH 会话里通常已经自动设置 DBUS/XDG 环境变量，因此可以直接 `busctl --user ...`。如果失败，请**先读取当前会话的 DBUS/XDG**，再导出后执行。

```
printenv | grep -E 'DBUS|XDG_RUNTIME_DIR'

# 示例（不同环境会变化）：
# DBUS_SESSION_BUS_ADDRESS=unix:abstract=/tmp/dbus-XXXX,guid=...
# XDG_RUNTIME_DIR=/run/user/502

# 使用上面打印出来的值：
XDG_RUNTIME_DIR=/run/user/502 \
DBUS_SESSION_BUS_ADDRESS=unix:abstract=/tmp/dbus-XXXX,guid=... \
busctl --user --no-pager list
```

常见用法：

```
# 列出服务对象树（例如 hwproxy）— 输出很大，需要等待
XDG_RUNTIME_DIR=/run/user/502 DBUS_SESSION_BUS_ADDRESS=unix:abstract=/tmp/dbus-XXXX,guid=... \
  busctl --user --no-pager tree bmc.kepler.hwproxy

# 查看某个路径的属性/方法
XDG_RUNTIME_DIR=/run/user/502 DBUS_SESSION_BUS_ADDRESS=unix:abstract=/tmp/dbus-XXXX,guid=... \
  busctl --user --no-pager introspect bmc.kepler.hwproxy /bmc/kepler/hwproxy/...

# 调用方法
XDG_RUNTIME_DIR=/run/user/502 DBUS_SESSION_BUS_ADDRESS=unix:abstract=/tmp/dbus-XXXX,guid=... \
  busctl --user call bmc.kepler.hwproxy /bmc/kepler/hwproxy/... interface method <sig> <args>
```

如果不知道服务名，先 list 再 grep（输出可能较慢）：

```
XDG_RUNTIME_DIR=/run/user/502 DBUS_SESSION_BUS_ADDRESS=unix:abstract=/tmp/dbus-XXXX,guid=... \
  busctl --user --no-pager list | grep -i kepler
```

如果 `busctl --user` 仍看不到服务，请在**同一交互会话**里再次 `printenv`，并使用其值。
若 `busctl` 无输出或报 `ServiceUnknown`：
- 先用 `python scripts/busctl_remote.py --ip <ip> --print-env` 检查 DBUS/XDG 是否为空
- 仍异常时回到交互 SSH，重新 `printenv` 后再试

环境变量提示：若 `busctl` 无法使用用户总线，可先 `. /etc/profile`，或 `export $(cat /dev/shm/dbus/.dbus)` 以加载 `DBUS_SESSION_BUS_ADDRESS`；`XDG_RUNTIME_DIR` 仍应优先通过 `printenv` 或脚本自动读取。

原生命令速查：
```
busctl --user list
busctl --user tree <service>
busctl --user introspect <service> <object>
busctl --user get-property <service> <object> <interface> <property>
busctl --user call <service> <object> <interface> <method> <signature> [args...]
busctl --user monitor [service] [object]
```
说明：openUBMC 方法签名常以 `a{ss}` 开头（上下文参数）。

### 脚本化 busctl（自动化）
使用 `scripts/busctl_remote.py` 自动完成：
1) 打开交互登录 shell 读取 DBUS/XDG
2) 带环境变量执行 `busctl --user`
3) 清理 SSH host-key 警告和远端 banner 噪音
4) 支持本地过滤大输出（`--grep`、`--head`、`--tail`）

示例：

```
# 列出服务树
python scripts/busctl_remote.py --ip <ip> --action tree --service bmc.kepler.hwproxy

# introspect 指定路径
python scripts/busctl_remote.py --ip <ip> --action introspect --service bmc.kepler.hwproxy --path /bmc/kepler/hwproxy/MicroComponent

# 如果需要手动覆盖 DBUS/XDG
python scripts/busctl_remote.py --ip <ip> --dbus 'unix:abstract=/tmp/dbus-XXXX,guid=...' --xdg /run/user/502 --action list

# 大输出场景建议本地过滤
python scripts/busctl_remote.py --ip <ip> --action tree --service bmc.kepler.sensor --grep SensorSelInfo --head 20

# 用环境变量传账号密码
export BMC_USER=Administrator
export BMC_PASS='Admin@9000'
python scripts/busctl_remote.py --ip <ip> --ssh-port 22 --ssh-user-env BMC_USER --ssh-password-env BMC_PASS --action tree --service bmc.kepler.sensor

# 需要机器可读输出时
python scripts/busctl_remote.py --ip <ip> --ssh-user-env BMC_USER --ssh-password-env BMC_PASS --action tree --service bmc.kepler.sensor --grep SensorSelInfo --head 20 --json
```

在有远端登录 banner 的环境里，优先用 `busctl_remote.py`，不要先手工拼 `DBUS_SESSION_BUS_ADDRESS` 再跑 `busctl --user`。

### mdbctl（微组件数据库）
优先使用**单条命令**模式，每条命令前都带 `mdbctl`，避免交互卡住：

```
mdbctl lsclass
mdbctl lsobj <class>
mdbctl lsprop <object> [interface]
mdbctl getprop <object> <interface> <property>
mdbctl lsmethod <object> [interface]
mdbctl call <object> <interface> <method> [args...]
mdbctl attach <module>
mdbctl lsmc
mdbctl setprop <set|unset> <object> <interface> <property> [value]
mdbctl traceprop <trace|untrace> <object> [interface] [property]
```

如果非交互 SSH 找不到 `mdbctl`，请优先用 POSIX 登录 shell：

```
sh -lc '. /etc/profile >/dev/null 2>&1; mdbctl lsclass'
```

如果仍失败，再切脚本化方式，不要继续手写 bash-only 语法：

```
python scripts/mdbctl_remote.py --ip <ip> lsclass
```

仅在确实需要 mdbctl 语义、且其他方式都不稳定时，再尝试 direct skynet（环境相关，成功率不如脚本化 `busctl`）：

```
printf 'lsclass\n' | /opt/bmc/skynet/lua /opt/bmc/apps/mdbctl/service/mdbctl.lua
```

注：如果 mdbctl 报 `ServiceUnknown`，可能服务未运行或 DBUS 环境不正确；在这类环境里，优先改用 `scripts/busctl_remote.py`，不要反复重试 raw skynet。

### mdbctl 常见失败与切换动作

| 现象 | 常见原因 | 立即动作 |
|------|----------|----------|
| `mdbctl: command not found` | 非交互 SSH 未加载 alias 或 profile | 改用 `sh -lc '. /etc/profile >/dev/null 2>&1; mdbctl ...'` |
| 命令无输出或一直卡住 | 进入了交互模式、stdout 未返回、服务未就绪 | 只用单条命令模式；避免交互会话；必要时切 direct skynet |
| `ServiceUnknown` | mdb 服务未注册、DBUS 环境异常、服务仍在启动 | 不要盲重试 raw skynet；优先切 `python scripts/busctl_remote.py ...` 验证服务和对象树 |
| 同一命令在交互 SSH 成功、非交互失败 | shell 环境差异 | 统一改成 `sh -lc '. /etc/profile >/dev/null 2>&1; mdbctl ...'` 或 direct skynet |
| 对象或属性查不到，但服务存在 | 路径、class、interface 不确定 | 先 `mdbctl lsclass`、`lsobj` 缩小范围；再切 `busctl introspect` / `get-property` 做交叉验证 |

推荐排障顺序：

```
# 1) 先试最轻量的单条命令
mdbctl lsclass

# 2) 非交互失败时，切 POSIX 登录 shell
sh -lc '. /etc/profile >/dev/null 2>&1; mdbctl lsclass'

# 3) 仍失败时，优先切 busctl script
python scripts/busctl_remote.py --ip <ip> --action list
python scripts/busctl_remote.py --ip <ip> --action tree --service <service>

# 4) 只有确实需要 mdbctl 语义时，再显式试 direct skynet
printf 'lsclass\n' | /opt/bmc/skynet/lua /opt/bmc/apps/mdbctl/service/mdbctl.lua
```

原则：
- 不要对同一种失败方式连续盲重试
- `mdbctl` 失败不等于现场不可查，很多场景可以直接切 `busctl_remote.py`
- 在结论里记录“哪一种 mdbctl 方式失败、哪一种替代方式成功”，方便后续固化脚本

### 脚本化 mdbctl（自动化）
使用 `scripts/mdbctl_remote.py` 自动完成：
1) 通过登录 shell 执行 `mdbctl`
2) 自动清理 SSH host-key 警告和远端 banner 噪音
3) 在 auto 模式下仅把 direct skynet 作为最后尝试；失败后应改用 `scripts/busctl_remote.py`
4) 失败时返回可区分的退出码，便于脚本按 `command-not-found` / `service-unknown` / `empty-output` 分流

示例：

```
# 远程列出所有 class
python scripts/mdbctl_remote.py --ip <ip> lsclass

# 远程列出某个 class 下的对象
python scripts/mdbctl_remote.py --ip <ip> lsobj DiscreteSensor

# 指定执行模式
python scripts/mdbctl_remote.py --ip <ip> --mode login-shell lsclass
python scripts/mdbctl_remote.py --ip <ip> --mode direct-skynet lsclass

# 需要分类时
python scripts/mdbctl_remote.py --ip <ip> --print-classification lsclass

# 用环境变量传账号密码
export BMC_USER=Administrator
export BMC_PASS='Admin@9000'
python scripts/mdbctl_remote.py --ip <ip> --ssh-port 22 --ssh-user-env BMC_USER --ssh-password-env BMC_PASS lsclass

# 需要机器可读输出时
python scripts/mdbctl_remote.py --ip <ip> --ssh-user-env BMC_USER --ssh-password-env BMC_PASS --json lsclass
```

如果环境上 `mdbctl` 在非交互 SSH 里经常失败，优先直接用 `mdbctl_remote.py`；如果 auto 模式仍失败，下一步应切 `busctl_remote.py`，不要继续手工试多种 raw skynet 变体。

## Telnet（日誌访问）
Telnet 用来读日志；如提示登录则使用 `Administrator / Admin@9000`。

适合 Telnet 的操作：
- `tail` / `grep` / `zcat` `app.log`、`framework.log`
- 结合时间点抓取 `/var/log` 与轮转 `.gz`
- 验证某个报错、告警、重启、服务异常在日志里的时间顺序
- 用 `collect_logs.py` 统一抓取日志，即使环境需要用户名密码登录也可以直接传参

不适合 Telnet 的默认操作：
- `busctl` / `mdbctl` 对象树和属性查询
- 把 Telnet 当成 SSH 的替代入口来做对象面采证

原因：
- Telnet 更适合日志面排查，输出容忍度高
- 对象面更依赖环境变量、service 可见性和可复现命令，SSH 更适合固化流程

```
telnet <ip>   # 端口 23
```

Telnet 登入后通常为 root，可直接访问 `/var/log`。

脚本示例：

```
python scripts/collect_logs.py --ip <ip> --user Administrator --password 'Admin@9000' --logs app.log,framework.log --lines 200

# 用环境变量传账号密码
export TEL_USER=Administrator
export TEL_PASS='Admin@9000'
python scripts/collect_logs.py --ip <ip> --telnet-port 23 --telnet-user-env TEL_USER --telnet-password-env TEL_PASS --logs app.log,framework.log --lines 200
```
