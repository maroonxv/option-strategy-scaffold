"""
Tests for StateRepository — Property-Based Tests and Unit Tests

Feature: persistence-resilience-enhancement

Property 2: Save then load returns latest snapshot — Validates: Requirements 1.4
Property 3: Non-existent strategy returns ArchiveNotFound — Validates: Requirements 2.1
Property 4: Corrupted record raises CorruptionError with details — Validates: Requirements 2.2, 2.4
Property 5: Integrity check without full deserialization — Validates: Requirements 2.5

Unit tests: cleanup 清理旧快照、CorruptionError 包含正确信息 — Requirements: 2.3, 2.4
"""

import json
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, strategies as st
from peewee import SqliteDatabase

# Mock vnpy modules before importing database_factory (avoids __init__.py chain)
for _mod_name in [
    "vnpy", "vnpy.event", "vnpy.trader", "vnpy.trader.setting",
    "vnpy.trader.engine", "vnpy.trader.database", "vnpy_mysql",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Ensure SETTINGS is a real dict for tests
sys.modules["vnpy.trader.setting"].SETTINGS = {}

from src.strategy.infrastructure.persistence.exceptions import CorruptionError
from src.strategy.infrastructure.persistence.json_serializer import (
    CURRENT_SCHEMA_VERSION,
    JsonSerializer,
)
from src.strategy.infrastructure.persistence.migration_chain import MigrationChain
from src.strategy.infrastructure.persistence.state_repository import (
    ArchiveNotFound,
    StateRepository,
)
from src.strategy.infrastructure.persistence.strategy_state_model import (
    StrategyStateModel,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _setup_test_db() -> SqliteDatabase:
    """Create an in-memory SQLite database and bind StrategyStateModel to it."""
    db = SqliteDatabase(":memory:")
    StrategyStateModel._meta.database = db
    db.connect()
    db.create_tables([StrategyStateModel])
    return db


def _make_repo(db: SqliteDatabase) -> StateRepository:
    """Create a StateRepository with a mocked DatabaseFactory returning the test db."""
    factory = MagicMock()
    factory.get_peewee_db.return_value = db
    serializer = JsonSerializer(MigrationChain())
    return StateRepository(serializer=serializer, database_factory=factory)


@pytest.fixture(autouse=True)
def _clean_db():
    """Ensure each test gets a fresh database."""
    db = _setup_test_db()
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy names: printable, non-empty, reasonable length
_strategy_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() != "")

# Simple snapshot data that survives JSON round-trip
_finite_floats = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e8, max_value=1e8
)

_snapshot_data = st.fixed_dictionaries({
    "value": st.integers(min_value=-10000, max_value=10000),
    "price": _finite_floats,
    "name": st.text(min_size=0, max_size=20),
})

# Corrupted JSON strings — not valid JSON or missing schema_version
_corrupted_json = st.one_of(
    st.text(min_size=1, max_size=50).filter(lambda s: _is_invalid_json(s)),
    st.just("{invalid json}"),
    st.just("not json at all"),
    st.just(""),
    st.just("\x00\x01\x02"),
)


def _is_invalid_json(s: str) -> bool:
    """Check if a string is NOT valid JSON."""
    try:
        json.loads(s)
        return False
    except (json.JSONDecodeError, ValueError):
        return True


# ===========================================================================
# Property-Based Tests (Task 6.2)
# ===========================================================================

