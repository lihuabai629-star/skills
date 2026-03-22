#!/usr/bin/env python3
"""Shared machine-readable payload helpers for openUBMC debug scripts."""
from __future__ import annotations

SCHEMA_VERSION = "openubmc-debug.v1"


def build_json_payload(
    *,
    tool: str,
    ip: str,
    ok: bool,
    code: str,
    returncode: int,
    request: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
    warnings: list[str] | None = None,
    error: str = "",
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": tool,
        "ip": ip,
        "ok": ok,
        "code": code,
        "returncode": returncode,
        "warnings": warnings or [],
        "error": error,
        "request": request or {},
        "result": result or {},
    }
