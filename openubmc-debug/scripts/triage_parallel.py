#!/usr/bin/env python3
"""Build or launch a parallel openUBMC triage session plan."""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from _json_common import build_json_payload as build_common_json_payload

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path("/home/workspace/source")
NOTEBOOKLM_RUN = Path("/root/.codex/skills/notebooklm-skill/scripts/run.py")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or launch parallel openUBMC debug lanes.")
    parser.add_argument("--ip", required=True, help="BMC IP")
    parser.add_argument("--keyword", default="", help="Primary local-code or object keyword")
    parser.add_argument("--service", default="bmc.kepler.sensor", help="DBus service for SSH object lane")
    parser.add_argument("--log", default="framework.log", help="Primary Telnet log target")
    parser.add_argument("--grep", default="", help="Keyword passed to collect_logs.py")
    parser.add_argument("--lines", type=int, default=200, help="Line count for log collection")
    parser.add_argument("--ssh-port", type=int, default=22, help="SSH port")
    parser.add_argument("--ssh-user", default="Administrator", help="SSH username")
    parser.add_argument("--ssh-user-env", default="", help="Environment variable holding the SSH username")
    parser.add_argument("--ssh-password-env", default="", help="Environment variable holding the SSH password")
    parser.add_argument("--ssh-identity-file", default="", help="SSH private key path")
    parser.add_argument("--telnet-port", type=int, default=23, help="Telnet port")
    parser.add_argument("--telnet-user", default="Administrator", help="Telnet username")
    parser.add_argument("--telnet-user-env", default="", help="Environment variable holding the Telnet username")
    parser.add_argument("--telnet-password-env", default="", help="Environment variable holding the Telnet password")
    parser.add_argument("--notebooklm-question", default="", help="Optional NotebookLM background question")
    parser.add_argument("--notebooklm-notebook-id", default="", help="NotebookLM notebook id")
    parser.add_argument("--notebooklm-notebook-url", default="", help="NotebookLM notebook url")
    parser.add_argument("--notebooklm-show-browser", action="store_true", help="Show NotebookLM browser")
    parser.add_argument("--tmux-session", default="", help="Override tmux session name")
    parser.add_argument("--launch-tmux", action="store_true", help="Launch lanes in a detached tmux session when available")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser.parse_args(argv)


