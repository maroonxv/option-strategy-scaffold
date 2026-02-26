"""
Property 11: PnL 已实现盈亏正确性 - 属性测试

Feature: combination-service-optimization, Property 11: PnL 已实现盈亏正确性

*For any* Combination 和 realized_pnl_map，每个 LegPnL 的 realized_pnl 应等于
realized_pnl_map 中对应 vt_symbol 的值（不存在则为 0.0），total_realized_pnl 应等于
所有 Leg 的 realized_pnl 之和。当 realized_pnl_map 为空或未提供时，所有 realized_pnl 应为 0.0。

**Validates: Requirements 7.4, 7.5, 7.6**

测试策略：
- 生成随机 Combination + realized_pnl_map，验证求和正确性
- 验证空 map / None 时所有 realized_pnl 为 0.0
- 验证部分 Leg 有 realized_pnl 时的正确映射
"""
from datetime import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.domain_service.combination.combination_pnl_calculator import (
    CombinationPnLCalculator,
)
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)

# ---------------------------------------------------------------------------
# 策略：基础构建块
# ---------------------------------------------------------------------------

_option_type = st.sampled_from(["call", "put"])
_direction = st.sampled_from(["long", "short"])
_strike_price = st.floats(
    min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False
)
_expiry_date = st.sampled_from(["20250901", "20251001", "20251101", "20251201"])
_volume = st.integers(min_value=1, max_value=100)
_open_price = st.floats(
    min_value=0.01, max_value=5000.0, allow_nan=False, allow_infinity=False
)
_current_price = st.floats(
    min_value=0.01, max_value=5000.0, allow_nan=False, allow_infinity=False
)
_multiplier = st.floats(
    min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False
)
_realized_pnl_value = st.floats(
    min_value=-100000.0, max_value=100000.0, allow_nan=False, allow_infinity=False
)


def _unique_vt_symbols(n: int):
    """生成 n 个唯一的 vt_symbol。"""
    return st.lists(
        st.from_regex(r"[a-z]{2}[0-9]{4}-[CP]-[0-9]{4}\.[A-Z]{3}", fullmatch=True),
        min_size=n,
        max_size=n,
        unique=True,
    )


def _combination_with_realized_data():
    """
    生成随机 Combination、current_prices、multiplier 和 realized_pnl_map。
    所有 Leg 都有对应的当前价格和已实现盈亏。
    """
    return st.integers(min_value=1, max_value=6).flatmap(
        lambda n: st.tuples(
            _unique_vt_symbols(n),
            st.lists(_option_type, min_size=n, max_size=n),
            st.lists(_strike_price, min_size=n, max_size=n),
            st.lists(_expiry_date, min_size=n, max_size=n),
            st.lists(_direction, min_size=n, max_size=n),
            st.lists(_volume, min_size=n, max_size=n),
            st.lists(_open_price, min_size=n, max_size=n),
            st.lists(_current_price, min_size=n, max_size=n),
            _multiplier,
            st.lists(_realized_pnl_value, min_size=n, max_size=n),
        )
    )


def _combination_with_partial_realized():
    """
    生成随机 Combination，其中部分 Leg 有 realized_pnl。
    返回额外的 include_flags 控制哪些 Leg 在 realized_pnl_map 中。
    """
    return st.integers(min_value=1, max_value=6).flatmap(
        lambda n: st.tuples(
            _unique_vt_symbols(n),
            st.lists(_option_type, min_size=n, max_size=n),
            st.lists(_strike_price, min_size=n, max_size=n),
            st.lists(_expiry_date, min_size=n, max_size=n),
            st.lists(_direction, min_size=n, max_size=n),
            st.lists(_volume, min_size=n, max_size=n),
            st.lists(_open_price, min_size=n, max_size=n),
            st.lists(_current_price, min_size=n, max_size=n),
            _multiplier,
            st.lists(_realized_pnl_value, min_size=n, max_size=n),
            st.lists(st.booleans(), min_size=n, max_size=n),
        )
    )


def _build_combination(
    symbols, opt_types, strikes, expiries, directions, volumes, open_prices
) -> Combination:
    n = len(symbols)
    legs = [
        Leg(
            vt_symbol=symbols[i],
            option_type=opt_types[i],
            strike_price=strikes[i],
            expiry_date=expiries[i],
            direction=directions[i],
            volume=volumes[i],
            open_price=open_prices[i],
        )
        for i in range(n)
    ]
    return Combination(
        combination_id="prop11-test",
        combination_type=CombinationType.CUSTOM,
        underlying_vt_symbol="underlying.EX",
        legs=legs,
        status=CombinationStatus.ACTIVE,
        create_time=datetime(2025, 1, 1),
    )


# ---------------------------------------------------------------------------
# Feature: combination-service-optimization, Property 11: PnL 已实现盈亏正确性
# ---------------------------------------------------------------------------


