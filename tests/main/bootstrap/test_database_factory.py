"""
Tests for DatabaseFactory — Property-Based Tests and Unit Tests

Feature: persistence-resilience-enhancement

Property 6: Missing environment variables detection
Validates: Requirements 3.3

Property 9: Database factory singleton identity
Validates: Requirements 5.6

Unit tests validate: Requirements 3.4, 3.5, 5.5
"""

import logging
import os
import sys
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, strategies as st

# Mock vnpy modules before importing database_factory (avoids __init__.py chain)
_vnpy_mock = MagicMock()
_vnpy_mocks = {}
for _mod_name in [
    "vnpy", "vnpy.event", "vnpy.trader", "vnpy.trader.setting",
    "vnpy.trader.engine", "vnpy.trader.database", "vnpy_mysql",
]:
    if _mod_name not in sys.modules:
        _vnpy_mocks[_mod_name] = MagicMock()
        sys.modules[_mod_name] = _vnpy_mocks[_mod_name]

# Ensure SETTINGS is a real dict for tests
sys.modules["vnpy.trader.setting"].SETTINGS = {}

from src.main.bootstrap.database_factory import (
    DatabaseFactory,
    REQUIRED_ENV_VARS,
)
from src.strategy.infrastructure.persistence.exceptions import (
    DatabaseConfigError,
    DatabaseConnectionError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_factory():
    """Reset DatabaseFactory singleton before and after each test."""
    DatabaseFactory._instance = None
    DatabaseFactory._db = None  # type: ignore[attr-defined]
    DatabaseFactory._peewee_db = None  # type: ignore[attr-defined]
    yield
    if DatabaseFactory._instance is not None:
        DatabaseFactory._instance.reset()


FULL_ENV = {
    "VNPY_DATABASE_DRIVER": "mysql",
    "VNPY_DATABASE_HOST": "localhost",
    "VNPY_DATABASE_DATABASE": "vnpy_test",
    "VNPY_DATABASE_USER": "root",
    "VNPY_DATABASE_PASSWORD": "secret",
}


# ===========================================================================
# Property-Based Tests (Task 5.3)
# ===========================================================================

class TestDatabaseFactoryProperties:
    """Property tests for DatabaseFactory.

    Feature: persistence-resilience-enhancement
    """

    @settings(max_examples=100, deadline=None)
    @given(
        present_flags=st.lists(
            st.booleans(),
            min_size=len(REQUIRED_ENV_VARS),
            max_size=len(REQUIRED_ENV_VARS),
        )
    )
    def test_property_6_missing_env_vars_detection(self, present_flags):
        """
        Property 6: Missing environment variables detection

        For any subset of the required environment variables that is missing,
        validate_env_vars() should return exactly the set of missing variable names.

        Feature: persistence-resilience-enhancement, Property 6: Missing environment variables detection
        Validates: Requirements 3.3
        """
        # Save original env state and restore after test
        saved = {var: os.environ.get(var) for var in REQUIRED_ENV_VARS}
        try:
            expected_missing = []
            for var, present in zip(REQUIRED_ENV_VARS, present_flags):
                if present:
                    os.environ[var] = f"value_for_{var}"
                else:
                    os.environ.pop(var, None)
                    expected_missing.append(var)

            result = DatabaseFactory.validate_env_vars()

            assert set(result) == set(expected_missing), (
                f"Expected missing: {expected_missing}, got: {result}"
            )
        finally:
            for var, val in saved.items():
                if val is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = val

    @settings(max_examples=100, deadline=None)
    @given(call_count=st.integers(min_value=2, max_value=20))
    def test_property_9_singleton_identity(self, call_count):
        """
        Property 9: Database factory singleton identity

        For any number of calls to get_instance(), the returned object
        should always be the same instance (identity equality via `is`).

        Feature: persistence-resilience-enhancement, Property 9: Database factory singleton identity
        Validates: Requirements 5.6
        """
        # Reset before each hypothesis example
        DatabaseFactory._instance = None

        first = DatabaseFactory.get_instance()
        for _ in range(call_count - 1):
            current = DatabaseFactory.get_instance()
            assert current is first, "get_instance() returned a different object"


# ===========================================================================
# Unit Tests (Task 5.4)
# ===========================================================================

class TestDatabaseFactoryUnit:
    """Unit tests for DatabaseFactory.

    Validates: Requirements 3.4, 3.5, 5.5
    """

    def test_validate_env_vars_all_present(self, monkeypatch):
        """All required env vars present → empty list."""
        for var, val in FULL_ENV.items():
            monkeypatch.setenv(var, val)
        assert DatabaseFactory.validate_env_vars() == []

    def test_validate_env_vars_all_missing(self, monkeypatch):
        """All required env vars missing → full list."""
        for var in REQUIRED_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        result = DatabaseFactory.validate_env_vars()
        assert set(result) == set(REQUIRED_ENV_VARS)

    def test_validate_env_vars_empty_string_counts_as_missing(self, monkeypatch):
        """Empty string value should count as missing."""
        for var, val in FULL_ENV.items():
            monkeypatch.setenv(var, val)
        monkeypatch.setenv("VNPY_DATABASE_DRIVER", "")
        result = DatabaseFactory.validate_env_vars()
        assert "VNPY_DATABASE_DRIVER" in result

    def test_validate_env_vars_whitespace_only_counts_as_missing(self, monkeypatch):
        """Whitespace-only value should count as missing."""
        for var, val in FULL_ENV.items():
            monkeypatch.setenv(var, val)
        monkeypatch.setenv("VNPY_DATABASE_HOST", "   ")
        result = DatabaseFactory.validate_env_vars()
        assert "VNPY_DATABASE_HOST" in result

    def test_initialize_raises_config_error_on_missing_vars(self, monkeypatch):
        """initialize() should raise DatabaseConfigError when env vars are missing."""
        for var in REQUIRED_ENV_VARS:
            monkeypatch.delenv(var, raising=False)

        factory = DatabaseFactory.get_instance()
        with pytest.raises(DatabaseConfigError) as exc_info:
            factory.initialize()
        assert len(exc_info.value.missing_vars) == len(REQUIRED_ENV_VARS)

    def test_eager_initialization_creates_connection(self, monkeypatch):
        """eager=True should attempt to create connections immediately.

        Validates: Requirements 5.5 (eager initialization)
        """
        for var, val in FULL_ENV.items():
            monkeypatch.setenv(var, val)

        mock_settings = {}
        mock_db_instance = MagicMock()
        mock_peewee = MagicMock()
        mock_db_instance.db = mock_peewee

        with patch("src.main.bootstrap.database_factory.DatabaseFactory._inject_vnpy_settings"), \
             patch("src.main.bootstrap.database_factory.DatabaseFactory._configure_table_names"), \
             patch("vnpy.trader.database.get_database", return_value=mock_db_instance):

            factory = DatabaseFactory.get_instance()
            factory.initialize(eager=True)

            assert factory._db is mock_db_instance
            assert factory._peewee_db is mock_peewee

    def test_lazy_initialization_defers_connection(self, monkeypatch):
        """eager=False should NOT create connections immediately.

        Validates: Requirements 5.5 (lazy initialization)
        """
        for var, val in FULL_ENV.items():
            monkeypatch.setenv(var, val)

        with patch("src.main.bootstrap.database_factory.DatabaseFactory._inject_vnpy_settings"), \
             patch("src.main.bootstrap.database_factory.DatabaseFactory._configure_table_names"):

            factory = DatabaseFactory.get_instance()
            factory.initialize(eager=False)

            assert factory._initialized is True
            assert factory._db is None
            assert factory._peewee_db is None

    def test_no_sqlite_fallback_on_connection_failure(self, monkeypatch):
        """When MySQL connection fails, should raise DatabaseConnectionError, NOT fall back to SQLite.

        Validates: Requirements 3.4
        """
        for var, val in FULL_ENV.items():
            monkeypatch.setenv(var, val)

        with patch("src.main.bootstrap.database_factory.DatabaseFactory._inject_vnpy_settings"), \
             patch("src.main.bootstrap.database_factory.DatabaseFactory._configure_table_names"), \
             patch("vnpy.trader.database.get_database", side_effect=Exception("Connection refused")):

            factory = DatabaseFactory.get_instance()
            with pytest.raises(DatabaseConnectionError) as exc_info:
                factory.initialize(eager=True)

            assert exc_info.value.host == "localhost"
            assert exc_info.value.database == "vnpy_test"
            assert factory._db is None
            assert factory._peewee_db is None

    def test_initialize_logs_connection_info(self, monkeypatch, caplog):
        """Successful initialization should log host and database name.

        Validates: Requirements 3.5
        """
        for var, val in FULL_ENV.items():
            monkeypatch.setenv(var, val)

        with patch("src.main.bootstrap.database_factory.DatabaseFactory._inject_vnpy_settings"), \
             patch("src.main.bootstrap.database_factory.DatabaseFactory._configure_table_names"), \
             patch("vnpy.trader.database.get_database", return_value=MagicMock(db=MagicMock())):

            factory = DatabaseFactory.get_instance()
            with caplog.at_level(logging.INFO, logger="src.main.bootstrap.database_factory"):
                factory.initialize(eager=True)

            assert "localhost" in caplog.text
            assert "vnpy_test" in caplog.text

    def test_reset_clears_singleton_and_connections(self):
        """reset() should clear _instance, _db, and _peewee_db."""
        factory = DatabaseFactory.get_instance()
        factory._db = MagicMock()
        factory._peewee_db = MagicMock()
        factory._initialized = True

        factory.reset()

        assert DatabaseFactory._instance is None
        assert factory._db is None
        assert factory._peewee_db is None
        assert factory._initialized is False

    def test_singleton_returns_same_instance(self):
        """get_instance() should always return the same object."""
        a = DatabaseFactory.get_instance()
        b = DatabaseFactory.get_instance()
        assert a is b

    def test_get_database_triggers_lazy_init(self, monkeypatch):
        """get_database() on uninitialized factory should trigger initialization.

        Validates: Requirements 5.5
        """
        for var, val in FULL_ENV.items():
            monkeypatch.setenv(var, val)

        mock_db = MagicMock()
        mock_db.db = MagicMock()

        with patch("src.main.bootstrap.database_factory.DatabaseFactory._inject_vnpy_settings"), \
             patch("src.main.bootstrap.database_factory.DatabaseFactory._configure_table_names"), \
             patch("vnpy.trader.database.get_database", return_value=mock_db):

            factory = DatabaseFactory.get_instance()
            result = factory.get_database()

            assert result is mock_db
            assert factory._initialized is True
