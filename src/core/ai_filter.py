"""AI 活动筛选器 - 使用大模型 API 筛选用户感兴趣的新活动"""

import asyncio
import json
import time
import traceback
from typing import Optional, TYPE_CHECKING

from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from pyustc.young import SecondClass

from src.models.activity import (
    get_display_time,
    get_status_text,
    get_apply_progress,
    get_module_name,
    get_department_name,
    get_description_text,
    get_conceive_text,
)
from src.models.filter_result import FilteredActivity
from src.utils.logger import get_logger
from src.utils.rate_limiter import RateLimiterWrapper
from src.utils.retry import RetryConfig, with_retry

if TYPE_CHECKING:
    from src.core.user_preference_manager import UserPreferenceManager

logger = get_logger("ai_filter")


class AIRateLimiterConfig:
    def __init__(
            self,
            requests_per_minute: int = 0,
            max_concurrency: int = 3,
            enable_queue: bool = True,
            queue_timeout: float = 300.0,
    ):
        self.requests_per_minute = requests_per_minute
        self.max_concurrency = max_concurrency
        self.enable_queue = enable_queue
        self.queue_timeout = queue_timeout

        self._wrapper = RateLimiterWrapper(
            requests_per_minute=requests_per_minute,
            max_concurrency=max_concurrency,
            enable_queue=enable_queue,
            queue_timeout=queue_timeout,
        )

        if requests_per_minute > 0:
            logger.info(f"AI API 速率限制: {requests_per_minute}请求/分钟, 最大并发: {max_concurrency}")
        else:
            logger.info(f"AI API 无速率限制, 最大并发: {max_concurrency}")

    def acquire(self):
        return self._wrapper.acquire()


class AIRetryConfig(RetryConfig):
    def __init__(
            self,
            max_retries: int = 3,
            base_delay: float = 2.0,
            max_delay: float = 60.0,
            backoff_factor: float = 2.0,
            retry_on_status: Optional[list[int]] = None,
            retry_on_network_error: bool = True,
    ):
        super().__init__(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            backoff_factor=backoff_factor,
            retry_on_status=retry_on_status or [429, 500, 502, 503, 504],
            retry_on_network_error=retry_on_network_error,
            on_retry=self._on_retry,
        )

    def _on_retry(self, exception: Exception, attempt: int, delay: float):
        if isinstance(exception, RateLimitError):
            logger.warning(f"AI API 触发限流(429)，第{attempt}次重试，等待{delay:.1f}秒...")
        elif isinstance(exception, APITimeoutError):
            logger.warning(f"AI API 超时，第{attempt}次重试，等待{delay:.1f}秒...")
        elif isinstance(exception, APIError):
            status = getattr(exception, 'status_code', 'unknown')
            logger.warning(f"AI API 错误(状态码:{status})，第{attempt}次重试，等待{delay:.1f}秒...")
        else:
            logger.warning(f"AI API 请求失败({type(exception).__name__})，第{attempt}次重试，等待{delay:.1f}秒...")


