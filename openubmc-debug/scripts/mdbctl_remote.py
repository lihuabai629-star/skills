#!/usr/bin/env python3
"""Run mdbctl commands on openUBMC over SSH with environment-aware fallbacks."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
import subprocess

from _cli_common import resolve_ssh_credentials
from _debug_dump import build_debug_dumper
from _json_common import build_json_payload as build_common_json_payload
from _remote_common import build_posix_shell_command, run_ssh, sanitize_remote_text

CLASS_EXIT_CODES = {
    "remote-command-failed": 10,
    "empty-output": 11,
    "command-not-found": 12,
    "service-unknown": 13,
    "timeout": 14,
    "unknown": 15,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run mdbctl remotely with login-shell/skynet fallbacks.")
    parser.add_argument("--ip", required=True, help="BMC IP")
    parser.add_argument("--user", "--ssh-user", dest="ssh_user", default="Administrator", help="SSH user")
    parser.add_argument("--password", "--ssh-password", dest="ssh_password", default="Admin@9000", help="SSH password")
    parser.add_argument("--port", "--ssh-port", dest="ssh_port", type=int, default=22, help="SSH port")
    parser.add_argument("--user-env", "--ssh-user-env", dest="ssh_user_env", default="", help="Environment variable holding the SSH username")
    parser.add_argument("--password-env", "--ssh-password-env", dest="ssh_password_env", default="", help="Environment variable holding the SSH password")
    parser.add_argument("--identity-file", "--ssh-identity-file", dest="ssh_identity_file", default="", help="SSH private key path")
    parser.add_argument(
        "--mode",
        choices=["auto", "login-shell", "direct-skynet"],
        default="auto",
        help="Execution mode (default: auto)",
    )
    parser.add_argument("--timeout", type=int, default=60, help="SSH timeout seconds")
    parser.add_argument(
        "--print-classification",
        action="store_true",
        help="Print the final failure classification to stderr when the command does not succeed",
    )
    parser.add_argument("--debug-dump", default="", help="Optional directory for raw SSH debug artifacts")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text output")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="mdbctl command, e.g. lsclass or lsobj DiscreteSensor")
    return parser.parse_args()


def normalize_command(parts: list[str]) -> list[str]:
    if parts and parts[0] == "--":
        parts = parts[1:]
    return parts or ["lsclass"]


def build_login_shell_cmd(parts: list[str]) -> str:
    mdbctl_cmd = " ".join(shlex.quote(p) for p in (["mdbctl"] + parts))
    return build_posix_shell_command(mdbctl_cmd, load_profile=True)


def build_direct_skynet_cmd(parts: list[str]) -> str:
    line = " ".join(parts)
    payload = line.replace("\\", "\\\\").replace("'", "'\"'\"'")
    return (
        f"printf '{payload}\\n' | "
        "/opt/bmc/skynet/lua /opt/bmc/apps/mdbctl/service/mdbctl.lua"
    )


def classify_failure(cp: subprocess.CompletedProcess[str], stdout: str, stderr: str) -> str:
    combined = f"{stdout}\n{stderr}".lower()
    if "timed out" in combined or cp.returncode == 124:
        return "timeout"
    if "command not found" in combined:
        return "command-not-found"
    if "serviceunknown" in combined or "not provided by any .service files" in combined:
        return "service-unknown"
    if cp.returncode != 0:
        return "remote-command-failed"
    if not stdout.strip():
        return "empty-output"
    return "unknown"


def is_success(cp: subprocess.CompletedProcess[str], stdout: str, stderr: str) -> bool:
    if cp.returncode != 0:
        return False
    if not stdout.strip():
        return False
    return classify_failure(cp, stdout, stderr) == "unknown"


def build_attempt(mode: str, classification: str, returncode: int) -> dict[str, object]:
    return {
        "mode": mode,
        "classification": classification,
        "returncode": returncode,
    }


def build_json_payload(
    args: argparse.Namespace,
    command: list[str],
    *,
    ok: bool,
    code: str,
    returncode: int,
    selected_mode: str | None,
    stdout: str,
    stderr: str,
    attempts: list[dict[str, object]],
    hint: str,
) -> dict[str, object]:
    payload = build_common_json_payload(
        tool="mdbctl_remote",
        ip=args.ip,
        ok=ok,
        code=code,
        returncode=returncode,
        warnings=[],
        request={
            "requested_mode": args.mode,
            "command_parts": command,
        },
        result={
            "selected_mode": selected_mode,
            "stdout": stdout,
            "stdout_lines": stdout.splitlines(),
            "stderr": stderr,
            "stderr_lines": stderr.splitlines(),
            "attempts": attempts,
            "hint": hint,
        },
    )
    payload.update({
        "ip": args.ip,
        "ok": ok,
        "code": code,
        "returncode": returncode,
        "requested_mode": args.mode,
        "selected_mode": selected_mode,
        "command_parts": command,
        "stdout": stdout,
        "stdout_lines": stdout.splitlines(),
        "stderr": stderr,
        "stderr_lines": stderr.splitlines(),
        "attempts": attempts,
        "hint": hint,
    })
    return payload


def emit_json_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    args = parse_args()
    ssh = resolve_ssh_credentials(args)
    debug_dumper = build_debug_dumper(args.debug_dump, secrets=[str(ssh["password"])])
    command = normalize_command(args.command)

    attempt_specs: list[tuple[str, str]]
    if args.mode == "login-shell":
        attempt_specs = [("login-shell", build_login_shell_cmd(command))]
    elif args.mode == "direct-skynet":
        attempt_specs = [("direct-skynet", build_direct_skynet_cmd(command))]
    else:
        attempt_specs = [
            ("login-shell", build_login_shell_cmd(command)),
            ("direct-skynet", build_direct_skynet_cmd(command)),
        ]

    attempt_results: list[dict[str, object]] = []
    last_cp: subprocess.CompletedProcess | None = None
    last_stdout = ""
    last_stderr = ""

    for mode, remote_cmd in attempt_specs:
        cp = run_ssh(
            args.ip,
            str(ssh["user"]),
            str(ssh["password"]),
            remote_cmd,
            args.timeout,
            port=int(ssh["port"]),
            identity_file=str(ssh["identity_file"]),
            debug_dumper=debug_dumper,
            debug_label=f"mdbctl_{mode}",
        )
        stdout = sanitize_remote_text(cp.stdout or "")
        stderr = sanitize_remote_text(cp.stderr or "")
        success = is_success(cp, stdout, stderr)
        classification = "ok" if success else classify_failure(cp, stdout, stderr)
        attempt_results.append(build_attempt(mode, classification, cp.returncode))
        if success:
            if args.json:
                emit_json_payload(
                    build_json_payload(
                        args,
                        command,
                        ok=True,
                        code="ok",
                        returncode=0,
                        selected_mode=mode,
                        stdout=stdout,
                        stderr=stderr,
                        attempts=attempt_results,
                        hint="",
                    )
                )
                return 0
            if stdout:
                print(stdout)
            if stderr:
                print(stderr, file=sys.stderr)
            return 0
        last_cp = cp
        last_stdout = stdout
        last_stderr = stderr
        detail = stderr or stdout or "no output"
        if not args.json:
            print(f"[WARN] {mode} failed: classification={classification}: {detail}", file=sys.stderr)

    if last_stdout:
        if not args.json:
            print(last_stdout)
    if last_stderr:
        if not args.json:
            print(last_stderr, file=sys.stderr)
    final_classification = classify_failure(last_cp, last_stdout, last_stderr) if last_cp is not None else "unknown"
    hint = "[HINT] mdbctl remote fallback exhausted; try scripts/busctl_remote.py for service/tree/introspect checks."
    exit_code = CLASS_EXIT_CODES.get(final_classification, 15)
    if args.json:
        emit_json_payload(
            build_json_payload(
                args,
                command,
                ok=False,
                code=final_classification,
                returncode=exit_code,
                selected_mode=None,
                stdout=last_stdout,
                stderr=last_stderr,
                attempts=attempt_results,
                hint=hint,
            )
        )
        return exit_code
    if args.print_classification:
        print(f"[RESULT] classification={final_classification}", file=sys.stderr)
    print(hint, file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
