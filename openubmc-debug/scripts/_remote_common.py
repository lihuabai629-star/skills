#!/usr/bin/env python3
"""Shared SSH helpers for openUBMC remote scripts."""
from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
from typing import List

ENV_RE = re.compile(r"^(DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR)=(.*)$")
HOST_KEY_RE = re.compile(
    r"Warning: Permanently added '.*?' \([^)]+\) to the list of known hosts\.\s*",
    re.DOTALL,
)
LEGAL_BANNER_RE = re.compile(
    r"WARNING! This system is PRIVATE and PROPRIETARY.*?law enforcement and other purposes\.\s*",
    re.DOTALL,
)
DEBUG_SHELL_RE = re.compile(
    r"\*{10,}\s*Debug Shell\s*Copyright\(C\) 2023\s*\*{10,}\s*",
    re.DOTALL,
)
NOISE_MARKERS = (
    "bash: can't access tty; job control turned off",
)


def sanitize_remote_text(text: str) -> str:
    if not text:
        return ""
    text = HOST_KEY_RE.sub("", text)
    text = LEGAL_BANNER_RE.sub("", text)
    text = DEBUG_SHELL_RE.sub("", text)

    cleaned: list[str] = []
    for raw in text.replace("\r", "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if any(marker in line for marker in NOISE_MARKERS):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).rstrip()


def run_ssh(
    ip: str,
    user: str,
    password: str,
    remote_cmd: str,
    timeout: int,
    tty: bool = False,
    port: int = 22,
    identity_file: str = "",
    debug_dumper=None,
    debug_label: str = "ssh",
) -> subprocess.CompletedProcess[str]:
    cmd: List[str] = []
    if password:
        if not shutil.which("sshpass"):
            print("sshpass not found; install it or use key-based auth", file=sys.stderr)
            sys.exit(2)
        cmd += ["sshpass", "-p", password]
    cmd += [
        "ssh",
        "-p",
        str(port),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
    ]
    if identity_file:
        cmd += ["-i", identity_file, "-o", "IdentitiesOnly=yes"]
    if tty:
        cmd.append("-tt")
    cmd.append(f"{user}@{ip}")
    cmd.append(remote_cmd)
    if debug_dumper is not None:
        debug_dumper.write_text(
            debug_label,
            "command",
            " ".join(shlex.quote(part) for part in cmd),
            metadata={
                "stage": debug_label,
                "artifact": "command",
                "transport": "ssh",
                "command_summary": remote_cmd,
            },
        )
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        cp = subprocess.CompletedProcess(
            args=cmd,
            returncode=124,
            stdout="",
            stderr=f"SSH command timed out after {timeout}s",
        )
    if debug_dumper is not None:
        metadata = {
            "stage": debug_label,
            "transport": "ssh",
            "returncode": cp.returncode,
            "command_summary": remote_cmd,
        }
        debug_dumper.write_text(debug_label, "stdout", cp.stdout or "", metadata={**metadata, "artifact": "stdout"})
        debug_dumper.write_text(debug_label, "stderr", cp.stderr or "", metadata={**metadata, "artifact": "stderr"})
    return cp


def build_posix_shell_command(inner: str, *, load_profile: bool = False) -> str:
    commands: list[str] = []
    if load_profile:
        commands.append(". /etc/profile >/dev/null 2>&1")
    commands.append(inner)
    return "sh -lc " + shlex.quote("; ".join(commands))


def detect_dbus_env(
    ip: str,
    user: str,
    password: str,
    timeout: int,
    port: int = 22,
    identity_file: str = "",
    debug_dumper=None,
    debug_label: str = "dbus_env",
) -> dict[str, str]:
    cmd = build_posix_shell_command('printenv | grep -E "DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR"')
    cp = run_ssh(
        ip,
        user,
        password,
        cmd,
        timeout,
        tty=True,
        port=port,
        identity_file=identity_file,
        debug_dumper=debug_dumper,
        debug_label=debug_label,
    )
    combined = sanitize_remote_text((cp.stdout or "") + "\n" + (cp.stderr or ""))
    found: dict[str, str] = {}
    for line in combined.splitlines():
        match = ENV_RE.match(line.strip())
        if match:
            found[match.group(1)] = match.group(2)
    return found


def filter_text_output(
    text: str,
    grep_keywords: list[str],
    head: int | None = None,
    tail: int | None = None,
) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if grep_keywords:
        lowered = [item.lower() for item in grep_keywords]
        lines = [line for line in lines if any(keyword in line.lower() for keyword in lowered)]
    if head is not None:
        lines = lines[:head]
    if tail is not None:
        lines = lines[-tail:]
    return "\n".join(lines).strip()


def build_filter_notice(grep_keywords: list[str], head: int | None, tail: int | None) -> str:
    parts: list[str] = []
    if grep_keywords:
        parts.append(f"grep={','.join(grep_keywords)}")
    if head is not None:
        parts.append(f"head={head}")
    if tail is not None:
        parts.append(f"tail={tail}")
    if not parts:
        return "[INFO] 0 matching lines after filters"
    return f"[INFO] 0 matching lines after filters ({'; '.join(parts)})"


def preview_lines(text: str, limit: int = 5, width: int = 180) -> list[str]:
    preview: list[str] = []
    for raw in text.splitlines()[:limit]:
        line = raw.strip()
        if not line:
            continue
        if len(line) > width:
            line = line[: width - 3] + "..."
        preview.append(line)
    return preview
