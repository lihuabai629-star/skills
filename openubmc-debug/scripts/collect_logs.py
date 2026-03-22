#!/usr/bin/env python3
"""Collect openUBMC logs over telnet, with optional login handling."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from _cli_common import resolve_telnet_credentials
from _debug_dump import build_debug_dumper
from _json_common import build_json_payload as build_common_json_payload
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

from _telnet_common import close_telnet, run_cmd, telnet_connect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect app/framework logs via telnet.")
    parser.add_argument("--ip", required=True, help="BMC IP")
    parser.add_argument("--port", "--telnet-port", dest="telnet_port", type=int, default=23, help="Telnet port (default: 23)")
    parser.add_argument("--user", "--telnet-user", dest="telnet_user", default="Administrator", help="Telnet username when login prompt appears")
    parser.add_argument("--password", "--telnet-password", dest="telnet_password", default="Admin@9000", help="Telnet password when login prompt appears")
    parser.add_argument("--user-env", "--telnet-user-env", dest="telnet_user_env", default="", help="Environment variable holding the Telnet username")
    parser.add_argument("--password-env", "--telnet-password-env", dest="telnet_password_env", default="", help="Environment variable holding the Telnet password")
    parser.add_argument("--connect-timeout", type=int, default=10, help="Telnet connect timeout seconds")
    parser.add_argument("--prompt-timeout", type=int, default=5, help="Telnet prompt/login timeout seconds")
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
    parser.add_argument("--debug-dump", default="", help="Optional directory for raw Telnet debug artifacts")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text output")
    return parser.parse_args()

def get_boot_time_str(tn) -> str | None:
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


def list_log_files(tn, base: str, include_rotated: bool, rotated_limit: int) -> list[str]:
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


def build_empty_message(path: str, since_boot: str | None, keywords: list[str]) -> str:
    reasons: list[str] = []
    if keywords:
        reasons.append(f"grep={','.join(keywords)}")
    if since_boot:
        reasons.append(f"since_boot>={since_boot}")
    suffix = f" after filters ({'; '.join(reasons)})" if reasons else ""
    return f"[INFO] 0 matching lines for {path}{suffix}"


def build_json_payload(
    args: argparse.Namespace,
    *,
    ok: bool,
    code: str,
    returncode: int,
    logs: list[str],
    keywords: list[str],
    boot_time: str | None,
    warnings: list[str],
    entries: list[dict[str, object]],
    error: str = "",
    written_files: list[str] | None = None,
) -> dict[str, object]:
    payload = build_common_json_payload(
        tool="collect_logs",
        ip=args.ip,
        ok=ok,
        code=code,
        returncode=returncode,
        warnings=warnings,
        error=error,
        request={
            "logs_requested": logs,
            "keywords": keywords,
            "since_boot_requested": args.since_boot,
            "lines": args.lines,
            "include_rotated": args.include_rotated,
            "rotated_limit": args.rotated_limit,
            "output_dir": args.output_dir or "",
        },
        result={
            "boot_time": boot_time,
            "entries": entries,
            "written_files": written_files or [],
        },
    )
    payload.update({
        "ip": args.ip,
        "ok": ok,
        "code": code,
        "returncode": returncode,
        "logs_requested": logs,
        "keywords": keywords,
        "since_boot_requested": args.since_boot,
        "boot_time": boot_time,
        "warnings": warnings,
        "entries": entries,
        "error": error,
        "output_dir": args.output_dir or "",
        "written_files": written_files or [],
    })
    return payload


def emit_json_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    args = parse_args()
    telnet = resolve_telnet_credentials(args)
    debug_dumper = build_debug_dumper(args.debug_dump, secrets=[str(telnet["password"])])
    logs = [item.strip() for item in args.logs.split(",") if item.strip()]
    keywords = [k.strip().lower() for k in args.grep.split(",") if k.strip()]
    out_dir = Path(args.output_dir) if args.output_dir else None
    warnings: list[str] = []
    entries: list[dict[str, object]] = []
    written_files: list[str] = []
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    try:
        tn = telnet_connect(
            args.ip,
            int(telnet["port"]),
            str(telnet["user"]),
            str(telnet["password"]),
            connect_timeout=args.connect_timeout,
            prompt_timeout=args.prompt_timeout,
            debug_dumper=debug_dumper,
            debug_label="collect_logs_connect",
        )
    except (RuntimeError, OSError) as exc:
        if args.json:
            emit_json_payload(
                build_json_payload(
                    args,
                    ok=False,
                    code="telnet_connect_failed",
                    returncode=2,
                    logs=logs,
                    keywords=keywords,
                    boot_time=None,
                    warnings=[],
                    entries=[],
                    error=str(exc),
                )
            )
            return 2
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    try:
        boot_str = get_boot_time_str(tn) if args.since_boot else None
        if args.since_boot and not boot_str:
            warnings.append("Cannot compute boot time; --since-boot ignored")
            if not args.json:
                print("[WARN] Cannot compute boot time; --since-boot ignored", file=sys.stderr)
        for base in logs:
            files = list_log_files(tn, base, args.include_rotated, args.rotated_limit)
            for path in files:
                cmd = tail_file_cmd(path, args.lines)
                content = run_cmd(
                    tn,
                    cmd,
                    timeout=30,
                    debug_dumper=debug_dumper,
                    debug_name=f"log_{Path(path).name}",
                )
                lines = [l for l in content.splitlines() if l.strip()]
                lines = filter_lines(lines, boot_str, keywords)
                header = f"# {path}"
                empty_message = "" if lines else build_empty_message(path, boot_str, keywords)
                body = "\n".join(lines) if lines else empty_message
                entries.append(
                    {
                        "path": path,
                        "header": header,
                        "line_count": len(lines),
                        "lines": lines,
                        "empty": not bool(lines),
                        "empty_message": empty_message,
                    }
                )
                if out_dir:
                    safe_name = path.replace("/", "_").strip("_") + ".txt"
                    out_path = out_dir / safe_name
                    out_path.write_text(header + "\n" + body + "\n", encoding="utf-8")
                    written_files.append(str(out_path))
                else:
                    if not args.json:
                        print(header)
                        print(body)
                        print("")
    finally:
        close_telnet(tn)
    if args.json:
        emit_json_payload(
            build_json_payload(
                args,
                ok=True,
                code="ok",
                returncode=0,
                logs=logs,
                keywords=keywords,
                boot_time=boot_str,
                warnings=warnings,
                entries=entries,
                written_files=written_files,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
