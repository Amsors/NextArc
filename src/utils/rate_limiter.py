"""速率限制器 - Token Bucket 算法实现"""

import asyncio
import time


class TokenBucketRateLimiter:
    """Token Bucket 速率限制器"""

    def __init__(
            self,
            requests_per_minute: int,
            max_concurrency: int = 3,
            enable_queue: bool = True,
            queue_timeout: float = 300.0,
    ):
        """初始化速率限制器。requests_per_minute=0 表示不限制。"""
        self.requests_per_minute = requests_per_minute
        self.max_concurrency = max_concurrency
        self.enable_queue = enable_queue
        self.queue_timeout = queue_timeout

        self._tokens: float = max_concurrency
        self._last_update = time.monotonic()
        self._rate = requests_per_minute / 60.0 if requests_per_minute > 0 else float('inf')
        self._max_tokens = max(max_concurrency,
                               requests_per_minute / 60.0 if requests_per_minute > 0 else max_concurrency)

        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """获取执行许可，失败表示超时"""
        async with self._semaphore:
            if self.requests_per_minute <= 0:
                return True

            start_time = time.monotonic()

            while True:
                async with self._lock:
                    now = time.monotonic()
                    elapsed = now - self._last_update

                    self._tokens = min(
                        self._max_tokens,
                        self._tokens + elapsed * self._rate
                    )
                    self._last_update = now

                    if self._tokens >= 1:
                        self._tokens -= 1
                        return True

                if not self.enable_queue:
                    return False

                if time.monotonic() - start_time > self.queue_timeout:
                    return False

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
        pass


class RateLimiterWrapper:
    """速率限制器包装器，根据配置决定是否启用速率限制"""

    def __init__(
            self,
            requests_per_minute: int = 0,
            max_concurrency: int = 3,
            enable_queue: bool = True,
            queue_timeout: float = 300.0,
    ):
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
