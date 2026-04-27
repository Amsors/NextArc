"""版本更新说明通知回归测试。"""

import unittest

from src.main import NextArcApp


class ChangeLogNotificationTest(unittest.TestCase):
    def test_change_log_card_uses_markdown_element(self) -> None:
        app = NextArcApp()
        section = "## v2.6.0\n\n新增配置项 `monitor.notify_filtered_activities`\n\n- 默认开启"
        expected_content = "**v2.6.0**\n\n新增配置项 `monitor.notify_filtered_activities`\n\n- 默认开启"

        card = app._build_change_log_card("2.6.0", section)

        self.assertEqual(card["header"]["title"]["content"], "更新说明（v2.6.0）")
        self.assertEqual(card["elements"], [{"tag": "markdown", "content": expected_content}])

    def test_change_log_formatter_converts_headings_to_bold(self) -> None:
        app = NextArcApp()
        section = "# 一级\n## 二级\n### 三级 ###\n- 保留列表"

        content = app._format_change_log_for_feishu_card(section)

        self.assertEqual(content, "**一级**\n**二级**\n**三级**\n- 保留列表")
