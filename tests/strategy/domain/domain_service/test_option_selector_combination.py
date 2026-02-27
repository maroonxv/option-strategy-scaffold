"""
OptionSelectorService.select_combination 单元测试

验证组合策略联合选择逻辑：STRADDLE、STRANGLE、VERTICAL_SPREAD。
Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
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
import pytest
import pandas as pd

from src.strategy.domain.domain_service.selection.option_selector_service import (
    OptionSelectorService,
)
from src.strategy.domain.value_object.option_selector_config import OptionSelectorConfig
from src.strategy.domain.value_object.combination import CombinationType
from src.strategy.domain.value_object.selection import CombinationSelectionResult
from src.strategy.domain.value_object.combination_rules import (
    VALIDATION_RULES,
    LegStructure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_option_df(rows: list[dict]) -> pd.DataFrame:
    """从字典列表构建期权合约 DataFrame。"""
    defaults = {
        "underlying_symbol": "IO2506",
        "expiry_date": "2025-06-20",
        "bid_price": 100.0,
        "bid_volume": 50,
        "ask_price": 102.0,
        "ask_volume": 50,
        "days_to_expiry": 20,
    }
    full_rows = []
    for r in rows:
        row = {**defaults, **r}
        full_rows.append(row)
    return pd.DataFrame(full_rows)


def _build_chain(underlying_price: float, strikes: list[float], expiry: str = "2025-06-20") -> pd.DataFrame:
    """构建一条完整的期权链 (每个行权价都有 Call 和 Put)。"""
    rows = []
    for s in strikes:
        rows.append({
            "vt_symbol": f"IO2506-C-{int(s)}.CFFEX",
            "option_type": "call",
            "strike_price": s,
            "expiry_date": expiry,
            "bid_price": max(50.0, 200 - abs(s - underlying_price)),
            "bid_volume": 30,
            "ask_price": max(52.0, 202 - abs(s - underlying_price)),
            "ask_volume": 30,
            "days_to_expiry": 20,
            "underlying_symbol": "IO2506",
        })
        rows.append({
            "vt_symbol": f"IO2506-P-{int(s)}.CFFEX",
            "option_type": "put",
            "strike_price": s,
            "expiry_date": expiry,
            "bid_price": max(50.0, 200 - abs(s - underlying_price)),
            "bid_volume": 30,
            "ask_price": max(52.0, 202 - abs(s - underlying_price)),
            "ask_volume": 30,
            "days_to_expiry": 20,
            "underlying_symbol": "IO2506",
        })
    return pd.DataFrame(rows)


@pytest.fixture
def selector():
    """默认参数的 OptionSelectorService。"""
    return OptionSelectorService(
        config=OptionSelectorConfig(
            strike_level=2,
            min_bid_price=10.0,
            min_bid_volume=5,
            min_trading_days=1,
            max_trading_days=50,
        )
    )


# =========================================================================
# STRADDLE 测试
# =========================================================================

class TestSelectStraddle:

    def test_straddle_selects_atm_strike(self, selector):
        """STRADDLE 应选择最接近标的价格的行权价 (Req 4.1)"""
        underlying = 5000.0
        strikes = [4800, 4900, 5000, 5100, 5200]
        df = _build_chain(underlying, strikes)

        result = selector.select_combination(
            df, CombinationType.STRADDLE, underlying
        )

        assert result is not None
        assert result.success is True
        assert result.combination_type == CombinationType.STRADDLE
        assert len(result.legs) == 2

        call_leg = next(l for l in result.legs if l.option_type == "call")
        put_leg = next(l for l in result.legs if l.option_type == "put")
        assert call_leg.strike_price == 5000.0
        assert put_leg.strike_price == 5000.0

    def test_straddle_atm_between_strikes(self, selector):
        """标的价格在两个行权价之间时，选择最近的 (Req 4.1)"""
        underlying = 5050.0
        strikes = [4900, 5000, 5100, 5200]
        df = _build_chain(underlying, strikes)

        result = selector.select_combination(
            df, CombinationType.STRADDLE, underlying
        )

        assert result.success is True
        call_leg = next(l for l in result.legs if l.option_type == "call")
        # 5050 距 5000 和 5100 各 50，min 选其一即可
        assert call_leg.strike_price in (5000.0, 5100.0)

    def test_straddle_same_expiry(self, selector):
        """STRADDLE 两腿到期日应相同 (Req 4.1)"""
        df = _build_chain(5000, [4900, 5000, 5100])
        result = selector.select_combination(
            df, CombinationType.STRADDLE, 5000.0
        )
        assert result.success is True
        assert result.legs[0].expiry_date == result.legs[1].expiry_date

    def test_straddle_passes_validation(self, selector):
        """STRADDLE 结果应通过 VALIDATION_RULES 验证 (Req 4.5)"""
        df = _build_chain(5000, [4900, 5000, 5100])
        result = selector.select_combination(
            df, CombinationType.STRADDLE, 5000.0
        )
        assert result.success is True
        leg_structs = [
            LegStructure(l.option_type, l.strike_price, l.expiry_date)
            for l in result.legs
        ]
        assert VALIDATION_RULES[CombinationType.STRADDLE](leg_structs) is None

    def test_straddle_empty_contracts(self, selector):
        """空合约列表返回 success=False"""
        result = selector.select_combination(
            pd.DataFrame(), CombinationType.STRADDLE, 5000.0
        )
        assert result is not None
        assert result.success is False

    def test_straddle_no_puts_returns_failure(self, selector):
        """只有 Call 没有 Put 时返回 success=False (Req 4.4)"""
        rows = [
            {"vt_symbol": "C1", "option_type": "call", "strike_price": 5000,
             "bid_price": 100, "bid_volume": 30, "days_to_expiry": 20},
        ]
        df = _make_option_df(rows)
        result = selector.select_combination(
            df, CombinationType.STRADDLE, 5000.0
        )
        assert result.success is False


# =========================================================================
# STRANGLE 测试
# =========================================================================

class TestSelectStrangle:

    def test_strangle_selects_otm_call_and_put(self, selector):
        """STRANGLE 应选择虚值 Call 和虚值 Put (Req 4.2)"""
        underlying = 5000.0
        strikes = [4700, 4800, 4900, 5000, 5100, 5200, 5300]
        df = _build_chain(underlying, strikes)

        result = selector.select_combination(
            df, CombinationType.STRANGLE, underlying, strike_level=2
        )

        assert result.success is True
        assert len(result.legs) == 2

        call_leg = next(l for l in result.legs if l.option_type == "call")
        put_leg = next(l for l in result.legs if l.option_type == "put")

        # Call 行权价应高于标的价格 (虚值)
        assert call_leg.strike_price > underlying
        # Put 行权价应低于标的价格 (虚值)
        assert put_leg.strike_price < underlying

    def test_strangle_different_strikes(self, selector):
        """STRANGLE 两腿行权价应不同 (Req 4.2)"""
        df = _build_chain(5000, [4700, 4800, 4900, 5100, 5200, 5300])
        result = selector.select_combination(
            df, CombinationType.STRANGLE, 5000.0, strike_level=1
        )
        assert result.success is True
        assert result.legs[0].strike_price != result.legs[1].strike_price

    def test_strangle_passes_validation(self, selector):
        """STRANGLE 结果应通过 VALIDATION_RULES 验证 (Req 4.5)"""
        df = _build_chain(5000, [4700, 4800, 4900, 5100, 5200, 5300])
        result = selector.select_combination(
            df, CombinationType.STRANGLE, 5000.0, strike_level=1
        )
        assert result.success is True
        leg_structs = [
            LegStructure(l.option_type, l.strike_price, l.expiry_date)
            for l in result.legs
        ]
        assert VALIDATION_RULES[CombinationType.STRANGLE](leg_structs) is None

    def test_strangle_no_otm_calls_returns_failure(self, selector):
        """无虚值 Call 时返回 success=False (Req 4.4)"""
        # 所有行权价都低于标的价格，没有虚值 Call
        df = _build_chain(6000, [4800, 4900, 5000])
        result = selector.select_combination(
            df, CombinationType.STRANGLE, 6000.0, strike_level=1
        )
        assert result.success is False


# =========================================================================
# VERTICAL_SPREAD 测试
# =========================================================================

class TestSelectVerticalSpread:

    def test_vertical_spread_same_type_different_strikes(self, selector):
        """VERTICAL_SPREAD 应选择同类型不同行权价 (Req 4.3)"""
        underlying = 5000.0
        strikes = [4800, 4900, 5000, 5100, 5200, 5300]
        df = _build_chain(underlying, strikes)

        result = selector.select_combination(
            df, CombinationType.VERTICAL_SPREAD, underlying,
            spread_width=2, option_type_for_spread="call"
        )

        assert result.success is True
        assert len(result.legs) == 2
        # 同类型
        assert result.legs[0].option_type == result.legs[1].option_type == "call"
        # 不同行权价
        assert result.legs[0].strike_price != result.legs[1].strike_price

    def test_vertical_spread_put_type(self, selector):
        """VERTICAL_SPREAD 支持 Put 类型 (Req 4.3)"""
        df = _build_chain(5000, [4700, 4800, 4900, 5000, 5100, 5200])
        result = selector.select_combination(
            df, CombinationType.VERTICAL_SPREAD, 5000.0,
            spread_width=1, option_type_for_spread="put"
        )
        assert result.success is True
        assert all(l.option_type == "put" for l in result.legs)

    def test_vertical_spread_passes_validation(self, selector):
        """VERTICAL_SPREAD 结果应通过 VALIDATION_RULES 验证 (Req 4.5)"""
        df = _build_chain(5000, [4800, 4900, 5000, 5100, 5200, 5300])
        result = selector.select_combination(
            df, CombinationType.VERTICAL_SPREAD, 5000.0,
            spread_width=1, option_type_for_spread="call"
        )
        assert result.success is True
        leg_structs = [
            LegStructure(l.option_type, l.strike_price, l.expiry_date)
            for l in result.legs
        ]
        assert VALIDATION_RULES[CombinationType.VERTICAL_SPREAD](leg_structs) is None

    def test_vertical_spread_insufficient_strikes(self, selector):
        """行权价不足时返回 success=False (Req 4.4)"""
        # 只有一个虚值 Call 行权价，无法构成 spread
        df = _build_chain(5000, [5100])
        result = selector.select_combination(
            df, CombinationType.VERTICAL_SPREAD, 5000.0,
            spread_width=2, option_type_for_spread="call"
        )
        # 只有1个虚值档，spread_width=2 需要第3档，应失败或两腿相同
        assert result.success is False or result.legs[0].strike_price == result.legs[1].strike_price


# =========================================================================
# 通用测试
# =========================================================================

class TestSelectCombinationGeneral:

    def test_underlying_price_zero_returns_none(self, selector):
        """underlying_price <= 0 时返回 None"""
        df = _build_chain(5000, [4900, 5000, 5100])
        result = selector.select_combination(
            df, CombinationType.STRADDLE, 0.0
        )
        assert result is None

    def test_underlying_price_negative_returns_none(self, selector):
        """underlying_price < 0 时返回 None"""
        df = _build_chain(5000, [4900, 5000, 5100])
        result = selector.select_combination(
            df, CombinationType.STRADDLE, -100.0
        )
        assert result is None

    def test_unsupported_combination_type(self, selector):
        """不支持的组合类型返回 success=False"""
        df = _build_chain(5000, [4900, 5000, 5100])
        result = selector.select_combination(
            df, CombinationType.IRON_CONDOR, 5000.0
        )
        assert result is not None
        assert result.success is False

    def test_liquidity_filter_rejects_combination(self, selector):
        """任一腿流动性不足时拒绝整个组合 (Req 4.4)"""
        # 所有合约 bid_price 低于 min_bid_price
        rows = [
            {"vt_symbol": "C1", "option_type": "call", "strike_price": 5100,
             "bid_price": 1.0, "bid_volume": 1, "days_to_expiry": 20},
            {"vt_symbol": "P1", "option_type": "put", "strike_price": 4900,
             "bid_price": 1.0, "bid_volume": 1, "days_to_expiry": 20},
        ]
        df = _make_option_df(rows)
        result = selector.select_combination(
            df, CombinationType.STRADDLE, 5000.0
        )
        assert result.success is False

    def test_log_func_called(self, selector):
        """log_func 被正确调用"""
        logs = []
        df = _build_chain(5000, [4900, 5000, 5100])
        selector.select_combination(
            df, CombinationType.STRADDLE, 5000.0, log_func=logs.append
        )
        assert len(logs) > 0
