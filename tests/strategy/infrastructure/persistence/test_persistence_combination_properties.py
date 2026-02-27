"""
Property-Based Tests for CombinationAggregate Snapshot - Data Persistence Optimization

Feature: data-persistence-optimization, Property 1: CombinationAggregate 快照往返一致性

Validates: Requirements 1.1, 1.2, 1.5
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from hypothesis import given, settings, strategies as st

from src.strategy.domain.aggregate.combination_aggregate import CombinationAggregate
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_option_type_strategy = st.sampled_from(["call", "put"])

_direction_strategy = st.sampled_from(["long", "short"])

_combination_status_strategy = st.sampled_from([
    CombinationStatus.PENDING,
    CombinationStatus.ACTIVE,
    CombinationStatus.PARTIALLY_CLOSED,
    CombinationStatus.CLOSED,
])

_combination_type_strategy = st.sampled_from([
    CombinationType.STRADDLE,
    CombinationType.STRANGLE,
    CombinationType.VERTICAL_SPREAD,
    CombinationType.CALENDAR_SPREAD,
    CombinationType.IRON_CONDOR,
    CombinationType.CUSTOM,
])

# Finite floats for prices
_finite_floats = st.floats(
    allow_nan=False, 
    allow_infinity=False, 
    min_value=0.01, 
    max_value=10000.0
)

# Datetimes for create_time and close_time (naive datetimes)
_datetime_strategy = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
)

# Expiry dates as strings (YYYYMMDD format)
_expiry_date_strategy = st.dates(
    min_value=datetime(2024, 1, 1).date(),
    max_value=datetime(2025, 12, 31).date(),
).map(lambda d: d.strftime("%Y%m%d"))


def _leg_strategy() -> st.SearchStrategy[Leg]:
    """Generate random Leg instances."""
    return st.builds(
        Leg,
        vt_symbol=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Nd")),
            min_size=5,
            max_size=20,
        ),
        option_type=_option_type_strategy,
        strike_price=_finite_floats,
        expiry_date=_expiry_date_strategy,
        direction=_direction_strategy,
        volume=st.integers(min_value=1, max_value=100),
        open_price=_finite_floats,
    )


def _combination_strategy() -> st.SearchStrategy[Combination]:
    """Generate random Combination instances.
    
    Note: We use CUSTOM type to avoid validation constraints from specific
    combination types (e.g., STRADDLE requires specific leg structures).
    """
    return st.builds(
        Combination,
        combination_id=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Nd", "Pd")),
            min_size=5,
            max_size=30,
        ),
        combination_type=st.just(CombinationType.CUSTOM),  # Use CUSTOM to avoid validation
        underlying_vt_symbol=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Nd")),
            min_size=5,
            max_size=20,
        ),
        legs=st.lists(_leg_strategy(), min_size=1, max_size=4),
        status=_combination_status_strategy,
        create_time=_datetime_strategy,
        close_time=st.none() | _datetime_strategy,
    )


def _combination_aggregate_strategy() -> st.SearchStrategy[CombinationAggregate]:
    """Generate random CombinationAggregate instances with registered combinations."""
    @st.composite
    def _build_aggregate(draw):
        aggregate = CombinationAggregate()
        
        # Generate 0-5 combinations
        num_combinations = draw(st.integers(min_value=0, max_value=5))
        
        for _ in range(num_combinations):
            combination = draw(_combination_strategy())
            aggregate.register_combination(combination)
        
        return aggregate
    
    return _build_aggregate()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _legs_equal(leg1: Leg, leg2: Leg) -> bool:
    """Compare two Leg instances for equality."""
    return (
        leg1.vt_symbol == leg2.vt_symbol
        and leg1.option_type == leg2.option_type
        and abs(leg1.strike_price - leg2.strike_price) < 1e-9
        and leg1.expiry_date == leg2.expiry_date
        and leg1.direction == leg2.direction
        and leg1.volume == leg2.volume
        and abs(leg1.open_price - leg2.open_price) < 1e-9
    )


def _combinations_equal(combo1: Combination, combo2: Combination) -> bool:
    """Compare two Combination instances for equality."""
    if combo1.combination_id != combo2.combination_id:
        return False
    if combo1.combination_type != combo2.combination_type:
        return False
    if combo1.underlying_vt_symbol != combo2.underlying_vt_symbol:
        return False
    if combo1.status != combo2.status:
        return False
    if combo1.create_time != combo2.create_time:
        return False
    if combo1.close_time != combo2.close_time:
        return False
    if len(combo1.legs) != len(combo2.legs):
        return False
    
    # Compare legs (order matters)
    for leg1, leg2 in zip(combo1.legs, combo2.legs):
        if not _legs_equal(leg1, leg2):
            return False
    
    return True


def _aggregates_equal(agg1: CombinationAggregate, agg2: CombinationAggregate) -> bool:
    """Compare two CombinationAggregate instances for equivalence.
    
    Two aggregates are equivalent if they have the same combinations and
    symbol_index mappings.
    """
    # Access private attributes for testing purposes
    combinations1 = agg1._combinations
    combinations2 = agg2._combinations
    symbol_index1 = agg1._symbol_index
    symbol_index2 = agg2._symbol_index
    
    # Check combinations dictionary
    if set(combinations1.keys()) != set(combinations2.keys()):
        return False
    
    for cid in combinations1:
        if not _combinations_equal(combinations1[cid], combinations2[cid]):
            return False
    
    # Check symbol_index
    if set(symbol_index1.keys()) != set(symbol_index2.keys()):
        return False
    
    for symbol in symbol_index1:
        if symbol_index1[symbol] != symbol_index2[symbol]:
            return False
    
    return True


# ===========================================================================
# Property-Based Tests
# ===========================================================================

class TestCombinationAggregateSnapshotProperties:
    """Property 1: CombinationAggregate 快照往返一致性
    
    Feature: data-persistence-optimization, Property 1: CombinationAggregate 快照往返一致性
    Validates: Requirements 1.1, 1.2, 1.5
    """

    @settings(max_examples=100, deadline=None)
    @given(aggregate=_combination_aggregate_strategy())
    def test_property_1_combination_aggregate_snapshot_round_trip(
        self, aggregate: CombinationAggregate
    ):
        """
        **Validates: Requirements 1.1, 1.2, 1.5**
        
        Property 1: CombinationAggregate 快照往返一致性
        
        For any valid CombinationAggregate instance, calling to_snapshot() to 
        generate a snapshot dictionary, then restoring via 
        CombinationAggregate.from_snapshot(), the restored instance should be 
        equivalent to the original instance in terms of combinations and 
        symbol_index.
        
        This test verifies that CombinationAggregate can be correctly serialized 
        and restored without data loss, which is critical for strategy restart 
        scenarios where combination state must be preserved.
        """
        # Generate snapshot from original aggregate
        snapshot = aggregate.to_snapshot()
        
        # Verify snapshot structure
        assert isinstance(snapshot, dict), "Snapshot must be a dictionary"
        assert "combinations" in snapshot, "Snapshot must contain 'combinations'"
        assert "symbol_index" in snapshot, "Snapshot must contain 'symbol_index'"
        
        # Restore aggregate from snapshot
        restored = CombinationAggregate.from_snapshot(snapshot)
        
        # Verify the restored aggregate is equivalent to the original
        assert _aggregates_equal(aggregate, restored), (
            "Restored CombinationAggregate is not equivalent to original.\n"
            f"Original combinations: {list(aggregate._combinations.keys())}\n"
            f"Restored combinations: {list(restored._combinations.keys())}\n"
            f"Original symbol_index: {aggregate._symbol_index}\n"
            f"Restored symbol_index: {restored._symbol_index}"
        )
