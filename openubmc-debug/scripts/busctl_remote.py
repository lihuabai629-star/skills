#!/usr/bin/env python3
"""Run busctl --user commands on openUBMC over SSH, auto-detecting DBUS/XDG env."""
from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
from typing import List, Optional

ENV_RE = re.compile(r"^(DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR)=(.*)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run busctl --user remotely with proper DBUS env.")
    parser.add_argument("--ip", required=True, help="BMC IP")
    parser.add_argument("--user", default="Administrator", help="SSH user (default: Administrator)")
    parser.add_argument("--password", default="Admin@9000", help="SSH password (default: Admin@9000)")
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
    parser.add_argument("--print-env", action="store_true", help="Only print detected DBUS/XDG env")
    return parser.parse_args()


def run_ssh(
    ip: str,
    user: str,
    password: str,
    remote_cmd: str,
    timeout: int,
    tty: bool = False,
) -> subprocess.CompletedProcess:
    cmd: List[str] = []
    if password:
        if not shutil.which("sshpass"):
            print("sshpass not found; install it or use key-based auth", file=sys.stderr)
            sys.exit(2)
        cmd += ["sshpass", "-p", password]
    cmd += [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
    ]
    if tty:
        cmd.append("-tt")
    cmd.append(f"{user}@{ip}")
    cmd.append(remote_cmd)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def detect_env(ip: str, user: str, password: str, timeout: int) -> dict:
    # Force a login + interactive shell to capture env
    cmd = 'bash -ilc "printenv | grep -E \\"DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR\\""'
    cp = run_ssh(ip, user, password, cmd, timeout, tty=True)
    combined = (cp.stdout or "") + "\n" + (cp.stderr or "")
    found: dict[str, str] = {}
    for line in combined.splitlines():
        m = ENV_RE.match(line.strip())
        if m:
            found[m.group(1)] = m.group(2)
    return found


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
    # call
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


def main() -> int:
    args = parse_args()

    dbus = args.dbus
    xdg = args.xdg
    if not (dbus and xdg):
        env = detect_env(args.ip, args.user, args.password, args.timeout)
        dbus = dbus or env.get("DBUS_SESSION_BUS_ADDRESS", "")
        xdg = xdg or env.get("XDG_RUNTIME_DIR", "")

    if args.print_env:
        print(f"DBUS_SESSION_BUS_ADDRESS={dbus}")
        print(f"XDG_RUNTIME_DIR={xdg}")
        return 0

    if not (dbus and xdg):
        print("Failed to detect DBUS/XDG env; run interactively and pass --dbus/--xdg.", file=sys.stderr)
        return 2

    busctl_cmd = build_busctl_cmd(args)
    remote_cmd = (
        f"XDG_RUNTIME_DIR={shlex.quote(xdg)} "
        f"DBUS_SESSION_BUS_ADDRESS={shlex.quote(dbus)} "
        f"{busctl_cmd}"
    )
    cp = run_ssh(args.ip, args.user, args.password, remote_cmd, args.timeout, tty=False)
    if cp.stdout:
        print(cp.stdout, end="")
    if cp.stderr:
        # ssh warnings go to stderr; still print for transparency
        print(cp.stderr, end="", file=sys.stderr)
    return cp.returncode


if __name__ == "__main__":
    raise SystemExit(main())
