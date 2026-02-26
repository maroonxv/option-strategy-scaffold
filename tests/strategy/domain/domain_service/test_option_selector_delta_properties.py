"""
OptionSelectorService.select_by_delta 属性测试

# Feature: selection-service-enhancement, Property 9-10: Delta 选择属性测试

**Validates: Requirements 5.1, 5.3**

Property 9: Delta 选择最优性
Property 10: Delta 范围过滤正确性
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
from src.strategy.domain.value_object.greeks import GreeksResult


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Underlying price: positive float in a realistic range
_underlying_price = st.floats(
    min_value=1000.0, max_value=10000.0, allow_nan=False, allow_infinity=False
)

# Strike step: distance between consecutive strikes
_strike_step = st.sampled_from([50.0, 100.0, 200.0])

# Number of strikes on each side of ATM
_num_strikes_per_side = st.integers(min_value=3, max_value=8)

# Option type for delta selection
_option_type = st.sampled_from(["call", "put"])

# Target delta: realistic range for calls (0, 1) and puts (-1, 0)
_target_delta_call = st.floats(min_value=0.05, max_value=0.95, allow_nan=False, allow_infinity=False)
_target_delta_put = st.floats(min_value=-0.95, max_value=-0.05, allow_nan=False, allow_infinity=False)

# Delta tolerance
_delta_tolerance = st.floats(min_value=0.02, max_value=0.30, allow_nan=False, allow_infinity=False)

# Expiry date string
_expiry = st.sampled_from(["2025-06-20", "2025-07-18", "2025-08-15", "2025-09-19"])

# Bid price: above min_bid_price threshold
_bid_price = st.floats(min_value=20.0, max_value=500.0, allow_nan=False, allow_infinity=False)

# Bid volume: above min_bid_volume threshold
_bid_volume = st.integers(min_value=15, max_value=200)

# Days to expiry: within typical trading day range
_days_to_expiry = st.integers(min_value=5, max_value=40)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_option_chain_with_greeks(
    underlying_price: float,
    num_per_side: int,
    strike_step: float,
    option_type: str,
    expiry: str,
    bid_price: float,
    bid_volume: int,
    days_to_expiry: int,
) -> tuple[pd.DataFrame, dict[str, GreeksResult]]:
    """
    Build an option chain for a single option type with synthetic Greeks data.
    Delta values are generated to be realistic:
    - Calls: delta decreases as strike increases (ITM -> OTM)
    - Puts: delta increases (becomes less negative) as strike increases
    """
    atm_strike = round(underlying_price / strike_step) * strike_step

    strikes = []
    for i in range(-num_per_side, num_per_side + 1):
        s = atm_strike + i * strike_step
        if s > 0:
            strikes.append(s)

    strikes = sorted(set(strikes))
    n = len(strikes)

    rows = []
    greeks_data: dict[str, GreeksResult] = {}

    for idx, s in enumerate(strikes):
        prefix = "C" if option_type == "call" else "P"
        sym = f"OPT-{prefix}-{int(s)}.TEST"

        rows.append({
            "vt_symbol": sym,
            "option_type": option_type,
            "strike_price": s,
            "expiry_date": expiry,
            "bid_price": bid_price,
            "bid_volume": bid_volume,
            "ask_price": bid_price + 2.0,
            "ask_volume": bid_volume,
            "days_to_expiry": days_to_expiry,
            "underlying_symbol": "TEST2506",
        })

        # Generate realistic delta: linearly spaced
        if option_type == "call":
            # High delta for low strikes (ITM), low delta for high strikes (OTM)
            delta = 0.95 - (idx / max(n - 1, 1)) * 0.90  # range ~[0.05, 0.95]
        else:
            # Put delta: from -0.95 (deep ITM) to -0.05 (deep OTM)
            delta = -0.95 + (idx / max(n - 1, 1)) * 0.90  # range ~[-0.95, -0.05]

        greeks_data[sym] = GreeksResult(
            delta=round(delta, 4), gamma=0.01, theta=-0.5, vega=0.2, success=True
        )

    df = pd.DataFrame(rows)
    return df, greeks_data


def _make_selector() -> OptionSelectorService:
    """Create a selector with relaxed thresholds suitable for property testing."""
    return OptionSelectorService(
        strike_level=2,
        min_bid_price=10.0,
        min_bid_volume=5,
        min_trading_days=1,
        max_trading_days=50,
    )


# ---------------------------------------------------------------------------
# Property 9: Delta 选择最优性
# Feature: selection-service-enhancement, Property 9: Delta 选择最优性
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
    target_delta=_target_delta_call,
    delta_tolerance=_delta_tolerance,
)
def test_delta_selection_optimality_call(
    underlying_price,
    num_per_side,
    strike_step,
    expiry,
    bid_price,
    bid_volume,
    days_to_expiry,
    target_delta,
    delta_tolerance,
):
    """
    Property 9: Delta 选择最优性 (Call)

    **Validates: Requirements 5.1**

    For any candidate contract set, target Delta value, and corresponding
    Greeks data, the contract returned by select_by_delta should have the
    smallest absolute difference between its Delta and the target Delta
    among all candidates within the tolerance range.
    """
    selector = _make_selector()
    df, greeks_data = _build_option_chain_with_greeks(
        underlying_price, num_per_side, strike_step, "call",
        expiry, bid_price, bid_volume, days_to_expiry,
    )

    result = selector.select_by_delta(
        contracts=df,
        option_type="call",
        underlying_price=underlying_price,
        target_delta=target_delta,
        greeks_data=greeks_data,
        delta_tolerance=delta_tolerance,
    )

    if result is None:
        # If None, verify no candidate was within tolerance
        for sym, gr in greeks_data.items():
            if gr.success:
                # Check this contract passes liquidity/trading day filters
                row = df[df["vt_symbol"] == sym]
                if row.empty:
                    continue
                r = row.iloc[0]
                if (
                    r.get("bid_price", 0) >= selector.min_bid_price
                    and r.get("bid_volume", 0) >= selector.min_bid_volume
                    and r.get("days_to_expiry", 0) >= selector.min_trading_days
                    and r.get("days_to_expiry", 999) <= selector.max_trading_days
                ):
                    assert abs(gr.delta - target_delta) > delta_tolerance, (
                        f"select_by_delta returned None but {sym} has delta={gr.delta} "
                        f"within tolerance of target={target_delta} (tol={delta_tolerance})"
                    )
        return

    # Find the selected contract's delta
    selected_greeks = greeks_data.get(result.vt_symbol)
    assert selected_greeks is not None, (
        f"Selected contract {result.vt_symbol} has no Greeks data"
    )
    selected_diff = abs(selected_greeks.delta - target_delta)

    # Verify optimality: no other eligible candidate has a smaller diff
    for sym, gr in greeks_data.items():
        if not gr.success:
            continue
        row = df[df["vt_symbol"] == sym]
        if row.empty:
            continue
        r = row.iloc[0]
        if r.get("option_type") != "call":
            continue
        if (
            r.get("bid_price", 0) < selector.min_bid_price
            or r.get("bid_volume", 0) < selector.min_bid_volume
            or r.get("days_to_expiry", 0) < selector.min_trading_days
            or r.get("days_to_expiry", 999) > selector.max_trading_days
        ):
            continue
        if abs(gr.delta - target_delta) > delta_tolerance:
            continue

        candidate_diff = abs(gr.delta - target_delta)
        assert selected_diff <= candidate_diff + 1e-9, (
            f"Selected {result.vt_symbol} (delta={selected_greeks.delta}, diff={selected_diff}) "
            f"is not optimal. {sym} (delta={gr.delta}, diff={candidate_diff}) is closer "
            f"to target={target_delta}"
        )


@settings(max_examples=100)
@given(
    underlying_price=_underlying_price,
    num_per_side=_num_strikes_per_side,
    strike_step=_strike_step,
    expiry=_expiry,
    bid_price=_bid_price,
    bid_volume=_bid_volume,
    days_to_expiry=_days_to_expiry,
    target_delta=_target_delta_put,
    delta_tolerance=_delta_tolerance,
)
def test_delta_selection_optimality_put(
    underlying_price,
    num_per_side,
    strike_step,
    expiry,
    bid_price,
    bid_volume,
    days_to_expiry,
    target_delta,
    delta_tolerance,
):
    """
    Property 9: Delta 选择最优性 (Put)

    **Validates: Requirements 5.1**

    Same property as above but for Put options with negative delta values.
    """
    selector = _make_selector()
    df, greeks_data = _build_option_chain_with_greeks(
        underlying_price, num_per_side, strike_step, "put",
        expiry, bid_price, bid_volume, days_to_expiry,
    )

    result = selector.select_by_delta(
        contracts=df,
        option_type="put",
        underlying_price=underlying_price,
        target_delta=target_delta,
        greeks_data=greeks_data,
        delta_tolerance=delta_tolerance,
    )

    if result is None:
        # If None, verify no candidate was within tolerance
        for sym, gr in greeks_data.items():
            if gr.success:
                row = df[df["vt_symbol"] == sym]
                if row.empty:
                    continue
                r = row.iloc[0]
                if (
                    r.get("bid_price", 0) >= selector.min_bid_price
                    and r.get("bid_volume", 0) >= selector.min_bid_volume
                    and r.get("days_to_expiry", 0) >= selector.min_trading_days
                    and r.get("days_to_expiry", 999) <= selector.max_trading_days
                ):
                    assert abs(gr.delta - target_delta) > delta_tolerance, (
                        f"select_by_delta returned None but {sym} has delta={gr.delta} "
                        f"within tolerance of target={target_delta} (tol={delta_tolerance})"
                    )
        return

    selected_greeks = greeks_data.get(result.vt_symbol)
    assert selected_greeks is not None
    selected_diff = abs(selected_greeks.delta - target_delta)

    for sym, gr in greeks_data.items():
        if not gr.success:
            continue
        row = df[df["vt_symbol"] == sym]
        if row.empty:
            continue
        r = row.iloc[0]
        if r.get("option_type") != "put":
            continue
        if (
            r.get("bid_price", 0) < selector.min_bid_price
            or r.get("bid_volume", 0) < selector.min_bid_volume
            or r.get("days_to_expiry", 0) < selector.min_trading_days
            or r.get("days_to_expiry", 999) > selector.max_trading_days
        ):
            continue
        if abs(gr.delta - target_delta) > delta_tolerance:
            continue

        candidate_diff = abs(gr.delta - target_delta)
        assert selected_diff <= candidate_diff + 1e-9, (
            f"Selected {result.vt_symbol} (delta={selected_greeks.delta}, diff={selected_diff}) "
            f"is not optimal. {sym} (delta={gr.delta}, diff={candidate_diff}) is closer "
            f"to target={target_delta}"
        )


# ---------------------------------------------------------------------------
# Property 10: Delta 范围过滤正确性
# Feature: selection-service-enhancement, Property 10: Delta 范围过滤正确性
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
    target_delta=_target_delta_call,
    delta_tolerance=_delta_tolerance,
)
def test_delta_range_filtering_call(
    underlying_price,
    num_per_side,
    strike_step,
    expiry,
    bid_price,
    bid_volume,
    days_to_expiry,
    target_delta,
    delta_tolerance,
):
    """
    Property 10: Delta 范围过滤正确性 (Call)

    **Validates: Requirements 5.3**

    For any candidate contract set and Delta tolerance constraint, the contract
    returned by select_by_delta should have a Delta value within
    [target_delta - delta_tolerance, target_delta + delta_tolerance].
    """
    selector = _make_selector()
    df, greeks_data = _build_option_chain_with_greeks(
        underlying_price, num_per_side, strike_step, "call",
        expiry, bid_price, bid_volume, days_to_expiry,
    )

    result = selector.select_by_delta(
        contracts=df,
        option_type="call",
        underlying_price=underlying_price,
        target_delta=target_delta,
        greeks_data=greeks_data,
        delta_tolerance=delta_tolerance,
    )

    if result is None:
        return  # No candidate within range, nothing to verify

    # The selected contract's delta must be within the tolerance range
    selected_greeks = greeks_data.get(result.vt_symbol)
    assert selected_greeks is not None, (
        f"Selected contract {result.vt_symbol} has no Greeks data"
    )

    lower_bound = target_delta - delta_tolerance
    upper_bound = target_delta + delta_tolerance

    assert lower_bound - 1e-9 <= selected_greeks.delta <= upper_bound + 1e-9, (
        f"Selected contract {result.vt_symbol} delta={selected_greeks.delta} "
        f"is outside range [{lower_bound}, {upper_bound}] "
        f"(target={target_delta}, tolerance={delta_tolerance})"
    )


@settings(max_examples=100)
@given(
    underlying_price=_underlying_price,
    num_per_side=_num_strikes_per_side,
    strike_step=_strike_step,
    expiry=_expiry,
    bid_price=_bid_price,
    bid_volume=_bid_volume,
    days_to_expiry=_days_to_expiry,
    target_delta=_target_delta_put,
    delta_tolerance=_delta_tolerance,
)
def test_delta_range_filtering_put(
    underlying_price,
    num_per_side,
    strike_step,
    expiry,
    bid_price,
    bid_volume,
    days_to_expiry,
    target_delta,
    delta_tolerance,
):
    """
    Property 10: Delta 范围过滤正确性 (Put)

    **Validates: Requirements 5.3**

    Same property as above but for Put options with negative delta values.
    """
    selector = _make_selector()
    df, greeks_data = _build_option_chain_with_greeks(
        underlying_price, num_per_side, strike_step, "put",
        expiry, bid_price, bid_volume, days_to_expiry,
    )

    result = selector.select_by_delta(
        contracts=df,
        option_type="put",
        underlying_price=underlying_price,
        target_delta=target_delta,
        greeks_data=greeks_data,
        delta_tolerance=delta_tolerance,
    )

    if result is None:
        return

    selected_greeks = greeks_data.get(result.vt_symbol)
    assert selected_greeks is not None

    lower_bound = target_delta - delta_tolerance
    upper_bound = target_delta + delta_tolerance

    assert lower_bound - 1e-9 <= selected_greeks.delta <= upper_bound + 1e-9, (
        f"Selected contract {result.vt_symbol} delta={selected_greeks.delta} "
        f"is outside range [{lower_bound}, {upper_bound}] "
        f"(target={target_delta}, tolerance={delta_tolerance})"
    )
