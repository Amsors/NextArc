"""飞书日历服务 - 报名成功后自动同步到用户飞书日历"""

import asyncio
import datetime as dt
import time
from typing import Optional

import httpx

from src.utils.logger import get_logger

logger = get_logger("feishu.calendar")


class CalendarService:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: Optional[str] = None
        self._token_expires_at: float = 0
        self._lock: asyncio.Lock = asyncio.Lock()

    async def _get_token(self) -> Optional[str]:
        """获取 tenant_access_token，带缓存，异步安全"""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        async with self._lock:
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token

            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            payload = {"app_id": self.app_id, "app_secret": self.app_secret}

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(url, json=payload)
                    result = resp.json()

                if result.get("code") == 0:
                    self._token = result.get("tenant_access_token")
                    self._token_expires_at = time.time() + 7200
                    return self._token
                else:
                    logger.error(f"获取 tenant_access_token 失败: {result.get('msg')}")
                    return None
            except Exception as e:
                logger.error(f"获取 tenant_access_token 异常: {e}")
                return None

    async def create_calendar_event(
        self,
        open_id: str,
        summary: str,
        description: str,
        start_timestamp: str,
        end_timestamp: str,
        user_token: str = None,
    ) -> dict:
        """
        在用户的飞书日历主日历上创建一个日程事件。

        Args:
            open_id: 用户的飞书 open_id
            summary: 日程标题
            description: 日程描述
            start_timestamp: 开始时间，Unix 时间戳（秒）
            end_timestamp: 结束时间，Unix 时间戳（秒）
            user_token: 用户的飞书 user_access_token（可选），如果有则直接创建到用户日历
        """
        # 如果有用户 token，使用用户身份创建日程（直接显示在用户日历中）
        # 否则使用应用身份（需要用户接受邀请）
        token = user_token if user_token else await self._get_token()
        if not token:
            return {"code": 1, "msg": "获取 access_token 失败"}

        # 使用用户 token 时，日程直接创建在用户的主日历上
        # 不需要添加 attendees，日程会自动出现在用户日历中
        url = "https://open.feishu.cn/open-apis/calendar/v4/calendars/primary/events"
        payload = {
            "summary": summary,
            "description": description,
            "start_time": {
                "timestamp": start_timestamp,
                "timezone": "Asia/Shanghai",
            },
            "end_time": {
                "timestamp": end_timestamp,
                "timezone": "Asia/Shanghai",
            },
            "location": {},
            "reminders": [
                {"minutes": 30}
            ],
        }

        # 只有使用应用身份时才需要添加 attendees
        if not user_token:
            payload["attendees"] = [
                {
                    "type": "user",
                    "user_id": open_id,
                    "user_id_type": "open_id",
                }
            ]

        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        }

        logger.info(f"日历请求 open_id={open_id} summary={summary} start={start_timestamp} end={end_timestamp} user_token={'有' if user_token else '无'}")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload, headers=headers)
                result = resp.json()

            logger.info(f"日历响应: code={result.get('code')} msg={result.get('msg')}")

            if result.get("code") == 0:
                logger.info(f"日历事件创建成功: {summary}")
                # 如果使用应用身份，需要发送邀请
                if not user_token:
                    event_data = result.get("data", {}).get("event", {})
                    event_id = event_data.get("event_id")
                    if event_id:
                        await self._share_event_to_user(event_id, open_id)
            else:
                logger.warning(
                    f"日历事件创建失败: code={result.get('code')} msg={result.get('msg')}"
                )
            return result
        except Exception as e:
            logger.error(f"调用日历 API 异常: {e}")
            import traceback
            traceback.print_exc()
            return {"code": 1, "msg": str(e)}

    async def _share_event_to_user(self, event_id: str, open_id: str) -> bool:
        """
        将日程邀请发送给用户。
        用户收到邀请后可以在飞书日历中接受邀请查看日程。
        """
        token = await self._get_token()
        if not token:
            return False

        calendar_id = "primary"
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        }

        try:
            # 用 POST 添加 attendee，并发送邀请通知
            add_url = (
                f"https://open.feishu.cn/open-apis/calendar/v4/calendars/{calendar_id}"
                f"/events/{event_id}/attendees"
            )
            add_payload = {
                "attendees": [
                    {
                        "type": "user",
                        "user_id": open_id,
                        "user_id_type": "open_id",
                        "is_optional": False,
                    }
                ],
                "need_notification": True,
            }

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(add_url, json=add_payload, headers=headers)
                add_result = resp.json()

            logger.info(f"添加参会人响应: code={add_result.get('code')} msg={add_result.get('msg')}")

            if add_result.get("code") == 0:
                logger.info(f"日程邀请已发送: event_id={event_id} open_id={open_id}")
                return True
            else:
                logger.warning(
                    f"日程邀请发送失败: code={add_result.get('code')} msg={add_result.get('msg')}"
                )
                return False
        except Exception as e:
            logger.error(f"日程邀请发送异常: {e}")
            return False

    async def create_event_from_secondclass(self, open_id: str, sc, user_token: str = None) -> dict:
        """
        从 SecondClass 活动对象直接创建日历事件。

        Args:
            open_id: 用户的飞书 open_id
            sc: SecondClass 活动对象
            user_token: 用户的飞书 user_access_token（可选）
        """
        summary = f"【第二课堂】{sc.name}"

        desc_parts = []
        if sc.module:
            desc_parts.append(f"模块：{sc.module.text}")
        if sc.department:
            desc_parts.append(f"组织单位：{sc.department.name}")
        if sc.place_info:
            desc_parts.append(f"地点：{sc.place_info}")
        if sc.description:
            desc_parts.append(f"\n活动介绍：{sc.description}")
        if sc.valid_hour:
            desc_parts.append(f"\n学时：{sc.valid_hour}")
        description = "\n".join(desc_parts) if desc_parts else "第二课堂活动"

        def ts_from_datetime(dt_val):
            return str(int(dt_val.timestamp()))

        start_ts: str
        end_ts: str

        if sc.hold_time and sc.hold_time.start and sc.hold_time.end:
            start_ts = ts_from_datetime(sc.hold_time.start)
            end_ts = ts_from_datetime(sc.hold_time.end)
        elif sc.apply_time and sc.apply_time.start and sc.apply_time.end:
            start_ts = ts_from_datetime(sc.apply_time.start)
            end_ts = ts_from_datetime(sc.apply_time.end)
        else:
            now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
            start_ts = str(int(now.timestamp()))
            end_ts = str(int((now + dt.timedelta(hours=2)).timestamp()))

        return await self.create_calendar_event(
            open_id=open_id,
            summary=summary,
            description=description,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            user_token=user_token,
        )