class TestStateRepositoryProperties:
    """Property-based tests for StateRepository."""

    @settings(max_examples=100, deadline=None)
    @given(
        strategy_name=_strategy_names,
        snapshots=st.lists(_snapshot_data, min_size=1, max_size=5),
    )
    def test_property_2_save_then_load_returns_latest(
        self, strategy_name: str, snapshots: list
    ):
        """
        Property 2: Save then load returns latest snapshot

        For any valid snapshot data and strategy name, after calling save()
        one or more times, load() should return data equivalent to the most
        recently saved snapshot.

        Feature: persistence-resilience-enhancement, Property 2: Save then load returns latest snapshot
        Validates: Requirements 1.4
        """
        db = _setup_test_db()
        repo = _make_repo(db)

        for snap in snapshots:
            repo.save(strategy_name, snap)

        result = repo.load(strategy_name)

        assert not isinstance(result, ArchiveNotFound)
        assert isinstance(result, dict)

        latest = snapshots[-1]
        for key in latest:
            assert key in result, f"Missing key: {key}"
            assert result[key] == latest[key], (
                f"Mismatch on key '{key}': expected {latest[key]!r}, got {result[key]!r}"
            )

        assert result.get("schema_version") == CURRENT_SCHEMA_VERSION
        db.close()

    @settings(max_examples=100, deadline=None)
    @given(strategy_name=_strategy_names)
    def test_property_3_nonexistent_returns_archive_not_found(
        self, strategy_name: str
    ):
        """
        Property 3: Non-existent strategy returns ArchiveNotFound

        For any strategy name that has no record in the database,
        load() should return an ArchiveNotFound instance.

        Feature: persistence-resilience-enhancement, Property 3: Non-existent strategy returns ArchiveNotFound
        Validates: Requirements 2.1
        """
        db = _setup_test_db()
        repo = _make_repo(db)

        result = repo.load(strategy_name)

        assert isinstance(result, ArchiveNotFound)
        assert result.strategy_name == strategy_name
        db.close()

    @settings(max_examples=100, deadline=None)
    @given(
        strategy_name=_strategy_names,
        corrupted=_corrupted_json,
    )
    def test_property_4_corrupted_raises_corruption_error(
        self, strategy_name: str, corrupted: str
    ):
        """
        Property 4: Corrupted record raises CorruptionError with details

        For any strategy name whose database record contains invalid JSON,
        load() should raise a CorruptionError whose message contains both
        the strategy name and the original exception details.

        Feature: persistence-resilience-enhancement, Property 4: Corrupted record raises CorruptionError with details
        Validates: Requirements 2.2, 2.4
        """
        db = _setup_test_db()
        repo = _make_repo(db)

        # Insert a corrupted record directly
        StrategyStateModel._meta.database = db
        StrategyStateModel.create(
            strategy_name=strategy_name,
            snapshot_json=corrupted,
            schema_version=1,
            saved_at=datetime.now(),
        )

        with pytest.raises(CorruptionError) as exc_info:
            repo.load(strategy_name)

        err = exc_info.value
        assert err.strategy_name == strategy_name
        assert err.original_error is not None
        assert strategy_name in str(err)
        db.close()

    @settings(max_examples=100, deadline=None)
    @given(
        strategy_name=_strategy_names,
        snapshot=_snapshot_data,
    )
    def test_property_5_integrity_check(
        self, strategy_name: str, snapshot: dict
    ):
        """
        Property 5: Integrity check without full deserialization

        For any strategy name with a valid JSON record containing schema_version,
        verify_integrity should return True. For invalid JSON or missing
        schema_version, it should return False.

        Feature: persistence-resilience-enhancement, Property 5: Integrity check without full deserialization
        Validates: Requirements 2.5
        """
        db = _setup_test_db()
        repo = _make_repo(db)

        # No record → False
        assert repo.verify_integrity(strategy_name) is False

        # Save valid data → True
        repo.save(strategy_name, snapshot)
        assert repo.verify_integrity(strategy_name) is True

        # Insert a record with invalid JSON for a different name
        bad_name = strategy_name + "_bad"
        StrategyStateModel._meta.database = db
        StrategyStateModel.create(
            strategy_name=bad_name,
            snapshot_json="not valid json",
            schema_version=1,
            saved_at=datetime.now(),
        )
        assert repo.verify_integrity(bad_name) is False

        # Insert a record with valid JSON but missing schema_version
        no_version_name = strategy_name + "_noversion"
        StrategyStateModel.create(
            strategy_name=no_version_name,
            snapshot_json=json.dumps({"data": "test"}),
            schema_version=1,
            saved_at=datetime.now(),
        )
        assert repo.verify_integrity(no_version_name) is False

        db.close()


# ===========================================================================
# Unit Tests (Task 6.3)
# ===========================================================================

