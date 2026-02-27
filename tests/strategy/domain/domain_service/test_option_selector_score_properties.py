"""
OptionSelectorService.score_candidates 属性测试

# Feature: selection-service-enhancement, Property 11-12: 评分排名属性测试

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

Property 11: 评分单调性
Property 12: 评分完整性与排序
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


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Underlying price: positive float in a realistic range
_underlying_price = st.floats(
    min_value=1000.0, max_value=10000.0, allow_nan=False, allow_infinity=False
)

# Strike step: distance between consecutive strikes
_strike_step = st.sampled_from([50.0, 100.0, 200.0])

# Number of OTM strikes to generate
_num_otm_strikes = st.integers(min_value=3, max_value=8)

# Option type
_option_type = st.sampled_from(["call", "put"])

# Expiry date string
_expiry = st.sampled_from(["2025-06-20", "2025-07-18", "2025-08-15", "2025-09-19"])

# Bid price: above min_bid_price threshold
_bid_price = st.floats(min_value=20.0, max_value=500.0, allow_nan=False, allow_infinity=False)

# Bid volume: above min_bid_volume threshold
_bid_volume = st.integers(min_value=15, max_value=200)

# Days to expiry: within typical trading day range
_days_to_expiry = st.integers(min_value=5, max_value=40)

# Weights: positive floats that sum > 0
_weight = st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_selector(min_days: int = 1, max_days: int = 50) -> OptionSelectorService:
    """Create a selector with relaxed thresholds suitable for property testing."""
    return OptionSelectorService(
        config=OptionSelectorConfig(
            strike_level=2,
            min_bid_price=10.0,
            min_bid_volume=5,
            min_trading_days=min_days,
            max_trading_days=max_days,
        )
    )


def _build_otm_chain(
    underlying_price: float,
    num_strikes: int,
    strike_step: float,
    option_type: str,
    expiry: str,
    bid_price: float,
    bid_volume: int,
    days_to_expiry: int,
    ask_spread: float = 2.0,
) -> pd.DataFrame:
    """
    Build an option chain containing only OTM options for a single type.

    For calls: strikes above underlying_price.
    For puts: strikes below underlying_price.
    """
    rows = []
    for i in range(1, num_strikes + 1):
        if option_type == "call":
            strike = underlying_price + i * strike_step
        else:
            strike = underlying_price - i * strike_step
            if strike <= 0:
                continue

        prefix = "C" if option_type == "call" else "P"
        sym = f"OPT-{prefix}-{int(strike)}.TEST"

        rows.append({
            "vt_symbol": sym,
            "option_type": option_type,
            "strike_price": strike,
            "expiry_date": expiry,
            "bid_price": bid_price,
            "bid_volume": bid_volume,
            "ask_price": bid_price + ask_spread,
            "ask_volume": bid_volume,
            "days_to_expiry": days_to_expiry,
            "underlying_symbol": "TEST2506",
        })

    return pd.DataFrame(rows)


def _build_pair_for_monotonicity(
    underlying_price: float,
    option_type: str,
    expiry: str,
    # Contract A params
    spread_a: float,
    bid_volume_a: int,
    strike_offset_a: float,
    days_a: int,
    # Contract B params
    spread_b: float,
    bid_volume_b: int,
    strike_offset_b: float,
    days_b: int,
) -> pd.DataFrame:
    """
    Build a DataFrame with exactly two OTM contracts A and B for monotonicity testing.
    strike_offset is the distance from underlying_price (always positive, applied in OTM direction).
    """
    rows = []
    for label, spread, bvol, offset, days in [
        ("A", spread_a, bid_volume_a, strike_offset_a, days_a),
        ("B", spread_b, bid_volume_b, strike_offset_b, days_b),
    ]:
        if option_type == "call":
            strike = underlying_price + offset
        else:
            strike = underlying_price - offset
            if strike <= 0:
                return pd.DataFrame()  # invalid, will be filtered by assume

        prefix = "C" if option_type == "call" else "P"
        sym = f"OPT-{prefix}-{label}.TEST"
        bid_price = max(20.0, 100.0 - spread)  # ensure bid_price > min_bid_price

        rows.append({
            "vt_symbol": sym,
            "option_type": option_type,
            "strike_price": strike,
            "expiry_date": expiry,
            "bid_price": bid_price,
            "bid_volume": bvol,
            "ask_price": bid_price + spread,
            "ask_volume": bvol,
            "days_to_expiry": days,
            "underlying_symbol": "TEST2506",
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Property 11: 评分单调性
# Feature: selection-service-enhancement, Property 11: 评分单调性
# ---------------------------------------------------------------------------

# --- 11a: 流动性得分单调性 ---

@settings(max_examples=100)
@given(
    underlying_price=_underlying_price,
    option_type=_option_type,
    expiry=_expiry,
    days=_days_to_expiry,
    # A has smaller spread AND larger volume
    spread_a=st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
    spread_b=st.floats(min_value=5.1, max_value=50.0, allow_nan=False, allow_infinity=False),
    volume_a=st.integers(min_value=50, max_value=200),
    volume_b=st.integers(min_value=15, max_value=49),
    strike_offset=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
)
def test_liquidity_score_monotonicity(
    underlying_price, option_type, expiry, days,
    spread_a, spread_b, volume_a, volume_b, strike_offset,
):
    """
    Property 11: 评分单调性 - 流动性维度

    **Validates: Requirements 6.2**

    If contract A has a smaller bid-ask spread AND larger bid volume than B,
    then A's liquidity_score should be higher than B's.
    """
    # Ensure A strictly dominates B on both dimensions
    assume(spread_a < spread_b)
    assume(volume_a > volume_b)

    selector = _make_selector()
    df = _build_pair_for_monotonicity(
        underlying_price, option_type, expiry,
        spread_a=spread_a, bid_volume_a=volume_a, strike_offset_a=strike_offset, days_a=days,
        spread_b=spread_b, bid_volume_b=volume_b, strike_offset_b=strike_offset, days_b=days,
    )
    assume(not df.empty)
    assume(len(df) == 2)

    scores = selector.score_candidates(
        contracts=df,
        option_type=option_type,
        underlying_price=underlying_price,
    )

    # Both contracts should be scored (both are OTM with valid liquidity)
    assume(len(scores) == 2)

    score_map = {s.option_contract.vt_symbol: s for s in scores}
    prefix = "C" if option_type == "call" else "P"
    sa = score_map.get(f"OPT-{prefix}-A.TEST")
    sb = score_map.get(f"OPT-{prefix}-B.TEST")
    assume(sa is not None and sb is not None)

    assert sa.liquidity_score > sb.liquidity_score, (
        f"Liquidity monotonicity violated: A(spread={spread_a}, vol={volume_a}) "
        f"score={sa.liquidity_score:.6f} should be > "
        f"B(spread={spread_b}, vol={volume_b}) score={sb.liquidity_score:.6f}"
    )


# --- 11b: 虚值程度得分单调性 ---

@settings(max_examples=100)
@given(
    underlying_price=_underlying_price,
    option_type=_option_type,
    expiry=_expiry,
    days=_days_to_expiry,
    bid_price=_bid_price,
    bid_volume=_bid_volume,
    # A has smaller OTM deviation (closer to ATM)
    offset_a=st.floats(min_value=50.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    offset_b=st.floats(min_value=301.0, max_value=800.0, allow_nan=False, allow_infinity=False),
)
def test_otm_score_monotonicity(
    underlying_price, option_type, expiry, days,
    bid_price, bid_volume, offset_a, offset_b,
):
    """
    Property 11: 评分单调性 - 虚值程度维度

    **Validates: Requirements 6.3**

    If contract A's OTM level deviation is smaller (closer to ATM) than B's,
    then A's otm_score should be higher than B's.
    """
    assume(offset_a < offset_b)

    selector = _make_selector()
    spread = 2.0
    df = _build_pair_for_monotonicity(
        underlying_price, option_type, expiry,
        spread_a=spread, bid_volume_a=bid_volume, strike_offset_a=offset_a, days_a=days,
        spread_b=spread, bid_volume_b=bid_volume, strike_offset_b=offset_b, days_b=days,
    )
    assume(not df.empty)
    assume(len(df) == 2)

    scores = selector.score_candidates(
        contracts=df,
        option_type=option_type,
        underlying_price=underlying_price,
    )

    assume(len(scores) == 2)

    score_map = {s.option_contract.vt_symbol: s for s in scores}
    prefix = "C" if option_type == "call" else "P"
    sa = score_map.get(f"OPT-{prefix}-A.TEST")
    sb = score_map.get(f"OPT-{prefix}-B.TEST")
    assume(sa is not None and sb is not None)

    assert sa.otm_score > sb.otm_score, (
        f"OTM monotonicity violated: A(offset={offset_a}) "
        f"score={sa.otm_score:.6f} should be > "
        f"B(offset={offset_b}) score={sb.otm_score:.6f}"
    )


# --- 11c: 到期日得分单调性 ---

@settings(max_examples=100)
@given(
    underlying_price=_underlying_price,
    option_type=_option_type,
    expiry=_expiry,
    bid_price=_bid_price,
    bid_volume=_bid_volume,
    strike_offset=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    # min/max trading days define the range; midpoint = (min+max)/2
    min_days=st.integers(min_value=5, max_value=15),
    max_days=st.integers(min_value=25, max_value=45),
    # days_a closer to midpoint than days_b
    deviation_a=st.integers(min_value=0, max_value=3),
    deviation_b=st.integers(min_value=4, max_value=10),
    direction_a=st.sampled_from([-1, 1]),
    direction_b=st.sampled_from([-1, 1]),
)
def test_expiry_score_monotonicity(
    underlying_price, option_type, expiry, bid_price, bid_volume,
    strike_offset, min_days, max_days, deviation_a, deviation_b,
    direction_a, direction_b,
):
    """
    Property 11: 评分单调性 - 到期日维度

    **Validates: Requirements 6.4**

    If contract A's remaining trading days are closer to the target range
    midpoint than B's, then A's expiry_score should be higher than B's.
    """
    assume(min_days < max_days)
    assume(deviation_a < deviation_b)

    midpoint = (min_days + max_days) / 2.0
    half_range = (max_days - min_days) / 2.0

    days_a = int(midpoint + direction_a * deviation_a)
    days_b = int(midpoint + direction_b * deviation_b)

    # Ensure days are positive and within a reasonable range for the selector
    assume(days_a >= 1)
    assume(days_b >= 1)
    # Ensure both are within the selector's trading day range so they pass filters
    assume(min_days <= days_a <= max_days)
    assume(min_days <= days_b <= max_days)

    # Verify A is strictly closer to midpoint
    assume(abs(days_a - midpoint) < abs(days_b - midpoint))

    selector = _make_selector(min_days=min_days, max_days=max_days)
    spread = 2.0
    df = _build_pair_for_monotonicity(
        underlying_price, option_type, expiry,
        spread_a=spread, bid_volume_a=bid_volume, strike_offset_a=strike_offset, days_a=days_a,
        spread_b=spread, bid_volume_b=bid_volume, strike_offset_b=strike_offset, days_b=days_b,
    )
    assume(not df.empty)
    assume(len(df) == 2)

    scores = selector.score_candidates(
        contracts=df,
        option_type=option_type,
        underlying_price=underlying_price,
    )

    assume(len(scores) == 2)

    score_map = {s.option_contract.vt_symbol: s for s in scores}
    prefix = "C" if option_type == "call" else "P"
    sa = score_map.get(f"OPT-{prefix}-A.TEST")
    sb = score_map.get(f"OPT-{prefix}-B.TEST")
    assume(sa is not None and sb is not None)

    assert sa.expiry_score > sb.expiry_score, (
        f"Expiry monotonicity violated: A(days={days_a}, dev={abs(days_a - midpoint):.1f}) "
        f"score={sa.expiry_score:.6f} should be > "
        f"B(days={days_b}, dev={abs(days_b - midpoint):.1f}) score={sb.expiry_score:.6f} "
        f"(midpoint={midpoint}, half_range={half_range})"
    )


# ---------------------------------------------------------------------------
# Property 12: 评分完整性与排序
# Feature: selection-service-enhancement, Property 12: 评分完整性与排序
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    underlying_price=_underlying_price,
    num_strikes=_num_otm_strikes,
    strike_step=_strike_step,
    option_type=_option_type,
    expiry=_expiry,
    bid_price=_bid_price,
    bid_volume=_bid_volume,
    days_to_expiry=_days_to_expiry,
    liquidity_weight=_weight,
    otm_weight=_weight,
    expiry_weight=_weight,
)
def test_score_completeness_and_sorting(
    underlying_price, num_strikes, strike_step, option_type, expiry,
    bid_price, bid_volume, days_to_expiry,
    liquidity_weight, otm_weight, expiry_weight,
):
    """
    Property 12: 评分完整性与排序

    **Validates: Requirements 6.1, 6.5**

    For any candidate contract list and weight configuration:
    1. Each SelectionScore's total_score should equal
       liquidity_score × liquidity_weight + otm_score × otm_weight + expiry_score × expiry_weight
    2. The returned list should be sorted by total_score descending.
    """
    selector = _make_selector()
    df = _build_otm_chain(
        underlying_price, num_strikes, strike_step, option_type,
        expiry, bid_price, bid_volume, days_to_expiry,
    )
    assume(not df.empty)

    scores = selector.score_candidates(
        contracts=df,
        option_type=option_type,
        underlying_price=underlying_price,
        liquidity_weight=liquidity_weight,
        otm_weight=otm_weight,
        expiry_weight=expiry_weight,
    )

    assume(len(scores) >= 1)

    # 1. Verify total_score = weighted sum of component scores
    for s in scores:
        expected_total = (
            s.liquidity_score * liquidity_weight
            + s.otm_score * otm_weight
            + s.expiry_score * expiry_weight
        )
        assert abs(s.total_score - expected_total) < 1e-9, (
            f"Score completeness violated for {s.option_contract.vt_symbol}: "
            f"total_score={s.total_score:.9f} != "
            f"liq({s.liquidity_score:.6f})*{liquidity_weight} + "
            f"otm({s.otm_score:.6f})*{otm_weight} + "
            f"exp({s.expiry_score:.6f})*{expiry_weight} = {expected_total:.9f}"
        )

    # 2. Verify descending sort by total_score
    for i in range(len(scores) - 1):
        assert scores[i].total_score >= scores[i + 1].total_score - 1e-9, (
            f"Sort order violated: scores[{i}].total_score={scores[i].total_score:.9f} < "
            f"scores[{i + 1}].total_score={scores[i + 1].total_score:.9f}"
        )
