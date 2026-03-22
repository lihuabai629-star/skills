#!/usr/bin/env python3
"""
Environment setup for the IMA web skill.
"""

import os
import subprocess
import sys
import venv
from pathlib import Path


class SkillEnvironment:
    def __init__(self):
        self.skill_dir = Path(__file__).parent.parent
        self.venv_dir = self.skill_dir / ".venv"
        self.requirements_file = self.skill_dir / "requirements.txt"

        if os.name == "nt":
            self.venv_python = self.venv_dir / "Scripts" / "python.exe"
            self.venv_pip = self.venv_dir / "Scripts" / "pip.exe"
        else:
            self.venv_python = self.venv_dir / "bin" / "python"
            self.venv_pip = self.venv_dir / "bin" / "pip"

    def is_in_skill_venv(self) -> bool:
        if hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        ):
            return Path(sys.prefix) == self.venv_dir
        return False

    def ensure_venv(self) -> bool:
        if self.is_in_skill_venv():
            print("✅ Already running in skill virtual environment")
            return True

        if not self.venv_dir.exists():
            print(f"🔧 Creating virtual environment in {self.venv_dir.name}/")
            try:
                venv.create(self.venv_dir, with_pip=True)
            except Exception as exc:
                print(f"❌ Failed to create venv: {exc}")
                return False
            print("✅ Virtual environment created")

        if not self.requirements_file.exists():
            print("⚠️ No requirements.txt found, skipping dependency installation")
            return True

        print("📦 Installing dependencies...")
        try:
            subprocess.run(
                [str(self.venv_pip), "install", "--upgrade", "pip"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [str(self.venv_pip), "install", "-r", str(self.requirements_file)],
                check=True,
                capture_output=True,
                text=True,
            )
            print("✅ Dependencies installed")
            print("🌐 Installing Chrome for Patchright...")
            try:
                subprocess.run(
                    [str(self.venv_python), "-m", "patchright", "install", "chrome"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                print("✅ Chrome installed")
            except subprocess.CalledProcessError as exc:
                print(f"⚠️ Warning: failed to install Chrome automatically: {exc}")
                print("   You may need to run: python -m patchright install chrome")
            return True
        except subprocess.CalledProcessError as exc:
            print(f"❌ Failed to install dependencies: {exc}")
            return False

    def run_script(self, script_name: str, args: list[str] | None = None) -> int:
        script_path = self.skill_dir / "scripts" / script_name
        if not script_path.exists():
            print(f"❌ Script not found: {script_path}")
            return 1

        if not self.ensure_venv():
            return 1

        cmd = [str(self.venv_python), str(script_path)]
        if args:
            cmd.extend(args)

        result = subprocess.run(cmd)
        return result.returncode


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Setup IMA skill environment")
    parser.add_argument("--check", action="store_true", help="Check current environment")
    parser.add_argument("--run", help="Run a script with the skill venv")
    parser.add_argument("args", nargs="*", help="Arguments to pass to the script")
    args = parser.parse_args()

    env = SkillEnvironment()

    if args.check:
        if env.venv_dir.exists():
            print(f"✅ Virtual environment exists: {env.venv_dir}")
            print(f"   Python: {env.venv_python}")
        else:
            print("❌ No virtual environment found")
        return 0

    if args.run:
        return env.run_script(args.run, args.args)

    return 0 if env.ensure_venv() else 1


if __name__ == "__main__":
    sys.exit(main())