class TestProperty11RealizedPnL:
    """
    Property 11: PnL 已实现盈亏正确性

    *For any* Combination 和 realized_pnl_map，每个 LegPnL 的 realized_pnl 应等于
    realized_pnl_map 中对应 vt_symbol 的值（不存在则为 0.0），total_realized_pnl 应等于
    所有 Leg 的 realized_pnl 之和。当 realized_pnl_map 为空或未提供时，所有 realized_pnl 应为 0.0。

    **Validates: Requirements 7.4, 7.5, 7.6**
    """

    def setup_method(self) -> None:
        self.calculator = CombinationPnLCalculator()

    @given(data=_combination_with_realized_data())
    @settings(max_examples=100)
    def test_leg_realized_pnl_matches_map(self, data):
        """
        Feature: combination-service-optimization, Property 11: PnL 已实现盈亏正确性

        验证每个 LegPnL 的 realized_pnl 等于 realized_pnl_map 中对应值。

        **Validates: Requirements 7.4, 7.5, 7.6**
        """
        (
            symbols, opt_types, strikes, expiries, directions,
            volumes, open_prices, cur_prices, multiplier, realized_values,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, open_prices
        )
        current_prices = {symbols[i]: cur_prices[i] for i in range(len(symbols))}
        realized_map = {symbols[i]: realized_values[i] for i in range(len(symbols))}

        result = self.calculator.calculate(combo, current_prices, multiplier, realized_map)

        assert len(result.leg_details) == len(symbols)
        for i, detail in enumerate(result.leg_details):
            assert detail.realized_pnl == pytest.approx(realized_values[i], abs=1e-6)

    @given(data=_combination_with_realized_data())
    @settings(max_examples=100)
    def test_total_realized_pnl_equals_sum(self, data):
        """
        Feature: combination-service-optimization, Property 11: PnL 已实现盈亏正确性

        验证 total_realized_pnl 等于所有 Leg 的 realized_pnl 之和。

        **Validates: Requirements 7.4, 7.5, 7.6**
        """
        (
            symbols, opt_types, strikes, expiries, directions,
            volumes, open_prices, cur_prices, multiplier, realized_values,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, open_prices
        )
        current_prices = {symbols[i]: cur_prices[i] for i in range(len(symbols))}
        realized_map = {symbols[i]: realized_values[i] for i in range(len(symbols))}

        result = self.calculator.calculate(combo, current_prices, multiplier, realized_map)

        expected_total = sum(realized_values)
        assert result.total_realized_pnl == pytest.approx(expected_total, abs=1e-6)

    @given(data=_combination_with_partial_realized())
    @settings(max_examples=100)
    def test_partial_realized_pnl_defaults_to_zero(self, data):
        """
        Feature: combination-service-optimization, Property 11: PnL 已实现盈亏正确性

        验证部分 Leg 有 realized_pnl 时，不在 map 中的 Leg realized_pnl 为 0.0，
        total_realized_pnl 仍等于所有 Leg realized_pnl 之和。

        **Validates: Requirements 7.4, 7.5, 7.6**
        """
        (
            symbols, opt_types, strikes, expiries, directions,
            volumes, open_prices, cur_prices, multiplier,
            realized_values, include_flags,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, open_prices
        )
        current_prices = {symbols[i]: cur_prices[i] for i in range(len(symbols))}
        realized_map = {
            symbols[i]: realized_values[i]
            for i in range(len(symbols))
            if include_flags[i]
        }

        result = self.calculator.calculate(combo, current_prices, multiplier, realized_map)

        expected_total = 0.0
        for i, detail in enumerate(result.leg_details):
            if include_flags[i]:
                assert detail.realized_pnl == pytest.approx(realized_values[i], abs=1e-6)
                expected_total += realized_values[i]
            else:
                assert detail.realized_pnl == 0.0

        assert result.total_realized_pnl == pytest.approx(expected_total, abs=1e-6)

    @given(data=_combination_with_realized_data())
    @settings(max_examples=100)
    def test_empty_realized_map_all_zero(self, data):
        """
        Feature: combination-service-optimization, Property 11: PnL 已实现盈亏正确性

        验证 realized_pnl_map 为空时，所有 realized_pnl 为 0.0。

        **Validates: Requirements 7.4, 7.5, 7.6**
        """
        (
            symbols, opt_types, strikes, expiries, directions,
            volumes, open_prices, cur_prices, multiplier, _realized_values,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, open_prices
        )
        current_prices = {symbols[i]: cur_prices[i] for i in range(len(symbols))}

        result = self.calculator.calculate(combo, current_prices, multiplier, {})

        assert result.total_realized_pnl == 0.0
        for detail in result.leg_details:
            assert detail.realized_pnl == 0.0

    @given(data=_combination_with_realized_data())
    @settings(max_examples=100)
    def test_none_realized_map_all_zero(self, data):
        """
        Feature: combination-service-optimization, Property 11: PnL 已实现盈亏正确性

        验证 realized_pnl_map 为 None（未提供）时，所有 realized_pnl 为 0.0。

        **Validates: Requirements 7.4, 7.5, 7.6**
        """
        (
            symbols, opt_types, strikes, expiries, directions,
            volumes, open_prices, cur_prices, multiplier, _realized_values,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, open_prices
        )
        current_prices = {symbols[i]: cur_prices[i] for i in range(len(symbols))}

        result = self.calculator.calculate(combo, current_prices, multiplier, None)

        assert result.total_realized_pnl == 0.0
        for detail in result.leg_details:
            assert detail.realized_pnl == 0.0
