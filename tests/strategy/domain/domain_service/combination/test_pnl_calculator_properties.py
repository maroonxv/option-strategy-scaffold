"""
Property 3: PnL 计算方向加权正确性 - 属性测试

Feature: combination-service-optimization, Property 3: PnL 计算方向加权正确性

*For any* Combination、current_prices 和 multiplier，CombinationPnLCalculator 计算的每腿未实现盈亏
应等于 `(current_price - open_price) × volume × multiplier × direction_sign`，
总未实现盈亏应等于各腿之和。

**Validates: Requirements 1.3, 1.5**

测试策略：
- Generate random Combination + prices
- Verify PnL formula: pnl = (current_price - open_price) × volume × multiplier × direction_sign
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


def _unique_vt_symbols(n: int):
    """生成 n 个唯一的 vt_symbol。"""
    return st.lists(
        st.from_regex(r"[a-z]{2}[0-9]{4}-[CP]-[0-9]{4}\.[A-Z]{3}", fullmatch=True),
        min_size=n,
        max_size=n,
        unique=True,
    )


def _combination_with_prices_data():
    """
    生成随机 CUSTOM Combination、对应的 current_prices 映射和 multiplier。
    所有 Leg 都有对应的当前价格。
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
        )
    )


def _combination_with_partial_prices():
    """
    生成随机 CUSTOM Combination，其中部分 Leg 的当前价格不可用。
    返回 (symbols, ..., current_prices_list, multiplier, price_available_flags)。
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
    open_prices: list[float],
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
            open_price=open_prices[i],
        )
        for i in range(n)
    ]
    return Combination(
        combination_id="prop3-test",
        combination_type=CombinationType.CUSTOM,
        underlying_vt_symbol="underlying.EX",
        legs=legs,
        status=CombinationStatus.ACTIVE,
        create_time=datetime(2025, 1, 1),
    )


def _build_current_prices(
    symbols: list[str],
    current_prices: list[float],
    include_flags: list[bool] | None = None,
) -> dict[str, float]:
    """从生成的数据构建 current_prices 映射。"""
    n = len(symbols)
    if include_flags is None:
        include_flags = [True] * n

    return {
        symbols[i]: current_prices[i]
        for i in range(n)
        if include_flags[i]
    }


def _calculate_expected_pnl(
    directions: list[str],
    volumes: list[int],
    open_prices: list[float],
    current_prices: list[float],
    multiplier: float,
    include_flags: list[bool] | None = None,
) -> tuple[float, list[float]]:
    """
    手动计算期望的 PnL 值。
    
    返回 (total_pnl, leg_pnls)，其中 leg_pnls[i] 为第 i 腿的盈亏（无价格时为 0.0）。
    """
    n = len(directions)
    if include_flags is None:
        include_flags = [True] * n

    total_pnl = 0.0
    leg_pnls = []

    for i in range(n):
        if not include_flags[i]:
            leg_pnls.append(0.0)
            continue

        direction_sign = 1.0 if directions[i] == "long" else -1.0
        leg_pnl = (
            (current_prices[i] - open_prices[i])
            * volumes[i]
            * multiplier
            * direction_sign
        )
        leg_pnls.append(leg_pnl)
        total_pnl += leg_pnl

    return total_pnl, leg_pnls


# ---------------------------------------------------------------------------
# Feature: combination-service-optimization, Property 3: PnL 计算方向加权正确性
# ---------------------------------------------------------------------------


class TestProperty3PnLDirectionWeighting:
    """
    Property 3: PnL 计算方向加权正确性

    *For any* Combination、current_prices 和 multiplier，CombinationPnLCalculator 计算的每腿未实现盈亏
    应等于 `(current_price - open_price) × volume × multiplier × direction_sign`，
    总未实现盈亏应等于各腿之和。

    **Validates: Requirements 1.3, 1.5**
    """

    def setup_method(self) -> None:
        self.calculator = CombinationPnLCalculator()

    @given(data=_combination_with_prices_data())
    @settings(max_examples=100)
    def test_pnl_formula_correctness(self, data):
        """
        Feature: combination-service-optimization, Property 3: PnL 计算方向加权正确性

        验证 PnL 公式：pnl = (current_price - open_price) × volume × multiplier × direction_sign
        其中 direction_sign: long = +1.0, short = -1.0

        **Validates: Requirements 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            open_prices,
            current_prices,
            multiplier,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, open_prices
        )
        prices_map = _build_current_prices(symbols, current_prices)

        result = self.calculator.calculate(combo, prices_map, multiplier)

        expected_total, expected_leg_pnls = _calculate_expected_pnl(
            directions, volumes, open_prices, current_prices, multiplier
        )

        # 验证总盈亏
        assert result.total_unrealized_pnl == pytest.approx(expected_total, abs=1e-6)
        # 验证每腿盈亏
        assert len(result.leg_details) == len(symbols)
        for i, detail in enumerate(result.leg_details):
            assert detail.vt_symbol == symbols[i]
            assert detail.unrealized_pnl == pytest.approx(expected_leg_pnls[i], abs=1e-6)
            assert detail.price_available is True

    @given(data=_combination_with_prices_data())
    @settings(max_examples=100)
    def test_direction_sign_long_positive_short_negative(self, data):
        """
        Feature: combination-service-optimization, Property 3: PnL 计算方向加权正确性

        验证方向符号映射：long 方向使用 +1.0，short 方向使用 -1.0。
        通过单独计算每个 Leg 的贡献来验证。

        **Validates: Requirements 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            open_prices,
            current_prices,
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
                    open_price=open_prices[i],
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
            single_prices = {symbols[i]: current_prices[i]}

            result = self.calculator.calculate(single_combo, single_prices, multiplier)

            # 验证方向符号
            expected_sign = 1.0 if directions[i] == "long" else -1.0
            expected_pnl = (
                (current_prices[i] - open_prices[i])
                * volumes[i]
                * multiplier
                * expected_sign
            )

            assert result.total_unrealized_pnl == pytest.approx(expected_pnl, abs=1e-6)
            assert len(result.leg_details) == 1
            assert result.leg_details[0].unrealized_pnl == pytest.approx(
                expected_pnl, abs=1e-6
            )

    @given(data=_combination_with_partial_prices())
    @settings(max_examples=100)
    def test_missing_prices_use_zero_pnl(self, data):
        """
        Feature: combination-service-optimization, Property 3: PnL 计算方向加权正确性

        验证当部分 Leg 价格不可用时，缺失价格的腿盈亏为 0 且 price_available=False，
        总盈亏仅包含有价格的腿。

        **Validates: Requirements 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            open_prices,
            current_prices,
            multiplier,
            include_flags,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, open_prices
        )
        prices_map = _build_current_prices(symbols, current_prices, include_flags)

        result = self.calculator.calculate(combo, prices_map, multiplier)

        expected_total, expected_leg_pnls = _calculate_expected_pnl(
            directions, volumes, open_prices, current_prices, multiplier, include_flags
        )

        # 验证总盈亏
        assert result.total_unrealized_pnl == pytest.approx(expected_total, abs=1e-6)
        # 验证每腿盈亏和 price_available 标志
        assert len(result.leg_details) == len(symbols)
        for i, detail in enumerate(result.leg_details):
            assert detail.vt_symbol == symbols[i]
            assert detail.unrealized_pnl == pytest.approx(expected_leg_pnls[i], abs=1e-6)
            assert detail.price_available is include_flags[i]

    @given(data=_combination_with_prices_data())
    @settings(max_examples=100)
    def test_total_pnl_equals_sum_of_leg_pnls(self, data):
        """
        Feature: combination-service-optimization, Property 3: PnL 计算方向加权正确性

        验证总未实现盈亏等于各腿未实现盈亏之和。

        **Validates: Requirements 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            open_prices,
            current_prices,
            multiplier,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, open_prices
        )
        prices_map = _build_current_prices(symbols, current_prices)

        result = self.calculator.calculate(combo, prices_map, multiplier)

        # 验证总盈亏等于各腿盈亏之和
        sum_of_legs = sum(detail.unrealized_pnl for detail in result.leg_details)
        assert result.total_unrealized_pnl == pytest.approx(sum_of_legs, abs=1e-6)

    @given(data=_combination_with_prices_data())
    @settings(max_examples=100)
    def test_aggregation_is_sum_of_individual_contributions(self, data):
        """
        Feature: combination-service-optimization, Property 3: PnL 计算方向加权正确性

        验证组合级 PnL 等于各 Leg 单独计算后的求和。
        这是加权求和公式的另一种验证方式。

        **Validates: Requirements 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            open_prices,
            current_prices,
            multiplier,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, open_prices
        )
        prices_map = _build_current_prices(symbols, current_prices)

        # 计算组合级结果
        combo_result = self.calculator.calculate(combo, prices_map, multiplier)

        # 逐个 Leg 计算并求和
        sum_pnl = 0.0

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
                    open_price=open_prices[i],
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
            single_prices = {symbols[i]: current_prices[i]}

            single_result = self.calculator.calculate(
                single_combo, single_prices, multiplier
            )
            sum_pnl += single_result.total_unrealized_pnl

        # 验证组合结果等于各 Leg 结果之和
        assert combo_result.total_unrealized_pnl == pytest.approx(sum_pnl, abs=1e-6)

    @given(multiplier=_multiplier)
    @settings(max_examples=100)
    def test_empty_combination_returns_zero_pnl(self, multiplier: float):
        """
        Feature: combination-service-optimization, Property 3: PnL 计算方向加权正确性

        验证空 Combination（无 Leg）返回零值 PnL。

        **Validates: Requirements 1.3, 1.5**
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

        assert result.total_unrealized_pnl == 0.0
        assert result.leg_details == []

    @given(data=_combination_with_prices_data())
    @settings(max_examples=100)
    def test_leg_details_order_matches_combination_legs(self, data):
        """
        Feature: combination-service-optimization, Property 3: PnL 计算方向加权正确性

        验证 leg_details 的顺序与 combination.legs 一致。

        **Validates: Requirements 1.3, 1.5**
        """
        (
            symbols,
            opt_types,
            strikes,
            expiries,
            directions,
            volumes,
            open_prices,
            current_prices,
            multiplier,
        ) = data

        combo = _build_combination(
            symbols, opt_types, strikes, expiries, directions, volumes, open_prices
        )
        prices_map = _build_current_prices(symbols, current_prices)

        result = self.calculator.calculate(combo, prices_map, multiplier)

        # 验证顺序一致
        assert len(result.leg_details) == len(combo.legs)
        for i, (detail, leg) in enumerate(zip(result.leg_details, combo.legs)):
            assert detail.vt_symbol == leg.vt_symbol

