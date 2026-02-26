"""
Property 2: Greeks 计算方向加权正确性 - 属性测试

Feature: combination-service-optimization, Property 2: Greeks 计算方向加权正确性

*For any* Combination 和 greeks_map，CombinationGreeksCalculator 计算的组合级 Greeks
应等于各 Leg 的 Greeks 按 `volume × multiplier × direction_sign` 加权求和的结果。

**Validates: Requirements 1.2, 1.3, 1.5**

测试策略：
- Generate random Combination + greeks_map
- Verify weighted sum formula: greek_total = Σ(greek_per_unit × volume × multiplier × direction_sign)
"""
from datetime import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.domain_service.combination.combination_greeks_calculator import (
    CombinationGreeksCalculator,
)
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)
from src.strategy.domain.value_object.greeks import GreeksResult


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

# Greeks 值范围：合理的期权 Greeks 范围
_greek_value = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False
)


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


def _combination_with_partial_greeks():
    """
    生成随机 CUSTOM Combination，其中部分 Leg 在 greeks_map 中缺失。
    返回 (combination_data, greeks_data, multiplier, include_flags)。
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
            # include flag for each leg in greeks_map
            st.lists(st.booleans(), min_size=n, max_size=n),
        )
    )


def _combination_with_mixed_success():
    """
    生成随机 CUSTOM Combination，其中部分 Leg 的 GreeksResult.success = False。
    返回 (combination_data, greeks_data, multiplier, success_flags)。
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


def _build_combination(
    symbols: list[str],
    opt_types: list[str],
    strikes: list[float],
    expiries: list[str],
    directions: list[str],
    volumes: list[int],
    prices: list[float],
) -> Combination:
    """从生成的数据构建 Combination 实体。"""
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
    return Combination(
        combination_id="prop2-test",
        combination_type=CombinationType.CUSTOM,
        underlying_vt_symbol="underlying.EX",
        legs=legs,
        status=CombinationStatus.ACTIVE,
        create_time=datetime(2025, 1, 1),
    )


def _build_greeks_map(
    symbols: list[str],
    greeks_tuples: list[tuple[float, float, float, float]],
    success_flags: list[bool] | None = None,
    include_flags: list[bool] | None = None,
) -> dict[str, GreeksResult]:
    """从生成的数据构建 greeks_map。"""
    n = len(symbols)
    if success_flags is None:
        success_flags = [True] * n
    if include_flags is None:
        include_flags = [True] * n

    greeks_map = {}
    for i in range(n):
        if not include_flags[i]:
            continue
        greeks_map[symbols[i]] = GreeksResult(
            delta=greeks_tuples[i][0],
            gamma=greeks_tuples[i][1],
            theta=greeks_tuples[i][2],
            vega=greeks_tuples[i][3],
            success=success_flags[i],
        )
    return greeks_map


def _calculate_expected_greeks(
    directions: list[str],
    volumes: list[int],
    greeks_tuples: list[tuple[float, float, float, float]],
    multiplier: float,
    success_flags: list[bool] | None = None,
    include_flags: list[bool] | None = None,
) -> tuple[float, float, float, float]:
    """手动计算期望的加权 Greeks 值。"""
    n = len(directions)
    if success_flags is None:
        success_flags = [True] * n
    if include_flags is None:
        include_flags = [True] * n

    expected_delta = 0.0
    expected_gamma = 0.0
    expected_theta = 0.0
    expected_vega = 0.0

    for i in range(n):
        # 跳过不在 greeks_map 中的 Leg 或 success=False 的 Leg
        if not include_flags[i] or not success_flags[i]:
            continue

        direction_sign = 1.0 if directions[i] == "long" else -1.0
        weight = volumes[i] * multiplier * direction_sign

        expected_delta += greeks_tuples[i][0] * weight
        expected_gamma += greeks_tuples[i][1] * weight
        expected_theta += greeks_tuples[i][2] * weight
        expected_vega += greeks_tuples[i][3] * weight

    return expected_delta, expected_gamma, expected_theta, expected_vega


# ---------------------------------------------------------------------------
# Feature: combination-service-optimization, Property 2: Greeks 计算方向加权正确性
# ---------------------------------------------------------------------------