class TestStateRepositoryUnit:
    """Unit tests for StateRepository.

    Requirements: 2.3, 2.4
    """

    def test_cleanup_removes_old_snapshots(self):
        """cleanup() should delete records older than keep_days."""
        db = _setup_test_db()
        repo = _make_repo(db)

        strategy = "test_strategy"
        serializer = JsonSerializer(MigrationChain())

        # Insert old records (10 days ago)
        StrategyStateModel._meta.database = db
        old_time = datetime.now() - timedelta(days=10)
        for i in range(3):
            StrategyStateModel.create(
                strategy_name=strategy,
                snapshot_json=serializer.serialize({"old": i}),
                schema_version=CURRENT_SCHEMA_VERSION,
                saved_at=old_time + timedelta(seconds=i),
            )

        # Insert recent records (1 day ago)
        recent_time = datetime.now() - timedelta(days=1)
        for i in range(2):
            StrategyStateModel.create(
                strategy_name=strategy,
                snapshot_json=serializer.serialize({"recent": i}),
                schema_version=CURRENT_SCHEMA_VERSION,
                saved_at=recent_time + timedelta(seconds=i),
            )

        # Cleanup with keep_days=7
        deleted = repo.cleanup(strategy, keep_days=7)

        assert deleted == 3
        remaining = StrategyStateModel.select().where(
            StrategyStateModel.strategy_name == strategy
        ).count()
        assert remaining == 2
        db.close()

    def test_cleanup_does_not_affect_other_strategies(self):
        """cleanup() should only delete records for the specified strategy."""
        db = _setup_test_db()
        repo = _make_repo(db)

        serializer = JsonSerializer(MigrationChain())
        StrategyStateModel._meta.database = db

        old_time = datetime.now() - timedelta(days=10)

        # Insert 2 old records for strategy_a (so one can be deleted while preserving latest)
        StrategyStateModel.create(
            strategy_name="strategy_a",
            snapshot_json=serializer.serialize({"a": 1}),
            schema_version=CURRENT_SCHEMA_VERSION,
            saved_at=old_time,
        )
        StrategyStateModel.create(
            strategy_name="strategy_a",
            snapshot_json=serializer.serialize({"a": 2}),
            schema_version=CURRENT_SCHEMA_VERSION,
            saved_at=old_time + timedelta(seconds=1),
        )

        # Insert old records for strategy_b
        StrategyStateModel.create(
            strategy_name="strategy_b",
            snapshot_json=serializer.serialize({"b": 1}),
            schema_version=CURRENT_SCHEMA_VERSION,
            saved_at=old_time,
        )

        deleted = repo.cleanup("strategy_a", keep_days=7)

        # Should delete 1 old record from strategy_a (preserving the latest)
        assert deleted == 1
        # strategy_a should still have 1 record (the latest)
        count_a = StrategyStateModel.select().where(
            StrategyStateModel.strategy_name == "strategy_a"
        ).count()
        assert count_a == 1
        # strategy_b should still have its record
        count_b = StrategyStateModel.select().where(
            StrategyStateModel.strategy_name == "strategy_b"
        ).count()
        assert count_b == 1
        db.close()

    def test_cleanup_returns_zero_when_nothing_to_delete(self):
        """cleanup() should return 0 when no old records exist."""
        db = _setup_test_db()
        repo = _make_repo(db)

        deleted = repo.cleanup("nonexistent", keep_days=7)
        assert deleted == 0
        db.close()

    def test_cleanup_preserves_latest_record_even_if_old(self):
        """cleanup() should preserve the latest record even if it's older than keep_days.
        
        This ensures the strategy can always load its last known state.
        Requirements: 4.4
        """
        db = _setup_test_db()
        repo = _make_repo(db)

        serializer = JsonSerializer(MigrationChain())
        StrategyStateModel._meta.database = db

        strategy = "test_strategy"
        old_time = datetime.now() - timedelta(days=30)

        # Insert only old records (all older than keep_days=7)
        for i in range(3):
            StrategyStateModel.create(
                strategy_name=strategy,
                snapshot_json=serializer.serialize({"old": i}),
                schema_version=CURRENT_SCHEMA_VERSION,
                saved_at=old_time + timedelta(seconds=i),
            )

        # Cleanup with keep_days=7
        deleted = repo.cleanup(strategy, keep_days=7)

        # Should delete 2 records, but preserve the latest one
        assert deleted == 2
        remaining = StrategyStateModel.select().where(
            StrategyStateModel.strategy_name == strategy
        ).count()
        assert remaining == 1
        
        # Verify the remaining record is the latest one
        latest_record = (
            StrategyStateModel.select()
            .where(StrategyStateModel.strategy_name == strategy)
            .order_by(StrategyStateModel.saved_at.desc())
            .first()
        )
        assert latest_record is not None
        data = serializer.deserialize(latest_record.snapshot_json)
        assert data["old"] == 2  # The last inserted record
        db.close()

    def test_corruption_error_contains_strategy_name(self):
        """CorruptionError should contain the strategy name and original error."""
        db = _setup_test_db()
        repo = _make_repo(db)

        StrategyStateModel._meta.database = db
        StrategyStateModel.create(
            strategy_name="broken_strategy",
            snapshot_json="this is not json",
            schema_version=1,
            saved_at=datetime.now(),
        )

        with pytest.raises(CorruptionError) as exc_info:
            repo.load("broken_strategy")

        err = exc_info.value
        assert err.strategy_name == "broken_strategy"
        assert "broken_strategy" in str(err)
        assert err.original_error is not None
        assert isinstance(err.original_error, Exception)

    def test_corruption_error_includes_original_exception_details(self):
        """CorruptionError message should include original exception info."""
        db = _setup_test_db()
        repo = _make_repo(db)

        StrategyStateModel._meta.database = db
        StrategyStateModel.create(
            strategy_name="corrupt_test",
            snapshot_json="{malformed",
            schema_version=1,
            saved_at=datetime.now(),
        )

        with pytest.raises(CorruptionError) as exc_info:
            repo.load("corrupt_test")

        err = exc_info.value
        error_msg = str(err)
        assert "corrupt_test" in error_msg
        assert "Original error" in error_msg

    def test_load_returns_archive_not_found_for_empty_db(self):
        """load() on empty database should return ArchiveNotFound."""
        db = _setup_test_db()
        repo = _make_repo(db)

        result = repo.load("no_such_strategy")
        assert isinstance(result, ArchiveNotFound)
        assert result.strategy_name == "no_such_strategy"
        db.close()

    def test_save_and_load_basic(self):
        """Basic save/load round-trip should work."""
        db = _setup_test_db()
        repo = _make_repo(db)

        data = {"key": "value", "number": 42}
        repo.save("my_strategy", data)

        result = repo.load("my_strategy")
        assert isinstance(result, dict)
        assert result["key"] == "value"
        assert result["number"] == 42
        assert result["schema_version"] == CURRENT_SCHEMA_VERSION
        db.close()

    def test_load_returns_latest_of_multiple_saves(self):
        """load() should return the most recently saved snapshot."""
        db = _setup_test_db()
        repo = _make_repo(db)

        repo.save("strat", {"version": 1})
        repo.save("strat", {"version": 2})
        repo.save("strat", {"version": 3})

        result = repo.load("strat")
        assert result["version"] == 3
        db.close()

    def test_verify_integrity_valid_record(self):
        """verify_integrity should return True for valid records."""
        db = _setup_test_db()
        repo = _make_repo(db)

        repo.save("valid_strat", {"data": "test"})
        assert repo.verify_integrity("valid_strat") is True
        db.close()

    def test_verify_integrity_no_record(self):
        """verify_integrity should return False when no record exists."""
        db = _setup_test_db()
        repo = _make_repo(db)

        assert repo.verify_integrity("missing") is False
        db.close()

    def test_verify_integrity_invalid_json(self):
        """verify_integrity should return False for invalid JSON."""
        db = _setup_test_db()
        repo = _make_repo(db)

        StrategyStateModel._meta.database = db
        StrategyStateModel.create(
            strategy_name="bad_json",
            snapshot_json="not json",
            schema_version=1,
            saved_at=datetime.now(),
        )

        assert repo.verify_integrity("bad_json") is False
        db.close()
