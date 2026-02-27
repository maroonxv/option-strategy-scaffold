"""
OptionSelectorService.select_combination 属性测试

# Feature: selection-service-enhancement, Property 5-8: 组合选择属性测试

**Validates: Requirements 4.1, 4.2, 4.4, 4.5**

Property 5: 组合选择结构合规
Property 6: Straddle 选择最接近 ATM
Property 7: Strangle 选择虚值档位正确
Property 8: 流动性不足拒绝整个组合
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing
# ---------------------------------------------------------------------------
for _name in [
    "vnpy",
    "vnpy.event",
    "vnpy.trader",
    "vnpy.trader.setting",
    "vnpy.trader.engine",
    "vnpy.trader.database",
    "vnpy.trader.constant",
    "vnpy.trader.object",
    "vnpy_mysql",
]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

# ---------------------------------------------------------------------------
import pandas as pd
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.domain_service.selection.option_selector_service import (
    OptionSelectorService,
)
from src.strategy.domain.value_object.selection.option_selector_config import OptionSelectorConfig
from src.strategy.domain.value_object.combination.combination import CombinationType
from src.strategy.domain.value_object.combination.combination_rules import (
    VALIDATION_RULES,
    LegStructure,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies for option chain generation
# ---------------------------------------------------------------------------

# Underlying price: positive float in a realistic range
_underlying_price = st.floats(min_value=1000.0, max_value=10000.0, allow_nan=False, allow_infinity=False)

# Strike step: distance between consecutive strikes
_strike_step = st.sampled_from([50.0, 100.0, 200.0])

# Number of strikes on each side of ATM
_num_strikes_per_side = st.integers(min_value=3, max_value=8)

# Strike level for strangle
_strike_level = st.integers(min_value=1, max_value=5)

# Expiry date string
_expiry = st.sampled_from(["2025-06-20", "2025-07-18", "2025-08-15", "2025-09-19"])

# Bid price: must be above typical min_bid_price threshold
_bid_price = st.floats(min_value=20.0, max_value=500.0, allow_nan=False, allow_infinity=False)

# Bid volume: must be above typical min_bid_volume threshold
_bid_volume = st.integers(min_value=15, max_value=200)

# Days to expiry: within typical trading day range
_days_to_expiry = st.integers(min_value=5, max_value=40)


def _build_option_chain(
    underlying_price: float,
    num_per_side: int,
    strike_step: float,
    expiry: str,
    bid_price: float,
    bid_volume: int,
    days_to_expiry: int,
) -> pd.DataFrame:
    """
    Build a symmetric option chain around the underlying price.
    Each strike has both a Call and a Put with good liquidity.
    """
    # Round underlying to nearest strike_step to get ATM strike
    atm_strike = round(underlying_price / strike_step) * strike_step

    strikes = []
    for i in range(-num_per_side, num_per_side + 1):
        s = atm_strike + i * strike_step
        if s > 0:
            strikes.append(s)

    # Deduplicate and sort
    strikes = sorted(set(strikes))

    rows = []
    for s in strikes:
        for opt_type in ["call", "put"]:
            rows.append({
                "vt_symbol": f"OPT-{opt_type[0].upper()}-{int(s)}.TEST",
                "option_type": opt_type,
                "strike_price": s,
                "expiry_date": expiry,
                "bid_price": bid_price,
                "bid_volume": bid_volume,
                "ask_price": bid_price + 2.0,
                "ask_volume": bid_volume,
                "days_to_expiry": days_to_expiry,
                "underlying_symbol": "TEST2506",
            })
    return pd.DataFrame(rows)


def _build_illiquid_chain(
    underlying_price: float,
    strike_step: float = 100.0,
) -> pd.DataFrame:
    """
    Build an option chain where ALL contracts have insufficient liquidity
    (bid_price and bid_volume below typical thresholds).
    """
    atm_strike = round(underlying_price / strike_step) * strike_step
    strikes = [atm_strike - strike_step, atm_strike, atm_strike + strike_step]

    rows = []
    for s in strikes:
        for opt_type in ["call", "put"]:
            rows.append({
                "vt_symbol": f"OPT-{opt_type[0].upper()}-{int(s)}.TEST",
                "option_type": opt_type,
                "strike_price": s,
                "expiry_date": "2025-06-20",
                "bid_price": 1.0,   # Below min_bid_price=10
                "bid_volume": 1,    # Below min_bid_volume=5
                "ask_price": 3.0,
                "ask_volume": 1,
                "days_to_expiry": 20,
                "underlying_symbol": "TEST2506",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Default selector factory
# ---------------------------------------------------------------------------

def _make_selector() -> OptionSelectorService:
    """Create a selector with relaxed thresholds suitable for property testing."""
    return OptionSelectorService(
        config=OptionSelectorConfig(
            strike_level=2,
            min_bid_price=10.0,
            min_bid_volume=5,
            min_trading_days=1,
            max_trading_days=50,
        )
    )


# ---------------------------------------------------------------------------
# Property 5: 组合选择结构合规
# Feature: selection-service-enhancement, Property 5: 组合选择结构合规
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    underlying_price=_underlying_price,
    num_per_side=_num_strikes_per_side,
    strike_step=_strike_step,
    expiry=_expiry,
    bid_price=_bid_price,
    bid_volume=_bid_volume,
    days_to_expiry=_days_to_expiry,
    combo_type=st.sampled_from([
        CombinationType.STRADDLE,
        CombinationType.STRANGLE,
        CombinationType.VERTICAL_SPREAD,
    ]),
    strike_level=_strike_level,
)
def test_combination_selection_structural_compliance(
    underlying_price,
    num_per_side,
    strike_step,
    expiry,
    bid_price,
    bid_volume,
    days_to_expiry,
    combo_type,
    strike_level,
):
    """
    Property 5: 组合选择结构合规

    **Validates: Requirements 4.5**

    For any successful combination selection result, converting its legs to
    LegStructure and calling the corresponding VALIDATION_RULES validator
    should return None (i.e., pass validation).
    """
    selector = _make_selector()
    df = _build_option_chain(
        underlying_price, num_per_side, strike_step, expiry,
        bid_price, bid_volume, days_to_expiry,
    )

    # Determine extra kwargs based on combo type
    kwargs = {}
    if combo_type == CombinationType.STRANGLE:
        kwargs["strike_level"] = strike_level
    elif combo_type == CombinationType.VERTICAL_SPREAD:
        kwargs["spread_width"] = max(1, strike_level)
        kwargs["option_type_for_spread"] = "call"

    result = selector.select_combination(
        df, combo_type, underlying_price, **kwargs
    )

    # We only test the property for successful selections
    if result is not None and result.success:
        validator = VALIDATION_RULES.get(combo_type)
        assert validator is not None, f"No validator for {combo_type}"

        leg_structures = [
            LegStructure(
                option_type=leg.option_type,
                strike_price=leg.strike_price,
                expiry_date=leg.expiry_date,
            )
            for leg in result.legs
        ]
        validation_error = validator(leg_structures)
        assert validation_error is None, (
            f"Structural validation failed for {combo_type.value}: {validation_error}"
        )


# ---------------------------------------------------------------------------
# Property 6: Straddle 选择最接近 ATM
# Feature: selection-service-enhancement, Property 6: Straddle 选择最接近 ATM
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    underlying_price=_underlying_price,
    num_per_side=_num_strikes_per_side,
    strike_step=_strike_step,
    expiry=_expiry,
    bid_price=_bid_price,
    bid_volume=_bid_volume,
    days_to_expiry=_days_to_expiry,
)
def test_straddle_selects_closest_to_atm(
    underlying_price,
    num_per_side,
    strike_step,
    expiry,
    bid_price,
    bid_volume,
    days_to_expiry,
):
    """
    Property 6: Straddle 选择最接近 ATM

    **Validates: Requirements 4.1**

    For any option chain and underlying price, a successful STRADDLE selection
    should have Call and Put with the same strike price, and that strike should
    be the closest available strike to the underlying price.
    """
    selector = _make_selector()
    df = _build_option_chain(
        underlying_price, num_per_side, strike_step, expiry,
        bid_price, bid_volume, days_to_expiry,
    )

    result = selector.select_combination(
        df, CombinationType.STRADDLE, underlying_price
    )

    if result is not None and result.success:
        assert len(result.legs) == 2

        call_leg = next((l for l in result.legs if l.option_type == "call"), None)
        put_leg = next((l for l in result.legs if l.option_type == "put"), None)
        assert call_leg is not None and put_leg is not None

        # Call and Put must have the same strike
        assert call_leg.strike_price == put_leg.strike_price, (
            f"STRADDLE Call strike {call_leg.strike_price} != "
            f"Put strike {put_leg.strike_price}"
        )

        selected_strike = call_leg.strike_price
        selected_distance = abs(selected_strike - underlying_price)

        # Collect all common strikes (available in both call and put after filtering)
        filtered_df = df.copy()
        filtered_df = filtered_df[filtered_df["bid_price"] >= selector.config.min_bid_price]
        filtered_df = filtered_df[filtered_df["bid_volume"] >= selector.config.min_bid_volume]
        if "days_to_expiry" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["days_to_expiry"] >= selector.config.min_trading_days]
            filtered_df = filtered_df[filtered_df["days_to_expiry"] <= selector.config.max_trading_days]

        call_strikes = set(
            filtered_df[filtered_df["option_type"] == "call"]["strike_price"].unique()
        )
        put_strikes = set(
            filtered_df[filtered_df["option_type"] == "put"]["strike_price"].unique()
        )
        common_strikes = call_strikes & put_strikes

        assume(len(common_strikes) > 0)

        # The selected strike should be the closest to underlying
        for s in common_strikes:
            assert selected_distance <= abs(s - underlying_price) + 1e-9, (
                f"Selected strike {selected_strike} (dist={selected_distance}) "
                f"is not closest to ATM. Strike {s} (dist={abs(s - underlying_price)}) "
                f"is closer. underlying={underlying_price}"
            )


# ---------------------------------------------------------------------------
# Property 7: Strangle 选择虚值档位正确
# Feature: selection-service-enhancement, Property 7: Strangle 选择虚值档位正确
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    underlying_price=_underlying_price,
    num_per_side=st.integers(min_value=5, max_value=8),
    strike_step=_strike_step,
    expiry=_expiry,
    bid_price=_bid_price,
    bid_volume=_bid_volume,
    days_to_expiry=_days_to_expiry,
    strike_level=st.integers(min_value=1, max_value=3),
)
def test_strangle_selects_correct_otm_levels(
    underlying_price,
    num_per_side,
    strike_step,
    expiry,
    bid_price,
    bid_volume,
    days_to_expiry,
    strike_level,
):
    """
    Property 7: Strangle 选择虚值档位正确

    **Validates: Requirements 4.2**

    For any option chain, underlying price, and OTM level config, a successful
    STRANGLE selection should have:
    - Call strike > underlying price (OTM call)
    - Put strike < underlying price (OTM put)
    - Each leg's OTM ranking position equals the configured strike_level
    """
    selector = _make_selector()
    df = _build_option_chain(
        underlying_price, num_per_side, strike_step, expiry,
        bid_price, bid_volume, days_to_expiry,
    )

    result = selector.select_combination(
        df, CombinationType.STRANGLE, underlying_price,
        strike_level=strike_level,
    )

    if result is not None and result.success:
        assert len(result.legs) == 2

        call_leg = next((l for l in result.legs if l.option_type == "call"), None)
        put_leg = next((l for l in result.legs if l.option_type == "put"), None)
        assert call_leg is not None and put_leg is not None

        # Call must be OTM: strike > underlying
        assert call_leg.strike_price > underlying_price, (
            f"STRANGLE Call strike {call_leg.strike_price} should be > "
            f"underlying {underlying_price}"
        )

        # Put must be OTM: strike < underlying
        assert put_leg.strike_price < underlying_price, (
            f"STRANGLE Put strike {put_leg.strike_price} should be < "
            f"underlying {underlying_price}"
        )

        # Verify OTM ranking position matches strike_level
        # Reconstruct the OTM ranking the same way the service does
        filtered_df = df.copy()
        filtered_df = filtered_df[filtered_df["bid_price"] >= selector.config.min_bid_price]
        filtered_df = filtered_df[filtered_df["bid_volume"] >= selector.config.min_bid_volume]
        if "days_to_expiry" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["days_to_expiry"] >= selector.config.min_trading_days]
            filtered_df = filtered_df[filtered_df["days_to_expiry"] <= selector.config.max_trading_days]

        # OTM calls: strike > underlying, sorted by distance ascending
        otm_calls = filtered_df[
            (filtered_df["option_type"] == "call") &
            (filtered_df["strike_price"] > underlying_price)
        ].sort_values("strike_price", ascending=True)

        # OTM puts: strike < underlying, sorted by distance ascending (closest first)
        otm_puts = filtered_df[
            (filtered_df["option_type"] == "put") &
            (filtered_df["strike_price"] < underlying_price)
        ].sort_values("strike_price", ascending=False)

        assume(len(otm_calls) >= strike_level and len(otm_puts) >= strike_level)

        # The selected call should be at position strike_level (1-indexed)
        expected_call_strike = otm_calls.iloc[strike_level - 1]["strike_price"]
        assert call_leg.strike_price == expected_call_strike, (
            f"STRANGLE Call strike {call_leg.strike_price} != expected "
            f"OTM level {strike_level} strike {expected_call_strike}"
        )

        # The selected put should be at position strike_level (1-indexed)
        expected_put_strike = otm_puts.iloc[strike_level - 1]["strike_price"]
        assert put_leg.strike_price == expected_put_strike, (
            f"STRANGLE Put strike {put_leg.strike_price} != expected "
            f"OTM level {strike_level} strike {expected_put_strike}"
        )


# ---------------------------------------------------------------------------
# Property 8: 流动性不足拒绝整个组合
# Feature: selection-service-enhancement, Property 8: 流动性不足拒绝整个组合
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    underlying_price=_underlying_price,
    combo_type=st.sampled_from([
        CombinationType.STRADDLE,
        CombinationType.STRANGLE,
        CombinationType.VERTICAL_SPREAD,
    ]),
)
def test_illiquid_chain_rejects_combination(
    underlying_price,
    combo_type,
):
    """
    Property 8: 流动性不足拒绝整个组合

    **Validates: Requirements 4.4**

    When all contracts in the option chain have insufficient liquidity
    (bid_price and bid_volume below thresholds), select_combination should
    return success=False.
    """
    selector = _make_selector()
    df = _build_illiquid_chain(underlying_price)

    kwargs = {}
    if combo_type == CombinationType.STRANGLE:
        kwargs["strike_level"] = 1
    elif combo_type == CombinationType.VERTICAL_SPREAD:
        kwargs["spread_width"] = 1
        kwargs["option_type_for_spread"] = "call"

    result = selector.select_combination(
        df, combo_type, underlying_price, **kwargs
    )

    # Result should either be None (invalid price) or success=False
    if result is not None:
        assert result.success is False, (
            f"Expected success=False for illiquid chain with {combo_type.value}, "
            f"but got success=True with legs: {result.legs}"
        )
