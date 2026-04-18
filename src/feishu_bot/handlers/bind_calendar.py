"""飞书日历绑定处理器"""

import httpx
from src.feishu_bot.handlers.base import CommandHandler
from src.notifications.response import Response
from src.utils.logger import get_logger

logger = get_logger("feishu.bind_calendar")


class BindCalendarHandler(CommandHandler):
    """处理飞书日历绑定流程"""

    # 类变量，用于存储 bot 信息
    _bot = None
    _pending_auth_codes: dict[str, str] = {}  # auth_code -> user_id

    @property
    def command(self) -> str:
        return "绑定日历"

    @classmethod
    def set_bot(cls, bot):
        cls._bot = bot

    async def handle(self, args: list[str], session) -> Response:
        """
        处理 /绑定日历 指令

        用法：
        /绑定日历 - 获取授权链接
        /绑定日历 <授权码> - 使用授权码完成绑定
        """
        if not self._bot:
            return Response.error("服务未就绪，请稍后重试")

        # 无参数：生成授权链接
        if not args:
            return await self._generate_auth_link(session)

        # 有参数：处理授权码
        auth_code = args[0].strip()
        if len(auth_code) < 10:
            return Response.text("授权码格式不正确，请确认是否复制完整")

        return await self._exchange_code_for_token(session, auth_code)

    async def _generate_auth_link(self, session) -> Response:
        """生成飞书 OAuth 授权链接"""
        app_id = self._bot.app_id

        # 飞书 OAuth 授权链接
        # 使用官方授权页面，授权成功后会显示授权码
        # 需要以下权限：calendar:calendar:rw, calendar.event:rw
        redirect_uri = "https://open.feishu.cn/open-apis/authen/v1/authorize_app"
        auth_link = (
            f"https://open.feishu.cn/open-apis/authen/v1/authorize"
            f"?app_id={app_id}"
            f"&redirect_uri={redirect_uri}"
            f"&state=calendar_bind"
        )

        instructions = [
            "📅 **飞书日历绑定指南**",
            "",
            "1. 点击以下链接授权：",
            f"[点击授权]({auth_link})",
            "",
            "2. 授权后会显示一个页面，把页面上的**授权码**复制下来",
            "",
            "3. 发送给我：`/绑定日历 <授权码>`",
            "",
            "💡 授权码有效期约 5 分钟，请尽快完成",
        ]

        return Response.text("\n".join(instructions))

    async def _exchange_code_for_token(self, session, auth_code: str) -> Response:
        """用授权码换取 user_access_token"""
        app_id = self._bot.app_id
        app_secret = self._bot.app_secret

        try:
            # 获取 tenant_access_token
            token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            token_payload = {"app_id": app_id, "app_secret": app_secret}

            async with httpx.AsyncClient(timeout=10) as client:
                token_resp = await client.post(token_url, json=token_payload)
                token_result = token_resp.json()

            if token_result.get("code") != 0:
                logger.error(f"获取 tenant_access_token 失败: {token_result}")
                return Response.text("获取访问凭证失败，请稍后重试")

            tenant_token = token_result.get("tenant_access_token")

            # 用授权码换取 user_access_token
            exchange_url = "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token"
            exchange_payload = {
                "grant_type": "authorization_code",
                "code": auth_code,
            }
            headers = {
                "Authorization": f"Bearer {tenant_token}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(timeout=10) as client:
                exchange_resp = await client.post(exchange_url, json=exchange_payload, headers=headers)
                exchange_result = exchange_resp.json()

            logger.info(f"授权码兑换响应: code={exchange_result.get('code')} msg={exchange_result.get('msg')}")

            if exchange_result.get("code") != 0:
                error_msg = exchange_result.get("msg", "未知错误")
                return Response.text(f"授权失败：{error_msg}\n\n请确保授权码正确且未过期")

            # 提取 user_access_token 和 open_id
            data = exchange_result.get("data", {})
            user_access_token = data.get("access_token")
            open_id = data.get("open_id")
            refresh_token = data.get("refresh_token")

            if not user_access_token:
                return Response.text("授权失败：未能获取访问令牌")

            # 保存到用户会话
            session.open_id = open_id
            session.feishu_user_token = user_access_token

            logger.info(f"飞书日历绑定成功: open_id={open_id}")

            return Response.text(
                "✅ **飞书日历绑定成功！**\n\n"
                "现在报名活动后，日程会直接同步到你的飞书日历中，无需手动接受邀请。"
            )

        except Exception as e:
            logger.error(f"日历绑定异常: {e}")
            import traceback
            traceback.print_exc()
            return Response.text(f"绑定失败：{str(e)}\n\n请稍后重试")


# 全局存储用户 token（因为 UserSession 可能不持久化）
_calendar_tokens: dict[str, dict] = {}  # open_id -> {user_token, refresh_token}


def save_calendar_token(open_id: str, user_token: str, refresh_token: str = None):
    """保存用户的日历 token"""
    _calendar_tokens[open_id] = {
        "user_token": user_token,
        "refresh_token": refresh_token,
    }
    logger.info(f"已保存用户日历 token: open_id={open_id}")


def get_calendar_token(open_id: str) -> str | None:
    """获取用户的日历 token"""
    token_info = _calendar_tokens.get(open_id)
    if token_info:
        return token_info.get("user_token")
    return None


def clear_calendar_token(open_id: str):
    """清除用户的日历 token"""
    if open_id in _calendar_tokens:
        del _calendar_tokens[open_id]
        logger.info(f"已清除用户日历 token: open_id={open_id}")
