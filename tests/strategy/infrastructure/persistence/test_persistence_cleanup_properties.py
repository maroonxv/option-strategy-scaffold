"""
Property-Based Tests for StateRepository Cleanup - Data Persistence Optimization

Feature: data-persistence-optimization, Property 7: 清理保留最新记录

Validates: Requirements 4.3, 4.4
"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

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

from src.main.bootstrap.database_factory import DatabaseFactory
from src.strategy.infrastructure.persistence.json_serializer import JsonSerializer
from src.strategy.infrastructure.persistence.migration_chain import MigrationChain
from src.strategy.infrastructure.persistence.state_repository import StateRepository
from src.strategy.infrastructure.persistence.strategy_state_model import (
    StrategyStateModel,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

def _snapshot_records_strategy():
    """Generate a list of snapshot records with random timestamps.
    
    This strategy generates:
    - A list of 3-20 snapshot records
    - Each record has a timestamp within the last 30 days
    - Records are sorted by timestamp (oldest first)
    - At least one record is recent (within 7 days)
    - At least one record is old (older than 7 days)
    
    This ensures we test the cleanup logic with various scenarios:
    - All records expired
    - Mix of expired and recent records
    - Only recent records
    """
    return st.builds(
        _generate_snapshot_records,
        num_records=st.integers(min_value=3, max_value=20),
        keep_days=st.integers(min_value=1, max_value=14),
    )


def _generate_snapshot_records(num_records: int, keep_days: int):
    """Generate snapshot records with controlled timestamps.
    
    Args:
        num_records: Number of records to generate
        keep_days: Number of days to keep (for cutoff calculation)
        
    Returns:
        tuple: (records_data, keep_days, cutoff_date, latest_timestamp)
    """
    now = datetime.now()
    cutoff = now - timedelta(days=keep_days)
    
    # Generate timestamps spanning from 30 days ago to now
    # Ensure we have both old and recent records
    timestamps = []
    
    # Add some old records (before cutoff)
    num_old = max(1, num_records // 2)
    for i in range(num_old):
        # Random timestamp between 30 days ago and cutoff
        # Use a fraction to distribute evenly
        fraction = i / max(1, num_old - 1) if num_old > 1 else 0
        days_ago = 30 - fraction * (30 - keep_days)
        timestamp = now - timedelta(days=days_ago, hours=i)
        timestamps.append(timestamp)
    
    # Add some recent records (after cutoff)
    num_recent = num_records - num_old
    for i in range(num_recent):
        # Random timestamp between cutoff and now
        # Use a fraction to distribute evenly
        fraction = i / max(1, num_recent - 1) if num_recent > 1 else 0
        days_ago = keep_days - fraction * keep_days
        timestamp = now - timedelta(days=days_ago, hours=i)
        timestamps.append(timestamp)
    
    # Sort timestamps (oldest first)
    timestamps.sort()
    
    # Create record data (without pre-assigned IDs - let database auto-increment)
    records_data = [
        {
            "strategy_name": "test_strategy",
            "snapshot_json": f'{{"data": "snapshot_{i}"}}',
            "schema_version": 1,
            "saved_at": ts,
        }
        for i, ts in enumerate(timestamps)
    ]
    
    latest_timestamp = timestamps[-1]
    
    return records_data, keep_days, cutoff, latest_timestamp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_test_database():
    """Setup an in-memory SQLite database for testing."""
    from peewee import SqliteDatabase
    
    db = SqliteDatabase(":memory:")
    StrategyStateModel._meta.database = db
    db.create_tables([StrategyStateModel])
    
    return db


def _make_repository(db) -> StateRepository:
    """Create a StateRepository instance for testing."""
    serializer = JsonSerializer(MigrationChain())
    
    # Create a mock database factory that returns our test database
    database_factory = MagicMock(spec=DatabaseFactory)
    database_factory.get_peewee_db.return_value = db
    
    logger = None
    
    return StateRepository(
        serializer=serializer,
        database_factory=database_factory,
        logger=logger,
    )


# ===========================================================================
# Property-Based Tests
# ===========================================================================

class TestStateRepositoryCleanupProperties:
    """Property 7: 清理保留最新记录
    
    Feature: data-persistence-optimization, Property 7: 清理保留最新记录
    Validates: Requirements 4.3, 4.4
    """

    @settings(max_examples=100, deadline=None)
    @given(data=_snapshot_records_strategy())
    def test_property_7_cleanup_preserves_latest_record(self, data):
        """
        **Validates: Requirements 4.3, 4.4**
        
        Property 7: 清理保留最新记录
        
        For any strategy name and a set of historical snapshot records (with 
        different saved_at timestamps), after executing cleanup:
        1. All records with saved_at earlier than keep_days should be deleted
        2. BUT at least one latest record must be preserved, even if it's 
           older than keep_days
        
        This ensures the strategy can always load its last known state, even
        if all records are expired.
        """
        records_data, keep_days, cutoff, latest_timestamp = data
        
        # Setup test database
        db = _setup_test_database()
        repository = _make_repository(db)
        
        # Insert all records
        for record_data in records_data:
            StrategyStateModel.create(**record_data)
        
        # Verify all records were inserted
        total_records_before = StrategyStateModel.select().count()
        assert total_records_before == len(records_data)
        
        # Get the latest record ID before cleanup
        latest_record = (
            StrategyStateModel.select()
            .where(StrategyStateModel.strategy_name == "test_strategy")
            .order_by(StrategyStateModel.saved_at.desc())
            .first()
        )
        assert latest_record is not None
        latest_id = latest_record.id
        
        # Execute cleanup
        deleted_count = repository.cleanup("test_strategy", keep_days=keep_days)
        
        # Verify the latest record still exists
        latest_after_cleanup = StrategyStateModel.get_by_id(latest_id)
        assert latest_after_cleanup is not None, (
            f"Latest record (ID={latest_id}) was deleted during cleanup! "
            f"This violates the requirement to preserve at least one record."
        )
        
        # Verify at least one record remains
        remaining_records = (
            StrategyStateModel.select()
            .where(StrategyStateModel.strategy_name == "test_strategy")
            .count()
        )
        assert remaining_records >= 1, (
            f"Cleanup deleted all records! At least one record must be preserved. "
            f"Total before: {total_records_before}, Deleted: {deleted_count}, "
            f"Remaining: {remaining_records}"
        )
        
        # Verify all remaining records are either:
        # 1. The latest record (preserved regardless of age), OR
        # 2. Recent records (saved_at >= cutoff)
        for record in StrategyStateModel.select().where(
            StrategyStateModel.strategy_name == "test_strategy"
        ):
            is_latest = record.id == latest_id
            is_recent = record.saved_at >= cutoff
            
            assert is_latest or is_recent, (
                f"Record ID={record.id} with saved_at={record.saved_at} should "
                f"have been deleted (cutoff={cutoff}, latest_id={latest_id})"
            )
        
        # Verify deleted count is correct
        # Count how many records should have been deleted:
        # Records with saved_at < cutoff, excluding the latest record
        all_records_after = list(
            StrategyStateModel.select()
            .where(StrategyStateModel.strategy_name == "test_strategy")
            .order_by(StrategyStateModel.saved_at)
        )
        
        # The expected deleted count is:
        # total_before - remaining_after
        expected_deleted = total_records_before - len(all_records_after)
        
        assert deleted_count == expected_deleted, (
            f"Deleted count mismatch: expected {expected_deleted}, got {deleted_count}"
        )
        
        # Cleanup
        db.close()

    @settings(max_examples=50, deadline=None)
    @given(
        num_records=st.integers(min_value=1, max_value=10),
        keep_days=st.integers(min_value=1, max_value=7),
    )
    def test_cleanup_with_all_records_expired_preserves_latest(
        self, num_records: int, keep_days: int
    ):
        """
        Additional property: When ALL records are expired (older than keep_days),
        cleanup must still preserve the latest record.
        
        This is a critical edge case that ensures the strategy can always recover
        its last known state, even after a long period of inactivity.
        """
        db = _setup_test_database()
        repository = _make_repository(db)
        
        now = datetime.now()
        cutoff = now - timedelta(days=keep_days)
        
        # Create records that are ALL older than keep_days
        for i in range(num_records):
            # All records are at least keep_days + 1 day old
            days_ago = keep_days + 1 + i
            timestamp = now - timedelta(days=days_ago)
            
            StrategyStateModel.create(
                strategy_name="test_strategy",
                snapshot_json=f'{{"data": "snapshot_{i}"}}',
                schema_version=1,
                saved_at=timestamp,
            )
        
        # Verify all records are expired
        for record in StrategyStateModel.select():
            assert record.saved_at < cutoff, (
                f"Test setup failed: record {record.id} is not expired"
            )
        
        # Get the latest record ID
        latest_record = (
            StrategyStateModel.select()
            .order_by(StrategyStateModel.saved_at.desc())
            .first()
        )
        latest_id = latest_record.id
        
        # Execute cleanup
        deleted_count = repository.cleanup("test_strategy", keep_days=keep_days)
        
        # Verify exactly one record remains (the latest)
        remaining_count = StrategyStateModel.select().count()
        assert remaining_count == 1, (
            f"When all records are expired, exactly 1 record (the latest) should "
            f"remain. Found {remaining_count} records."
        )
        
        # Verify the remaining record is the latest
        remaining_record = StrategyStateModel.select().first()
        assert remaining_record.id == latest_id, (
            f"The remaining record should be the latest (ID={latest_id}), "
            f"but found ID={remaining_record.id}"
        )
        
        # Verify deleted count
        assert deleted_count == num_records - 1, (
            f"Should have deleted {num_records - 1} records, but deleted {deleted_count}"
        )
        
        # Cleanup
        db.close()

    @settings(max_examples=50, deadline=None)
    @given(keep_days=st.integers(min_value=1, max_value=14))
    def test_cleanup_with_no_records_returns_zero(self, keep_days: int):
        """
        Additional property: Cleanup on a non-existent strategy should return 0
        and not raise an error.
        
        This ensures the cleanup operation is safe to call even when no records
        exist for the strategy.
        """
        db = _setup_test_database()
        repository = _make_repository(db)
        
        # Execute cleanup on non-existent strategy
        deleted_count = repository.cleanup("nonexistent_strategy", keep_days=keep_days)
        
        # Should return 0 without error
        assert deleted_count == 0, (
            f"Cleanup on non-existent strategy should return 0, got {deleted_count}"
        )
        
        # Cleanup
        db.close()

    @settings(max_examples=50, deadline=None)
    @given(keep_days=st.integers(min_value=1, max_value=14))
    def test_cleanup_with_single_record_preserves_it(self, keep_days: int):
        """
        Additional property: When there's only one record, cleanup must preserve
        it regardless of its age.
        
        This is another critical edge case for strategies with minimal history.
        """
        db = _setup_test_database()
        repository = _make_repository(db)
        
        now = datetime.now()
        
        # Create a single record that's older than keep_days
        old_timestamp = now - timedelta(days=keep_days + 10)
        
        StrategyStateModel.create(
            strategy_name="test_strategy",
            snapshot_json='{"data": "single_snapshot"}',
            schema_version=1,
            saved_at=old_timestamp,
        )
        
        # Execute cleanup
        deleted_count = repository.cleanup("test_strategy", keep_days=keep_days)
        
        # Verify no records were deleted
        assert deleted_count == 0, (
            f"Single record should not be deleted, but {deleted_count} records "
            f"were deleted"
        )
        
        # Verify the record still exists
        remaining_count = StrategyStateModel.select().count()
        assert remaining_count == 1, (
            f"Single record should be preserved, but {remaining_count} records remain"
        )
        
        # Cleanup
        db.close()


# ===========================================================================
# Unit Tests for Boundary Conditions
# ===========================================================================

class TestStateRepositoryCleanupBoundaryConditions:
    """Unit tests for cleanup boundary conditions.
    
    These tests verify specific edge cases and boundary conditions that
    complement the property-based tests.
    """

    def test_cleanup_with_multiple_strategies_only_affects_target(self):
        """
        Verify that cleanup only affects the specified strategy and doesn't
        touch records from other strategies.
        """
        db = _setup_test_database()
        repository = _make_repository(db)
        
        now = datetime.now()
        old_timestamp = now - timedelta(days=10)
        
        # Create records for two different strategies
        for strategy_name in ["strategy_a", "strategy_b"]:
            for i in range(5):
                StrategyStateModel.create(
                    strategy_name=strategy_name,
                    snapshot_json=f'{{"data": "snapshot_{i}"}}',
                    schema_version=1,
                    saved_at=old_timestamp - timedelta(days=i),
                )
        
        # Cleanup only strategy_a
        deleted_count = repository.cleanup("strategy_a", keep_days=7)
        
        # Verify strategy_a has only 1 record left (the latest)
        strategy_a_count = (
            StrategyStateModel.select()
            .where(StrategyStateModel.strategy_name == "strategy_a")
            .count()
        )
        assert strategy_a_count == 1
        
        # Verify strategy_b still has all 5 records
        strategy_b_count = (
            StrategyStateModel.select()
            .where(StrategyStateModel.strategy_name == "strategy_b")
            .count()
        )
        assert strategy_b_count == 5, (
            f"Cleanup should not affect other strategies, but strategy_b has "
            f"{strategy_b_count} records instead of 5"
        )
        
        # Cleanup
        db.close()

    def test_cleanup_with_records_at_exact_cutoff_boundary(self):
        """
        Verify behavior when records are exactly at the cutoff boundary.
        
        Records with saved_at < cutoff should be deleted (exclusive).
        Records with saved_at >= cutoff should be kept.
        
        Note: The cutoff is calculated as datetime.now() - timedelta(days=keep_days)
        inside the cleanup method, so we need to account for timing differences.
        """
        db = _setup_test_database()
        repository = _make_repository(db)
        
        # Use a fixed reference time to avoid timing issues
        now = datetime.now()
        keep_days = 7
        cutoff = now - timedelta(days=keep_days)
        
        # Create records at various positions relative to cutoff
        # Add some buffer to account for timing differences between test and cleanup
        records = [
            ("old_1", cutoff - timedelta(hours=2)),  # Should be deleted
            ("old_2", cutoff - timedelta(hours=1)),  # Should be deleted
            ("at_cutoff", cutoff + timedelta(seconds=1)),  # Should be kept
            ("after_cutoff", cutoff + timedelta(hours=1)),  # Should be kept
            ("recent", now - timedelta(hours=1)),  # Should be kept (latest)
        ]
        
        for name, timestamp in records:
            StrategyStateModel.create(
                strategy_name="test_strategy",
                snapshot_json=f'{{"data": "{name}"}}',
                schema_version=1,
                saved_at=timestamp,
            )
        
        # Execute cleanup
        deleted_count = repository.cleanup("test_strategy", keep_days=keep_days)
        
        # Verify at least the old records were deleted
        # Due to timing differences, we check that some records were deleted
        # and the latest record is preserved
        assert deleted_count >= 2, (
            f"Expected at least 2 old records to be deleted, got {deleted_count}"
        )
        
        # Verify remaining records
        remaining = list(
            StrategyStateModel.select()
            .where(StrategyStateModel.strategy_name == "test_strategy")
            .order_by(StrategyStateModel.saved_at)
        )
        
        # At least 3 records should remain (at_cutoff, after_cutoff, recent)
        assert len(remaining) >= 3, (
            f"Expected at least 3 records to remain, got {len(remaining)}"
        )
        
        # Verify the latest record is present
        latest_record = remaining[-1]
        assert '{"data": "recent"}' in latest_record.snapshot_json
        
        # Verify the old records are not present
        remaining_data = [r.snapshot_json for r in remaining]
        assert '{"data": "old_1"}' not in remaining_data
        assert '{"data": "old_2"}' not in remaining_data
        
        # Cleanup
        db.close()