def quote_cmd(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def build_ssh_flags(args: argparse.Namespace) -> list[str]:
    flags: list[str] = []
    if args.ssh_port != 22:
        flags.extend(["--ssh-port", str(args.ssh_port)])
    if args.ssh_user_env:
        flags.extend(["--ssh-user-env", args.ssh_user_env])
    elif args.ssh_user:
        flags.extend(["--ssh-user", args.ssh_user])
    if args.ssh_password_env:
        flags.extend(["--ssh-password-env", args.ssh_password_env])
    else:
        flags.extend(["--ssh-password-env", "SSH_PASS"])
    if args.ssh_identity_file:
        flags.extend(["--ssh-identity-file", args.ssh_identity_file])
    return flags


def build_telnet_flags(args: argparse.Namespace) -> list[str]:
    flags: list[str] = []
    if args.telnet_port != 23:
        flags.extend(["--telnet-port", str(args.telnet_port)])
    if args.telnet_user_env:
        flags.extend(["--telnet-user-env", args.telnet_user_env])
    elif args.telnet_user:
        flags.extend(["--telnet-user", args.telnet_user])
    if args.telnet_password_env:
        flags.extend(["--telnet-password-env", args.telnet_password_env])
    else:
        flags.extend(["--telnet-password-env", "TEL_PASS"])
    return flags


def build_local_lane(args: argparse.Namespace) -> dict[str, object]:
    keyword = args.keyword or "<keyword>"
    quoted_keyword = shlex.quote(keyword)
    if not (quoted_keyword.startswith("'") and quoted_keyword.endswith("'")):
        quoted_keyword = f"'{keyword}'"
    command = f"rg -n {quoted_keyword} {REPO_ROOT}/"
    return {
        "name": "local",
        "title": "Local Code",
        "transport": "local",
        "background": False,
        "commands": [command],
        "command": command,
    }


def build_ssh_lane(args: argparse.Namespace) -> dict[str, object]:
    preflight = quote_cmd(
        ["python", str(SCRIPT_DIR / "preflight_remote.py"), "--ip", args.ip] + build_ssh_flags(args) + build_telnet_flags(args)
    )
    busctl_parts = [
        "python",
        str(SCRIPT_DIR / "busctl_remote.py"),
        "--ip",
        args.ip,
        *build_ssh_flags(args),
        "--action",
        "tree",
        "--service",
        args.service,
    ]
    grep_keyword = args.keyword or ""
    if grep_keyword:
        busctl_parts.extend(["--grep", grep_keyword, "--head", "20"])
    busctl = quote_cmd(busctl_parts)
    commands = [preflight, busctl]
    return {
        "name": "ssh",
        "title": "SSH Object Lane",
        "transport": "ssh",
        "background": False,
        "commands": commands,
        "command": "\n".join(commands),
    }


def build_telnet_lane(args: argparse.Namespace) -> dict[str, object]:
    grep_value = args.grep or args.keyword
    collect_parts = [
        "python",
        str(SCRIPT_DIR / "collect_logs.py"),
        "--ip",
        args.ip,
        *build_telnet_flags(args),
        "--logs",
        args.log,
        "--lines",
        str(args.lines),
    ]
    if grep_value:
        collect_parts.extend(["--grep", grep_value])
    collect = quote_cmd(collect_parts)
    return {
        "name": "telnet",
        "title": "Telnet Log Lane",
        "transport": "telnet",
        "background": False,
        "commands": [collect],
        "command": collect,
    }


def build_notebooklm_lane(args: argparse.Namespace) -> dict[str, object]:
    ask_parts = [
        "python",
        str(NOTEBOOKLM_RUN),
        "ask_question.py",
        "--question",
        args.notebooklm_question,
    ]
    if args.notebooklm_notebook_id:
        ask_parts.extend(["--notebook-id", args.notebooklm_notebook_id])
    if args.notebooklm_notebook_url:
        ask_parts.extend(["--notebook-url", args.notebooklm_notebook_url])
    if args.notebooklm_show_browser:
        ask_parts.append("--show-browser")
    ask_cmd = quote_cmd(ask_parts)
    return {
        "name": "notebooklm",
        "title": "NotebookLM Background",
        "transport": "notebooklm",
        "background": True,
        "commands": [ask_cmd],
        "command": ask_cmd,
    }


def default_session_name(ip: str) -> str:
    return f"openubmc-debug-{ip.replace('.', '-')}"


def build_session_plan(args: argparse.Namespace) -> dict[str, object]:
    lanes = [
        build_local_lane(args),
        build_ssh_lane(args),
        build_telnet_lane(args),
    ]
    if args.notebooklm_question:
        lanes.append(build_notebooklm_lane(args))
    session_name = args.tmux_session or default_session_name(args.ip)
    return {
        "session_name": session_name,
        "mode": "manual",
        "lanes": lanes,
    }


def launch_tmux_session(plan: dict[str, object]) -> str:
    session_name = str(plan["session_name"])
    lanes = list(plan["lanes"])
    if not shutil.which("tmux"):
        raise RuntimeError("tmux is not available in PATH")

    first = lanes[0]
    subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "-n", str(first["name"])], check=True)
    first_commands = list(first.get("commands") or [first["command"]])
    for command in first_commands:
        subprocess.run(["tmux", "send-keys", "-t", f"{session_name}:{first['name']}", str(command), "C-m"], check=True)

    for lane in lanes[1:]:
        subprocess.run(["tmux", "new-window", "-t", session_name, "-n", str(lane["name"])], check=True)
        lane_commands = list(lane.get("commands") or [lane["command"]])
        for command in lane_commands:
            subprocess.run(["tmux", "send-keys", "-t", f"{session_name}:{lane['name']}", str(command), "C-m"], check=True)
    return session_name


def emit_text_plan(plan: dict[str, object], launched: bool, warnings: list[str]) -> None:
    for warning in warnings:
        print(f"[WARN] {warning}")
    print(f"session: {plan['session_name']}")
    print(f"mode: {plan['mode']}")
    print("")
    for lane in plan["lanes"]:
        suffix = " (background)" if lane["background"] else ""
        print(f"[{lane['name']}] {lane['title']}{suffix}")
        for command in lane["commands"]:
            print(f"  {command}")
        print("")
    if launched:
        print(f"attach: tmux attach -t {plan['session_name']}")


def build_json_report(plan: dict[str, object], args: argparse.Namespace, launched: bool, warnings: list[str]) -> dict[str, object]:
    payload = build_common_json_payload(
        tool="triage_parallel",
        ip=args.ip,
        ok=True,
        code="ok",
        returncode=0,
        warnings=warnings,
        request={
            "ip": args.ip,
            "keyword": args.keyword,
            "service": args.service,
            "log": args.log,
            "grep": args.grep,
            "launch_tmux": args.launch_tmux,
            "notebooklm_enabled": bool(args.notebooklm_question),
        },
        result={
            "mode": plan["mode"],
            "session_name": plan["session_name"],
            "launched": launched,
            "lane_names": [lane["name"] for lane in plan["lanes"]],
            "lanes": plan["lanes"],
        },
    )
    payload.update(
        {
            "mode": plan["mode"],
            "session_name": plan["session_name"],
            "launched": launched,
            "lane_names": [lane["name"] for lane in plan["lanes"]],
            "lanes": plan["lanes"],
        }
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_session_plan(args)
    warnings: list[str] = []
    launched = False

    if args.launch_tmux:
        if shutil.which("tmux"):
            launch_tmux_session(plan)
            plan["mode"] = "tmux"
            launched = True
        else:
            warnings.append("tmux not found; falling back to manual lane plan.")

    if args.json:
        print(json.dumps(build_json_report(plan, args, launched, warnings), indent=2, ensure_ascii=False))
        return 0

    emit_text_plan(plan, launched, warnings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
