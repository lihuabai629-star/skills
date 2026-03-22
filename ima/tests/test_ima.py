import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path("/root/.codex/skills/ima/scripts/ima.py")


def load_ima_module():
    spec = importlib.util.spec_from_file_location("ima_skill_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ImaScriptTests(unittest.TestCase):
    def test_help_works_without_skill_venv(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage", result.stdout.lower())

    def test_parse_query_request_detects_private_knowledge_prefix(self):
        module = load_ima_module()

        request = module.parse_query_request("@knowledge 项目进展")

        self.assertEqual(
            request,
            {
                "question": "项目进展",
                "knowledge_mode": True,
            },
        )

    def test_parse_query_request_supports_chinese_prefix(self):
        module = load_ima_module()

        request = module.parse_query_request("@个人知识库 设计文档")

        self.assertEqual(
            request,
            {
                "question": "设计文档",
                "knowledge_mode": True,
            },
        )

    def test_parse_query_request_leaves_public_questions_unchanged(self):
        module = load_ima_module()

        request = module.parse_query_request("帮我总结一下今天的要点")

        self.assertEqual(
            request,
            {
                "question": "帮我总结一下今天的要点",
                "knowledge_mode": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
