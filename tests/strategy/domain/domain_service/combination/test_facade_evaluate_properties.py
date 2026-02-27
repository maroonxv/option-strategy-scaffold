"""
Property 10: Facade evaluate 组合正确性 - 属性测试

Feature: combination-service-optimization, Property 10: Facade evaluate 组合正确性

*For any* 合法的 Combination、greeks_map、current_prices 和 multiplier，
CombinationFacade.evaluate() 返回的 CombinationEvaluation 中 greeks 应等于
GreeksCalculator 的结果，pnl 应等于 PnLCalculator 的结果，risk_result 应等于
RiskChecker 对计算出的 greeks 的检查结果。

**Validates: Requirements 6.2, 6.3**

测试策略：
- 生成随机 Combination + greeks_map + current_prices + multiplier
- 分别独立调用三个子服务获取预期结果
- 验证 Facade.evaluate() 返回的 CombinationEvaluation 各字段与独立调用结果一致
"""
from datetime import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.domain_service.combination.combination_facade import (
    CombinationFacade,
)
from src.strategy.domain.domain_service.combination.combination_greeks_calculator import (
    CombinationGreeksCalculator,
)
from src.strategy.domain.domain_service.combination.combination_pnl_calculator import (
    CombinationPnLCalculator,
)
from src.strategy.domain.domain_service.combination.combination_risk_checker import (
    CombinationRiskChecker,
)
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationRiskConfig,
    CombinationStatus,
    CombinationType,
    Leg,
)
from src.strategy.domain.value_object.pricing.greeks import GreeksResult


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
_multiplier = st.floats(
    min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False
)
_greek_value = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False
)
_current_price = st.floats(
    min_value=0.01, max_value=5000.0, allow_nan=False, allow_infinity=False
)
_realized_pnl_value = st.floats(
    min_value=-10000.0, max_value=10000.0, allow_nan=False, allow_infinity=False
)
_risk_limit = st.floats(
    min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False
)


def _unique_vt_symbols(n: int):
    """生成 n 个唯一的 vt_symbol。"""
    return st.lists(
        st.from_regex(r"[a-z]{2}[0-9]{4}-[CP]-[0-9]{4}\.[A-Z]{3}", fullmatch=True),
        min_size=n,
        max_size=n,
        unique=True,
    )


def _facade_evaluate_data():
    """
    生成 Facade.evaluate 所需的完整输入数据：
    Combination, greeks_map, current_prices, multiplier, realized_pnl_map, risk_config
    """
    return st.integers(min_value=1, max_value=5).flatmap(
        lambda n: st.tuples(
            _unique_vt_symbols(n),
            st.lists(_option_type, min_size=n, max_size=n),
            st.lists(_strike_price, min_size=n, max_size=n),
            st.lists(_expiry_date, min_size=n, max_size=n),
            st.lists(_direction, min_size=n, max_size=n),
            st.lists(_volume, min_size=n, max_size=n),
            st.lists(_open_price, min_size=n, max_size=n),
            # Greeks for each leg: (delta, gamma, theta, vega)
            st.lists(
                st.tuples(_greek_value, _greek_value, _greek_value, _greek_value),
                min_size=n,
                max_size=n,
            ),
            # Current prices for each leg
            st.lists(_current_price, min_size=n, max_size=n),
            _multiplier,
            # Realized PnL for each leg
            st.lists(_realized_pnl_value, min_size=n, max_size=n),
            # Risk config limits
            st.tuples(_risk_limit, _risk_limit, _risk_limit, _risk_limit),
        )
    )


def _build_combination(vt_symbols, option_types, strikes, expiries, directions, volumes, open_prices):
    """构建 Combination 实体。"""
    legs = [
        Leg(
            vt_symbol=sym,
            option_type=ot,
            strike_price=sp,
            expiry_date=exp,
            direction=d,
            volume=v,
            open_price=op,
        )
        for sym, ot, sp, exp, d, v, op in zip(
            vt_symbols, option_types, strikes, expiries, directions, volumes, open_prices
        )
    ]
    return Combination(
        combination_id="test-facade-prop",
        combination_type=CombinationType.CUSTOM,
        underlying_vt_symbol="TEST.UNDERLYING",
        legs=legs,
        status=CombinationStatus.ACTIVE,
        create_time=datetime(2025, 1, 1),
    )


def _build_greeks_map(vt_symbols, greeks_tuples):
    """构建 greeks_map。"""
    return {
        sym: GreeksResult(delta=g[0], gamma=g[1], theta=g[2], vega=g[3])
        for sym, g in zip(vt_symbols, greeks_tuples)
    }


def _build_current_prices(vt_symbols, prices):
    """构建 current_prices。"""
    return {sym: p for sym, p in zip(vt_symbols, prices)}


def _build_realized_pnl_map(vt_symbols, realized_values):
    """构建 realized_pnl_map。"""
    return {sym: r for sym, r in zip(vt_symbols, realized_values)}


