"""
CombinationGreeksCalculator 单元测试

测试组合级 Greeks 加权求和逻辑，包括：
- 正常加权计算（long/short 方向）
- 某个 Leg 的 GreeksResult.success 为 False 时记入 failed_legs
- greeks_map 中缺少某个 Leg 时记入 failed_legs
- 空 Leg 列表返回零值
"""
from datetime import datetime

from src.strategy.domain.domain_service.combination.combination_greeks_calculator import (
    CombinationGreeksCalculator,
)
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)
from src.strategy.domain.value_object.pricing.greeks import GreeksResult


def _make_combination(legs: list[Leg]) -> Combination:
    """创建 CUSTOM 类型组合（无结构约束）用于测试。"""
    return Combination(
        combination_id="test-combo-1",
        combination_type=CombinationType.CUSTOM,
        underlying_vt_symbol="m2509.DCE",
        legs=legs,
        status=CombinationStatus.ACTIVE,
        create_time=datetime(2025, 1, 15, 10, 30),
    )


class TestCombinationGreeksCalculator:
    """CombinationGreeksCalculator 测试"""

    def setup_method(self) -> None:
        self.calculator = CombinationGreeksCalculator()

    def test_single_long_leg(self) -> None:
        """单个 long 腿：greek × volume × multiplier × (+1)"""
        legs = [
            Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 2, 120.0)
        ]
        combo = _make_combination(legs)
        greeks_map = {
            "m2509-C-2800.DCE": GreeksResult(delta=0.5, gamma=0.02, theta=-0.1, vega=15.0)
        }
        result = self.calculator.calculate(combo, greeks_map, multiplier=10.0)

        # weight = 2 * 10.0 * 1.0 = 20.0
        assert result.delta == 0.5 * 20.0
        assert result.gamma == 0.02 * 20.0
        assert result.theta == -0.1 * 20.0
        assert result.vega == 15.0 * 20.0
        assert result.failed_legs == []

    def test_single_short_leg(self) -> None:
        """单个 short 腿：greek × volume × multiplier × (-1)"""
        legs = [
            Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 3, 95.0)
        ]
        combo = _make_combination(legs)
        greeks_map = {
            "m2509-P-2800.DCE": GreeksResult(delta=-0.4, gamma=0.03, theta=-0.05, vega=12.0)
        }
        result = self.calculator.calculate(combo, greeks_map, multiplier=10.0)

        # weight = 3 * 10.0 * (-1.0) = -30.0
        assert result.delta == -0.4 * -30.0
        assert result.gamma == 0.03 * -30.0
        assert result.theta == -0.05 * -30.0
        assert result.vega == 12.0 * -30.0
        assert result.failed_legs == []

    def test_multi_leg_aggregation(self) -> None:
        """多腿加权求和"""
        legs = [
            Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 1, 120.0),
            Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 1, 95.0),
        ]
        combo = _make_combination(legs)
        greeks_map = {
            "m2509-C-2800.DCE": GreeksResult(delta=0.5, gamma=0.02, theta=-0.1, vega=15.0),
            "m2509-P-2800.DCE": GreeksResult(delta=-0.4, gamma=0.03, theta=-0.05, vega=12.0),
        }
        result = self.calculator.calculate(combo, greeks_map, multiplier=10.0)

        # leg1: weight = 1 * 10 * 1 = 10
        # leg2: weight = 1 * 10 * (-1) = -10
        assert result.delta == 0.5 * 10.0 + (-0.4) * (-10.0)  # 5.0 + 4.0 = 9.0
        assert result.gamma == 0.02 * 10.0 + 0.03 * (-10.0)   # 0.2 - 0.3 = -0.1
        assert result.failed_legs == []

    def test_failed_leg_recorded(self) -> None:
        """GreeksResult.success=False 的 Leg 记入 failed_legs，不参与计算"""
        legs = [
            Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 1, 120.0),
            Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "long", 1, 95.0),
        ]
        combo = _make_combination(legs)
        greeks_map = {
            "m2509-C-2800.DCE": GreeksResult(delta=0.5, gamma=0.02, theta=-0.1, vega=15.0),
            "m2509-P-2800.DCE": GreeksResult(success=False, error_message="calc failed"),
        }
        result = self.calculator.calculate(combo, greeks_map, multiplier=10.0)

        # 只有第一个 leg 参与计算
        assert result.delta == 0.5 * 10.0
        assert result.gamma == 0.02 * 10.0
        assert result.failed_legs == ["m2509-P-2800.DCE"]

    def test_missing_leg_in_greeks_map(self) -> None:
        """greeks_map 中缺少某个 Leg 时记入 failed_legs"""
        legs = [
            Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 1, 120.0),
            Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "long", 1, 95.0),
        ]
        combo = _make_combination(legs)
        greeks_map = {
            "m2509-C-2800.DCE": GreeksResult(delta=0.5, gamma=0.02, theta=-0.1, vega=15.0),
        }
        result = self.calculator.calculate(combo, greeks_map, multiplier=10.0)

        assert result.delta == 0.5 * 10.0
        assert result.failed_legs == ["m2509-P-2800.DCE"]

    def test_empty_legs(self) -> None:
        """空 Leg 列表返回零值"""
        combo = _make_combination([])
        result = self.calculator.calculate(combo, {}, multiplier=10.0)

        assert result.delta == 0.0
        assert result.gamma == 0.0
        assert result.theta == 0.0
        assert result.vega == 0.0
        assert result.failed_legs == []

    def test_all_legs_failed(self) -> None:
        """所有 Leg 都失败时，Greeks 为零，failed_legs 包含所有 Leg"""
        legs = [
            Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 1, 120.0),
            Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 1, 95.0),
        ]
        combo = _make_combination(legs)
        greeks_map = {
            "m2509-C-2800.DCE": GreeksResult(success=False, error_message="err1"),
            "m2509-P-2800.DCE": GreeksResult(success=False, error_message="err2"),
        }
        result = self.calculator.calculate(combo, greeks_map, multiplier=10.0)

        assert result.delta == 0.0
        assert result.gamma == 0.0
        assert result.theta == 0.0
        assert result.vega == 0.0
        assert result.failed_legs == ["m2509-C-2800.DCE", "m2509-P-2800.DCE"]


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# ---------------------------------------------------------------------------

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# 策略：基础构建块
# ---------------------------------------------------------------------------

