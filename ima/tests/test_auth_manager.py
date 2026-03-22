import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import auth_manager  # noqa: E402


class PageRequiresLoginTests(unittest.TestCase):
    def test_detects_qr_login_modal(self):
        body_text = "微信扫码登录\n扫码视为已阅读并同意《服务协议》与《隐私保护指引》"

        self.assertTrue(auth_manager.page_requires_login(body_text))

    def test_detects_logged_out_sidebar_copy(self):
        body_text = "新对话\n我的知识库\n知识库广场\n问答历史\n登录以同步历史会话\n登录"

        self.assertTrue(auth_manager.page_requires_login(body_text))

    def test_accepts_logged_in_homepage_copy(self):
        body_text = "新对话\n我的知识库\n知识库广场\n问答历史\n暂无历史会话\n关于ima\n打开电脑版"

        self.assertFalse(auth_manager.page_requires_login(body_text))


if __name__ == "__main__":
    unittest.main()
