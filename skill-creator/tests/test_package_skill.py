#!/usr/bin/env python3
"""Regression coverage for skill packaging."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

SKILL_CREATOR_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = SKILL_CREATOR_ROOT / "scripts" / "package_skill.py"


class PackageSkillTests(unittest.TestCase):
    def _load_module(self):
        spec = importlib.util.spec_from_file_location("package_skill", SCRIPT_PATH)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_package_skill_creates_archive_and_excludes_cache(self) -> None:
        module = self._load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: Demo skill for packaging tests.\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (skill_dir / "data.txt").write_text("payload\n", encoding="utf-8")
            pycache_dir = skill_dir / "__pycache__"
            pycache_dir.mkdir()
            (pycache_dir / "skip.pyc").write_bytes(b"cache")
            (skill_dir / ".DS_Store").write_text("noise", encoding="utf-8")

            output_dir = root / "dist"
            archive_path = module.package_skill(skill_dir, output_dir)

            self.assertEqual(archive_path.name, "demo-skill.skill")
            self.assertTrue(archive_path.exists())
            with zipfile.ZipFile(archive_path) as zf:
                names = set(zf.namelist())

            self.assertIn("demo-skill/SKILL.md", names)
            self.assertIn("demo-skill/data.txt", names)
            self.assertNotIn("demo-skill/__pycache__/skip.pyc", names)
            self.assertNotIn("demo-skill/.DS_Store", names)

    def test_package_skill_rejects_invalid_skill(self) -> None:
        module = self._load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "broken-skill"
            skill_dir.mkdir()
            output_dir = Path(tmpdir) / "dist"

            with self.assertRaises(SystemExit):
                module.package_skill(skill_dir, output_dir)


if __name__ == "__main__":
    unittest.main()