class AIFilter:
    """AI 活动筛选器，支持速率限制、智能重试和缓存。"""

    def __init__(
            self,
            api_key: str,
            system_prompt: str,
            user_prompt: str,
            model: str,
            temperature: float,
            base_url: Optional[str] = None,
            timeout: int = 30,
            extra_body: Optional[dict] = None,
            rate_limit_requests_per_minute: int = 0,
            rate_limit_max_concurrency: int = 3,
            rate_limit_enable_queue: bool = True,
            rate_limit_queue_timeout: float = 300.0,
            retry_max_retries: int = 3,
            retry_base_delay: float = 2.0,
            retry_max_delay: float = 60.0,
            retry_backoff_factor: float = 2.0,
            retry_on_status: Optional[list[int]] = None,
            retry_on_network_error: bool = True,
    ):
        if not api_key:
            raise ValueError("AI 筛选器初始化失败：api_key 不能为空")
        if not model:
            raise ValueError("AI 筛选器初始化失败：model 不能为空")
        if not system_prompt:
            raise ValueError("AI 筛选器初始化失败：system_prompt 不能为空")
        if not user_prompt:
            raise ValueError("AI 筛选器初始化失败：user_prompt 不能为空")
        if temperature is None:
            raise ValueError("AI 筛选器初始化失败：temperature 不能为空")

        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.temperature = temperature
        self.timeout = timeout
        self.extra_body = extra_body or {}

        self.rate_limiter = AIRateLimiterConfig(
            requests_per_minute=rate_limit_requests_per_minute,
            max_concurrency=rate_limit_max_concurrency,
            enable_queue=rate_limit_enable_queue,
            queue_timeout=rate_limit_queue_timeout,
        )

        self.retry_config = AIRetryConfig(
            max_retries=retry_max_retries,
            base_delay=retry_base_delay,
            max_delay=retry_max_delay,
            backoff_factor=retry_backoff_factor,
            retry_on_status=retry_on_status,
            retry_on_network_error=retry_on_network_error,
        )

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)

        logger.info(f"AI 筛选器初始化完成，模型: {model}")
        logger.info(f"重试配置: 最多{retry_max_retries}次，基础延迟{retry_base_delay}秒")
        if self.extra_body:
            logger.info(f"已配置额外请求参数: {self.extra_body}")

    async def test_connection(self) -> tuple[bool, str]:
        """测试 API 连接是否可用，返回tuple[bool, str]: (是否成功, 详细信息)"""
        try:
            models = await self.client.models.list()
            model_ids = [m.id for m in models.data]

            if self.model not in model_ids:
                available = ", ".join(model_ids[:5])
                if len(model_ids) > 5:
                    available += f" 等共 {len(model_ids)} 个模型"
                return False, f"API 连接成功，但模型 '{self.model}' 不在可用列表中。可用模型: {available}"

        except Exception as e:
            error_msg = str(e)
            if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
                return False, f"API 认证失败，请检查 api_key 是否正确: {error_msg}"
            elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                return False, f"API 连接失败，请检查网络或 base_url 是否正确: {error_msg}"
            else:
                return False, f"API 连接测试失败: {error_msg}"

        try:
            mock_activity_info = """活动名称：AI 测试活动
活动状态：报名中
举办时间：2024-01-01 14:00
模块：创新创业
组织单位：测试部门
学时：2
已报名/名额：10/100
活动简介：这是一个用于测试 AI 响应格式的模拟活动，请正常返回 JSON 格式。"""

            test_user_prompt = self.user_prompt.format(
                user_info="用户对所有类型的活动都感兴趣",
                activity_info=mock_activity_info,
            )

            request_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": test_user_prompt},
                ],
                "timeout": self.timeout,
            }

            if self.extra_body:
                request_params["extra_body"] = self.extra_body

            response = await self.client.chat.completions.create(**request_params)
            content = response.choices[0].message.content.strip()

            result = self._parse_response(content)

            if "interested" not in result:
                return False, f"API 连接成功，但 AI 响应缺少 'interested' 字段。响应: {content[:200]}"
            if "reason" not in result:
                return False, f"API 连接成功，但 AI 响应缺少 'reason' 字段。响应: {content[:200]}"
            if not isinstance(result["interested"], bool):
                return False, f"API 连接成功，但 'interested' 字段不是布尔类型。响应: {content[:200]}"
            if not isinstance(result["reason"], str):
                return False, f"API 连接成功，但 'reason' 字段不是字符串类型。响应: {content[:200]}"

            return True, f"API 连接成功，模型 '{self.model}' 可用，AI 响应格式正确 (interested={result['interested']})"

        except Exception as e:
            return False, f"API 连接成功，但 AI 响应测试失败: {str(e)}"

    def _format_activity_info(self, activity: SecondClass) -> str:
        lines = [
            f"活动名称：{activity.name}",
            f"活动状态：{get_status_text(activity)}",
            f"举办时间：{get_display_time(activity, 'hold_time')}",
            f"模块：{get_module_name(activity)}",
            f"组织单位：{get_department_name(activity)}",
        ]
        if not activity.is_series:
            lines.append(f"学时：{activity.valid_hour or '未知'}")
            lines.append(f"已报名/名额：{get_apply_progress(activity)}")

        if activity.conceive:
            lines.append(f"活动构想：{activity.conceive}")

        if activity.description:
            lines.append(f"活动简介: {activity.description}")

        return "\n".join(lines)

    async def filter_activities(
            self,
            activities: list[SecondClass],
            user_info: str,
            write_to_db: bool = True,
            prefer_cached: bool = False,
            preference_manager: Optional['UserPreferenceManager'] = None,
    ) -> tuple[list[SecondClass], list[FilteredActivity]]:
        if not activities:
            return [], []

        if not self.api_key:
            logger.warning("未配置 API 密钥，跳过 AI 筛选")
            return activities, []

        cached_results: dict[str, dict] = {}
        activities_to_judge = activities

        if prefer_cached and preference_manager:
            activity_ids = [a.id for a in activities]
            cached_results = await preference_manager.get_ai_filter_results(activity_ids)

            cached_ids = set(cached_results.keys())
            activities_to_judge = [a for a in activities if a.id not in cached_ids]

            logger.info(f"AI 筛选: {len(cached_results)} 个活动使用缓存，{len(activities_to_judge)} 个活动需要 API 审核")
        else:
            logger.info(f"开始 AI 筛选 {len(activities)} 个活动（带速率限制和重试）...")

        api_results: list[tuple[SecondClass, bool, str]] = []
        if activities_to_judge:
            api_results = await self._judge_activities_batch(activities_to_judge, user_info)

        all_results = self._merge_results(activities, cached_results, api_results)

        if write_to_db and preference_manager:
            results_to_save: list[tuple[str, bool, str, Optional[int]]] = []
            current_time = int(time.time())

            for activity, is_interested, reason in all_results:
                if not prefer_cached or activity.id not in cached_results:
                    results_to_save.append((activity.id, is_interested, reason, current_time))

            if results_to_save:
                success, failed = await preference_manager.save_ai_filter_results(results_to_save)
                logger.debug(f"保存 AI 筛选结果到数据库: 成功 {success} 个, 失败 {failed} 个")

        kept_activities: list[SecondClass] = []
        filtered_activities: list[FilteredActivity] = []

        for activity, is_interested, reason in all_results:
            if is_interested:
                kept_activities.append(activity)
                logger.debug(f"通过AI筛选：活动 '{activity.name}'")
            else:
                filtered_activities.append(FilteredActivity(
                    activity=activity,
                    reason=reason or "AI认为不符合用户兴趣",
                    filter_type="ai"
                ))
                logger.debug(f"没有通过AI筛选：活动 '{activity.name}'")

        logger.info(f"AI 筛选完成：{len(kept_activities)}/{len(activities)} 个活动通过")
        return kept_activities, filtered_activities

    def _merge_results(
            self,
            activities: list[SecondClass],
            cached_results: dict[str, dict],
            api_results: list[tuple[SecondClass, bool, str]]
    ) -> list[tuple[SecondClass, bool, str]]:
        api_results_dict = {activity.id: (is_interested, reason) for activity, is_interested, reason in api_results}

        merged: list[tuple[SecondClass, bool, str]] = []
        for activity in activities:
            if activity.id in cached_results:
                cached = cached_results[activity.id]
                merged.append((activity, cached["is_interested"], cached["reason"]))
            elif activity.id in api_results_dict:
                is_interested, reason = api_results_dict[activity.id]
                merged.append((activity, is_interested, reason))
            else:
                logger.warning(f"活动 '{activity.name}' 没有审核结果，默认保留")
                merged.append((activity, True, "无审核结果，默认保留"))

        return merged

    async def _judge_activities_batch(
            self,
            activities: list[SecondClass],
            user_info: str
    ) -> list[tuple[SecondClass, bool, str]]:
        async def judge_with_limit_and_retry(activity: SecondClass) -> tuple[SecondClass, bool, str]:
            async with self.rate_limiter.acquire():
                try:
                    is_interested, reason = await with_retry(
                        self._judge_activity_with_reason,
                        activity,
                        user_info,
                        config=self.retry_config,
                    )
                    return activity, is_interested, reason
                except asyncio.TimeoutError:
                    logger.warning(f"AI 判断活动 '{activity.name}' 超时，保留该活动")
                    return activity, True, "AI判断超时，默认保留"
                except Exception as e:
                    logger.warning(f"AI 判断活动 '{activity.name}' 最终失败: {e}，保留该活动")
                    traceback.print_exc()
                    return activity, True, f"AI判断失败: {e}，默认保留"

        tasks = [judge_with_limit_and_retry(activity) for activity in activities]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results: list[tuple[SecondClass, bool, str]] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"AI 筛选任务异常: {result}")
                continue
            processed_results.append(result)

        return processed_results

    async def _judge_activity_with_reason(self, activity: SecondClass, user_info: str) -> tuple[bool, str]:
        activity_info = self._format_activity_info(activity)

        user_prompt = self.user_prompt.format(
            user_info=user_info,
            activity_info=activity_info,
        )

        request_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "timeout": self.timeout,
        }

        if self.extra_body:
            request_params["extra_body"] = self.extra_body

        response = await self.client.chat.completions.create(**request_params)

        content = response.choices[0].message.content.strip()

        result = self._parse_response(content)
        reason = result.get('reason', '')

        if result.get("interested"):
            logger.debug(f"AI 认为 '{activity.name}' 符合用户兴趣: {reason}")
            return True, reason
        else:
            logger.debug(f"AI 认为 '{activity.name}' 不符合用户兴趣: {reason}")
            return False, reason

    def _parse_response(self, content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        import re

        json_pattern = r"```(?:json)?\s*(.*?)\s*```"
        matches = re.findall(json_pattern, content, re.DOTALL)

        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        brace_pattern = r"(\{[\s\S]*\})"
        matches = re.findall(brace_pattern, content)

        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        logger.warning(f"无法解析 AI 响应: {content[:200]}...")
        return {"interested": True, "reason": "解析失败，默认保留"}


class AIFilterConfig:
    @staticmethod
    def create_from_settings(settings) -> Optional[AIFilter]:
        if not hasattr(settings, 'ai'):
            return None

        ai_config = settings.ai

        if not ai_config.enabled:
            logger.info("AI 筛选功能已禁用")
            return None

        ai_config.validate_required_fields()

        from src.config.settings import load_prompt_file_strict

        system_prompt = load_prompt_file_strict(ai_config.system_prompt_file)
        user_prompt = load_prompt_file_strict(ai_config.user_prompt_file)

        logger.info(f"已加载系统提示词: {ai_config.system_prompt_file}")
        logger.info(f"已加载用户提示词: {ai_config.user_prompt_file}")

        rate_limit_kwargs = {}
        if hasattr(ai_config, 'rate_limit') and ai_config.rate_limit:
            rate_limit = ai_config.rate_limit
            rate_limit_kwargs['rate_limit_requests_per_minute'] = getattr(rate_limit, 'requests_per_minute', 0)
            rate_limit_kwargs['rate_limit_max_concurrency'] = getattr(rate_limit, 'max_concurrency', 3)
            rate_limit_kwargs['rate_limit_enable_queue'] = getattr(rate_limit, 'enable_queue', True)
            rate_limit_kwargs['rate_limit_queue_timeout'] = getattr(rate_limit, 'queue_timeout', 300.0)

        retry_kwargs = {}
        if hasattr(ai_config, 'retry') and ai_config.retry:
            retry = ai_config.retry
            retry_kwargs['retry_max_retries'] = getattr(retry, 'max_retries', 3)
            retry_kwargs['retry_base_delay'] = getattr(retry, 'base_delay', 2.0)
            retry_kwargs['retry_max_delay'] = getattr(retry, 'max_delay', 60.0)
            retry_kwargs['retry_backoff_factor'] = getattr(retry, 'backoff_factor', 2.0)
            retry_kwargs['retry_on_status'] = getattr(retry, 'retry_on_status', [429, 500, 502, 503, 504])
            retry_kwargs['retry_on_network_error'] = getattr(retry, 'retry_on_network_error', True)

        return AIFilter(
            api_key=ai_config.api_key,
            base_url=ai_config.base_url if ai_config.base_url else None,
            model=ai_config.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=ai_config.temperature,
            timeout=ai_config.timeout,
            extra_body=ai_config.extra_body,
            **rate_limit_kwargs,
            **retry_kwargs,
        )
