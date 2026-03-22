#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from auto_sync import DEFAULT_PID_FILE, status_payload
from session_memory import DEFAULT_CODEX_ROOT, DEFAULT_EXPORT_ROOT, load_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Health checks for Codex session memory.")
    parser.add_argument("--codex-root", default=str(DEFAULT_CODEX_ROOT), help="Codex state root")
    parser.add_argument("--out-dir", default=str(DEFAULT_EXPORT_ROOT), help="Obsidian export root")
    parser.add_argument("--pid-file", default=str(DEFAULT_PID_FILE), help="pid file for daemon mode")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    return parser.parse_args()


def build_check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def collect_checks(*, codex_root: Path, out_dir: Path, pid_file: Path) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    checks.append(
        build_check(
            "codex_root",
            "ok" if codex_root.exists() else "fail",
            str(codex_root),
        )
    )
    checks.append(
        build_check(
            "export_root",
            "ok" if out_dir.exists() else "fail",
            str(out_dir),
        )
    )

    try:
        manifest = load_manifest(out_dir)
        manifest_ok = isinstance(manifest.get("sessions"), dict) and isinstance(manifest.get("rollouts"), dict)
        checks.append(
            build_check(
                "manifest",
                "ok" if manifest_ok else "fail",
                f"sessions={len(manifest.get('sessions', {}))} rollouts={len(manifest.get('rollouts', {}))}",
            )
        )
    except Exception as exc:
        checks.append(build_check("manifest", "fail", str(exc)))

    global_store = codex_root / "memories" / "global" / "lessons"
    checks.append(
        build_check(
            "global_store",
            "ok" if global_store.exists() else "fail",
            str(global_store),
        )
    )

    daemon = status_payload(pid_file)
    if daemon["running"]:
        checks.append(build_check("daemon_status", "ok", f"pid={daemon['pid']}"))
    elif daemon["pid"] is None:
        checks.append(build_check("daemon_status", "ok", "no pid file present"))
    else:
        checks.append(build_check("daemon_status", "fail", f"stale_or_mismatched_pid={daemon['pid']}"))

    return checks


def summarize(checks: list[dict[str, str]]) -> dict[str, Any]:
    failing = [check for check in checks if check["status"] == "fail"]
    return {
        "status": "ok" if not failing else "fail",
        "checks": checks,
    }


def main() -> int:
    args = parse_args()
    payload = summarize(
        collect_checks(
            codex_root=Path(args.codex_root),
            out_dir=Path(args.out_dir),
            pid_file=Path(args.pid_file),
        )
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for check in payload["checks"]:
            print(f"[{check['status']}] {check['name']}: {check['detail']}")
        print(f"overall={payload['status']}")
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
