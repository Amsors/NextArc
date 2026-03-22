"""AI 活动筛选器

使用大模型 API 筛选用户感兴趣的新活动
支持 OpenAI API 格式
"""

import asyncio
import json
import traceback
from typing import Optional

from openai import AsyncOpenAI

from src.models import Activity, ActivityChange
from src.utils.logger import get_logger

logger = get_logger("ai_filter")


class AIFilter:
    """
    AI 活动筛选器
    
    使用大模型 API 判断新活动是否符合用户兴趣
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
    ):
        """
        初始化 AI 筛选器
        
        Args:
            api_key: API 密钥
            base_url: API 基础 URL（可选，用于第三方兼容服务）
            model: 模型名称
            system_prompt: 系统提示词（可选，使用默认值）
            user_prompt_template: 用户提示词模板（可选，使用默认值）
            temperature: 采样温度
            timeout: 请求超时时间（秒）
            extra_body: 额外的请求体参数（可选，用于第三方 API 扩展功能）
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
        
        # 初始化 OpenAI 客户端
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        
        self.client = AsyncOpenAI(**client_kwargs)
        
        logger.info(f"AI 筛选器初始化完成，模型: {model}")
        if self.extra_body:
            logger.info(f"已配置额外请求参数: {self.extra_body}")
    
    def _format_activity_info(self, activity: Activity) -> str:
        """
        格式化活动信息为文本
        
        Args:
            activity: 活动对象
            
        Returns:
            格式化后的活动信息文本
        """
        lines = [
            f"活动名称：{activity.name}",
            f"活动状态：{activity.get_status_text()}",
            f"举办时间：{activity.get_display_time('hold_time')}",
            f"报名时间：{activity.get_display_time('apply_time')}",
            f"学时：{activity.valid_hour or '未知'}",
            f"模块：{activity.get_module_name()}",
            f"组织单位：{activity.get_department_name()}",
            f"已报名/名额：{activity.get_apply_progress()}",
        ]
        
        # 添加活动简介（如果存在且不太长）
        if activity.conceive and len(activity.conceive) > 10:
            conceive = activity.conceive[:500]  # 限制长度
            lines.append(f"活动简介：{conceive}")
        
        return "\n".join(lines)
    
    async def filter_activities(
        self,
        activities: list[Activity],
        user_info: str,
        uninterested_activities: list[Activity] | None = None,
    ) -> list[Activity]:
        """
        批量筛选活动（并发执行，带超时控制）
        
        使用 asyncio.gather 并发处理多个活动，避免顺序执行导致 WebSocket 心跳超时。
        每个 AI 调用有独立的超时控制。
        
        Args:
            activities: 待筛选的活动列表
            user_info: 用户信息描述
            uninterested_activities: 返回不感兴趣的活动(可选参数)
            
        Returns:
            筛选后的活动列表（仅保留 AI 认为感兴趣的）
        """
        if not activities:
            return []
        
        if not self.api_key:
            logger.warning("未配置 API 密钥，跳过 AI 筛选")
            return activities
        
        logger.info(f"开始 AI 筛选 {len(activities)} 个活动（并发执行，超时 {self.timeout} 秒）...")
        
        # 创建信号量限制并发数（避免同时发送太多请求）
        semaphore = asyncio.Semaphore(3)
        
        async def judge_with_semaphore(activity: Activity) -> tuple[Activity, bool]:
            """带信号量和超时的判断任务"""
            async with semaphore:
                try:
                    # 使用 wait_for 添加超时控制
                    is_interested = await asyncio.wait_for(
                        self._judge_activity(activity, user_info),
                        timeout=self.timeout
                    )
                    return activity, is_interested
                except asyncio.TimeoutError:
                    logger.warning(f"AI 判断活动 '{activity.name}' 超时，保留该活动")
                    return activity, True  # 超时保守处理：保留
                except Exception as e:
                    logger.warning(f"AI 判断活动 '{activity.name}' 失败: {e}，保留该活动")
                    return activity, True  # 失败保守处理：保留
        
        # 并发执行所有判断任务
        tasks = [judge_with_semaphore(activity) for activity in activities]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 收集通过筛选的活动
        filtered_activities = []
        for result in results:
            if isinstance(result, Exception):
                # 任务本身出错（不应该发生，但保险起见）
                logger.error(f"AI 筛选任务异常: {result}")
                continue
            
            activity, is_interested = result
            if is_interested:
                filtered_activities.append(activity)
                logger.debug(f"活动 '{activity.name}' 通过 AI 筛选")
            else:
                if uninterested_activities is not None:
                    uninterested_activities.append(activity)
                logger.debug(f"活动 '{activity.name}' AI 认为用户不感兴趣")
        
        logger.info(f"AI 筛选完成：{len(filtered_activities)}/{len(activities)} 个活动通过")
        return filtered_activities
    
    async def _judge_activity(self, activity: Activity, user_info: str) -> bool:
        """
        判断单个活动是否符合用户兴趣
        
        Args:
            activity: 活动对象
            user_info: 用户信息描述
            
        Returns:
            是否感兴趣
        """
        activity_info = self._format_activity_info(activity)
        
        user_prompt = self.user_prompt_template.format(
            user_info=user_info,
            activity_info=activity_info,
        )
        
        try:
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
            
            if result.get("interested"):
                logger.debug(f"AI 认为 '{activity.name}' 符合用户兴趣: {result.get('reason', '')}")
                return True
            else:
                logger.debug(f"AI 认为 '{activity.name}' 不符合用户兴趣: {result.get('reason', '')}")
                return False
                
        except Exception as e:
            logger.error(f"AI API 调用失败: {e}")
            raise
    
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
        
        从配置文件中读取提示词文件路径，然后从文件加载提示词内容。
        如果 AI 功能已启用但配置不完整或提示词文件不存在，会抛出异常。
        
        Args:
            settings: 配置对象
            
        Returns:
            AIFilter 实例，如果未启用则返回 None
            
        Raises:
            ValueError: 如果 AI 功能已启用但配置不完整
            FileNotFoundError: 如果提示词文件不存在
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
        
        return AIFilter(
            api_key=ai_config.api_key,
            base_url=ai_config.base_url if ai_config.base_url else None,
            model=ai_config.model,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
            temperature=ai_config.temperature,
            timeout=ai_config.timeout,
            extra_body=ai_config.extra_body,
        )
