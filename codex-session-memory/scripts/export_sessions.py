#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from session_memory import (
    DEFAULT_CODEX_ROOT,
    DEFAULT_EXPORT_ROOT,
    export_session_record,
    find_rollout_by_session_id,
    find_rollout_files,
    latest_rollout,
    load_manifest,
    parse_rollout,
    rollout_session_id,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Codex rollout sessions into Obsidian notes.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true", help="export the latest rollout")
    group.add_argument("--sync-all", action="store_true", help="export all known rollouts")
    group.add_argument("--session-id", help="export the rollout for the given Codex session id")
    group.add_argument("--rollout", help="export a specific rollout jsonl file")
    parser.add_argument("--codex-root", default=str(DEFAULT_CODEX_ROOT), help="path to the Codex state root")
    parser.add_argument("--out-dir", default=str(DEFAULT_EXPORT_ROOT), help="output directory for Obsidian notes")
    parser.add_argument("--limit", type=int, default=0, help="maximum rollouts to process for --sync-all")
    parser.add_argument("--force", action="store_true", help="rewrite notes even if manifest says rollout is unchanged")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    return parser.parse_args()


def rollouts_from_args(args: argparse.Namespace) -> list[Path]:
    codex_root = Path(args.codex_root)
    if args.rollout:
        rollout = Path(args.rollout)
        return [rollout]
    if args.latest:
        rollout = latest_rollout(codex_root)
        return [rollout] if rollout else []
    if args.session_id:
        rollout = find_rollout_by_session_id(codex_root, args.session_id)
        return [rollout] if rollout else []
    rollouts = find_rollout_files(codex_root)
    if args.limit:
        rollouts = rollouts[-args.limit :]
    return rollouts


def should_skip_rollout(rollout: Path, manifest: dict[str, object], force: bool) -> bool:
    if force:
        return False
    session_id = rollout_session_id(rollout)
    if not session_id:
        return False
    session_entry = manifest.get("sessions", {}).get(session_id)
    if not session_entry:
        return False
    return session_entry.get("rollout_mtime") == rollout.stat().st_mtime


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    manifest = load_manifest(out_dir)
    rollouts = rollouts_from_args(args)
    if not rollouts:
        message = {"error": "no matching rollout found"}
        print(json.dumps(message, ensure_ascii=False, indent=2) if args.json else message["error"])
        return 1

    exported: list[dict[str, str]] = []
    skipped: list[str] = []

    for rollout in rollouts:
        if should_skip_rollout(rollout, manifest, args.force):
            skipped.append(str(rollout))
            continue
        record = parse_rollout(rollout, codex_root=args.codex_root)
        exported.append(export_session_record(record, out_dir))
        manifest = load_manifest(out_dir)

    if args.json:
        print(json.dumps({"exported": exported, "skipped": skipped}, ensure_ascii=False, indent=2))
        return 0

    for result in exported:
        print(f"[OK] {result['session_id']} -> {result['note_path']}")
    for skipped_rollout in skipped:
        print(f"[SKIP] unchanged rollout: {skipped_rollout}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
