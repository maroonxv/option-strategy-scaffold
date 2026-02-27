"""
CombinationRecognizer 属性测试

Feature: combination-strategy-management, Property 2: 组合类型识别

**Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**
"""
from datetime import datetime

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.domain_service.combination.combination_recognizer import (
    CombinationRecognizer,
)
from src.strategy.domain.entity.position import Position
from src.strategy.domain.value_object.combination import CombinationType
from src.strategy.domain.value_object.market.option_contract import OptionContract

# ---------------------------------------------------------------------------
# 基础策略
# ---------------------------------------------------------------------------

_underlying = st.sampled_from(["m2509.DCE", "cu2506.SHFE", "i2509.DCE", "SR509.CZCE"])
_expiry = st.sampled_from(["20250901", "20251001", "20251101", "20251201"])
_strike = st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
_direction = st.sampled_from(["long", "short"])
_volume = st.integers(min_value=1, max_value=100)
_price = st.floats(min_value=0.01, max_value=5000.0, allow_nan=False, allow_infinity=False)
_days = st.integers(min_value=1, max_value=365)

_recognizer = CombinationRecognizer()


def _make_position(vt_symbol: str, underlying: str, direction: str = "short") -> Position:
    """创建一个最小化的 Position 实例。"""
    return Position(
        vt_symbol=vt_symbol,
        underlying_vt_symbol=underlying,
        signal="test",
        volume=1,
        target_volume=1,
        direction=direction,
    )


def _make_contract(
    vt_symbol: str,
    underlying: str,
    option_type: str,
    strike_price: float,
    expiry_date: str,
) -> OptionContract:
    """创建一个最小化的 OptionContract 实例。"""
    return OptionContract(
        vt_symbol=vt_symbol,
        underlying_symbol=underlying,
        option_type=option_type,
        strike_price=strike_price,
        expiry_date=expiry_date,
        diff1=0.0,
        bid_price=1.0,
        bid_volume=10,
        ask_price=1.5,
        ask_volume=10,
        days_to_expiry=30,
    )


# ---------------------------------------------------------------------------
# 生成器：为每种组合类型生成有效的 (positions, contracts) 对
# ---------------------------------------------------------------------------


@st.composite
def straddle_inputs(draw):
    """
    STRADDLE: 2 positions, 同标的, 同到期日, 同行权价, 一 Call 一 Put
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)
    strike = draw(_strike)
    dir1 = draw(_direction)
    dir2 = draw(_direction)

    sym_c = f"{underlying}-C-{strike}-{expiry}"
    sym_p = f"{underlying}-P-{strike}-{expiry}"

    positions = [
        _make_position(sym_c, underlying, dir1),
        _make_position(sym_p, underlying, dir2),
    ]
    contracts = {
        sym_c: _make_contract(sym_c, underlying, "call", strike, expiry),
        sym_p: _make_contract(sym_p, underlying, "put", strike, expiry),
    }
    return positions, contracts


@st.composite
def strangle_inputs(draw):
    """
    STRANGLE: 2 positions, 同标的, 同到期日, 不同行权价, 一 Call 一 Put
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)
    strike1 = draw(_strike)
    strike2 = draw(_strike)
    assume(strike1 != strike2)
    dir1 = draw(_direction)
    dir2 = draw(_direction)

    sym_c = f"{underlying}-C-{strike1}-{expiry}"
    sym_p = f"{underlying}-P-{strike2}-{expiry}"

    positions = [
        _make_position(sym_c, underlying, dir1),
        _make_position(sym_p, underlying, dir2),
    ]
    contracts = {
        sym_c: _make_contract(sym_c, underlying, "call", strike1, expiry),
        sym_p: _make_contract(sym_p, underlying, "put", strike2, expiry),
    }
    return positions, contracts


