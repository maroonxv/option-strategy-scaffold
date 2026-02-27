"""
Property-Based Tests for AutoSaveService - Data Persistence Optimization

Feature: data-persistence-optimization, Property 5: Digest 去重正确性
Feature: data-persistence-optimization, Property 8: 异步保存跳过未完成请求

Validates: Requirements 2.2, 2.3, 5.3
"""

import sys
from unittest.mock import MagicMock, Mock

import pytest
from hypothesis import given, settings, strategies as st

# Mock vnpy modules before importing database_factory (avoids __init__.py chain)
for _mod_name in [
    "vnpy", "vnpy.event", "vnpy.trader", "vnpy.trader.setting",
    "vnpy.trader.engine", "vnpy.trader.database", "vnpy_mysql",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Ensure SETTINGS is a real dict for tests
sys.modules["vnpy.trader.setting"].SETTINGS = {}

from src.strategy.infrastructure.persistence.auto_save_service import AutoSaveService
from src.strategy.infrastructure.persistence.json_serializer import JsonSerializer
from src.strategy.infrastructure.persistence.migration_chain import MigrationChain
from src.strategy.infrastructure.persistence.state_repository import StateRepository


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

def _snapshot_strategy():
    """Generate random Snapshot dictionaries.
    
    This strategy generates snapshot dictionaries with varying content to test
    digest-based deduplication. The snapshots contain:
    - target_aggregate: with varying numeric values
    - position_aggregate: with varying symbols and positions
    - current_dt: with varying timestamps
    - status: with varying status strings
    
    This ensures we can test both identical and different snapshots.
    """
    return st.fixed_dictionaries({
        "target_aggregate": st.fixed_dictionaries({
            "signal_value": st.floats(
                allow_nan=False, allow_infinity=False, min_value=-100, max_value=100
            ),
            "threshold": st.floats(
                allow_nan=False, allow_infinity=False, min_value=0, max_value=10
            ),
            "last_update": st.integers(min_value=0, max_value=1_000_000),
        }),
        "position_aggregate": st.fixed_dictionaries({
            "symbols": st.lists(
                st.text(min_size=5, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
                min_size=0,
                max_size=5,
            ),
            "total_position": st.integers(min_value=-1000, max_value=1000),
            "unrealized_pnl": st.floats(
                allow_nan=False, allow_infinity=False, min_value=-10000, max_value=10000
            ),
        }),
        "current_dt": st.integers(min_value=1_600_000_000, max_value=1_700_000_000),
        "status": st.sampled_from(["ACTIVE", "PAUSED", "STOPPED", "INITIALIZING"]),
    })


def _snapshot_pair_strategy():
    """Generate pairs of snapshots (identical or different).
    
    Returns:
        tuple: (snapshot1, snapshot2, are_identical)
    """
    # Strategy 1: Generate identical snapshots
    identical_pair = st.builds(
        lambda s: (s, s.copy(), True),
        _snapshot_strategy(),
    )
    
    # Strategy 2: Generate different snapshots
    different_pair = st.builds(
        lambda s1, s2: (s1, s2, False),
        _snapshot_strategy(),
        _snapshot_strategy(),
    ).filter(lambda pair: pair[0] != pair[1])  # Ensure they're actually different
    
    # Mix both strategies
    return st.one_of(identical_pair, different_pair)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_auto_save_service(
    mock_repository: Mock,
    interval_seconds: float = 0.0,  # No time-based throttling for tests
) -> AutoSaveService:
    """Create an AutoSaveService instance for testing.
    
    Args:
        mock_repository: Mock StateRepository for tracking save calls
        interval_seconds: Save interval (default 0 for immediate saves in tests)
        
    Returns:
        AutoSaveService instance configured for testing
    """
    serializer = JsonSerializer(MigrationChain())
    
    return AutoSaveService(
        state_repository=mock_repository,
        strategy_name="test_strategy",
        serializer=serializer,
        interval_seconds=interval_seconds,
        cleanup_interval_hours=24.0,
        keep_days=7,
        logger=None,
    )


# ===========================================================================
# Property-Based Tests
# ===========================================================================

class TestAutoSaveServiceDigestDeduplicationProperties:
    """Property 5: Digest 去重正确性
    
    Feature: data-persistence-optimization, Property 5: Digest 去重正确性
    Validates: Requirements 2.2, 2.3
    """

    @settings(max_examples=100, deadline=None)
    @given(snapshot_pair=_snapshot_pair_strategy())
    def test_property_5_digest_deduplication_correctness(self, snapshot_pair):
        """
        **Validates: Requirements 2.2, 2.3**
        
        Property 5: Digest 去重正确性
        
        For any valid Snapshot, if two consecutive saves have identical snapshots
        (state unchanged), the second save should be skipped (no database write).
        If the two snapshots are different, the second save should execute.
        
        This property verifies that digest-based deduplication works correctly:
        1. Identical snapshots → second save skipped
        2. Different snapshots → second save executed
        
        This is critical for reducing unnecessary database writes and I/O when
        the strategy state hasn't changed.
        """
        snapshot1, snapshot2, are_identical = snapshot_pair
        
        # Create mock repository to track save calls
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService with no time-based throttling
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # First save: should always execute
        service.maybe_save(lambda: snapshot1)
        
        # Wait for async save to complete
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Verify first save was called
        assert mock_repository.save_raw.call_count == 1, (
            "First save should always execute"
        )
        
        # Reset mock to track second save
        mock_repository.save_raw.reset_mock()
        
        # Second save: behavior depends on whether snapshots are identical
        service.maybe_save(lambda: snapshot2)
        
        # Wait for async save to complete (if any)
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        if are_identical:
            # Identical snapshots: second save should be skipped
            assert mock_repository.save_raw.call_count == 0, (
                f"Second save should be skipped when snapshots are identical.\n"
                f"Snapshot: {snapshot1}\n"
                f"save_raw was called {mock_repository.save_raw.call_count} times"
            )
        else:
            # Different snapshots: second save should execute
            assert mock_repository.save_raw.call_count == 1, (
                f"Second save should execute when snapshots are different.\n"
                f"Snapshot1: {snapshot1}\n"
                f"Snapshot2: {snapshot2}\n"
                f"save_raw was called {mock_repository.save_raw.call_count} times"
            )
        
        # Cleanup
        service.shutdown()

    @settings(max_examples=50, deadline=None)
    @given(snapshot=_snapshot_strategy(), num_saves=st.integers(min_value=2, max_value=10))
    def test_multiple_identical_saves_all_skipped(self, snapshot, num_saves):
        """
        Additional property: Multiple consecutive saves with identical snapshots
        should all be skipped (except the first one).
        
        This verifies that the digest-based deduplication works consistently
        across multiple save attempts, not just two.
        """
        # Create mock repository to track save calls
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService with no time-based throttling
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Perform multiple saves with the same snapshot
        for i in range(num_saves):
            service.maybe_save(lambda: snapshot)
            
            # Wait for async save to complete
            if service._pending_future:
                service._pending_future.result(timeout=5)
        
        # Only the first save should have executed
        assert mock_repository.save_raw.call_count == 1, (
            f"Only the first save should execute, but save_raw was called "
            f"{mock_repository.save_raw.call_count} times for {num_saves} saves"
        )
        
        # Cleanup
        service.shutdown()

    @settings(max_examples=50, deadline=None)
    @given(num_saves=st.integers(min_value=2, max_value=10))
    def test_all_different_saves_execute(self, num_saves):
        """
        Additional property: Multiple consecutive saves with different snapshots
        should all execute (no skipping).
        
        This verifies that digest-based deduplication doesn't incorrectly skip
        saves when the state is actually changing.
        """
        # Create mock repository to track save calls
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService with no time-based throttling
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Generate different snapshots by using a counter
        # This ensures each snapshot is different
        for i in range(num_saves):
            snapshot = {
                "counter": i,
                "data": f"snapshot_{i}",
                "value": i * 100,
            }
            service.maybe_save(lambda s=snapshot: s)
            
            # Wait for async save to complete
            if service._pending_future:
                service._pending_future.result(timeout=5)
        
        # All saves should have executed
        assert mock_repository.save_raw.call_count == num_saves, (
            f"All {num_saves} saves should execute, but save_raw was called "
            f"{mock_repository.save_raw.call_count} times"
        )
        
        # Cleanup
        service.shutdown()

    @settings(max_examples=50, deadline=None)
    @given(snapshot=_snapshot_strategy())
    def test_force_save_ignores_digest_check(self, snapshot):
        """
        Additional property: force_save should always execute, even if the
        snapshot is identical to the last saved snapshot.
        
        This verifies that force_save (used in on_stop) bypasses digest-based
        deduplication to ensure the final state is always saved.
        
        Validates: Requirements 2.4
        """
        # Create mock repository to track save calls
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        mock_repository.save = Mock()
        
        # Create AutoSaveService with no time-based throttling
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # First save via maybe_save
        service.maybe_save(lambda: snapshot)
        
        # Wait for async save to complete
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Verify first save was called
        assert mock_repository.save_raw.call_count == 1
        
        # Reset mock
        mock_repository.save_raw.reset_mock()
        mock_repository.save.reset_mock()
        
        # Second save via force_save with identical snapshot
        # force_save uses repository.save (not save_raw), so check that
        service.force_save(lambda: snapshot)
        
        # force_save is synchronous, no need to wait
        
        # force_save should execute even though snapshot is identical
        assert mock_repository.save.call_count == 1, (
            f"force_save should always execute, even with identical snapshot.\n"
            f"save was called {mock_repository.save.call_count} times"
        )
        
        # Cleanup
        service.shutdown()


# ===========================================================================
# Unit Tests for Boundary Conditions
# ===========================================================================

class TestAutoSaveServiceDigestBoundaryConditions:
    """Unit tests for digest deduplication boundary conditions.
    
    These tests verify specific edge cases and boundary conditions that
    complement the property-based tests.
    """

    def test_first_save_always_executes(self):
        """
        Verify that the very first save always executes, even though there's
        no previous digest to compare against.
        """
        # Create mock repository
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # First save
        snapshot = {"data": "test"}
        service.maybe_save(lambda: snapshot)
        
        # Wait for async save
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Verify save was called
        assert mock_repository.save_raw.call_count == 1
        
        # Cleanup
        service.shutdown()

    def test_digest_computed_from_serialized_json(self):
        """
        Verify that digest is computed from the serialized JSON string, not
        from the Python object. This ensures that two Python objects that
        serialize to the same JSON produce the same digest.
        """
        # Create mock repository
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Two different Python objects that serialize to the same JSON
        # (due to sort_keys=True, dict order doesn't matter)
        snapshot1 = {"a": 1, "b": 2, "c": 3}
        snapshot2 = {"c": 3, "b": 2, "a": 1}  # Different order, same content
        
        # First save
        service.maybe_save(lambda: snapshot1)
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Reset mock
        mock_repository.save_raw.reset_mock()
        
        # Second save with different object but same content
        service.maybe_save(lambda: snapshot2)
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Second save should be skipped (same digest)
        assert mock_repository.save_raw.call_count == 0, (
            "Snapshots with same content but different dict order should "
            "produce the same digest and skip the second save"
        )
        
        # Cleanup
        service.shutdown()

    def test_empty_snapshot_handled_correctly(self):
        """
        Verify that empty snapshots are handled correctly by digest computation.
        """
        # Create mock repository
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Save empty snapshot twice
        empty_snapshot = {}
        
        service.maybe_save(lambda: empty_snapshot)
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Reset mock
        mock_repository.save_raw.reset_mock()
        
        service.maybe_save(lambda: empty_snapshot)
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Second save should be skipped
        assert mock_repository.save_raw.call_count == 0
        
        # Cleanup
        service.shutdown()

    def test_nested_snapshot_digest_correctness(self):
        """
        Verify that digest computation works correctly for deeply nested
        snapshots with complex structures.
        """
        # Create mock repository
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Complex nested snapshot
        complex_snapshot = {
            "level1": {
                "level2": {
                    "level3": {
                        "data": [1, 2, 3, 4, 5],
                        "metadata": {"key": "value", "count": 42},
                    }
                }
            },
            "arrays": [[1, 2], [3, 4], [5, 6]],
        }
        
        # Save twice
        service.maybe_save(lambda: complex_snapshot)
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        mock_repository.save_raw.reset_mock()
        
        service.maybe_save(lambda: complex_snapshot)
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Second save should be skipped
        assert mock_repository.save_raw.call_count == 0
        
        # Cleanup
        service.shutdown()

    def test_small_change_in_nested_snapshot_detected(self):
        """
        Verify that even small changes in deeply nested snapshots are detected
        by the digest computation.
        """
        # Create mock repository
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # First snapshot
        snapshot1 = {
            "level1": {
                "level2": {
                    "level3": {
                        "data": [1, 2, 3, 4, 5],
                    }
                }
            }
        }
        
        # Second snapshot with tiny change deep in the structure
        snapshot2 = {
            "level1": {
                "level2": {
                    "level3": {
                        "data": [1, 2, 3, 4, 6],  # Changed 5 to 6
                    }
                }
            }
        }
        
        # First save
        service.maybe_save(lambda: snapshot1)
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        mock_repository.save_raw.reset_mock()
        
        # Second save with small change
        service.maybe_save(lambda: snapshot2)
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Second save should execute (different digest)
        assert mock_repository.save_raw.call_count == 1, (
            "Small change in nested snapshot should be detected and trigger save"
        )
        
        # Cleanup
        service.shutdown()


# ===========================================================================
# Property 8: 异步保存跳过未完成请求
# ===========================================================================

class TestAutoSaveServiceAsyncSkipProperties:
    """Property 8: 异步保存跳过未完成请求
    
    Feature: data-persistence-optimization, Property 8: 异步保存跳过未完成请求
    Validates: Requirements 5.3
    """

    @settings(max_examples=100, deadline=None)
    @given(
        num_requests=st.integers(min_value=2, max_value=10),
        save_delay_ms=st.integers(min_value=50, max_value=200),
    )
    def test_property_8_async_save_skips_incomplete_requests(
        self, num_requests, save_delay_ms
    ):
        """
        **Validates: Requirements 5.3**
        
        Property 8: 异步保存跳过未完成请求
        
        For any sequence of save requests, when a previous async save is still
        in progress, new save requests should be skipped rather than queued.
        This prevents task accumulation and ensures the service doesn't fall behind.
        
        This property verifies that:
        1. When an async save is in progress, subsequent saves are skipped
        2. No save requests are queued or accumulated
        3. Only the first request in a burst executes
        
        This is critical for preventing the save queue from growing unbounded
        when the strategy generates state changes faster than saves can complete.
        """
        import time
        from unittest.mock import Mock
        
        # Create a mock repository that simulates slow saves
        mock_repository = Mock(spec=StateRepository)
        
        # Track actual save calls
        save_call_count = [0]
        
        def slow_save_raw(strategy_name, json_str):
            """Simulate a slow save operation"""
            save_call_count[0] += 1
            time.sleep(save_delay_ms / 1000.0)  # Convert ms to seconds
        
        mock_repository.save_raw = Mock(side_effect=slow_save_raw)
        
        # Create AutoSaveService with no time-based throttling
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Generate different snapshots for each request
        # (to avoid digest-based deduplication)
        snapshots = [
            {"request_id": i, "data": f"snapshot_{i}", "value": i * 100}
            for i in range(num_requests)
        ]
        
        # Submit all save requests rapidly (without waiting for completion)
        for i, snapshot in enumerate(snapshots):
            service.maybe_save(lambda s=snapshot: s)
            # Small delay to ensure requests are submitted while first is processing
            if i == 0:
                # Give first request time to start processing
                time.sleep(0.01)
        
        # Wait for all async operations to complete
        if service._pending_future:
            service._pending_future.result(timeout=10)
        
        # Verify that only the first request executed
        # All subsequent requests should have been skipped because the first
        # async save was still in progress
        assert save_call_count[0] <= 2, (
            f"Expected at most 2 saves (first + possibly one more after completion), "
            f"but got {save_call_count[0]} saves for {num_requests} requests.\n"
            f"This indicates that saves are being queued instead of skipped."
        )
        
        # Cleanup
        service.shutdown()

    @settings(max_examples=50, deadline=None)
    @given(num_bursts=st.integers(min_value=2, max_value=5))
    def test_async_save_allows_new_request_after_completion(self, num_bursts):
        """
        Additional property: After an async save completes, new save requests
        should be allowed (not permanently blocked).
        
        This verifies that the skip mechanism only applies while a save is
        in progress, and doesn't permanently block future saves.
        """
        import time
        from unittest.mock import Mock
        
        # Create mock repository with fast saves
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService with no time-based throttling
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Submit multiple bursts of saves, waiting for completion between bursts
        for burst_id in range(num_bursts):
            snapshot = {
                "burst_id": burst_id,
                "data": f"burst_{burst_id}",
            }
            service.maybe_save(lambda s=snapshot: s)
            
            # Wait for this save to complete before next burst
            if service._pending_future:
                service._pending_future.result(timeout=5)
            
            # Small delay to ensure completion is registered
            time.sleep(0.01)
        
        # All bursts should have executed (one save per burst)
        assert mock_repository.save_raw.call_count == num_bursts, (
            f"Expected {num_bursts} saves (one per burst), "
            f"but got {mock_repository.save_raw.call_count} saves"
        )
        
        # Cleanup
        service.shutdown()

    @settings(max_examples=50, deadline=None)
    @given(
        num_rapid_requests=st.integers(min_value=3, max_value=10),
        save_delay_ms=st.integers(min_value=100, max_value=300),
    )
    def test_rapid_requests_during_slow_save_all_skipped(
        self, num_rapid_requests, save_delay_ms
    ):
        """
        Additional property: When multiple save requests arrive rapidly while
        a slow save is in progress, all of them should be skipped.
        
        This verifies that the skip mechanism works correctly even under
        high-frequency save request scenarios.
        """
        import time
        from unittest.mock import Mock
        
        # Create mock repository with slow saves
        mock_repository = Mock(spec=StateRepository)
        
        save_call_count = [0]
        
        def slow_save_raw(strategy_name, json_str):
            save_call_count[0] += 1
            time.sleep(save_delay_ms / 1000.0)
        
        mock_repository.save_raw = Mock(side_effect=slow_save_raw)
        
        # Create AutoSaveService
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Submit first request
        first_snapshot = {"id": 0, "data": "first"}
        service.maybe_save(lambda: first_snapshot)
        
        # Give it time to start processing
        time.sleep(0.02)
        
        # Submit rapid burst of requests while first is processing
        for i in range(1, num_rapid_requests):
            snapshot = {"id": i, "data": f"request_{i}"}
            service.maybe_save(lambda s=snapshot: s)
            # No delay between rapid requests
        
        # Wait for completion
        if service._pending_future:
            service._pending_future.result(timeout=10)
        
        # Only the first request should have executed
        # All rapid requests should have been skipped
        assert save_call_count[0] == 1, (
            f"Expected only 1 save (the first request), "
            f"but got {save_call_count[0]} saves for {num_rapid_requests} total requests.\n"
            f"All {num_rapid_requests - 1} rapid requests should have been skipped."
        )
        
        # Cleanup
        service.shutdown()

    def test_pending_future_checked_before_submission(self):
        """
        Unit test: Verify that _pending_future is checked before submitting
        a new async save task.
        
        This is a boundary condition test that verifies the implementation
        correctly checks the future's done() status.
        """
        import time
        from unittest.mock import Mock
        
        # Create mock repository with slow saves
        mock_repository = Mock(spec=StateRepository)
        
        def slow_save_raw(strategy_name, json_str):
            time.sleep(0.1)  # 100ms delay
        
        mock_repository.save_raw = Mock(side_effect=slow_save_raw)
        
        # Create AutoSaveService
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Submit first request
        service.maybe_save(lambda: {"id": 1})
        
        # Verify pending_future is set
        assert service._pending_future is not None
        assert not service._pending_future.done()
        
        # Submit second request while first is in progress
        service.maybe_save(lambda: {"id": 2})
        
        # Second request should be skipped, so save_raw should only be called once
        # Wait for first save to complete
        service._pending_future.result(timeout=5)
        
        assert mock_repository.save_raw.call_count == 1
        
        # Cleanup
        service.shutdown()

    def test_completed_future_allows_new_submission(self):
        """
        Unit test: Verify that a completed future allows new save submissions.
        
        This tests the boundary condition where a future exists but is already done.
        """
        import time
        from unittest.mock import Mock
        
        # Create mock repository
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Submit first request
        service.maybe_save(lambda: {"id": 1})
        
        # Wait for completion
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Verify future is done
        assert service._pending_future.done()
        
        # Submit second request (should succeed because first is done)
        service.maybe_save(lambda: {"id": 2})
        
        # Wait for second save
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Both saves should have executed
        assert mock_repository.save_raw.call_count == 2
        
        # Cleanup
        service.shutdown()

    def test_no_pending_future_allows_submission(self):
        """
        Unit test: Verify that when there's no pending future, save submission
        is allowed.
        
        This tests the initial state boundary condition.
        """
        from unittest.mock import Mock
        
        # Create mock repository
        mock_repository = Mock(spec=StateRepository)
        mock_repository.save_raw = Mock()
        
        # Create AutoSaveService
        service = _make_auto_save_service(mock_repository, interval_seconds=0.0)
        
        # Verify no pending future initially
        assert service._pending_future is None
        
        # Submit first request (should succeed)
        service.maybe_save(lambda: {"id": 1})
        
        # Wait for completion
        if service._pending_future:
            service._pending_future.result(timeout=5)
        
        # Save should have executed
        assert mock_repository.save_raw.call_count == 1
        
        # Cleanup
        service.shutdown()
