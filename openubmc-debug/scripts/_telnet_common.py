#!/usr/bin/env python3
"""Shared Telnet helpers for openUBMC log-oriented scripts."""
from __future__ import annotations

import re
import time
from _minimal_telnet import TelnetClient

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
LOGIN_RE = re.compile(br"(login:|username:)", re.IGNORECASE)
PASSWORD_RE = re.compile(br"password:", re.IGNORECASE)
SHELL_PROMPT_RE = re.compile(br"(?m)[^\n]*[#$] ?$")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _expect(
    tn: TelnetClient,
    patterns: list[re.Pattern[bytes]],
    timeout: int,
    debug_dumper=None,
    debug_name: str = "telnet_expect",
) -> tuple[int, bytes]:
    index, _match, data = tn.expect(patterns, timeout=timeout)
    if debug_dumper is not None:
        debug_dumper.write_bytes(
            debug_name,
            "raw",
            data,
            metadata={
                "stage": debug_name,
                "artifact": "raw",
                "transport": "telnet",
            },
        )
    return index, data


def telnet_connect(
    ip: str,
    port: int,
    user: str,
    password: str,
    connect_timeout: int = 10,
    prompt_timeout: int = 5,
    debug_dumper=None,
    debug_label: str = "telnet_connect",
) -> TelnetClient:
    try:
        tn = TelnetClient(ip, port, timeout=connect_timeout)
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc

    index, data = _expect(
        tn,
        [LOGIN_RE, SHELL_PROMPT_RE],
        timeout=prompt_timeout,
        debug_dumper=debug_dumper,
        debug_name=f"{debug_label}_initial",
    )
    if index == -1:
        tn.write(b"\n")
        index, data = _expect(
            tn,
            [LOGIN_RE, SHELL_PROMPT_RE],
            timeout=prompt_timeout,
            debug_dumper=debug_dumper,
            debug_name=f"{debug_label}_retry",
        )

    if index == 1:
        return tn

    if index != 0:
        raise RuntimeError("Telnet did not reach a login prompt or shell prompt")

    if not user:
        raise RuntimeError("Telnet login prompt detected but no username was provided")

    tn.write(user.encode("utf-8") + b"\n")
    index, data = _expect(
        tn,
        [PASSWORD_RE, SHELL_PROMPT_RE, LOGIN_RE],
        timeout=prompt_timeout,
        debug_dumper=debug_dumper,
        debug_name=f"{debug_label}_username",
    )
    if index == 0:
        tn.write(password.encode("utf-8") + b"\n")
        index, data = _expect(
            tn,
            [SHELL_PROMPT_RE, LOGIN_RE, PASSWORD_RE],
            timeout=prompt_timeout,
            debug_dumper=debug_dumper,
            debug_name=f"{debug_label}_password",
        )
        if index != 0:
            raise RuntimeError("Telnet login failed; shell prompt was not reached after password entry")
        return tn
    if index == 1:
        return tn
    raise RuntimeError("Telnet login failed; username was not accepted")


def run_cmd(tn: TelnetClient, cmd: str, timeout: int = 20, debug_dumper=None, debug_name: str = "telnet") -> str:
    start_b = b"\x1e"  # RS
    end_b = b"\x1f"    # US
    full_cmd = f"printf '\\036'; {cmd}; printf '\\037'"
    if debug_dumper is not None:
        debug_dumper.write_text(
            debug_name,
            "command",
            cmd,
            metadata={
                "stage": debug_name,
                "artifact": "command",
                "transport": "telnet",
                "command_summary": cmd,
            },
        )
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

    if debug_dumper is not None:
        debug_dumper.write_bytes(
            debug_name,
            "raw",
            data,
            metadata={
                "stage": debug_name,
                "artifact": "raw",
                "transport": "telnet",
                "command_summary": cmd,
            },
        )
    if start_b in data and end_b in data:
        data = data.split(start_b, 1)[1]
        data = data.rsplit(end_b, 1)[0]
    text = strip_ansi(data.decode("utf-8", errors="ignore"))
    cooked = text.strip("\r\n")
    if debug_dumper is not None:
        debug_dumper.write_text(
            debug_name,
            "text",
            cooked,
            metadata={
                "stage": debug_name,
                "artifact": "text",
                "transport": "telnet",
                "command_summary": cmd,
            },
        )
    return cooked


def close_telnet(tn: TelnetClient) -> None:
    try:
        tn.write(b"exit\n")
        time.sleep(0.2)
    except Exception:
        pass
    tn.close()