class TestProperty2GreeksDirectionWeighting:
    """
    Property 2: Greeks 计算方向加权正确性

    *For any* Combination 和 greeks_map，CombinationGreeksCalculator 计算的组合级 Greeks
    应等于各 Leg 的 Greeks 按 `volume × multiplier × direction_sign` 加权求和的结果。

    **Validates: Requirements 1.2, 1.3, 1.5**
    """

    def setup_method(self) -> None:
        self.calculator = CombinationGreeksCalculator()

    @given(data=_combination_with_greeks_data())
    @settings(max_examples=100)
    def test_weighted_sum_formula_correctness(self, data):
        """
        Feature: combination-service-optimization, Property 2: Greeks 计算方向加权正确性

        验证加权求和公式：greek_total = Σ(greek_per_unit × volume × multiplier × direction_sign)
        其中 direction_sign: long = +1.0, short = -1.0

        **Validates: Requirements 1.2, 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            prices,
            greeks_tuples,
            multiplier,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, prices
        )
        greeks_map = _build_greeks_map(symbols, greeks_tuples)

        result = self.calculator.calculate(combo, greeks_map, multiplier)

        expected_delta, expected_gamma, expected_theta, expected_vega = (
            _calculate_expected_greeks(directions, volumes, greeks_tuples, multiplier)
        )

        assert result.delta == pytest.approx(expected_delta, abs=1e-6)
        assert result.gamma == pytest.approx(expected_gamma, abs=1e-6)
        assert result.theta == pytest.approx(expected_theta, abs=1e-6)
        assert result.vega == pytest.approx(expected_vega, abs=1e-6)
        assert result.failed_legs == []

    @given(data=_combination_with_greeks_data())
    @settings(max_examples=100)
    def test_direction_sign_long_positive_short_negative(self, data):
        """
        Feature: combination-service-optimization, Property 2: Greeks 计算方向加权正确性

        验证方向符号映射：long 方向使用 +1.0，short 方向使用 -1.0。
        通过单独计算每个 Leg 的贡献来验证。

        **Validates: Requirements 1.2, 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            prices,
            greeks_tuples,
            multiplier,
        ) = data

        n = len(symbols)

        # 逐个 Leg 验证方向符号
        for i in range(n):
            single_leg = [
                Leg(
                    vt_symbol=symbols[i],
                    option_type=opt_types[i],
                    strike_price=strikes[i],
                    expiry_date=expiries[i],
                    direction=directions[i],
                    volume=volumes[i],
                    open_price=prices[i],
                )
            ]
            single_combo = Combination(
                combination_id=f"single-{i}",
                combination_type=CombinationType.CUSTOM,
                underlying_vt_symbol="underlying.EX",
                legs=single_leg,
                status=CombinationStatus.ACTIVE,
                create_time=datetime(2025, 1, 1),
            )
            single_greeks_map = {
                symbols[i]: GreeksResult(
                    delta=greeks_tuples[i][0],
                    gamma=greeks_tuples[i][1],
                    theta=greeks_tuples[i][2],
                    vega=greeks_tuples[i][3],
                )
            }

            result = self.calculator.calculate(single_combo, single_greeks_map, multiplier)

            # 验证方向符号
            expected_sign = 1.0 if directions[i] == "long" else -1.0
            expected_weight = volumes[i] * multiplier * expected_sign

            assert result.delta == pytest.approx(
                greeks_tuples[i][0] * expected_weight, abs=1e-6
            )
            assert result.gamma == pytest.approx(
                greeks_tuples[i][1] * expected_weight, abs=1e-6
            )
            assert result.theta == pytest.approx(
                greeks_tuples[i][2] * expected_weight, abs=1e-6
            )
            assert result.vega == pytest.approx(
                greeks_tuples[i][3] * expected_weight, abs=1e-6
            )

    @given(data=_combination_with_mixed_success())
    @settings(max_examples=100)
    def test_failed_legs_excluded_from_calculation(self, data):
        """
        Feature: combination-service-optimization, Property 2: Greeks 计算方向加权正确性

        验证当 GreeksResult.success=False 时，该 Leg 不参与加权求和，
        且被记入 failed_legs 列表。

        **Validates: Requirements 1.2, 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            prices,
            greeks_tuples,
            multiplier,
            success_flags,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, prices
        )
        greeks_map = _build_greeks_map(symbols, greeks_tuples, success_flags=success_flags)

        result = self.calculator.calculate(combo, greeks_map, multiplier)

        expected_delta, expected_gamma, expected_theta, expected_vega = (
            _calculate_expected_greeks(
                directions, volumes, greeks_tuples, multiplier, success_flags=success_flags
            )
        )

        # 计算期望的 failed_legs
        expected_failed = [
            symbols[i] for i in range(len(symbols)) if not success_flags[i]
        ]

        assert result.delta == pytest.approx(expected_delta, abs=1e-6)
        assert result.gamma == pytest.approx(expected_gamma, abs=1e-6)
        assert result.theta == pytest.approx(expected_theta, abs=1e-6)
        assert result.vega == pytest.approx(expected_vega, abs=1e-6)
        assert result.failed_legs == expected_failed

    @given(data=_combination_with_partial_greeks())
    @settings(max_examples=100)
    def test_missing_legs_in_greeks_map_excluded(self, data):
        """
        Feature: combination-service-optimization, Property 2: Greeks 计算方向加权正确性

        验证当 greeks_map 中缺少某个 Leg 时，该 Leg 不参与加权求和，
        且被记入 failed_legs 列表。

        **Validates: Requirements 1.2, 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            prices,
            greeks_tuples,
            multiplier,
            include_flags,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, prices
        )
        greeks_map = _build_greeks_map(symbols, greeks_tuples, include_flags=include_flags)

        result = self.calculator.calculate(combo, greeks_map, multiplier)

        expected_delta, expected_gamma, expected_theta, expected_vega = (
            _calculate_expected_greeks(
                directions, volumes, greeks_tuples, multiplier, include_flags=include_flags
            )
        )

        # 计算期望的 failed_legs（不在 greeks_map 中的 Leg）
        expected_failed = [
            symbols[i] for i in range(len(symbols)) if not include_flags[i]
        ]

        assert result.delta == pytest.approx(expected_delta, abs=1e-6)
        assert result.gamma == pytest.approx(expected_gamma, abs=1e-6)
        assert result.theta == pytest.approx(expected_theta, abs=1e-6)
        assert result.vega == pytest.approx(expected_vega, abs=1e-6)
        assert result.failed_legs == expected_failed

    @given(multiplier=_multiplier)
    @settings(max_examples=100)
    def test_empty_combination_returns_zero_greeks(self, multiplier: float):
        """
        Feature: combination-service-optimization, Property 2: Greeks 计算方向加权正确性

        验证空 Combination（无 Leg）返回零值 Greeks。

        **Validates: Requirements 1.2, 1.3, 1.5**
        """
        combo = Combination(
            combination_id="empty-combo",
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol="underlying.EX",
            legs=[],
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        result = self.calculator.calculate(combo, {}, multiplier)

        assert result.delta == 0.0
        assert result.gamma == 0.0
        assert result.theta == 0.0
        assert result.vega == 0.0
        assert result.failed_legs == []

    @given(data=_combination_with_greeks_data())
    @settings(max_examples=100)
    def test_aggregation_is_sum_of_individual_contributions(self, data):
        """
        Feature: combination-service-optimization, Property 2: Greeks 计算方向加权正确性

        验证组合级 Greeks 等于各 Leg 单独计算后的求和。
        这是加权求和公式的另一种验证方式。

        **Validates: Requirements 1.2, 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            prices,
            greeks_tuples,
            multiplier,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, prices
        )
        greeks_map = _build_greeks_map(symbols, greeks_tuples)

        # 计算组合级结果
        combo_result = self.calculator.calculate(combo, greeks_map, multiplier)

        # 逐个 Leg 计算并求和
        sum_delta = 0.0
        sum_gamma = 0.0
        sum_theta = 0.0
        sum_vega = 0.0

        n = len(symbols)
        for i in range(n):
            single_leg = [
                Leg(
                    vt_symbol=symbols[i],
                    option_type=opt_types[i],
                    strike_price=strikes[i],
                    expiry_date=expiries[i],
                    direction=directions[i],
                    volume=volumes[i],
                    open_price=prices[i],
                )
            ]
            single_combo = Combination(
                combination_id=f"single-{i}",
                combination_type=CombinationType.CUSTOM,
                underlying_vt_symbol="underlying.EX",
                legs=single_leg,
                status=CombinationStatus.ACTIVE,
                create_time=datetime(2025, 1, 1),
            )
            single_greeks_map = {symbols[i]: greeks_map[symbols[i]]}

            single_result = self.calculator.calculate(
                single_combo, single_greeks_map, multiplier
            )

            sum_delta += single_result.delta
            sum_gamma += single_result.gamma
            sum_theta += single_result.theta
            sum_vega += single_result.vega

        # 验证组合结果等于各 Leg 结果之和
        assert combo_result.delta == pytest.approx(sum_delta, abs=1e-6)
        assert combo_result.gamma == pytest.approx(sum_gamma, abs=1e-6)
        assert combo_result.theta == pytest.approx(sum_theta, abs=1e-6)
        assert combo_result.vega == pytest.approx(sum_vega, abs=1e-6)
