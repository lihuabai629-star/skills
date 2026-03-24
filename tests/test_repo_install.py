import os
import subprocess
import tempfile
import unittest
from pathlib import Path


INSTALLER_PATH = Path("/root/.codex/skills/install.sh")
REPO_ROOT = Path("/root/.codex/skills")


class RepoInstallScriptTests(unittest.TestCase):
    def run_installer(
        self, codex_home: Path, *skill_names: str
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CODEX_HOME"] = str(codex_home)
        env["HOME"] = str(codex_home / "home")
        return subprocess.run(
            [
                "bash",
                str(INSTALLER_PATH),
                "--source-dir",
                str(REPO_ROOT),
                *skill_names,
            ],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_installs_selected_skill_into_codex_home(self):
        with tempfile.TemporaryDirectory() as tempdir:
            codex_home = Path(tempdir) / "codex-home"

            result = self.run_installer(codex_home, "ima")

            target_dir = codex_home / "skills" / "ima"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target_dir / "SKILL.md").exists())
            self.assertTrue((target_dir / "README.md").exists())
            self.assertTrue((target_dir / "scripts" / "run.py").exists())

    def test_excludes_runtime_directories(self):
        with tempfile.TemporaryDirectory() as tempdir:
            codex_home = Path(tempdir) / "codex-home"

            result = self.run_installer(codex_home, "ima")

            target_dir = codex_home / "skills" / "ima"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((target_dir / ".venv").exists())
            self.assertFalse((target_dir / "data").exists())
            self.assertFalse((target_dir / "scripts" / "__pycache__").exists())

    def test_fails_for_unknown_skill_name(self):
        with tempfile.TemporaryDirectory() as tempdir:
            codex_home = Path(tempdir) / "codex-home"

            result = self.run_installer(codex_home, "missing-skill")

            combined_output = f"{result.stdout}\n{result.stderr}"
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing-skill", combined_output)
            self.assertIn("not found", combined_output.lower())


if __name__ == "__main__":
    unittest.main()
