"""
Property-Based Tests for JsonSerializer - Data Persistence Optimization

Feature: data-persistence-optimization, Property 2: JsonSerializer 序列化往返一致性

Validates: Requirements 1.4, 6.1
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict

import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from src.strategy.infrastructure.persistence.json_serializer import (
    CURRENT_SCHEMA_VERSION,
    JsonSerializer,
)
from src.strategy.infrastructure.persistence.migration_chain import MigrationChain


# ---------------------------------------------------------------------------
# Test helpers: Enum and dataclass types for round-trip testing
# ---------------------------------------------------------------------------

class _TestEnum(Enum):
    """Test enum for serialization testing."""
    OPTION_A = "option_a"
    OPTION_B = "option_b"
    OPTION_C = "option_c"


@dataclass
class _TestDataClass:
    """Test dataclass for serialization testing."""
    name: str
    value: float
    active: bool


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Finite floats only (no NaN/Inf — JSON doesn't support them)
_finite_floats = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e12, max_value=1e12
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

_enum_strategy = st.sampled_from(list(_TestEnum))

_set_strategy = st.frozensets(
    st.integers(min_value=-100, max_value=100),
    min_size=0,
    max_size=10,
).map(set)

_dataclass_strategy = st.builds(
    _TestDataClass,
    name=st.text(min_size=1, max_size=20),
    value=_finite_floats,
    active=st.booleans(),
)


def _snapshot_with_all_types_strategy():
    """Generate Snapshot dictionaries containing all supported special types.
    
    This strategy generates nested dictionaries that include:
    - DataFrame: pandas DataFrame with numeric data
    - datetime: datetime objects with timezone info
    - date: date objects
    - set: set of integers
    - Enum: custom enum values
    - dataclass: custom dataclass instances
    """
    return st.fixed_dictionaries({
        "target_aggregate": st.fixed_dictionaries({
            "bars": _dataframe_strategy,
            "signal": _enum_strategy,
            "last_update_time": _datetime_strategy,
            "metadata": _dataclass_strategy,
        }),
        "position_aggregate": st.fixed_dictionaries({
            "managed_symbols": _set_strategy,
            "last_trading_date": _date_strategy,
            "volume": st.integers(min_value=0, max_value=1000),
            "config": _dataclass_strategy,
        }),
        "current_dt": _datetime_strategy,
        "status": _enum_strategy,
        "tags": _set_strategy,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_serializer() -> JsonSerializer:
    """Create a JsonSerializer instance with empty migration chain."""
    return JsonSerializer(MigrationChain())


def _deep_equal(a: Any, b: Any) -> bool:
    """Deep equality that handles DataFrame, set, Enum, datetime, date, dataclass."""
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

    if isinstance(a, _TestDataClass) and isinstance(b, _TestDataClass):
        return (
            a.name == b.name
            and _scalar_equal(a.value, b.value)
            and a.active == b.active
        )

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
# Property-Based Tests
# ===========================================================================

class TestJsonSerializerRoundTripProperties:
    """Property 2: JsonSerializer 序列化往返一致性
    
    Feature: data-persistence-optimization, Property 2: JsonSerializer 序列化往返一致性
    Validates: Requirements 1.4, 6.1
    """

    @settings(max_examples=100, deadline=None)
    @given(snapshot=_snapshot_with_all_types_strategy())
    def test_property_2_serialization_round_trip_consistency(
        self, snapshot: Dict[str, Any]
    ):
        """
        **Validates: Requirements 1.4, 6.1**
        
        Property 2: JsonSerializer 序列化往返一致性
        
        For any valid Snapshot dictionary containing DataFrame, datetime, date, 
        set, Enum, dataclass types, JsonSerializer.serialize() followed by 
        JsonSerializer.deserialize() should produce results equivalent to the 
        original data.
        
        This test verifies that all special types supported by JsonSerializer
        can be serialized and deserialized without data loss or corruption.
        """
        serializer = _make_serializer()

        # Serialize the snapshot to JSON string
        json_str = serializer.serialize(snapshot)
        
        # Deserialize back to Python objects
        restored = serializer.deserialize(json_str)

        # schema_version is injected by serialize, so it should be present
        assert restored["schema_version"] == CURRENT_SCHEMA_VERSION

        # All original keys must be present and values must be equivalent
        for key in snapshot:
            assert key in restored, f"Missing key after round-trip: {key}"
            assert _deep_equal(snapshot[key], restored[key]), (
                f"Data mismatch on key '{key}' after round-trip:\n"
                f"Original: {snapshot[key]!r}\n"
                f"Restored: {restored[key]!r}"
            )
