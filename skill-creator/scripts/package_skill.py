#!/usr/bin/env python3
"""Validate and package a skill directory into a .skill archive."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from quick_validate import validate_skill

EXCLUDED_NAMES = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".DS_Store",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def should_include(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDED_NAMES:
            return False
    if path.name in EXCLUDED_NAMES:
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    return True


def package_skill(skill_dir: str | Path, output_dir: str | Path) -> Path:
    skill_path = Path(skill_dir).resolve()
    output_path = Path(output_dir).resolve()

    valid, message = validate_skill(skill_path)
    if not valid:
        raise SystemExit(message)

    output_path.mkdir(parents=True, exist_ok=True)
    archive_path = output_path / f"{skill_path.name}.skill"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_path.rglob("*")):
            if path.is_dir() or not should_include(path):
                continue
            arcname = Path(skill_path.name) / path.relative_to(skill_path)
            zf.write(path, arcname.as_posix())
    return archive_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and package a skill into a .skill archive.")
    parser.add_argument("skill_dir", help="Path to the skill directory")
    parser.add_argument("output_dir", help="Directory to write the .skill archive into")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    archive = package_skill(args.skill_dir, args.output_dir)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
