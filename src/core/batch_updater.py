"""批量并发更新 SecondClass 实例"""
import asyncio
from typing import Optional

from pyustc.young import SecondClass

from src.utils.logger import get_logger

logger = get_logger("batch_updater")


class SecondClassBatchUpdater:
    """
    批量并发更新 SecondClass 实例
    
    使用 Semaphore 限制并发数，避免对服务器造成过大压力
    """

    def __init__(self, max_concurrent: int = 5):
        """
        初始化批量更新器
        
        Args:
            max_concurrent: 最大并发数，默认为 5
        """
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent

    async def _update_single(self, sc: SecondClass) -> tuple[SecondClass, bool, Optional[Exception]]:
        """
        更新单个 SecondClass 实例（带信号量控制）
        
        Returns:
            (instance, success, exception)
        """
        async with self._semaphore:
            try:
                await sc.update()
                return sc, True, None
            except Exception as e:
                logger.warning(f"更新 SecondClass {sc.id} 失败: {e}")
                return sc, False, e

    async def update_batch(
            self,
            instances: list[SecondClass],
            continue_on_error: bool = True
    ) -> tuple[list[SecondClass], list[tuple[SecondClass, Exception]]]:
        """
        批量并发更新 SecondClass 实例
        
        Args:
            instances: 要更新的 SecondClass 实例列表
            continue_on_error: 遇到错误时是否继续更新其他实例
            
        Returns:
            (成功更新的实例列表, 失败的实例及异常列表)
        """
        if not instances:
            return [], []

        logger.info(f"开始批量更新 {len(instances)} 个 SecondClass 实例，并发数: {self._max_concurrent}")

        # 创建所有更新任务
        tasks = [self._update_single(sc) for sc in instances]

        # 并发执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful = []
        failed = []

        for result in results:
            if isinstance(result, Exception):
                # 这里理论上不会发生，因为 _update_single 捕获了异常
                logger.error(f"更新任务异常: {result}")
                continue

            sc, success, error = result
            if success:
                successful.append(sc)
            else:
                failed.append((sc, error))
                if not continue_on_error:
                    break

        logger.info(f"批量更新完成: {len(successful)} 成功, {len(failed)} 失败")
        return successful, failed
