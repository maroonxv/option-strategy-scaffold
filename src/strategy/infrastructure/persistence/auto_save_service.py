"""周期性自动保存服务。

在 on_bars 回调中按时间间隔自动保存策略状态到数据库，
避免仅在 on_stop 时保存导致崩溃丢失数据。

设计决策:
- maybe_save 接受 Callable 而非直接接受数据，实现惰性求值
- 使用 time.monotonic() 计时，避免系统时钟调整的影响
- 保存失败时捕获异常并记录日志，不中断策略执行
- 使用 digest 哈希检测状态变化，跳过重复保存
- 使用 ThreadPoolExecutor(max_workers=1) 异步保存，避免阻塞 on_bars
- 上一次异步保存未完成时跳过本次保存请求
- 按可配置频率（默认 24 小时）自动触发旧快照清理

Requirements: 1.1, 1.2, 1.3, 1.5, 2.1, 2.2, 2.3, 2.5, 4.1, 4.2, 4.5, 5.1, 5.2, 5.3, 5.5
"""

import hashlib
import time
from concurrent.futures import Future, ThreadPoolExecutor
from logging import Logger, getLogger
from typing import Any, Callable, Dict, Optional

from src.strategy.infrastructure.persistence.json_serializer import JsonSerializer
from src.strategy.infrastructure.persistence.state_repository import StateRepository


class AutoSaveService:
    """周期性自动保存服务"""

    def __init__(
        self,
        state_repository: StateRepository,
        strategy_name: str,
        serializer: JsonSerializer,
        interval_seconds: float = 60.0,
        cleanup_interval_hours: float = 24.0,
        keep_days: int = 7,
        logger: Optional[Logger] = None,
    ) -> None:
        self._repository = state_repository
        self._strategy_name = strategy_name
        self._serializer = serializer
        self._interval_seconds = interval_seconds
        self._logger = logger or getLogger(__name__)
        self._last_save_time: float = time.monotonic()
        self._last_digest: Optional[str] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._pending_future: Optional[Future] = None
        self._last_cleanup_time: float = time.monotonic()
        self._cleanup_interval_seconds = cleanup_interval_hours * 3600
        self._keep_days = keep_days

    def maybe_save(self, snapshot_fn: Callable[[], Dict[str, Any]]) -> None:
        """检查是否到达保存间隔，若到达则保存快照。

        snapshot_fn 是惰性求值，仅在需要保存时才调用，
        避免每次 on_bars 都执行序列化开销。
        """
        now = time.monotonic()
        elapsed = now - self._last_save_time
        if elapsed < self._interval_seconds:
            return

        self._do_save(snapshot_fn)

    def force_save(self, snapshot_fn: Callable[[], Dict[str, Any]]) -> None:
        """强制立即保存（用于 on_stop）。
        
        等待当前异步保存完成（timeout=30），然后无条件执行同步保存，
        忽略 digest 比较。确保 on_stop 时最终状态被保存。
        
        Requirements: 2.4, 5.4
        """
        try:
            # 等待当前异步保存完成
            if self._pending_future and not self._pending_future.done():
                self._logger.debug(
                    f"等待当前异步保存完成 [{self._strategy_name}]"
                )
                try:
                    self._pending_future.result(timeout=30)
                except Exception as e:
                    self._logger.error(
                        f"等待异步保存超时或失败 [{self._strategy_name}]: {e}",
                        exc_info=True,
                    )
            
            # 无条件执行同步保存，忽略 digest 比较
            data = snapshot_fn()
            self._repository.save(self._strategy_name, data)
            self._logger.info(f"强制保存完成 [{self._strategy_name}]")
        except Exception as e:
            self._logger.error(
                f"强制保存失败 [{self._strategy_name}]: {e}",
                exc_info=True,
            )

    def reset(self) -> None:
        """重置计时器。"""
        self._last_save_time = time.monotonic()

    def _do_save(self, snapshot_fn: Callable[[], Dict[str, Any]]) -> None:
        """执行保存操作，失败时记录日志但不中断策略执行。
        
        使用 digest 检测状态变化，跳过重复保存。
        异步保存：digest 变化时 submit 到后台线程执行。
        """
        try:
            data = snapshot_fn()
            json_str = self._serializer.serialize(data)
            digest = self._compute_digest(json_str)
            
            # 检查 digest 是否变化
            if self._last_digest is not None and digest == self._last_digest:
                self._logger.debug(
                    f"状态未变化 (digest={digest[:8]}...)，跳过保存 [{self._strategy_name}]"
                )
                self._last_save_time = time.monotonic()
                return
            
            # 检查上一次异步保存是否完成
            if self._pending_future and not self._pending_future.done():
                self._logger.debug(
                    f"上一次异步保存尚未完成，跳过本次 [{self._strategy_name}]"
                )
                return
            
            # 状态已变化，提交到后台线程执行
            self._pending_future = self._executor.submit(
                self._save_in_background, json_str
            )
            self._last_digest = digest
            self._last_save_time = time.monotonic()
            self._logger.debug(
                f"已提交异步保存 (digest={digest[:8]}...) [{self._strategy_name}]"
            )
        except Exception as e:
            self._logger.error(
                f"自动保存失败 [{self._strategy_name}]: {e}",
                exc_info=True,
            )

    def _compute_digest(self, json_str: str) -> str:
        """计算 JSON 字符串的 SHA-256 摘要。
        
        由于 JsonSerializer 使用 sort_keys=True，相同状态始终产生相同的 JSON 字符串，
        从而产生相同的 digest。
        """
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def _save_in_background(self, json_str: str) -> None:
        """后台线程执行保存操作。
        
        异常时记录错误日志，不影响主线程。
        保存成功后触发自动清理检查。
        """
        try:
            self._repository.save_raw(self._strategy_name, json_str)
            self._logger.debug(f"异步保存完成 [{self._strategy_name}]")
            # 保存成功后检查是否需要清理
            self._maybe_cleanup()
        except Exception as e:
            self._logger.error(
                f"异步保存失败 [{self._strategy_name}]: {e}",
                exc_info=True,
            )

    def _maybe_cleanup(self) -> None:
        """检查是否需要触发清理操作。
        
        按可配置频率（默认 24 小时）触发 StateRepository.cleanup。
        清理失败时记录错误日志，不影响策略运行。
        
        Requirements: 4.1, 4.2, 4.5
        """
        now = time.monotonic()
        elapsed = now - self._last_cleanup_time
        
        if elapsed >= self._cleanup_interval_seconds:
            try:
                deleted_count = self._repository.cleanup(
                    self._strategy_name, self._keep_days
                )
                self._last_cleanup_time = now
                self._logger.info(
                    f"自动清理完成，删除 {deleted_count} 条旧快照 [{self._strategy_name}]"
                )
            except Exception as e:
                self._logger.error(
                    f"清理旧快照失败 [{self._strategy_name}]: {e}",
                    exc_info=True,
                )

    def shutdown(self) -> None:
        """关闭线程池。
        
        等待所有后台任务完成后关闭线程池。
        
        Requirements: 5.4
        """
        self._executor.shutdown(wait=True)
        self._logger.debug(f"AutoSaveService 已关闭 [{self._strategy_name}]")
