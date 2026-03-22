#!/usr/bin/env python3
"""Sync source-managed skills from their upstream repositories."""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


IGNORE_NAMES = {
    "__pycache__",
    ".DS_Store",
}


@dataclass(frozen=True)
class SkillSource:
    name: str
    repo: str
    ref: str
    path: str
    copies: tuple[tuple[str, str], ...] = ()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=Path(__file__).resolve().parents[1] / "official_skill_sources.json",
        type=Path,
        help="Path to the official skill source manifest.",
    )
    parser.add_argument(
        "--root",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Skills root to update.",
    )
    parser.add_argument(
        "--skills",
        nargs="*",
        help="Optional subset of skills to sync.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only report which skills would change.",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> tuple[dict[str, SkillSource], list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = {}
    for name, entry in payload["sources"].items():
        copies = tuple((item["from"], item["to"]) for item in entry.pop("copies", []))
        sources[name] = SkillSource(name=name, copies=copies, **entry)
    return sources, payload.get("custom_skills", [])


def repo_key(source: SkillSource) -> tuple[str, str]:
    return source.repo, source.ref


def download_repo_zip(repo: str, ref: str, out_dir: Path) -> Path:
    repo_name = repo.split("/", 1)[1]
    zip_path = out_dir / f"{repo_name}-{ref}.zip"
    url = f"https://codeload.github.com/{repo}/zip/refs/heads/{ref}"
    cmd = [
        "curl",
        "-L",
        "--retry",
        "3",
        "--retry-all-errors",
        "-o",
        str(zip_path),
        url,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    extract_dir = out_dir / f"{repo_name}-{ref}"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
    children = [path for path in extract_dir.iterdir() if path.is_dir()]
    if len(children) != 1:
        raise RuntimeError(f"Unexpected archive layout for {repo}@{ref}: {children}")
    return children[0]


def dirs_differ(left: Path, right: Path) -> bool:
    if not left.exists() or not right.exists():
        return left.exists() != right.exists()
    comparison = filecmp.dircmp(left, right, ignore=list(IGNORE_NAMES))
    if comparison.left_only or comparison.right_only or comparison.diff_files or comparison.funny_files:
        return True
    return any(dirs_differ(left / name, right / name) for name in comparison.common_dirs)


def replace_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def build_staged_skill(repo_root: Path, source: SkillSource, staging_root: Path) -> Path:
    src_dir = repo_root / source.path
    if not src_dir.exists():
        raise RuntimeError(f"Upstream path does not exist for {source.name}: {src_dir}")

    staged_dir = staging_root / source.name
    if staged_dir.exists():
        shutil.rmtree(staged_dir)
    shutil.copytree(src_dir, staged_dir)

    for copy_from, copy_to in source.copies:
        copy_src = repo_root / copy_from
        copy_dest = staged_dir / copy_to
        if not copy_src.exists():
            raise RuntimeError(f"Overlay path does not exist for {source.name}: {copy_src}")
        if copy_dest.exists():
            if copy_dest.is_dir():
                shutil.rmtree(copy_dest)
            else:
                copy_dest.unlink()
        if copy_src.is_dir():
            shutil.copytree(copy_src, copy_dest)
        else:
            copy_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copy_src, copy_dest)

    return staged_dir


def main() -> int:
    args = parse_args()
    sources, custom_skills = load_manifest(args.manifest)

    selected = set(args.skills or sources.keys())
    unknown = sorted(selected - set(sources))
    if unknown:
        print(f"Unknown skills in --skills: {', '.join(unknown)}", file=sys.stderr)
        return 2

    if custom_skills:
        print("Custom skills excluded from sync:", ", ".join(custom_skills))

    grouped: dict[tuple[str, str], Path] = {}
    changed: list[str] = []
    unchanged: list[str] = []

    with tempfile.TemporaryDirectory(prefix="sync-official-skills-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)

        for source in sorted((sources[name] for name in selected), key=lambda item: (item.repo, item.name)):
            key = repo_key(source)
            if key not in grouped:
                grouped[key] = download_repo_zip(source.repo, source.ref, temp_dir)
            repo_root = grouped[key]
            src_dir = build_staged_skill(repo_root, source, temp_dir / "staged")
            dest_dir = args.root / source.name
            if dirs_differ(dest_dir, src_dir):
                changed.append(source.name)
                print(f"UPDATE {source.name} <- {source.repo}@{source.ref}:{source.path}")
                if not args.check:
                    replace_tree(src_dir, dest_dir)
            else:
                unchanged.append(source.name)
                print(f"OK     {source.name}")

    print()
    print(f"Changed: {len(changed)}")
    if changed:
        print("  " + ", ".join(changed))
    print(f"Unchanged: {len(unchanged)}")
    if unchanged:
        print("  " + ", ".join(unchanged))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
