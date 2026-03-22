# 日志路径与格式（Logs）

## 主要日志
- `/var/log/app.log`（组件日志）
- `/var/log/framework.log`（框架日志）

两者都有 `.gz` 轮转文件，例如 `app.log.1.gz`、`framework.log.7.gz`。

## 日志格式（示例）
```
YYYY-MM-DD HH:MM:SS.micro component LEVEL: file(line): message
```

## 常用手工命令（Telnet）
```
# 最近 N 行
 tail -n 2000 /var/log/app.log
 tail -n 2000 /var/log/framework.log

# 关键字过滤
 grep -i "gpu" /var/log/app.log | tail -n 200

# 读取轮转日志
 zcat /var/log/app.log.1.gz | tail -n 200
 zgrep -i "error" /var/log/framework.log.*.gz | tail -n 200
```

## 最近一次启动（since-boot）
如果只看“最近启动后的日志”：
1. 读取当前时间与 uptime
2. 计算 boot time
3. 过滤时间戳 >= boot time 的日志

`scripts/collect_logs.py` 可用 `--since-boot` 自动完成。

如果你要让 agent 或其他脚本自动消费日志抓取结果，也可以直接加 `--json`。现在推荐优先读统一外壳：
- `schema_version`
- `tool`
- `request`
- `result`
- `warnings`

其中 `collect_logs.py --json` 的 `request` 会包含 `logs_requested`、`keywords`、`since_boot_requested`、`lines`、`include_rotated` 和 `rotated_limit`；`result` 会包含 `boot_time`、`entries` 和 `written_files`。每个 `entries[*]` 里会带 `path`、`line_count`、`lines`、`empty` 和 `empty_message`。

## 环境快照（用于对齐时间/版本）
```
date
cat /proc/uptime
cat /etc/os-release 2>/dev/null || cat /etc/issue 2>/dev/null || cat /etc/version 2>/dev/null
```

## 脚本用法（collect_logs.py）
注：`collect_logs.py` 默认假设 Telnet 免登录；若环境需要登录，请改用手工 Telnet 或先完成登录后再执行命令。
```
python scripts/collect_logs.py --ip <ip> --lines 2000 --logs app.log,framework.log
python scripts/collect_logs.py --ip <ip> --lines 2000 --grep gpu,pcie --since-boot
python scripts/collect_logs.py --ip <ip> --lines 2000 --include-rotated --output-dir /tmp/openubmc-logs
python scripts/collect_logs.py --ip <ip> --lines 2000 --logs app.log --grep sensor --since-boot --json
```
