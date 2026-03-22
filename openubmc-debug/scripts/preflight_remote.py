#!/usr/bin/env python3
"""Run a quick SSH/Telnet/DBus preflight against an openUBMC BMC."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import shlex
from pathlib import Path

from _cli_common import resolve_ssh_credentials, resolve_telnet_credentials
from _debug_dump import build_debug_dumper
from _json_common import build_json_payload as build_common_json_payload
from _remote_common import build_posix_shell_command, detect_dbus_env, preview_lines, run_ssh, sanitize_remote_text
from _telnet_common import close_telnet, run_cmd, telnet_connect

FAILURE_CODES = {
    "SSH": "ssh_unavailable",
    "DBUS_ENV": "dbus_env_missing",
    "MDBCTL": "mdbctl_unavailable",
    "BUSCTL": "busctl_unavailable",
    "TELNET": "telnet_unavailable",
}
RECOMMENDED_NEXT_STEPS = {
    "ok": "Continue with busctl_remote.py for object queries or collect_logs.py for log queries.",
    "ssh_unavailable": "Fall back to local-only analysis or verify SSH credentials/port before object queries.",
    "dbus_env_missing": "Run busctl_remote.py --print-env or open an interactive SSH shell to inspect DBUS/XDG.",
    "mdbctl_unavailable": "Prefer busctl_remote.py for object queries; do not keep retrying mdbctl.",
    "busctl_unavailable": "Open an interactive SSH shell and re-check DBUS/XDG before retrying busctl.",
    "telnet_unavailable": "Request a log bundle or restore Telnet access before log collection.",
    "preflight_failed": "Inspect failed_checks and follow the first failed check's recommended_next_step.",
}
SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight remote access for openUBMC debug sessions.")
    parser.add_argument("--ip", required=True, help="BMC IP")
    parser.add_argument("--ssh-user", default="Administrator", help="SSH username")
    parser.add_argument("--ssh-password", default="Admin@9000", help="SSH password")
    parser.add_argument("--ssh-port", type=int, default=22, help="SSH port")
    parser.add_argument("--ssh-user-env", default="", help="Environment variable holding the SSH username")
    parser.add_argument("--ssh-password-env", default="", help="Environment variable holding the SSH password")
    parser.add_argument("--ssh-identity-file", default="", help="SSH private key path")
    parser.add_argument("--ssh-timeout", type=int, default=15, help="SSH timeout seconds")
    parser.add_argument("--telnet-port", type=int, default=23, help="Telnet port")
    parser.add_argument("--telnet-user", default="Administrator", help="Telnet username")
    parser.add_argument("--telnet-password", default="Admin@9000", help="Telnet password")
    parser.add_argument("--telnet-user-env", default="", help="Environment variable holding the Telnet username")
    parser.add_argument("--telnet-password-env", default="", help="Environment variable holding the Telnet password")
    parser.add_argument("--telnet-connect-timeout", type=int, default=10, help="Telnet connect timeout seconds")
    parser.add_argument("--telnet-prompt-timeout", type=int, default=5, help="Telnet prompt/login timeout seconds")
    parser.add_argument("--busctl-service", default="bmc.kepler.sensor", help="Service used for busctl tree smoke check")
    parser.add_argument("--debug-dump", default="", help="Optional directory for raw SSH/Telnet debug artifacts")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text sections")
    return parser.parse_args()


def print_section(title: str, status: str, lines: list[str]) -> None:
    print(f"[{title}] {status}")
    for line in lines:
        print(f"  {line}")
    print("")


def build_script_command(script_name: str, parts: list[str]) -> str:
    return " ".join(
        [shlex.quote("python"), shlex.quote(str(SCRIPT_DIR / script_name))]
        + [shlex.quote(part) for part in parts]
    )


def build_ssh_script_flags(args: argparse.Namespace) -> list[str]:
    parts: list[str] = []
    if args.ssh_port != 22:
        parts.extend(["--ssh-port", str(args.ssh_port)])
    if args.ssh_user_env:
        parts.extend(["--ssh-user-env", args.ssh_user_env])
    elif args.ssh_user:
        parts.extend(["--ssh-user", args.ssh_user])
    if args.ssh_password_env:
        parts.extend(["--ssh-password-env", args.ssh_password_env])
    else:
        parts.extend(["--ssh-password-env", "SSH_PASS"])
    if args.ssh_identity_file:
        parts.extend(["--ssh-identity-file", args.ssh_identity_file])
    return parts


def build_telnet_script_flags(args: argparse.Namespace) -> list[str]:
    parts: list[str] = []
    if args.telnet_port != 23:
        parts.extend(["--telnet-port", str(args.telnet_port)])
    if args.telnet_user_env:
        parts.extend(["--telnet-user-env", args.telnet_user_env])
    elif args.telnet_user:
        parts.extend(["--telnet-user", args.telnet_user])
    if args.telnet_password_env:
        parts.extend(["--telnet-password-env", args.telnet_password_env])
    else:
        parts.extend(["--telnet-password-env", "TEL_PASS"])
    return parts


def build_connectivity_command(args: argparse.Namespace) -> str:
    cmd = ["ssh", "-o", "ConnectTimeout=5"]
    if args.ssh_port != 22:
        cmd.extend(["-p", str(args.ssh_port)])
    if args.ssh_user_env:
        target = f"${{{args.ssh_user_env}}}@{args.ip}"
        return " ".join([shlex.quote(part) for part in cmd] + [target, "exit"])
    target = f"{args.ssh_user}@{args.ip}"
    return " ".join([shlex.quote(part) for part in cmd] + [shlex.quote(target), "exit"])


def build_recommended_command(code: str, args: argparse.Namespace) -> str:
    if code in {"ok", "mdbctl_unavailable"}:
        return build_script_command(
            "busctl_remote.py",
            ["--ip", args.ip] + build_ssh_script_flags(args) + ["--action", "tree", "--service", args.busctl_service],
        )
    if code in {"dbus_env_missing", "busctl_unavailable"}:
        return build_script_command(
            "busctl_remote.py",
            ["--ip", args.ip] + build_ssh_script_flags(args) + ["--print-env"],
        )
    if code == "ssh_unavailable":
        return build_connectivity_command(args)
    if code == "telnet_unavailable":
        return " ".join(["telnet", shlex.quote(args.ip), shlex.quote(str(args.telnet_port))])
    return ""


def build_check_result(
    name: str,
    ok: bool,
    lines: list[str],
    args: argparse.Namespace,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    code = "ok" if ok else FAILURE_CODES[name]
    result: dict[str, object] = {
        "ok": ok,
        "status": "OK" if ok else "FAIL",
        "code": code,
        "lines": lines,
        "recommended_next_step": RECOMMENDED_NEXT_STEPS[code],
        "recommended_command": build_recommended_command(code, args),
    }
    if env is not None:
        result["env"] = env
    return result


def emit_json_report(args: argparse.Namespace, checks: dict[str, dict[str, object]]) -> None:
    failed_checks = [name for name, item in checks.items() if not item["ok"]]
    failure_count = len(failed_checks)
    overall_code = "ok" if failure_count == 0 else "preflight_failed"
    overall_recommendation = (
        RECOMMENDED_NEXT_STEPS[checks[failed_checks[0]]["code"]] if failed_checks else RECOMMENDED_NEXT_STEPS["ok"]
    )
    overall_command = checks[failed_checks[0]]["recommended_command"] if failed_checks else checks["SSH"]["recommended_command"]
    payload = build_common_json_payload(
        tool="preflight_remote",
        ip=args.ip,
        ok=failure_count == 0,
        code=overall_code,
        returncode=0 if failure_count == 0 else 1,
        warnings=[],
        request={
            "ssh_port": args.ssh_port,
            "telnet_port": args.telnet_port,
            "busctl_service": args.busctl_service,
        },
        result={
            "overall_ok": failure_count == 0,
            "overall_code": overall_code,
            "failure_count": failure_count,
            "failed_checks": failed_checks,
            "recommended_next_step": overall_recommendation,
            "recommended_command": overall_command,
            "checks": checks,
        },
    )
    payload.update({
        "ip": args.ip,
        "overall_ok": failure_count == 0,
        "overall_code": overall_code,
        "failure_count": failure_count,
        "failed_checks": failed_checks,
        "recommended_next_step": overall_recommendation,
        "recommended_command": overall_command,
        "checks": checks,
    })
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def run_preflight_checks(
    args: argparse.Namespace,
    ssh: dict[str, str | int],
    telnet: dict[str, str | int],
    debug_dumper=None,
) -> dict[str, tuple]:
    with ThreadPoolExecutor(max_workers=4) as executor:
        ssh_future = executor.submit(check_ssh, args, ssh, debug_dumper)
        dbus_future = executor.submit(check_dbus_env, args, ssh, debug_dumper)
        mdbctl_future = executor.submit(check_mdbctl, args, ssh, debug_dumper)
        telnet_future = executor.submit(check_telnet, args, telnet, debug_dumper)

        ssh_result = ssh_future.result()
        dbus_result = dbus_future.result()
        mdbctl_result = mdbctl_future.result()
        telnet_result = telnet_future.result()

        env = dbus_result[2]
        busctl_result = executor.submit(check_busctl, args, ssh, env, debug_dumper).result()

    return {
        "SSH": ssh_result,
        "DBUS_ENV": dbus_result,
        "MDBCTL": mdbctl_result,
        "BUSCTL": busctl_result,
        "TELNET": telnet_result,
    }


def check_ssh(args: argparse.Namespace, ssh: dict[str, str | int], debug_dumper=None) -> tuple[bool, list[str]]:
    remote_cmd = build_posix_shell_command("date '+%F %T %Z'; uptime")
    cp = run_ssh(
        args.ip,
        str(ssh["user"]),
        str(ssh["password"]),
        remote_cmd,
        args.ssh_timeout,
        tty=True,
        port=int(ssh["port"]),
        identity_file=str(ssh["identity_file"]),
        debug_dumper=debug_dumper,
        debug_label="preflight_ssh",
    )
    stdout = sanitize_remote_text(cp.stdout or "")
    stderr = sanitize_remote_text(cp.stderr or "")
    lines = preview_lines(stdout, limit=4)
    if stderr:
        lines.extend(preview_lines(stderr, limit=2))
    if cp.returncode == 0 and lines:
        return True, lines
    return False, lines or [stderr or f"ssh preflight failed with exit code {cp.returncode}"]


def check_dbus_env(args: argparse.Namespace, ssh: dict[str, str | int], debug_dumper=None) -> tuple[bool, list[str], dict[str, str]]:
    env = detect_dbus_env(
        args.ip,
        str(ssh["user"]),
        str(ssh["password"]),
        args.ssh_timeout,
        port=int(ssh["port"]),
        identity_file=str(ssh["identity_file"]),
        debug_dumper=debug_dumper,
        debug_label="preflight_dbus_env",
    )
    lines = [
        f"DBUS_SESSION_BUS_ADDRESS={env.get('DBUS_SESSION_BUS_ADDRESS', '')}",
        f"XDG_RUNTIME_DIR={env.get('XDG_RUNTIME_DIR', '')}",
    ]
    return bool(env.get("DBUS_SESSION_BUS_ADDRESS") and env.get("XDG_RUNTIME_DIR")), lines, env


def check_mdbctl(args: argparse.Namespace, ssh: dict[str, str | int], debug_dumper=None) -> tuple[bool, list[str]]:
    remote_cmd = build_posix_shell_command("mdbctl lsclass", load_profile=True)
    cp = run_ssh(
        args.ip,
        str(ssh["user"]),
        str(ssh["password"]),
        remote_cmd,
        args.ssh_timeout,
        port=int(ssh["port"]),
        identity_file=str(ssh["identity_file"]),
        debug_dumper=debug_dumper,
        debug_label="preflight_mdbctl",
    )
    stdout = sanitize_remote_text(cp.stdout or "")
    stderr = sanitize_remote_text(cp.stderr or "")
    lines = preview_lines(stdout, limit=3)
    if stderr:
        lines.extend(preview_lines(stderr, limit=2))
    if cp.returncode == 0 and stdout:
        return True, lines
    return False, lines or [stderr or f"mdbctl login-shell failed with exit code {cp.returncode}"]


def check_busctl(args: argparse.Namespace, ssh: dict[str, str | int], env: dict[str, str], debug_dumper=None) -> tuple[bool, list[str]]:
    dbus = env.get("DBUS_SESSION_BUS_ADDRESS", "")
    xdg = env.get("XDG_RUNTIME_DIR", "")
    if not (dbus and xdg):
        return False, ["DBUS/XDG env not detected"]
    remote_cmd = (
        f"XDG_RUNTIME_DIR={shlex.quote(xdg)} "
        f"DBUS_SESSION_BUS_ADDRESS={shlex.quote(dbus)} "
        f"busctl --user --no-pager tree {shlex.quote(args.busctl_service)}"
    )
    cp = run_ssh(
        args.ip,
        str(ssh["user"]),
        str(ssh["password"]),
        remote_cmd,
        args.ssh_timeout,
        port=int(ssh["port"]),
        identity_file=str(ssh["identity_file"]),
        debug_dumper=debug_dumper,
        debug_label="preflight_busctl",
    )
    stdout = sanitize_remote_text(cp.stdout or "")
    stderr = sanitize_remote_text(cp.stderr or "")
    lines = preview_lines(stdout, limit=5)
    if stderr:
        lines.extend(preview_lines(stderr, limit=2))
    if cp.returncode == 0 and stdout:
        return True, lines
    return False, lines or [stderr or f"busctl tree failed with exit code {cp.returncode}"]


def check_telnet(args: argparse.Namespace, telnet: dict[str, str | int], debug_dumper=None) -> tuple[bool, list[str]]:
    try:
        tn = telnet_connect(
            args.ip,
            int(telnet["port"]),
            str(telnet["user"]),
            str(telnet["password"]),
            connect_timeout=args.telnet_connect_timeout,
            prompt_timeout=args.telnet_prompt_timeout,
            debug_dumper=debug_dumper,
            debug_label="preflight_telnet_connect",
        )
    except (RuntimeError, OSError) as exc:
        return False, [str(exc)]

    try:
        date_output = run_cmd(tn, "date '+%F %T %Z'", timeout=15, debug_dumper=debug_dumper, debug_name="preflight_telnet_date")
        log_output = run_cmd(
            tn,
            "ls -1 /var/log/app.log /var/log/framework.log 2>/dev/null",
            timeout=15,
            debug_dumper=debug_dumper,
            debug_name="preflight_telnet_logs",
        )
        lines = preview_lines(date_output, limit=1) + preview_lines(log_output, limit=4)
        return bool(lines), lines or ["telnet connected but no prompt output was captured"]
    finally:
        close_telnet(tn)


def main() -> int:
    args = parse_args()
    ssh = resolve_ssh_credentials(args)
    telnet = resolve_telnet_credentials(args)
    debug_dumper = build_debug_dumper(
        args.debug_dump,
        secrets=[str(ssh["password"]), str(telnet["password"])],
    )
    raw_results = run_preflight_checks(args, ssh, telnet, debug_dumper=debug_dumper)
    checks: dict[str, dict[str, object]] = {}

    ok, lines = raw_results["SSH"]
    checks["SSH"] = build_check_result("SSH", ok, lines, args)

    env_ok, env_lines, env = raw_results["DBUS_ENV"]
    checks["DBUS_ENV"] = build_check_result("DBUS_ENV", env_ok, env_lines, args, env=env)

    ok, lines = raw_results["MDBCTL"]
    checks["MDBCTL"] = build_check_result("MDBCTL", ok, lines, args)

    ok, lines = raw_results["BUSCTL"]
    checks["BUSCTL"] = build_check_result("BUSCTL", ok, lines, args)

    ok, lines = raw_results["TELNET"]
    checks["TELNET"] = build_check_result("TELNET", ok, lines, args)

    if args.json:
        emit_json_report(args, checks)
    else:
        for title, result in checks.items():
            print_section(title, str(result["status"]), list(result["lines"]))

    failures = sum(1 for item in checks.values() if not item["ok"])
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
