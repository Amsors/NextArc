"""速率限制器 - Token Bucket 算法实现

提供基于 Token Bucket 算法的速率限制功能，支持：
- 每分钟请求数限制
- 最大并发数限制
- 请求排队等待
- 队列超时控制
"""

import asyncio
import time
from typing import Optional


class TokenBucketRateLimiter:
    """
    Token Bucket 速率限制器
    
    用于限制单位时间内的请求数量，支持突发流量平滑处理。
    算法原理：
    - 桶中以恒定速率产生令牌
    - 每个请求需要获取一个令牌才能执行
    - 桶有容量限制，多余的令牌会被丢弃
    - 允许突发流量（桶中有累积的令牌时）
    """

    def __init__(
            self,
            requests_per_minute: int,
            max_concurrency: int = 3,
            enable_queue: bool = True,
            queue_timeout: float = 300.0,
    ):
        """
        初始化速率限制器
        
        Args:
            requests_per_minute: 每分钟最大请求数（0表示不限制）
            max_concurrency: 最大并发数
            enable_queue: 达到速率限制时是否排队等待
            queue_timeout: 队列最大等待时间（秒）
        """
        self.requests_per_minute = requests_per_minute
        self.max_concurrency = max_concurrency
        self.enable_queue = enable_queue
        self.queue_timeout = queue_timeout

        # Token Bucket 状态
        self._tokens: float = max_concurrency
        self._last_update = time.monotonic()
        self._rate = requests_per_minute / 60.0 if requests_per_minute > 0 else float('inf')
        self._max_tokens = max(max_concurrency,
                               requests_per_minute / 60.0 if requests_per_minute > 0 else max_concurrency)

        # 并发控制
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """
        获取执行许可
        
        如果当前有可用令牌，立即返回True；
        如果没有令牌且允许排队，则等待直到获取令牌或超时。
        
        Returns:
            是否成功获取（False表示超时）
        """
        async with self._semaphore:
            if self.requests_per_minute <= 0:
                # 不限制速率，直接通过
                return True

            start_time = time.monotonic()

            while True:
                async with self._lock:
                    now = time.monotonic()
                    elapsed = now - self._last_update

                    # 补充令牌：根据经过的时间按比例添加
                    self._tokens = min(
                        self._max_tokens,
                        self._tokens + elapsed * self._rate
                    )
                    self._last_update = now

                    if self._tokens >= 1:
                        # 有可用令牌，消耗一个并返回
                        self._tokens -= 1
                        return True

                # 无可用令牌
                if not self.enable_queue:
                    return False

                # 检查是否超时
                if time.monotonic() - start_time > self.queue_timeout:
                    return False

                # 计算等待时间（直到下一个令牌可用）
                wait_time = max(0.01, (1 - self._tokens) / self._rate if self._rate > 0 else 0.1)
                await asyncio.sleep(min(wait_time, 1.0))

    def release(self):
        """释放执行许可（由semaphore自动处理）"""
        pass


class RateLimitContext:
    """速率限制上下文管理器"""

    def __init__(self, limiter: TokenBucketRateLimiter):
        self.limiter = limiter
        self._acquired = False

    async def __aenter__(self):
        self._acquired = await self.limiter.acquire()
        if not self._acquired:
            raise TimeoutError("获取速率限制许可超时")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Semaphore 会自动释放
        pass


class RateLimiterWrapper:
    """
    速率限制器包装器
    
    根据配置决定是否启用速率限制，提供统一的接口。
    """

    def __init__(
            self,
            requests_per_minute: int = 0,
            max_concurrency: int = 3,
            enable_queue: bool = True,
            queue_timeout: float = 300.0,
    ):
        """
        初始化速率限制器包装器
        
        Args:
            requests_per_minute: 每分钟最大请求数（0表示不限制）
            max_concurrency: 最大并发数
            enable_queue: 达到速率限制时是否排队等待
            queue_timeout: 队列最大等待时间（秒）
        """
        self.requests_per_minute = requests_per_minute
        self.max_concurrency = max_concurrency

        if requests_per_minute > 0:
            self._limiter = TokenBucketRateLimiter(
                requests_per_minute=requests_per_minute,
                max_concurrency=max_concurrency,
                enable_queue=enable_queue,
                queue_timeout=queue_timeout,
            )
            self._semaphore = None
        else:
            self._limiter = None
            self._semaphore = asyncio.Semaphore(max_concurrency)

    def acquire(self):
        """获取执行许可的上下文管理器（同步方法，返回异步上下文管理器）"""
        if self._limiter:
            return RateLimitContext(self._limiter)
        else:
            return self._semaphore