@st.composite
def vertical_spread_inputs(draw):
    """
    VERTICAL_SPREAD: 2 positions, 同标的, 同到期日, 同期权类型, 不同行权价
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)
    opt_type = draw(st.sampled_from(["call", "put"]))
    strike1 = draw(_strike)
    strike2 = draw(_strike)
    assume(strike1 != strike2)
    dir1 = draw(_direction)
    dir2 = draw(_direction)

    sym1 = f"{underlying}-{opt_type}-{strike1}-{expiry}"
    sym2 = f"{underlying}-{opt_type}-{strike2}-{expiry}"

    positions = [
        _make_position(sym1, underlying, dir1),
        _make_position(sym2, underlying, dir2),
    ]
    contracts = {
        sym1: _make_contract(sym1, underlying, opt_type, strike1, expiry),
        sym2: _make_contract(sym2, underlying, opt_type, strike2, expiry),
    }
    return positions, contracts


@st.composite
def calendar_spread_inputs(draw):
    """
    CALENDAR_SPREAD: 2 positions, 同标的, 不同到期日, 同行权价, 同期权类型
    """
    underlying = draw(_underlying)
    expiry1 = draw(_expiry)
    expiry2 = draw(_expiry)
    assume(expiry1 != expiry2)
    opt_type = draw(st.sampled_from(["call", "put"]))
    strike = draw(_strike)
    dir1 = draw(_direction)
    dir2 = draw(_direction)

    sym1 = f"{underlying}-{opt_type}-{strike}-{expiry1}"
    sym2 = f"{underlying}-{opt_type}-{strike}-{expiry2}"

    positions = [
        _make_position(sym1, underlying, dir1),
        _make_position(sym2, underlying, dir2),
    ]
    contracts = {
        sym1: _make_contract(sym1, underlying, opt_type, strike, expiry1),
        sym2: _make_contract(sym2, underlying, opt_type, strike, expiry2),
    }
    return positions, contracts


@st.composite
def iron_condor_inputs(draw):
    """
    IRON_CONDOR: 4 positions, 同标的, 同到期日,
    2 Puts 不同行权价 + 2 Calls 不同行权价
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)

    put_strike1 = draw(_strike)
    put_strike2 = draw(_strike)
    assume(put_strike1 != put_strike2)

    call_strike1 = draw(_strike)
    call_strike2 = draw(_strike)
    assume(call_strike1 != call_strike2)

    sym_p1 = f"{underlying}-P-{put_strike1}-{expiry}"
    sym_p2 = f"{underlying}-P-{put_strike2}-{expiry}"
    sym_c1 = f"{underlying}-C-{call_strike1}-{expiry}"
    sym_c2 = f"{underlying}-C-{call_strike2}-{expiry}"

    positions = [
        _make_position(sym_p1, underlying, draw(_direction)),
        _make_position(sym_p2, underlying, draw(_direction)),
        _make_position(sym_c1, underlying, draw(_direction)),
        _make_position(sym_c2, underlying, draw(_direction)),
    ]
    contracts = {
        sym_p1: _make_contract(sym_p1, underlying, "put", put_strike1, expiry),
        sym_p2: _make_contract(sym_p2, underlying, "put", put_strike2, expiry),
        sym_c1: _make_contract(sym_c1, underlying, "call", call_strike1, expiry),
        sym_c2: _make_contract(sym_c2, underlying, "call", call_strike2, expiry),
    }
    return positions, contracts


