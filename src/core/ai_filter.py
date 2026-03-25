"""AI 活动筛选器 - 增强版

使用大模型 API 筛选用户感兴趣的新活动
支持 OpenAI API 格式，带速率限制和重试机制
"""

import asyncio
import json
import traceback
from typing import Optional

from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from pyustc.young import SecondClass

from src.models.activity import (
    get_display_time,
    get_status_text,
    get_apply_progress,
    get_module_name,
    get_department_name,
)
from src.models.filter_result import FilteredActivity
from src.utils.logger import get_logger
from src.utils.rate_limiter import RateLimiterWrapper
from src.utils.retry import RetryConfig, with_retry

logger = get_logger("ai_filter")


class AIRateLimiterConfig:
    """AI API 速率限制配置包装器"""

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

        # 初始化速率限制器
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
        """获取执行许可的上下文管理器（返回异步上下文管理器）"""
        return self._wrapper.acquire()


class AIRetryConfig(RetryConfig):
    """AI API 专用重试配置"""

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
        """重试回调，记录日志"""
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
    """
    AI 活动筛选器（增强版）
    
    特性：
    - 支持速率限制（每分钟请求数 + 并发数）
    - 智能重试机制（指数退避）
    - 429限流自动处理
    - 可配置的容错策略
    """

    def __init__(
            self,
            api_key: str,
            system_prompt: str,
            user_prompt_template: str,
            model: str,
            temperature: float,
            base_url: Optional[str] = None,
            timeout: int = 30,
            extra_body: Optional[dict] = None,
            # 速率限制参数
            rate_limit_requests_per_minute: int = 0,
            rate_limit_max_concurrency: int = 3,
            rate_limit_enable_queue: bool = True,
            rate_limit_queue_timeout: float = 300.0,
            # 重试参数
            retry_max_retries: int = 3,
            retry_base_delay: float = 2.0,
            retry_max_delay: float = 60.0,
            retry_backoff_factor: float = 2.0,
            retry_on_status: Optional[list[int]] = None,
            retry_on_network_error: bool = True,
    ):
        """
        初始化 AI 筛选器
        
        Args:
            api_key: API 密钥
            base_url: API 基础 URL（可选，用于第三方兼容服务）
            model: 模型名称
            system_prompt: 系统提示词
            user_prompt_template: 用户提示词模板
            temperature: 采样温度
            timeout: 请求超时时间（秒）
            extra_body: 额外的请求体参数
            
            # 速率限制参数
            rate_limit_requests_per_minute: 每分钟最大请求数（0表示不限制）
            rate_limit_max_concurrency: 最大并发数
            rate_limit_enable_queue: 达到限制时是否排队等待
            rate_limit_queue_timeout: 队列最大等待时间（秒）
            
            # 重试配置
            retry_max_retries: 最大重试次数
            retry_base_delay: 基础重试延迟（秒）
            retry_max_delay: 最大重试延迟（秒）
            retry_backoff_factor: 退避倍数
            retry_on_status: 触发重试的HTTP状态码列表
            retry_on_network_error: 网络错误是否重试
        """
        # 验证必填参数
        if not api_key:
            raise ValueError("AI 筛选器初始化失败：api_key 不能为空")
        if not model:
            raise ValueError("AI 筛选器初始化失败：model 不能为空")
        if not system_prompt:
            raise ValueError("AI 筛选器初始化失败：system_prompt 不能为空")
        if not user_prompt_template:
            raise ValueError("AI 筛选器初始化失败：user_prompt_template 不能为空")
        if temperature is None:
            raise ValueError("AI 筛选器初始化失败：temperature 不能为空")

        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.system_prompt = system_prompt
        self.user_prompt_template = user_prompt_template
        self.temperature = temperature
        self.timeout = timeout
        self.extra_body = extra_body or {}

        # 初始化速率限制器
        self.rate_limiter = AIRateLimiterConfig(
            requests_per_minute=rate_limit_requests_per_minute,
            max_concurrency=rate_limit_max_concurrency,
            enable_queue=rate_limit_enable_queue,
            queue_timeout=rate_limit_queue_timeout,
        )

        # 初始化重试配置
        self.retry_config = AIRetryConfig(
            max_retries=retry_max_retries,
            base_delay=retry_base_delay,
            max_delay=retry_max_delay,
            backoff_factor=retry_backoff_factor,
            retry_on_status=retry_on_status,
            retry_on_network_error=retry_on_network_error,
        )

        # 初始化 OpenAI 客户端
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)

        logger.info(f"AI 筛选器初始化完成，模型: {model}")
        logger.info(f"重试配置: 最多{retry_max_retries}次，基础延迟{retry_base_delay}秒")
        if self.extra_body:
            logger.info(f"已配置额外请求参数: {self.extra_body}")

    def _format_activity_info(self, activity: SecondClass) -> str:
        """
        格式化活动信息为文本
        
        Args:
            activity: SecondClass 对象
            
        Returns:
            格式化后的活动信息文本
        """
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

        # 添加活动简介（如果存在且不太长）
        if activity.conceive and len(activity.conceive) > 10:
            conceive = activity.conceive[:500]  # 限制长度
            lines.append(f"活动简介：{conceive}")

        return "\n".join(lines)

    async def filter_activities(
            self,
            activities: list[SecondClass],
            user_info: str,
    ) -> tuple[list[SecondClass], list[FilteredActivity]]:
        """
        批量筛选活动（带速率限制和重试机制）

        Args:
            activities: 待筛选的活动列表
            user_info: 用户信息描述

        Returns:
            (保留的活动列表, 被过滤掉的 FilteredActivity 列表)
        """
        if not activities:
            return [], []

        if not self.api_key:
            logger.warning("未配置 API 密钥，跳过 AI 筛选")
            return activities, []

        logger.info(f"开始 AI 筛选 {len(activities)} 个活动（带速率限制和重试）...")

        async def judge_with_limit_and_retry(activity: SecondClass) -> tuple[SecondClass, bool, str]:
            """带速率限制和重试的判断任务"""
            async with self.rate_limiter.acquire():
                try:
                    # 使用重试机制执行判断
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

        # 并发执行所有判断任务
        tasks = [judge_with_limit_and_retry(activity) for activity in activities]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 收集通过筛选的活动
        kept_activities = []
        filtered_activities: list[FilteredActivity] = []

        for result in results:
            if isinstance(result, Exception):
                # 任务本身出错（不应该发生，但保险起见）
                logger.error(f"AI 筛选任务异常: {result}")
                continue

            activity, is_interested, reason = result
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

    async def _judge_activity_with_reason(self, activity: SecondClass, user_info: str) -> tuple[bool, str]:
        """
        判断单个活动是否符合用户兴趣（内部方法，会被重试包装）

        Args:
            activity: SecondClass 对象
            user_info: 用户信息描述

        Returns:
            (是否感兴趣, 原因说明)
        """
        activity_info = self._format_activity_info(activity)

        user_prompt = self.user_prompt_template.format(
            user_info=user_info,
            activity_info=activity_info,
        )

        # 构建请求参数
        request_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "timeout": self.timeout,
        }

        # 添加额外的请求体参数（如 Kimi 的 thinking 控制）
        if self.extra_body:
            request_params["extra_body"] = self.extra_body

        response = await self.client.chat.completions.create(**request_params)

        content = response.choices[0].message.content.strip()

        # 解析 JSON 响应
        result = self._parse_response(content)
        reason = result.get('reason', '')

        if result.get("interested"):
            logger.debug(f"AI 认为 '{activity.name}' 符合用户兴趣: {reason}")
            return True, reason
        else:
            logger.debug(f"AI 认为 '{activity.name}' 不符合用户兴趣: {reason}")
            return False, reason

    def _parse_response(self, content: str) -> dict:
        """
        解析 AI 响应内容
        
        Args:
            content: AI 返回的文本内容
            
        Returns:
            解析后的字典
        """
        # 尝试直接解析 JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 代码块
        import re

        # 匹配 ```json ... ``` 格式
        json_pattern = r"```(?:json)?\s*(.*?)\s*```"
        matches = re.findall(json_pattern, content, re.DOTALL)

        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # 尝试匹配 { ... } 格式
        brace_pattern = r"(\{[\s\S]*\})"
        matches = re.findall(brace_pattern, content)

        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # 解析失败，返回默认值（保守起见认为感兴趣）
        logger.warning(f"无法解析 AI 响应: {content[:200]}...")
        return {"interested": True, "reason": "解析失败，默认保留"}


