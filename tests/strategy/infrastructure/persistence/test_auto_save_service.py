"""
Tests for AutoSaveService — Property-Based Tests and Unit Tests

Feature: persistence-resilience-enhancement

Property 1: Auto-save interval gating — Validates: Requirements 1.1, 1.3

Unit tests: 默认间隔 60 秒、写入失败不中断 — Requirements: 1.2, 1.5
"""

import sys
from unittest.mock import MagicMock, call, patch

import pytest
from hypothesis import given, settings, strategies as st

# Mock vnpy modules before importing anything that touches database_factory
for _mod_name in [
    "vnpy", "vnpy.event", "vnpy.trader", "vnpy.trader.setting",
    "vnpy.trader.engine", "vnpy.trader.database", "vnpy_mysql",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

sys.modules["vnpy.trader.setting"].SETTINGS = {}

from src.strategy.infrastructure.persistence.auto_save_service import AutoSaveService


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Positive intervals (seconds)
_intervals = st.floats(min_value=0.1, max_value=3600.0, allow_nan=False, allow_infinity=False)

# Non-negative time deltas (seconds elapsed between calls)
_time_deltas = st.floats(min_value=0.0, max_value=7200.0, allow_nan=False, allow_infinity=False)

# Sequences of time deltas representing gaps between maybe_save calls
_time_delta_sequences = st.lists(_time_deltas, min_size=1, max_size=20)


# ===========================================================================
# Property-Based Tests (Task 8.2)
# ===========================================================================

class TestAutoSaveServiceProperties:
    """Property-based tests for AutoSaveService.

    Feature: persistence-resilience-enhancement, Property 1: Auto-save interval gating
    """

    @settings(max_examples=100, deadline=None)
    @given(interval=_intervals, deltas=_time_delta_sequences)
    def test_property_1_auto_save_interval_gating(
        self, interval: float, deltas: list
    ):
        """
        **Validates: Requirements 1.1, 1.3**

        For any sequence of maybe_save calls with associated timestamps,
        a save operation should occur if and only if the elapsed time since
        the last save is >= the configured interval.
        """
        mock_repo = MagicMock()
        snapshot_data = {"test": "data"}
        snapshot_fn = MagicMock(return_value=snapshot_data)

        # Track the monotonic clock manually
        current_time = 1000.0  # arbitrary start

        with patch("src.strategy.infrastructure.persistence.auto_save_service.time") as mock_time:
            mock_time.monotonic.return_value = current_time
            service = AutoSaveService(
                state_repository=mock_repo,
                strategy_name="test_strategy",
                interval_seconds=interval,
            )

            # After construction, _last_save_time = current_time
            time_of_last_save = current_time
            expected_save_count = 0

            for delta in deltas:
                current_time += delta
                mock_time.monotonic.return_value = current_time

                service.maybe_save(snapshot_fn)

                elapsed = current_time - time_of_last_save
                if elapsed >= interval:
                    expected_save_count += 1
                    # After a successful save, _do_save calls monotonic() again
                    # to update _last_save_time, so we need to track that
                    time_of_last_save = current_time

            assert mock_repo.save.call_count == expected_save_count


# ===========================================================================
# Unit Tests (Task 8.3)
# ===========================================================================

class TestAutoSaveServiceUnit:
    """Unit tests for AutoSaveService."""

    def test_default_interval_is_60_seconds(self):
        """Requirement 1.2: 默认间隔 60 秒"""
        mock_repo = MagicMock()
        service = AutoSaveService(
            state_repository=mock_repo,
            strategy_name="test",
        )
        assert service._interval_seconds == 60.0

    def test_maybe_save_skips_when_interval_not_elapsed(self):
        """Requirement 1.3: 未到间隔时跳过保存"""
        mock_repo = MagicMock()
        snapshot_fn = MagicMock(return_value={"data": 1})

        with patch("src.strategy.infrastructure.persistence.auto_save_service.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            service = AutoSaveService(
                state_repository=mock_repo,
                strategy_name="test",
                interval_seconds=60.0,
            )

            # Only 30 seconds later — should NOT save
            mock_time.monotonic.return_value = 130.0
            service.maybe_save(snapshot_fn)

            mock_repo.save.assert_not_called()
            snapshot_fn.assert_not_called()

    def test_maybe_save_triggers_when_interval_elapsed(self):
        """Requirement 1.1: 到达间隔时触发保存"""
        mock_repo = MagicMock()
        snapshot_data = {"data": 1}
        snapshot_fn = MagicMock(return_value=snapshot_data)

        with patch("src.strategy.infrastructure.persistence.auto_save_service.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            service = AutoSaveService(
                state_repository=mock_repo,
                strategy_name="test",
                interval_seconds=60.0,
            )

            # Exactly 60 seconds later — should save
            mock_time.monotonic.return_value = 160.0
            service.maybe_save(snapshot_fn)

            mock_repo.save.assert_called_once_with("test", snapshot_data)
            snapshot_fn.assert_called_once()

    def test_force_save_always_saves(self):
        """force_save 应始终保存，不检查间隔"""
        mock_repo = MagicMock()
        snapshot_data = {"data": 1}
        snapshot_fn = MagicMock(return_value=snapshot_data)

        with patch("src.strategy.infrastructure.persistence.auto_save_service.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            service = AutoSaveService(
                state_repository=mock_repo,
                strategy_name="test",
                interval_seconds=60.0,
            )

            # Immediately force save — no interval check
            mock_time.monotonic.return_value = 100.0
            service.force_save(snapshot_fn)

            mock_repo.save.assert_called_once_with("test", snapshot_data)

    def test_save_failure_does_not_interrupt(self):
        """Requirement 1.5: 写入失败不中断策略执行"""
        mock_repo = MagicMock()
        mock_repo.save.side_effect = RuntimeError("DB connection lost")
        snapshot_fn = MagicMock(return_value={"data": 1})

        with patch("src.strategy.infrastructure.persistence.auto_save_service.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            service = AutoSaveService(
                state_repository=mock_repo,
                strategy_name="test",
                interval_seconds=10.0,
            )

            # Trigger save — should NOT raise
            mock_time.monotonic.return_value = 200.0
            service.maybe_save(snapshot_fn)

            # No exception propagated — strategy continues
            mock_repo.save.assert_called_once()

    def test_force_save_failure_does_not_interrupt(self):
        """Requirement 1.5: force_save 写入失败也不中断"""
        mock_repo = MagicMock()
        mock_repo.save.side_effect = Exception("disk full")
        snapshot_fn = MagicMock(return_value={"data": 1})

        service = AutoSaveService(
            state_repository=mock_repo,
            strategy_name="test",
        )

        # Should NOT raise
        service.force_save(snapshot_fn)
        mock_repo.save.assert_called_once()

    def test_reset_resets_timer(self):
        """reset 应重置计时器"""
        mock_repo = MagicMock()
        snapshot_fn = MagicMock(return_value={"data": 1})

        with patch("src.strategy.infrastructure.persistence.auto_save_service.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            service = AutoSaveService(
                state_repository=mock_repo,
                strategy_name="test",
                interval_seconds=60.0,
            )

            # 70 seconds later — would normally trigger save
            mock_time.monotonic.return_value = 170.0
            service.reset()  # reset timer to 170.0

            # Now only 10 seconds after reset — should NOT save
            mock_time.monotonic.return_value = 180.0
            service.maybe_save(snapshot_fn)

            mock_repo.save.assert_not_called()

    def test_snapshot_fn_not_called_when_skipping(self):
        """惰性求值: snapshot_fn 仅在需要保存时才被调用"""
        mock_repo = MagicMock()
        snapshot_fn = MagicMock(return_value={"data": 1})

        with patch("src.strategy.infrastructure.persistence.auto_save_service.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            service = AutoSaveService(
                state_repository=mock_repo,
                strategy_name="test",
                interval_seconds=60.0,
            )

            # 10 seconds — skip
            mock_time.monotonic.return_value = 110.0
            service.maybe_save(snapshot_fn)
            snapshot_fn.assert_not_called()
