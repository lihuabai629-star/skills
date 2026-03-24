import os
import subprocess
import tempfile
import unittest
from pathlib import Path


INSTALLER_PATH = Path("/root/.codex/skills/ima/install.sh")


class InstallScriptTests(unittest.TestCase):
    def run_installer(self, codex_home: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CODEX_HOME"] = str(codex_home)
        env["HOME"] = str(codex_home / "home")
        return subprocess.run(
            ["bash", str(INSTALLER_PATH)],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_installs_into_codex_home_skills_directory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            codex_home = Path(tempdir) / "codex-home"

            result = self.run_installer(codex_home)

            target_dir = codex_home / "skills" / "ima"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target_dir / "README.md").exists())
            self.assertTrue((target_dir / "scripts" / "run.py").exists())

    def test_excludes_runtime_directories_from_installation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            codex_home = Path(tempdir) / "codex-home"

            result = self.run_installer(codex_home)

            target_dir = codex_home / "skills" / "ima"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((target_dir / ".venv").exists())
            self.assertFalse((target_dir / "data").exists())
            self.assertFalse((target_dir / "scripts" / "__pycache__").exists())

    def test_backs_up_existing_installation_before_replacing_it(self):
        with tempfile.TemporaryDirectory() as tempdir:
            codex_home = Path(tempdir) / "codex-home"
            target_dir = codex_home / "skills" / "ima"
            target_dir.mkdir(parents=True, exist_ok=True)
            marker = target_dir / "old-marker.txt"
            marker.write_text("previous install", encoding="utf-8")

            result = self.run_installer(codex_home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(marker.exists())
            backups = list((codex_home / "skills").glob("ima.backup.*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "old-marker.txt").exists())
            self.assertTrue((target_dir / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
