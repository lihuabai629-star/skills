#!/usr/bin/env python3
"""Collect openUBMC logs over telnet (root, no password)."""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import telnetlib

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
LOGIN_RE = re.compile(br"(login:|password:)", re.IGNORECASE)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect app/framework logs via telnet.")
    parser.add_argument("--ip", required=True, help="BMC IP")
    parser.add_argument("--port", type=int, default=23, help="Telnet port (default: 23)")
    parser.add_argument(
        "--logs",
        default="app.log,framework.log",
        help="Comma-separated log filenames under /var/log (default: app.log,framework.log)",
    )
    parser.add_argument("--lines", type=int, default=2000, help="Tail N lines per file")
    parser.add_argument("--include-rotated", action="store_true", help="Include .gz rotated logs")
    parser.add_argument(
        "--rotated-limit",
        type=int,
        default=3,
        help="Max rotated .gz files per log when --include-rotated (0 = all, default: 3)",
    )
    parser.add_argument("--since-boot", action="store_true", help="Filter lines since last boot")
    parser.add_argument(
        "--grep",
        default="",
        help="Comma-separated keywords; only keep lines containing any keyword (case-insensitive)",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional directory to write output files; stdout otherwise",
    )
    return parser.parse_args()


def telnet_connect(ip: str, port: int) -> telnetlib.Telnet:
    tn = telnetlib.Telnet(ip, port, timeout=10)
    # Drain banner and land on a prompt if possible
    data = b""
    try:
        data += tn.read_until(b"# ", timeout=5)
    except Exception:
        pass
    if not data:
        try:
            tn.write(b"\n")
            data += tn.read_until(b"# ", timeout=5)
        except Exception:
            pass
    if data and LOGIN_RE.search(data):
        raise RuntimeError(
            "Telnet login prompt detected; collect_logs.py assumes passwordless access. "
            "Use manual telnet or login first."
        )
    return tn


def run_cmd(tn: telnetlib.Telnet, cmd: str, timeout: int = 20) -> str:
    # Use control-byte sentinels to avoid matching echoed command text
    start_b = b"\x1e"  # RS
    end_b = b"\x1f"    # US
    full_cmd = f"printf '\\036'; {cmd}; printf '\\037'"
    tn.write(full_cmd.encode("utf-8") + b"\n")

    deadline = time.time() + timeout
    data = b""
    while time.time() < deadline:
        chunk = tn.read_until(end_b, timeout=max(0.1, deadline - time.time()))
        if not chunk:
            break
        data += chunk
        if end_b in data:
            break

    if start_b in data and end_b in data:
        data = data.split(start_b, 1)[1]
        data = data.rsplit(end_b, 1)[0]
    text = strip_ansi(data.decode("utf-8", errors="ignore"))
    return text.strip("\r\n")


def get_boot_time_str(tn: telnetlib.Telnet) -> str | None:
    now_raw = run_cmd(tn, "date +%s")
    uptime_raw = run_cmd(tn, "cut -d' ' -f1 /proc/uptime")
    try:
        now = int(now_raw.strip().splitlines()[-1])
        uptime = float(uptime_raw.strip().splitlines()[-1])
    except Exception:
        return None
    boot_epoch = now - int(uptime)
    boot_str = run_cmd(tn, f"date -d @{boot_epoch} '+%Y-%m-%d %H:%M:%S'")
    boot_str = boot_str.strip().splitlines()[-1] if boot_str.strip() else ""
    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", boot_str):
        return None
    return boot_str


def list_log_files(
    tn: telnetlib.Telnet, base: str, include_rotated: bool, rotated_limit: int
) -> list[str]:
    if include_rotated:
        # Sort by mtime to keep most recent first
        ls_out = run_cmd(tn, f"ls -1t /var/log/{base}* 2>/dev/null")
        files = [line.strip() for line in ls_out.splitlines() if line.strip()]
        current = [p for p in files if not p.endswith(".gz")]
        rotated = [p for p in files if p.endswith(".gz")]
        if rotated_limit > 0:
            rotated = rotated[:rotated_limit]
        return current + rotated
    return [f"/var/log/{base}"]


def tail_file_cmd(path: str, lines: int) -> str:
    if path.endswith(".gz"):
        return f"zcat {path} | tail -n {lines}"
    return f"tail -n {lines} {path}"


def filter_lines(lines: list[str], since_boot: str | None, keywords: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        keep = True
        if since_boot:
            m = TS_RE.match(line)
            if m:
                ts = m.group(1)
                if ts < since_boot:
                    keep = False
        if keep and keywords:
            low = line.lower()
            if not any(k in low for k in keywords):
                keep = False
        if keep:
            result.append(line)
    return result


def main() -> int:
    args = parse_args()
    logs = [item.strip() for item in args.logs.split(",") if item.strip()]
    keywords = [k.strip().lower() for k in args.grep.split(",") if k.strip()]
    out_dir = Path(args.output_dir) if args.output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    try:
        tn = telnet_connect(args.ip, args.port)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    try:
        boot_str = get_boot_time_str(tn) if args.since_boot else None
        if args.since_boot and not boot_str:
            print("[WARN] Cannot compute boot time; --since-boot ignored", file=sys.stderr)
        for base in logs:
            files = list_log_files(tn, base, args.include_rotated, args.rotated_limit)
            for path in files:
                cmd = tail_file_cmd(path, args.lines)
                content = run_cmd(tn, cmd, timeout=30)
                lines = [l for l in content.splitlines() if l.strip()]
                lines = filter_lines(lines, boot_str, keywords)
                header = f"# {path}"
                if out_dir:
                    safe_name = path.replace("/", "_").strip("_") + ".txt"
                    out_path = out_dir / safe_name
                    out_path.write_text(header + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
                else:
                    print(header)
                    print("\n".join(lines))
                    print("")
    finally:
        try:
            tn.write(b"exit\n")
            time.sleep(0.2)
        except Exception:
            pass
        tn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