class AIFilterConfig:
    """AI 筛选器配置（用于从 settings 创建实例）"""

    @staticmethod
    def create_from_settings(settings) -> Optional[AIFilter]:
        """
        从配置创建 AI 筛选器实例
        
        支持新的速率限制和重试配置
        """
        if not hasattr(settings, 'ai'):
            return None

        ai_config = settings.ai

        if not ai_config.enabled:
            logger.info("AI 筛选功能已禁用")
            return None

        # 验证必填配置项（调用配置类的验证方法）
        ai_config.validate_required_fields()

        # 从文件加载提示词（严格要求文件必须存在）
        from src.config.settings import load_prompt_file_strict

        system_prompt = load_prompt_file_strict(ai_config.system_prompt_file)
        user_prompt_template = load_prompt_file_strict(ai_config.user_prompt_template_file)

        logger.info(f"已加载系统提示词: {ai_config.system_prompt_file}")
        logger.info(f"已加载用户提示词模板: {ai_config.user_prompt_template_file}")

        # 构建速率限制参数
        rate_limit_kwargs = {}
        if hasattr(ai_config, 'rate_limit') and ai_config.rate_limit:
            rate_limit = ai_config.rate_limit
            rate_limit_kwargs['rate_limit_requests_per_minute'] = getattr(rate_limit, 'requests_per_minute', 0)
            rate_limit_kwargs['rate_limit_max_concurrency'] = getattr(rate_limit, 'max_concurrency', 3)
            rate_limit_kwargs['rate_limit_enable_queue'] = getattr(rate_limit, 'enable_queue', True)
            rate_limit_kwargs['rate_limit_queue_timeout'] = getattr(rate_limit, 'queue_timeout', 300.0)

        # 构建重试参数
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
            user_prompt_template=user_prompt_template,
            temperature=ai_config.temperature,
            timeout=ai_config.timeout,
            extra_body=ai_config.extra_body,
            **rate_limit_kwargs,
            **retry_kwargs,
        )