_option_type = st.sampled_from(["call", "put"])
_direction = st.sampled_from(["long", "short"])
_strike_price = st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
_expiry_date = st.sampled_from(["20250901", "20251001", "20251101", "20251201"])
_volume = st.integers(min_value=1, max_value=100)
_open_price = st.floats(min_value=0.01, max_value=5000.0, allow_nan=False, allow_infinity=False)
_multiplier = st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False)

# Greeks 值范围：合理的期权 Greeks 范围
_greek_value = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)

_DIRECTION_SIGN = {"long": 1.0, "short": -1.0}


def _unique_vt_symbols(n: int):
    """生成 n 个唯一的 vt_symbol。"""
    return st.lists(
        st.from_regex(r"[a-z]{2}[0-9]{4}-[CP]-[0-9]{4}\.[A-Z]{3}", fullmatch=True),
        min_size=n,
        max_size=n,
        unique=True,
    )


def _combination_with_greeks_data():
    """
    生成随机 CUSTOM Combination、对应的 GreeksResult 映射和 multiplier。
    所有 Leg 的 GreeksResult.success = True。
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
            # Greeks for each leg: (delta, gamma, theta, vega)
            st.lists(
                st.tuples(_greek_value, _greek_value, _greek_value, _greek_value),
                min_size=n,
                max_size=n,
            ),
            _multiplier,
        )
    )


def _combination_with_mixed_greeks():
    """
    生成随机 CUSTOM Combination，其中部分 Leg 的 GreeksResult.success = False。
    返回 (combination, greeks_map, multiplier, success_flags)。
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
            st.lists(
                st.tuples(_greek_value, _greek_value, _greek_value, _greek_value),
                min_size=n,
                max_size=n,
            ),
            _multiplier,
            # success flag for each leg
            st.lists(st.booleans(), min_size=n, max_size=n),
        )
    )


# ---------------------------------------------------------------------------
# Feature: combination-strategy-management, Property 3: Greeks 加权求和
# ---------------------------------------------------------------------------

