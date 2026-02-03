# 环境访问（SSH vs Telnet）

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

环境变量提示（NotebookLM 摘要）：若 busctl 无法使用用户总线，可先 `source /etc/profile`，或 `export $(cat /dev/shm/dbus/.dbus)` 以加载 `DBUS_SESSION_BUS_ADDRESS`；文档未明确覆盖 `XDG_RUNTIME_DIR`，需要时请用 `printenv` 或脚本自动读取。

原生命令速查（NotebookLM 摘要）：
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

示例：

```
# 列出服务树
python scripts/busctl_remote.py --ip <ip> --action tree --service bmc.kepler.hwproxy

# introspect 指定路径
python scripts/busctl_remote.py --ip <ip> --action introspect --service bmc.kepler.hwproxy --path /bmc/kepler/hwproxy/MicroComponent

# 如果需要手动覆盖 DBUS/XDG
python scripts/busctl_remote.py --ip <ip> --dbus 'unix:abstract=/tmp/dbus-XXXX,guid=...' --xdg /run/user/502 --action list
```

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

如果非交互 SSH 找不到 `mdbctl`，请用登录 shell 触发 alias：

```
bash -ilc "mdbctl lsclass"
```

或直接用 skynet 启动（等价于 mdbctl，需要通过 stdin 传命令）：

```
printf 'lsclass\n' | /opt/bmc/skynet/lua /opt/bmc/apps/mdbctl/service/mdbctl.lua
```

注：如果 mdbctl 报 `ServiceUnknown`，可能服务未运行或 DBUS 环境不正确。

## Telnet（日誌访问）
Telnet 用来读日志；如提示登录则使用 `Administrator / Admin@9000`。

```
telnet <ip>   # 端口 23
```

Telnet 登入后通常为 root，可直接访问 `/var/log`。
