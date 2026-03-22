import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import ask_knowledge  # noqa: E402
from config import PAGE_LOAD_TIMEOUT_MS, WIKIS_URL  # noqa: E402


class FakeClickTarget:
    def __init__(self, page: "FakePage", label: str) -> None:
        self.page = page
        self.label = label
        self.first = self

    def click(self, timeout: int | None = None) -> None:
        self.page.clicks.append(
            {
                "label": self.label,
                "timeout": timeout,
            }
        )


class FakePage:
    def __init__(self) -> None:
        self.calls = []
        self.clicks = []

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.calls.append(
            {
                "url": url,
                "wait_until": wait_until,
                "timeout": timeout,
            }
        )

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self.calls.append({"wait_for_timeout": timeout_ms})

    def get_by_text(self, label: str, exact: bool) -> FakeClickTarget:
        self.calls.append(
            {
                "get_by_text": label,
                "exact": exact,
            }
        )
        return FakeClickTarget(self, label)


class OpenKnowledgeBaseTests(unittest.TestCase):
    def test_open_knowledge_base_uses_wikis_page_and_clicks_target_name(self):
        page = FakePage()
        entry = {"id": "openubmc", "name": "openUBMC"}

        ask_knowledge._open_knowledge_base(page, entry)

        self.assertEqual(
            page.calls,
            [
                {
                    "url": WIKIS_URL,
                    "wait_until": "domcontentloaded",
                    "timeout": PAGE_LOAD_TIMEOUT_MS,
                },
                {"wait_for_timeout": 2500},
                {
                    "get_by_text": "openUBMC",
                    "exact": True,
                },
                {"wait_for_timeout": 2500},
            ],
        )
        self.assertEqual(
            page.clicks,
            [
                {
                    "label": "openUBMC",
                    "timeout": 10000,
                }
            ],
        )


class ExtractMarkdownAnswerTests(unittest.TestCase):
    def test_returns_none_when_markdown_answer_is_unchanged(self):
        answer = ask_knowledge.extract_markdown_answer(
            previous_markdown="旧答案",
            current_markdown="旧答案",
            question="新问题",
        )

        self.assertIsNone(answer)

    def test_prefers_new_markdown_answer_text(self):
        answer = ask_knowledge.extract_markdown_answer(
            previous_markdown="旧答案",
            current_markdown="  新答案正文  \n",
            question="新问题",
        )

        self.assertEqual(answer, "新答案正文")

    def test_rejects_loading_state_markdown_text(self):
        answer = ask_knowledge.extract_markdown_answer(
            previous_markdown="旧答案",
            current_markdown="正在搜索知识库资料...\n停止回答",
            question="新问题",
        )

        self.assertIsNone(answer)


class ExtractAnswerTextTests(unittest.TestCase):
    def test_extracts_only_latest_answer_block_after_question(self):
        after_text = """
        历史问题
        ima
        找到了48篇知识库资料
        历史答案
        当前问题
        ima
        找到了28篇知识库资料

        当前答案第一句。
        当前答案第二句。

        对话模式
        DS 快速
        """

        answer = ask_knowledge.extract_answer_text("", after_text, "当前问题")

        self.assertEqual(answer, "当前答案第一句。\n当前答案第二句。")

    def test_ignores_loading_state_lines_before_final_answer(self):
        after_text = """
        当前问题
        ima
        找到了28篇知识库资料
        正在搜索知识库资料...
        停止回答

        最终答案。

        对话模式
        """

        answer = ask_knowledge.extract_answer_text("", after_text, "当前问题")

        self.assertEqual(answer, "最终答案。")

    def test_returns_empty_when_only_history_items_follow_loading_state(self):
        after_text = """
        当前问题
        ima
        找到了28篇知识库资料
        正在搜索知识库资料...
        停止回答
        对话模式
        DS 快速
        内容由AI生成仅供参考
        问答历史
        2026年3月21日
        历史问题
        pcie加载流程
        """

        answer = ask_knowledge.extract_answer_text("", after_text, "当前问题")

        self.assertEqual(answer, "")

    def test_prefers_question_block_followed_by_ima_over_history_entry(self):
        after_text = """
        当前问题
        ima
        找到了28篇知识库资料
        最终答案。
        问答历史
        2026年3月21日
        当前问题
        pcie加载流程
        """

        answer = ask_knowledge.extract_answer_text("", after_text, "当前问题")

        self.assertEqual(answer, "最终答案。")


if __name__ == "__main__":
    unittest.main()