class TestProperty3GreeksWeightedSum:
    """
    Property 3: Greeks 加权求和

    *For any* Combination 及其每个 Leg 的 GreeksResult，CombinationGreeksCalculator
    计算的聚合 Greeks 应等于所有活跃 Leg 的
    `greek × volume × multiplier × direction_sign` 之和
    （direction_sign: long=+1, short=-1）。

    **Validates: Requirements 3.1, 3.4**
    """

    def setup_method(self) -> None:
        self.calculator = CombinationGreeksCalculator()

    @given(data=_combination_with_greeks_data())
    @settings(max_examples=100)
    def test_greeks_weighted_sum_equals_manual_calculation(self, data):
        """Feature: combination-strategy-management, Property 3: Greeks 加权求和
        对于任意 Combination 和 GreeksResult（全部成功），聚合 Greeks 应等于手动加权求和。
        **Validates: Requirements 3.1, 3.4**
        """
        symbols, opt_types, strikes, expiries, directions, volumes, prices, greeks_tuples, multiplier = data

        n = len(symbols)
        legs = [
            Leg(
                vt_symbol=symbols[i],
                option_type=opt_types[i],
                strike_price=strikes[i],
                expiry_date=expiries[i],
                direction=directions[i],
                volume=volumes[i],
                open_price=prices[i],
            )
            for i in range(n)
        ]
        combo = Combination(
            combination_id="prop3-test",
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )
        greeks_map = {
            symbols[i]: GreeksResult(
                delta=greeks_tuples[i][0],
                gamma=greeks_tuples[i][1],
                theta=greeks_tuples[i][2],
                vega=greeks_tuples[i][3],
            )
            for i in range(n)
        }

        result = self.calculator.calculate(combo, greeks_map, multiplier)

        # 手动计算期望值
        expected_delta = 0.0
        expected_gamma = 0.0
        expected_theta = 0.0
        expected_vega = 0.0
        for i in range(n):
            sign = _DIRECTION_SIGN[directions[i]]
            weight = volumes[i] * multiplier * sign
            expected_delta += greeks_tuples[i][0] * weight
            expected_gamma += greeks_tuples[i][1] * weight
            expected_theta += greeks_tuples[i][2] * weight
            expected_vega += greeks_tuples[i][3] * weight

        assert result.delta == pytest.approx(expected_delta, abs=1e-6)
        assert result.gamma == pytest.approx(expected_gamma, abs=1e-6)
        assert result.theta == pytest.approx(expected_theta, abs=1e-6)
        assert result.vega == pytest.approx(expected_vega, abs=1e-6)
        assert result.failed_legs == []

    @given(data=_combination_with_mixed_greeks())
    @settings(max_examples=100)
    def test_failed_legs_excluded_from_weighted_sum(self, data):
        """Feature: combination-strategy-management, Property 3: Greeks 加权求和
        当部分 Leg 的 GreeksResult.success=False 时，失败的 Leg 不参与加权求和，
        且被记入 failed_legs 列表。
        **Validates: Requirements 3.1, 3.4**
        """
        symbols, opt_types, strikes, expiries, directions, volumes, prices, greeks_tuples, multiplier, success_flags = data

        n = len(symbols)
        legs = [
            Leg(
                vt_symbol=symbols[i],
                option_type=opt_types[i],
                strike_price=strikes[i],
                expiry_date=expiries[i],
                direction=directions[i],
                volume=volumes[i],
                open_price=prices[i],
            )
            for i in range(n)
        ]
        combo = Combination(
            combination_id="prop3-mixed",
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )
        greeks_map = {
            symbols[i]: GreeksResult(
                delta=greeks_tuples[i][0],
                gamma=greeks_tuples[i][1],
                theta=greeks_tuples[i][2],
                vega=greeks_tuples[i][3],
                success=success_flags[i],
            )
            for i in range(n)
        }

        result = self.calculator.calculate(combo, greeks_map, multiplier)

        # 手动计算：只包含 success=True 的 Leg
        expected_delta = 0.0
        expected_gamma = 0.0
        expected_theta = 0.0
        expected_vega = 0.0
        expected_failed = []
        for i in range(n):
            if not success_flags[i]:
                expected_failed.append(symbols[i])
                continue
            sign = _DIRECTION_SIGN[directions[i]]
            weight = volumes[i] * multiplier * sign
            expected_delta += greeks_tuples[i][0] * weight
            expected_gamma += greeks_tuples[i][1] * weight
            expected_theta += greeks_tuples[i][2] * weight
            expected_vega += greeks_tuples[i][3] * weight

        assert result.delta == pytest.approx(expected_delta, abs=1e-6)
        assert result.gamma == pytest.approx(expected_gamma, abs=1e-6)
        assert result.theta == pytest.approx(expected_theta, abs=1e-6)
        assert result.vega == pytest.approx(expected_vega, abs=1e-6)
        assert result.failed_legs == expected_failed

    @given(data=_combination_with_greeks_data())
    @settings(max_examples=100)
    def test_direction_sign_correctness(self, data):
        """Feature: combination-strategy-management, Property 3: Greeks 加权求和
        验证 long 方向使用 +1 符号，short 方向使用 -1 符号。
        **Validates: Requirements 3.1, 3.4**
        """
        symbols, opt_types, strikes, expiries, directions, volumes, prices, greeks_tuples, multiplier = data

        n = len(symbols)
        legs = [
            Leg(
                vt_symbol=symbols[i],
                option_type=opt_types[i],
                strike_price=strikes[i],
                expiry_date=expiries[i],
                direction=directions[i],
                volume=volumes[i],
                open_price=prices[i],
            )
            for i in range(n)
        ]
        combo = Combination(
            combination_id="prop3-sign",
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )
        greeks_map = {
            symbols[i]: GreeksResult(
                delta=greeks_tuples[i][0],
                gamma=greeks_tuples[i][1],
                theta=greeks_tuples[i][2],
                vega=greeks_tuples[i][3],
            )
            for i in range(n)
        }

        result = self.calculator.calculate(combo, greeks_map, multiplier)

        # 验证每个 Leg 的方向符号正确性：
        # 逐个 Leg 单独计算，确认方向符号
        for i in range(n):
            single_leg_combo = Combination(
                combination_id=f"single-{i}",
                combination_type=CombinationType.CUSTOM,
                underlying_vt_symbol="underlying.EX",
                legs=[legs[i]],
                status=CombinationStatus.ACTIVE,
                create_time=datetime(2025, 1, 1),
            )
            single_result = self.calculator.calculate(
                single_leg_combo, {symbols[i]: greeks_map[symbols[i]]}, multiplier
            )
            expected_sign = 1.0 if directions[i] == "long" else -1.0
            expected_weight = volumes[i] * multiplier * expected_sign
            assert single_result.delta == pytest.approx(
                greeks_tuples[i][0] * expected_weight, abs=1e-6
            )
