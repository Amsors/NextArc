"""批量并发更新 SecondClass 实例"""
import asyncio
from typing import Optional

from pyustc.young import SecondClass

from src.utils.logger import get_logger

logger = get_logger("batch_updater")


class SecondClassBatchUpdater:
    """批量并发更新 SecondClass 实例"""

    def __init__(self, max_concurrent: int = 5):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent

    async def _update_single(self, sc: SecondClass) -> tuple[SecondClass, bool, Optional[Exception]]:
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
        if not instances:
            return [], []

        logger.info(f"开始批量更新 {len(instances)} 个 SecondClass 实例，并发数: {self._max_concurrent}")

        successful = []
        failed = []

        if continue_on_error:
            tasks = [self._update_single(sc) for sc in instances]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            pending = {asyncio.create_task(self._update_single(sc)) for sc in instances}
            results = []
            try:
                for task in asyncio.as_completed(pending):
                    result = await task
                    results.append(result)
                    if not result[1]:
                        for pending_task in pending:
                            if not pending_task.done():
                                pending_task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        break
            finally:
                pending.clear()

        for result in results:
            if isinstance(result, Exception):
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