class TestProperty10FacadeEvaluateComposition:
    """
    Feature: combination-service-optimization, Property 10: Facade evaluate 组合正确性

    **Validates: Requirements 6.2, 6.3**
    """

    @given(data=_facade_evaluate_data())
    @settings(max_examples=100)
    def test_evaluate_greeks_equals_calculator_result(self, data):
        """Facade.evaluate() 返回的 greeks 应等于 GreeksCalculator 独立计算的结果。"""
        (
            vt_symbols, option_types, strikes, expiries, directions,
            volumes, open_prices, greeks_tuples, prices, multiplier,
            realized_values, risk_limits,
        ) = data

        combination = _build_combination(
            vt_symbols, option_types, strikes, expiries, directions, volumes, open_prices
        )
        greeks_map = _build_greeks_map(vt_symbols, greeks_tuples)
        current_prices = _build_current_prices(vt_symbols, prices)
        realized_pnl_map = _build_realized_pnl_map(vt_symbols, realized_values)

        config = CombinationRiskConfig(
            delta_limit=risk_limits[0],
            gamma_limit=risk_limits[1],
            vega_limit=risk_limits[2],
            theta_limit=risk_limits[3],
        )

        greeks_calculator = CombinationGreeksCalculator()
        pnl_calculator = CombinationPnLCalculator()
        risk_checker = CombinationRiskChecker(config)

        facade = CombinationFacade(greeks_calculator, pnl_calculator, risk_checker)
        result = facade.evaluate(
            combination, greeks_map, current_prices, multiplier, realized_pnl_map
        )

        expected_greeks = greeks_calculator.calculate(combination, greeks_map, multiplier)

        assert result.greeks.delta == expected_greeks.delta
        assert result.greeks.gamma == expected_greeks.gamma
        assert result.greeks.theta == expected_greeks.theta
        assert result.greeks.vega == expected_greeks.vega
        assert result.greeks.failed_legs == expected_greeks.failed_legs

    @given(data=_facade_evaluate_data())
    @settings(max_examples=100)
    def test_evaluate_pnl_equals_calculator_result(self, data):
        """Facade.evaluate() 返回的 pnl 应等于 PnLCalculator 独立计算的结果。"""
        (
            vt_symbols, option_types, strikes, expiries, directions,
            volumes, open_prices, greeks_tuples, prices, multiplier,
            realized_values, risk_limits,
        ) = data

        combination = _build_combination(
            vt_symbols, option_types, strikes, expiries, directions, volumes, open_prices
        )
        greeks_map = _build_greeks_map(vt_symbols, greeks_tuples)
        current_prices = _build_current_prices(vt_symbols, prices)
        realized_pnl_map = _build_realized_pnl_map(vt_symbols, realized_values)

        config = CombinationRiskConfig(
            delta_limit=risk_limits[0],
            gamma_limit=risk_limits[1],
            vega_limit=risk_limits[2],
            theta_limit=risk_limits[3],
        )

        greeks_calculator = CombinationGreeksCalculator()
        pnl_calculator = CombinationPnLCalculator()
        risk_checker = CombinationRiskChecker(config)

        facade = CombinationFacade(greeks_calculator, pnl_calculator, risk_checker)
        result = facade.evaluate(
            combination, greeks_map, current_prices, multiplier, realized_pnl_map
        )

        expected_pnl = pnl_calculator.calculate(
            combination, current_prices, multiplier, realized_pnl_map
        )

        assert result.pnl.total_unrealized_pnl == expected_pnl.total_unrealized_pnl
        assert result.pnl.total_realized_pnl == expected_pnl.total_realized_pnl
        assert len(result.pnl.leg_details) == len(expected_pnl.leg_details)
        for actual_leg, expected_leg in zip(result.pnl.leg_details, expected_pnl.leg_details):
            assert actual_leg.vt_symbol == expected_leg.vt_symbol
            assert actual_leg.unrealized_pnl == expected_leg.unrealized_pnl
            assert actual_leg.realized_pnl == expected_leg.realized_pnl
            assert actual_leg.price_available == expected_leg.price_available

    @given(data=_facade_evaluate_data())
    @settings(max_examples=100)
    def test_evaluate_risk_result_equals_checker_result(self, data):
        """Facade.evaluate() 返回的 risk_result 应等于 RiskChecker 对 greeks 的检查结果。"""
        (
            vt_symbols, option_types, strikes, expiries, directions,
            volumes, open_prices, greeks_tuples, prices, multiplier,
            realized_values, risk_limits,
        ) = data

        combination = _build_combination(
            vt_symbols, option_types, strikes, expiries, directions, volumes, open_prices
        )
        greeks_map = _build_greeks_map(vt_symbols, greeks_tuples)
        current_prices = _build_current_prices(vt_symbols, prices)
        realized_pnl_map = _build_realized_pnl_map(vt_symbols, realized_values)

        config = CombinationRiskConfig(
            delta_limit=risk_limits[0],
            gamma_limit=risk_limits[1],
            vega_limit=risk_limits[2],
            theta_limit=risk_limits[3],
        )

        greeks_calculator = CombinationGreeksCalculator()
        pnl_calculator = CombinationPnLCalculator()
        risk_checker = CombinationRiskChecker(config)

        facade = CombinationFacade(greeks_calculator, pnl_calculator, risk_checker)
        result = facade.evaluate(
            combination, greeks_map, current_prices, multiplier, realized_pnl_map
        )

        # Risk check should be based on the greeks computed by the facade
        expected_greeks = greeks_calculator.calculate(combination, greeks_map, multiplier)
        expected_risk = risk_checker.check(expected_greeks)

        assert result.risk_result.passed == expected_risk.passed
        assert result.risk_result.reject_reason == expected_risk.reject_reason
