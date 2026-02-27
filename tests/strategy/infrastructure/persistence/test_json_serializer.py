"""
Tests for JsonSerializer — Property-Based Tests and Unit Tests

Feature: persistence-resilience-enhancement, Property 7: JSON serialization round-trip

Validates: Requirements 4.1, 4.2, 4.5, 4.6, 4.8
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict

import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st, assume

from src.strategy.infrastructure.persistence.json_serializer import (
    CURRENT_SCHEMA_VERSION,
    JsonSerializer,
)
from src.strategy.infrastructure.persistence.migration_chain import MigrationChain


# ---------------------------------------------------------------------------
# Test helpers: Enum and dataclass types for round-trip testing
# ---------------------------------------------------------------------------

class _Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


@dataclass
class _Point:
    x: float
    y: float


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Finite floats only (no NaN/Inf — JSON doesn't support them)
_finite_floats = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e12, max_value=1e12
)

# Simple scalar values that survive JSON round-trip
_scalars = st.one_of(
    st.integers(min_value=-10_000, max_value=10_000),
    _finite_floats,
    st.text(min_size=0, max_size=30),
    st.booleans(),
    st.none(),
)


# Strategy for generating DataFrames with numeric columns
_dataframe_strategy = st.builds(
    lambda rows: pd.DataFrame(rows),
    st.lists(
        st.fixed_dictionaries({
            "open": _finite_floats,
            "high": _finite_floats,
            "low": _finite_floats,
            "close": _finite_floats,
            "volume": st.integers(min_value=0, max_value=100_000),
        }),
        min_size=0,
        max_size=5,
    ),
)

# Datetimes without microsecond precision loss (ISO 8601 round-trips cleanly)
_datetime_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc) | st.none(),
)

_date_strategy = st.dates(
    min_value=date(2000, 1, 1),
    max_value=date(2030, 12, 31),
)

_enum_strategy = st.sampled_from(list(_Color))

_set_strategy = st.frozensets(
    st.integers(min_value=-100, max_value=100),
    min_size=0,
    max_size=10,
).map(set)


def _aggregate_snapshot_strategy():
    """Generate Aggregate_Snapshot-like dictionaries with mixed types."""
    return st.fixed_dictionaries({
        "target_aggregate": st.fixed_dictionaries({
            "bars": _dataframe_strategy,
            "signal": _enum_strategy,
            "last_update_time": _datetime_strategy,
        }),
        "position_aggregate": st.fixed_dictionaries({
            "managed_symbols": _set_strategy,
            "last_trading_date": _date_strategy,
            "volume": st.integers(min_value=0, max_value=1000),
        }),
        "current_dt": _datetime_strategy,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_serializer() -> JsonSerializer:
    return JsonSerializer(MigrationChain())


def _deep_equal(a: Any, b: Any) -> bool:
    """Deep equality that handles DataFrame, set, Enum, datetime, date."""
    if isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame):
        if a.empty and b.empty:
            return True
        if set(a.columns) != set(b.columns):
            return False
        if len(a) != len(b):
            return False
        for col in a.columns:
            for va, vb in zip(a[col], b[col]):
                if not _scalar_equal(va, vb):
                    return False
        return True

    if isinstance(a, set) and isinstance(b, set):
        return a == b

    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_deep_equal(a[k], b[k]) for k in a)

    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_deep_equal(x, y) for x, y in zip(a, b))

    return _scalar_equal(a, b)


def _scalar_equal(a: Any, b: Any) -> bool:
    """Compare scalars, handling float precision."""
    if type(a) is not type(b):
        # int vs float comparison
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
        return False
    if isinstance(a, float):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    return a == b


# ===========================================================================
# Property-Based Tests (Task 3.2)
# ===========================================================================

class TestJsonSerializerProperties:
    """Property 7: JSON serialization round-trip

    Feature: persistence-resilience-enhancement, Property 7: JSON serialization round-trip
    Validates: Requirements 4.1, 4.2, 4.5, 4.6, 4.8
    """

    @settings(max_examples=100, deadline=None)
    @given(snapshot=_aggregate_snapshot_strategy())
    def test_property_7_round_trip(self, snapshot: Dict[str, Any]):
        """
        Property 7: JSON serialization round-trip

        For any valid Aggregate_Snapshot dictionary, serializing then
        deserializing should produce a data structure equivalent to the original.

        Feature: persistence-resilience-enhancement, Property 7: JSON serialization round-trip
        Validates: Requirements 4.1, 4.2, 4.5, 4.6, 4.8
        """
        serializer = _make_serializer()

        json_str = serializer.serialize(snapshot)
        restored = serializer.deserialize(json_str)

        # schema_version is injected by serialize
        assert restored["schema_version"] == CURRENT_SCHEMA_VERSION

        # All original keys must be present
        for key in snapshot:
            assert key in restored, f"Missing key: {key}"
            assert _deep_equal(snapshot[key], restored[key]), (
                f"Mismatch on key '{key}': {snapshot[key]!r} != {restored[key]!r}"
            )


# ===========================================================================
# Unit Tests (Task 3.3)
# ===========================================================================

class TestJsonSerializerUnit:
    """Unit tests for JsonSerializer edge cases.

    Validates: Requirements 4.5, 4.6
    """

    def test_empty_dataframe_round_trip(self):
        """Empty DataFrame should survive round-trip."""
        serializer = _make_serializer()
        data = {"df": pd.DataFrame()}
        restored = serializer.deserialize(serializer.serialize(data))
        assert isinstance(restored["df"], pd.DataFrame)
        assert restored["df"].empty

    def test_dataframe_with_data_round_trip(self):
        """DataFrame with rows should survive round-trip."""
        serializer = _make_serializer()
        df = pd.DataFrame([
            {"open": 3500.0, "high": 3510.0, "low": 3495.0, "close": 3505.0, "volume": 1200},
            {"open": 3505.0, "high": 3520.0, "low": 3500.0, "close": 3515.0, "volume": 800},
        ])
        data = {"bars": df}
        restored = serializer.deserialize(serializer.serialize(data))
        pd.testing.assert_frame_equal(restored["bars"], df, check_like=True)

    def test_datetime_round_trip(self):
        """datetime values should survive round-trip."""
        serializer = _make_serializer()
        dt = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        data = {"current_dt": dt}
        restored = serializer.deserialize(serializer.serialize(data))
        assert restored["current_dt"] == dt

    def test_date_round_trip(self):
        """date values should survive round-trip."""
        serializer = _make_serializer()
        d = date(2025, 1, 15)
        data = {"last_trading_date": d}
        restored = serializer.deserialize(serializer.serialize(data))
        assert restored["last_trading_date"] == d

    def test_nested_datetime_round_trip(self):
        """Nested datetime inside dicts should survive round-trip."""
        serializer = _make_serializer()
        data = {
            "position": {
                "create_time": datetime(2025, 1, 10, 9, 30, 0),
                "open_time": datetime(2025, 1, 10, 9, 30, 5),
                "close_time": None,
            }
        }
        restored = serializer.deserialize(serializer.serialize(data))
        assert restored["position"]["create_time"] == datetime(2025, 1, 10, 9, 30, 0)
        assert restored["position"]["open_time"] == datetime(2025, 1, 10, 9, 30, 5)
        assert restored["position"]["close_time"] is None

    def test_enum_round_trip(self):
        """Enum values should survive round-trip."""
        serializer = _make_serializer()
        data = {"signal": _Color.RED}
        restored = serializer.deserialize(serializer.serialize(data))
        assert restored["signal"] is _Color.RED

    def test_set_round_trip(self):
        """set values should survive round-trip."""
        serializer = _make_serializer()
        data = {"symbols": {1, 2, 3}}
        restored = serializer.deserialize(serializer.serialize(data))
        assert restored["symbols"] == {1, 2, 3}

    def test_empty_set_round_trip(self):
        """Empty set should survive round-trip."""
        serializer = _make_serializer()
        data = {"empty": set()}
        restored = serializer.deserialize(serializer.serialize(data))
        assert restored["empty"] == set()

    def test_schema_version_injected(self):
        """serialize() should inject schema_version."""
        serializer = _make_serializer()
        json_str = serializer.serialize({"key": "value"})
        import json
        parsed = json.loads(json_str)
        assert parsed["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_schema_version_migration(self):
        """deserialize() should apply migration when version < current."""
        chain = MigrationChain()
        # Suppose we bump to version 2 in the future
        import src.strategy.infrastructure.persistence.json_serializer as mod
        original_version = mod.CURRENT_SCHEMA_VERSION

        try:
            mod.CURRENT_SCHEMA_VERSION = 2
            chain.register(1, lambda d: {**d, "migrated": True})
            serializer = JsonSerializer(chain)

            # Manually craft a v1 JSON string
            import json
            v1_json = json.dumps({"schema_version": 1, "data": "test"})
            restored = serializer.deserialize(v1_json)

            assert restored["schema_version"] == 2
            assert restored["migrated"] is True
        finally:
            mod.CURRENT_SCHEMA_VERSION = original_version

    def test_complex_nested_structure(self):
        """Complex nested structure with mixed types should round-trip."""
        serializer = _make_serializer()
        data = {
            "target_aggregate": {
                "instruments": {
                    "rb2501.SHFE": {
                        "bars": pd.DataFrame([
                            {"open": 3500.0, "close": 3505.0, "volume": 1200}
                        ]),
                        "signal": _Color.GREEN,
                        "last_update_time": datetime(2025, 1, 15, 14, 29, 0),
                    }
                },
                "active_contracts": {"rb": "rb2501.SHFE"},
            },
            "position_aggregate": {
                "managed_symbols": {"rb2501P3400.SHFE"},
                "last_trading_date": date(2025, 1, 15),
            },
            "current_dt": datetime(2025, 1, 15, 14, 29, 0),
        }
        restored = serializer.deserialize(serializer.serialize(data))

        # Verify key types survived
        bars = restored["target_aggregate"]["instruments"]["rb2501.SHFE"]["bars"]
        assert isinstance(bars, pd.DataFrame)
        assert len(bars) == 1

        signal = restored["target_aggregate"]["instruments"]["rb2501.SHFE"]["signal"]
        assert signal is _Color.GREEN

        symbols = restored["position_aggregate"]["managed_symbols"]
        assert isinstance(symbols, set)
        assert "rb2501P3400.SHFE" in symbols

        ltd = restored["position_aggregate"]["last_trading_date"]
        assert isinstance(ltd, date)
        assert ltd == date(2025, 1, 15)
