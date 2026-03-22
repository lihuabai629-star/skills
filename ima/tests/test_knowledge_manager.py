import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import knowledge_manager  # noqa: E402


class SelectKnowledgeEntryTests(unittest.TestCase):
    def test_prefers_exact_name_match(self):
        entries = [
            {"id": "kb-1", "name": "产品文档"},
            {"id": "kb-2", "name": "产品文档归档"},
        ]

        selected = knowledge_manager.select_knowledge_entry(entries, "产品文档")

        self.assertEqual(selected["id"], "kb-1")

    def test_allows_unique_partial_match(self):
        entries = [
            {"id": "kb-1", "name": "客户端周报"},
            {"id": "kb-2", "name": "服务端设计"},
        ]

        selected = knowledge_manager.select_knowledge_entry(entries, "服务端")

        self.assertEqual(selected["id"], "kb-2")

    def test_rejects_ambiguous_partial_match(self):
        entries = [
            {"id": "kb-1", "name": "项目资料"},
            {"id": "kb-2", "name": "项目总结"},
        ]

        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            knowledge_manager.select_knowledge_entry(entries, "项目")

    def test_rejects_missing_entry(self):
        entries = [{"id": "kb-1", "name": "产品文档"}]

        with self.assertRaisesRegex(ValueError, "not found"):
            knowledge_manager.select_knowledge_entry(entries, "不存在")


class ExtractKnowledgeEntriesFromBodyTests(unittest.TestCase):
    def test_extracts_entries_from_wikis_sections(self):
        body_text = """
        个人知识库
        共享知识库
        我创建的
        Bios
        openBMC
        openUBMC
        我加入的
        Team Docs
        已使用908.11MB/50GB
        openUBMC
        本知识库是 openUBMC 开源社区 官方技术文档的完整集合
        """

        entries = knowledge_manager.extract_knowledge_entries_from_body(body_text)

        self.assertEqual(
            entries,
            [
                {"id": "bios", "name": "Bios"},
                {"id": "openbmc", "name": "openBMC"},
                {"id": "openubmc", "name": "openUBMC"},
                {"id": "team-docs", "name": "Team Docs"},
            ],
        )

    def test_deduplicates_names_and_skips_empty_sections(self):
        body_text = """
        个人知识库
        我创建的
        openUBMC
        openUBMC
        我加入的
        已使用100MB/50GB
        """

        entries = knowledge_manager.extract_knowledge_entries_from_body(body_text)

        self.assertEqual(entries, [{"id": "openubmc", "name": "openUBMC"}])


if __name__ == "__main__":
    unittest.main()
