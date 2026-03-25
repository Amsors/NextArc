"""重试机制 - 支持指数退避和条件判断

提供灵活的重试功能：
- 指数退避策略
- 随机抖动避免 thundering herd
- 可配置的重试条件
- 支持特定HTTP状态码重试
"""

import asyncio
import functools
import random
from typing import Callable, Optional, TypeVar

from openai import APIError, RateLimitError, APITimeoutError

T = TypeVar('T')


class RetryConfig:
    """重试配置类"""

    def __init__(
            self,
            max_retries: int = 3,
            base_delay: float = 2.0,
            max_delay: float = 60.0,
            backoff_factor: float = 2.0,
            retry_on_status: Optional[list[int]] = None,
            retry_on_network_error: bool = True,
            on_retry: Optional[Callable[[Exception, int, float], None]] = None,
    ):
        """
        初始化重试配置
        
        Args:
            max_retries: 最大重试次数
            base_delay: 基础重试延迟（秒）
            max_delay: 最大重试延迟（秒）
            backoff_factor: 退避倍数（指数退避）
            retry_on_status: 触发重试的HTTP状态码列表
            retry_on_network_error: 网络错误是否重试
            on_retry: 重试回调函数(exception, attempt, delay)
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.retry_on_status = set(retry_on_status or [429, 500, 502, 503, 504])
        self.retry_on_network_error = retry_on_network_error
        self.on_retry = on_retry

    def should_retry(self, exception: Exception) -> bool:
        """
        判断是否应该重试
        
        Args:
            exception: 发生的异常
            
        Returns:
            是否应该重试
        """
        # 429 Too Many Requests - 确定要重试
        if isinstance(exception, RateLimitError):
            return True

        # API 超时错误
        if isinstance(exception, APITimeoutError):
            return self.retry_on_network_error

        # 其他 API 错误，检查状态码
        if isinstance(exception, APIError):
            if hasattr(exception, 'status_code'):
                return exception.status_code in self.retry_on_status

        # 网络相关错误
        if self.retry_on_network_error:
            network_errors = (
                ConnectionError,
                TimeoutError,
                asyncio.TimeoutError,
                OSError,
            )
            if isinstance(exception, network_errors):
                return True

        return False

    def calculate_delay(self, attempt: int) -> float:
        """
        计算重试延迟（指数退避 + 抖动）
        
        公式：delay = base_delay * (backoff_factor ^ attempt) * jitter
        
        Args:
            attempt: 当前重试次数（从0开始）
            
        Returns:
            重试延迟（秒）
        """
        # 指数退避: base_delay * (backoff_factor ^ attempt)
        delay = self.base_delay * (self.backoff_factor ** attempt)

        # 添加随机抖动 (±25%)，避免 thundering herd
        jitter = random.uniform(0.75, 1.25)
        delay *= jitter

        # 限制最大延迟
        return min(delay, self.max_delay)


async def with_retry(
        func: Callable[..., T],
        *args,
        config: RetryConfig,
        **kwargs
) -> T:
    """
    带重试的异步函数执行
    
    Args:
        func: 要执行的异步函数
        config: 重试配置
        *args, **kwargs: 函数参数
    
    Returns:
        函数执行结果
    
    Raises:
        最后一次重试的异常
    """
    last_exception: Optional[Exception] = None

    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            # 最后一次尝试，不再重试
            if attempt >= config.max_retries:
                raise

            # 检查是否应该重试
            if not config.should_retry(e):
                raise

            # 计算延迟
            delay = config.calculate_delay(attempt)

            # 回调通知
            if config.on_retry:
                try:
                    config.on_retry(e, attempt + 1, delay)
                except Exception:
                    pass

            await asyncio.sleep(delay)

    # 理论上不会执行到这里
    raise last_exception or RuntimeError("重试逻辑异常")


def retryable(
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        retry_on_status: Optional[list[int]] = None,
        retry_on_network_error: bool = True,
):
    """
    重试装饰器工厂
    
    用法：
        @retryable(max_retries=3, base_delay=2.0)
        async def my_function():
            ...
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础重试延迟（秒）
        max_delay: 最大重试延迟（秒）
        backoff_factor: 退避倍数
        retry_on_status: 触发重试的HTTP状态码列表
        retry_on_network_error: 网络错误是否重试
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        backoff_factor=backoff_factor,
        retry_on_status=retry_on_status,
        retry_on_network_error=retry_on_network_error,
    )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await with_retry(func, *args, config=config, **kwargs)

        return wrapper

    return decorator
