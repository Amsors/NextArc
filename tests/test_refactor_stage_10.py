"""阶段 10 通知与卡片解耦回归测试。"""

import json
import unittest

from pyustc.young import SecondClass, Status

from src.core import FilteredActivity
from src.core.events.scan_events import NewActivitiesFoundEvent
from src.feishu_bot.card_builder import ActivityCardDisplayConfig
from src.notifications import Response
from src.notifications.builders import FilterDetailBuildConfig, FilterDetailNotificationBuilder
from src.notifications.listener import NotificationListener, NotificationRuntimeConfig
from src.notifications.service import NotificationService


def _activity(activity_id: str, name: str) -> SecondClass:
    SecondClass._instance_cache.pop(activity_id, None)
    return SecondClass.from_dict(
        {
            "id": activity_id,
            "itemName": name,
            "itemStatus": Status.APPLYING.code,
            "applySt": "2026-04-24 10:00:00",
            "applyEt": "2026-04-25 10:00:00",
            "st": "2026-04-26 14:00:00",
            "et": "2026-04-26 16:00:00",
            "validHour": 2.0,
            "applyNum": 1,
            "peopleNum": 20,
            "booleanRegistration": "0",
            "needSignInfo": "0",
            "module": "m1",
            "moduleName": "文化素质",
            "businessDeptId": "d1",
            "bussinessDeptName": "校团委",
            "itemLable": "l1",
            "lableNames": "讲座",
            "conceive": "活动构想",
            "baseContent": "活动描述",
            "itemCategory": "0",
            "placeInfo": "西区活动室",
            "form": "0",
        }
    )


class RecordingNotificationService(NotificationService):
    def __init__(self, card_config: ActivityCardDisplayConfig | None = None) -> None:
        super().__init__(card_config=card_config)
        self.texts: list[str] = []
        self.cards: list[dict] = []

    async def send_text(self, message: str) -> bool:
        self.texts.append(message)
        return True

    async def send_card(self, card_content: dict) -> bool:
        self.cards.append(card_content)
        return True


class ActivityResponseCardBuildTest(unittest.IsolatedAsyncioTestCase):
    async def test_activity_list_response_builds_card_once_in_send_response(self) -> None:
        activities = [
            _activity("stage10-a1", "活动一"),
            _activity("stage10-a2", "活动二"),
            _activity("stage10-a3", "活动三"),
        ]
        response = Response.activity_list(activities, title="测试活动")

        self.assertEqual(response.content, {"kind": "activity_list"})
        self.assertIn("activity_card_request", response.metadata)
        self.assertNotIn("activities", response.metadata)
        self.assertNotIn("title", response.metadata)

        service = RecordingNotificationService(
            ActivityCardDisplayConfig(max_activities_per_card=2)
        )
        success = await service.send_response(response)

        self.assertTrue(success)
        self.assertEqual(len(service.cards), 2)
        self.assertEqual(service.cards[0]["header"]["title"]["content"], "测试活动（1/2）")
        self.assertEqual(service.cards[1]["header"]["title"]["content"], "测试活动（2/2）")

        panel_titles = [
            element["header"]["title"]["content"]
            for card in service.cards
            for element in card["elements"]
            if element.get("tag") == "collapsible_panel"
        ]
        self.assertIn("[1] 活动一", panel_titles[0])
        self.assertIn("[2] 活动二", panel_titles[1])
        self.assertIn("[3] 活动三", panel_titles[2])

    async def test_direct_card_response_still_sends_given_card(self) -> None:
        direct_card = {
            "config": {"wide_screen_mode": True},
            "elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "直接卡片"}}],
        }
        response = Response.card(direct_card)
        service = RecordingNotificationService()

        success = await service.send_response(response)

        self.assertTrue(success)
        self.assertEqual(service.cards, [direct_card])


class NotificationBuilderTest(unittest.IsolatedAsyncioTestCase):
    async def test_listener_does_not_send_filter_detail_when_disabled(self) -> None:
        kept = _activity("stage10-kept", "保留活动")
        filtered = _activity("stage10-filtered", "过滤活动")
        event = NewActivitiesFoundEvent(
            activities=[kept],
            total_found=2,
            filters_applied={
                "ai": [FilteredActivity(filtered, "AI 判断不匹配", "ai")],
            },
            ai_keep_reasons={kept.id: "与用户偏好匹配"},
            overlap_reasons={kept.id: "与已报名活动部分重叠"},
        )
        service = RecordingNotificationService()
        listener = NotificationListener(
            service,
            runtime_config=NotificationRuntimeConfig(
                notify_filtered_activities=False,
                show_filtered_ai_reasons=True,
                show_kept_ai_reasons=True,
            ),
        )

        await listener.on_new_activities_found(event)

        self.assertEqual(service.texts, [])
        self.assertEqual(len(service.cards), 1)
        card_text = json.dumps(service.cards[0], ensure_ascii=False)
        self.assertIn("AI 判断理由", card_text)
        self.assertIn("与用户偏好匹配", card_text)
        self.assertIn("时间重叠", card_text)

    def test_filter_detail_builder_respects_ai_reason_config(self) -> None:
        filtered = _activity("stage10-builder-filtered", "过滤活动")
        event = NewActivitiesFoundEvent(
            activities=[],
            total_found=1,
            filters_applied={
                "ai": [FilteredActivity(filtered, "AI 判断不匹配", "ai")],
            },
        )
        builder = FilterDetailNotificationBuilder()

        disabled_message = builder.build(
            event,
            FilterDetailBuildConfig(enabled=False, include_ai_reasons=True),
        )
        enabled_message = builder.build(
            event,
            FilterDetailBuildConfig(enabled=True, include_ai_reasons=True),
        )

        self.assertIsNone(disabled_message)
        self.assertIsNotNone(enabled_message)
        self.assertIn("原因：AI 判断不匹配", enabled_message)


if __name__ == "__main__":
    unittest.main()
