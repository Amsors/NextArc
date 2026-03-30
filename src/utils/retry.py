"""重试机制 - 支持指数退避和条件判断"""

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
        """判断是否应该重试"""
        if isinstance(exception, RateLimitError):
            return True

        if isinstance(exception, APITimeoutError):
            return self.retry_on_network_error

        if isinstance(exception, APIError):
            if hasattr(exception, 'status_code'):
                return exception.status_code in self.retry_on_status

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
        """计算重试延迟（指数退避 + 抖动）"""
        delay = self.base_delay * (self.backoff_factor ** attempt)

        # 随机抖动
        jitter = random.uniform(0.75, 1.25)
        delay *= jitter
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

            if attempt >= config.max_retries:
                raise

            if not config.should_retry(e):
                raise

            delay = config.calculate_delay(attempt)

            if config.on_retry:
                try:
                    config.on_retry(e, attempt + 1, delay)
                except Exception:
                    pass

            await asyncio.sleep(delay)

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