@st.composite
def custom_inputs(draw):
    """
    生成不匹配任何预定义类型的持仓结构。
    策略：生成 3 个持仓（不是 2 也不是 4），保证不匹配任何类型。
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)
    n = draw(st.sampled_from([1, 3, 5, 6]))

    positions = []
    contracts = {}
    for i in range(n):
        opt_type = draw(st.sampled_from(["call", "put"]))
        strike = draw(_strike)
        sym = f"{underlying}-{opt_type}-{strike}-{expiry}-{i}"
        positions.append(_make_position(sym, underlying, draw(_direction)))
        contracts[sym] = _make_contract(sym, underlying, opt_type, strike, expiry)

    return positions, contracts


# ---------------------------------------------------------------------------
# Property 2: 组合类型识别
# ---------------------------------------------------------------------------


class TestProperty2CombinationTypeRecognition:
    """
    Feature: combination-strategy-management, Property 2: 组合类型识别

    **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

    For any 一组 Position 和对应的 OptionContract，当持仓结构满足某个预定义
    组合类型的特征时，CombinationRecognizer 应返回该类型；当不满足任何预定义
    类型时，应返回 CUSTOM。
    """

    # --- Req 2.2: STRADDLE 识别 ---

    @given(data=straddle_inputs())
    @settings(max_examples=100)
    def test_straddle_recognized(self, data):
        """
        STRADDLE: 2 positions, 同标的, 同到期日, 同行权价, 一 Call 一 Put
        → 应识别为 STRADDLE

        **Validates: Requirements 2.2**
        """
        positions, contracts = data
        result = _recognizer.recognize(positions, contracts)
        assert result == CombinationType.STRADDLE

    # --- Req 2.3: STRANGLE 识别 ---

    @given(data=strangle_inputs())
    @settings(max_examples=100)
    def test_strangle_recognized(self, data):
        """
        STRANGLE: 2 positions, 同标的, 同到期日, 不同行权价, 一 Call 一 Put
        → 应识别为 STRANGLE

        **Validates: Requirements 2.3**
        """
        positions, contracts = data
        result = _recognizer.recognize(positions, contracts)
        assert result == CombinationType.STRANGLE

    # --- Req 2.4: VERTICAL_SPREAD 识别 ---

    @given(data=vertical_spread_inputs())
    @settings(max_examples=100)
    def test_vertical_spread_recognized(self, data):
        """
        VERTICAL_SPREAD: 2 positions, 同标的, 同到期日, 同期权类型, 不同行权价
        → 应识别为 VERTICAL_SPREAD

        **Validates: Requirements 2.4**
        """
        positions, contracts = data
        result = _recognizer.recognize(positions, contracts)
        assert result == CombinationType.VERTICAL_SPREAD

    # --- Req 2.5: CALENDAR_SPREAD 识别 ---

    @given(data=calendar_spread_inputs())
    @settings(max_examples=100)
    def test_calendar_spread_recognized(self, data):
        """
        CALENDAR_SPREAD: 2 positions, 同标的, 不同到期日, 同行权价, 同期权类型
        → 应识别为 CALENDAR_SPREAD

        **Validates: Requirements 2.5**
        """
        positions, contracts = data
        result = _recognizer.recognize(positions, contracts)
        assert result == CombinationType.CALENDAR_SPREAD

    # --- Req 2.6: IRON_CONDOR 识别 ---

    @given(data=iron_condor_inputs())
    @settings(max_examples=100)
    def test_iron_condor_recognized(self, data):
        """
        IRON_CONDOR: 4 positions, 同标的, 同到期日,
        2 Puts 不同行权价 + 2 Calls 不同行权价
        → 应识别为 IRON_CONDOR

        **Validates: Requirements 2.6**
        """
        positions, contracts = data
        result = _recognizer.recognize(positions, contracts)
        assert result == CombinationType.IRON_CONDOR

    # --- Req 2.7: 不匹配时返回 CUSTOM ---

    @given(data=custom_inputs())
    @settings(max_examples=100)
    def test_non_matching_returns_custom(self, data):
        """
        当持仓数量不是 2 或 4（即 1, 3, 5, 6）时，不匹配任何预定义类型，
        应返回 CUSTOM。

        **Validates: Requirements 2.7**
        """
        positions, contracts = data
        result = _recognizer.recognize(positions, contracts)
        assert result == CombinationType.CUSTOM

    # --- Req 2.7: 空持仓返回 CUSTOM ---

    @given(data=st.just(([], {})))
    @settings(max_examples=10)
    def test_empty_positions_returns_custom(self, data):
        """
        空持仓列表应返回 CUSTOM。

        **Validates: Requirements 2.7**
        """
        positions, contracts = data
        result = _recognizer.recognize(positions, contracts)
        assert result == CombinationType.CUSTOM

    # --- Req 2.7: 缺少合约信息时返回 CUSTOM ---

    @given(data=straddle_inputs())
    @settings(max_examples=100)
    def test_missing_contract_returns_custom(self, data):
        """
        当 contracts 字典中缺少某个 Position 的合约信息时，
        无法匹配任何类型，应返回 CUSTOM。

        **Validates: Requirements 2.7**
        """
        positions, contracts = data
        # 移除第一个合约
        first_key = next(iter(contracts))
        incomplete_contracts = {k: v for k, v in contracts.items() if k != first_key}
        result = _recognizer.recognize(positions, incomplete_contracts)
        assert result == CombinationType.CUSTOM
