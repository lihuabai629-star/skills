#!/usr/bin/env python3
"""Run busctl --user commands on openUBMC over SSH, auto-detecting DBUS/XDG env."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from _cli_common import resolve_ssh_credentials
from _debug_dump import build_debug_dumper
from _json_common import build_json_payload as build_common_json_payload
from _remote_common import (
    build_filter_notice,
    detect_dbus_env,
    filter_text_output,
    run_ssh,
    sanitize_remote_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run busctl --user remotely with proper DBUS env.")
    parser.add_argument("--ip", required=True, help="BMC IP")
    parser.add_argument("--user", "--ssh-user", dest="ssh_user", default="Administrator", help="SSH user")
    parser.add_argument("--password", "--ssh-password", dest="ssh_password", default="Admin@9000", help="SSH password")
    parser.add_argument("--port", "--ssh-port", dest="ssh_port", type=int, default=22, help="SSH port")
    parser.add_argument("--user-env", "--ssh-user-env", dest="ssh_user_env", default="", help="Environment variable holding the SSH username")
    parser.add_argument("--password-env", "--ssh-password-env", dest="ssh_password_env", default="", help="Environment variable holding the SSH password")
    parser.add_argument("--identity-file", "--ssh-identity-file", dest="ssh_identity_file", default="", help="SSH private key path")
    parser.add_argument(
        "--action",
        choices=["list", "tree", "introspect", "call"],
        default="tree",
        help="busctl action (default: tree)",
    )
    parser.add_argument("--service", default="bmc.kepler.hwproxy", help="DBus service name")
    parser.add_argument("--path", default="/", help="DBus object path for introspect/call")
    parser.add_argument("--interface", default="", help="Interface name for call")
    parser.add_argument("--method", default="", help="Method name for call")
    parser.add_argument("--signature", default="", help="Signature string for call (use '' for no-arg calls)")
    parser.add_argument("--args", nargs="*", default=[], help="Arguments for call")
    parser.add_argument("--dbus", default="", help="Override DBUS_SESSION_BUS_ADDRESS")
    parser.add_argument("--xdg", default="", help="Override XDG_RUNTIME_DIR")
    parser.add_argument("--timeout", type=int, default=120, help="SSH timeout seconds")
    parser.add_argument(
        "--grep",
        default="",
        help="Comma-separated keywords to keep from stdout (case-insensitive)",
    )
    limit_group = parser.add_mutually_exclusive_group()
    limit_group.add_argument("--head", type=int, default=None, help="Keep the first N stdout lines after filtering")
    limit_group.add_argument("--tail", type=int, default=None, help="Keep the last N stdout lines after filtering")
    parser.add_argument("--print-env", action="store_true", help="Only print detected DBUS/XDG env")
    parser.add_argument("--debug-dump", default="", help="Optional directory for raw SSH debug artifacts")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text output")
    return parser.parse_args()


def build_busctl_cmd(args: argparse.Namespace) -> str:
    if args.action == "list":
        return "busctl --user --no-pager list"
    if args.action == "tree":
        return f"busctl --user --no-pager tree {shlex.quote(args.service)}"
    if args.action == "introspect":
        return (
            f"busctl --user --no-pager introspect {shlex.quote(args.service)} "
            f"{shlex.quote(args.path)}"
        )
    if not (args.interface and args.method):
        raise SystemExit("call requires --interface and --method (use --signature '' for no-arg calls)")
    parts = [
        "busctl",
        "--user",
        "call",
        args.service,
        args.path,
        args.interface,
        args.method,
        args.signature,
    ] + args.args
    return " ".join(shlex.quote(p) for p in parts)


def print_clean(stdout: str, stderr: str) -> None:
    clean_out = sanitize_remote_text(stdout)
    clean_err = sanitize_remote_text(stderr)
    if clean_out:
        print(clean_out)
    if clean_err:
        print(clean_err, file=sys.stderr)


def filter_stdout(stdout: str, grep_arg: str, head: int | None, tail: int | None) -> str:
    grep_keywords = [item.strip() for item in grep_arg.split(",") if item.strip()]
    if not (grep_keywords or head is not None or tail is not None):
        return stdout
    filtered = filter_text_output(stdout, grep_keywords=grep_keywords, head=head, tail=tail)
    if filtered:
        return filtered
    return build_filter_notice(grep_keywords, head, tail)


def build_json_payload(
    args: argparse.Namespace,
    *,
    ok: bool,
    code: str,
    returncode: int,
    stdout: str,
    stderr: str,
    dbus: str,
    xdg: str,
) -> dict[str, object]:
    payload = build_common_json_payload(
        tool="busctl_remote",
        ip=args.ip,
        ok=ok,
        code=code,
        returncode=returncode,
        warnings=[],
        request={
            "action": args.action,
            "service": args.service,
            "path": args.path,
            "interface": args.interface,
            "method": args.method,
            "print_env": args.print_env,
            "grep": [item.strip() for item in args.grep.split(",") if item.strip()],
            "head": args.head,
            "tail": args.tail,
        },
        result={
            "stdout": stdout,
            "stdout_lines": stdout.splitlines(),
            "stderr": stderr,
            "stderr_lines": stderr.splitlines(),
            "dbus_env": {
                "DBUS_SESSION_BUS_ADDRESS": dbus,
                "XDG_RUNTIME_DIR": xdg,
            },
        },
    )
    payload.update({
        "ip": args.ip,
        "ok": ok,
        "code": code,
        "returncode": returncode,
        "action": args.action,
        "service": args.service,
        "path": args.path,
        "interface": args.interface,
        "method": args.method,
        "print_env": args.print_env,
        "stdout": stdout,
        "stdout_lines": stdout.splitlines(),
        "stderr": stderr,
        "stderr_lines": stderr.splitlines(),
        "dbus_env": {
            "DBUS_SESSION_BUS_ADDRESS": dbus,
            "XDG_RUNTIME_DIR": xdg,
        },
    })
    return payload


def emit_json_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    args = parse_args()
    ssh = resolve_ssh_credentials(args)
    debug_dumper = build_debug_dumper(args.debug_dump, secrets=[str(ssh["password"])])

    dbus = args.dbus
    xdg = args.xdg
    if not (dbus and xdg):
        env = detect_dbus_env(
            args.ip,
            str(ssh["user"]),
            str(ssh["password"]),
            args.timeout,
            port=int(ssh["port"]),
            identity_file=str(ssh["identity_file"]),
            debug_dumper=debug_dumper,
            debug_label="busctl_env",
        )
        dbus = dbus or env.get("DBUS_SESSION_BUS_ADDRESS", "")
        xdg = xdg or env.get("XDG_RUNTIME_DIR", "")

    if args.print_env:
        stdout = f"DBUS_SESSION_BUS_ADDRESS={dbus}\nXDG_RUNTIME_DIR={xdg}".strip()
        if args.json:
            emit_json_payload(
                build_json_payload(
                    args,
                    ok=bool(dbus and xdg),
                    code="ok" if (dbus and xdg) else "dbus_env_missing",
                    returncode=0,
                    stdout=stdout,
                    stderr="",
                    dbus=dbus,
                    xdg=xdg,
                )
            )
            return 0
        print(stdout)
        return 0

    if not (dbus and xdg):
        stderr = "Failed to detect DBUS/XDG env; run interactively and pass --dbus/--xdg."
        if args.json:
            emit_json_payload(
                build_json_payload(
                    args,
                    ok=False,
                    code="dbus_env_missing",
                    returncode=2,
                    stdout="",
                    stderr=stderr,
                    dbus=dbus,
                    xdg=xdg,
                )
            )
            return 2
        print(stderr, file=sys.stderr)
        return 2

    busctl_cmd = build_busctl_cmd(args)
    remote_cmd = (
        f"XDG_RUNTIME_DIR={shlex.quote(xdg)} "
        f"DBUS_SESSION_BUS_ADDRESS={shlex.quote(dbus)} "
        f"{busctl_cmd}"
    )
    cp = run_ssh(
        args.ip,
        str(ssh["user"]),
        str(ssh["password"]),
        remote_cmd,
        args.timeout,
        tty=False,
        port=int(ssh["port"]),
        identity_file=str(ssh["identity_file"]),
        debug_dumper=debug_dumper,
        debug_label="busctl",
    )
    clean_stdout = sanitize_remote_text(cp.stdout or "")
    clean_stderr = sanitize_remote_text(cp.stderr or "")
    filtered_stdout = filter_stdout(clean_stdout, args.grep, args.head, args.tail)
    if args.json:
        emit_json_payload(
            build_json_payload(
                args,
                ok=cp.returncode == 0,
                code="ok" if cp.returncode == 0 else "remote_command_failed",
                returncode=cp.returncode,
                stdout=filtered_stdout,
                stderr=clean_stderr,
                dbus=dbus,
                xdg=xdg,
            )
        )
        return cp.returncode
    print_clean(filtered_stdout, clean_stderr)
    return cp.returncode


if __name__ == "__main__":
    raise SystemExit(main())
