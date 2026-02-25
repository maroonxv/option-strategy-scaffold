"""
CombinationPnLCalculator 单元测试

测试组合级盈亏计算：
- 所有腿价格可用时的正确计算
- 部分腿价格不可用时的处理
- 多头/空头方向符号
- 空组合
"""
from datetime import datetime

from src.strategy.domain.domain_service.combination.combination_pnl_calculator import (
    CombinationPnLCalculator,
)
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)


def _make_combination(legs: list[Leg]) -> Combination:
    return Combination(
        combination_id="test-combo-1",
        combination_type=CombinationType.CUSTOM,
        underlying_vt_symbol="m2509.DCE",
        legs=legs,
        status=CombinationStatus.ACTIVE,
        create_time=datetime(2025, 1, 15, 10, 30),
    )


def _make_leg(
    vt_symbol: str = "m2509-C-2800.DCE",
    direction: str = "long",
    volume: int = 1,
    open_price: float = 100.0,
    option_type: str = "call",
    strike_price: float = 2800.0,
) -> Leg:
    return Leg(
        vt_symbol=vt_symbol,
        option_type=option_type,
        strike_price=strike_price,
        expiry_date="20250901",
        direction=direction,
        volume=volume,
        open_price=open_price,
    )


class TestCombinationPnLCalculator:
    """CombinationPnLCalculator 单元测试"""

    def setup_method(self) -> None:
        self.calculator = CombinationPnLCalculator()

    def test_single_long_leg_profit(self) -> None:
        """单腿多头盈利：(120 - 100) × 1 × 10 × 1 = 200"""
        leg = _make_leg(direction="long", volume=1, open_price=100.0)
        combo = _make_combination([leg])
        prices = {"m2509-C-2800.DCE": 120.0}

        result = self.calculator.calculate(combo, prices, multiplier=10.0)

        assert result.total_unrealized_pnl == 200.0
        assert len(result.leg_details) == 1
        assert result.leg_details[0].unrealized_pnl == 200.0
        assert result.leg_details[0].price_available is True

    def test_single_short_leg_profit(self) -> None:
        """单腿空头盈利：(80 - 100) × 1 × 10 × (-1) = 200"""
        leg = _make_leg(direction="short", volume=1, open_price=100.0)
        combo = _make_combination([leg])
        prices = {"m2509-C-2800.DCE": 80.0}

        result = self.calculator.calculate(combo, prices, multiplier=10.0)

        assert result.total_unrealized_pnl == 200.0
        assert result.leg_details[0].price_available is True

    def test_single_long_leg_loss(self) -> None:
        """单腿多头亏损：(80 - 100) × 2 × 10 × 1 = -400"""
        leg = _make_leg(direction="long", volume=2, open_price=100.0)
        combo = _make_combination([leg])
        prices = {"m2509-C-2800.DCE": 80.0}

        result = self.calculator.calculate(combo, prices, multiplier=10.0)

        assert result.total_unrealized_pnl == -400.0

    def test_two_legs_straddle_pnl(self) -> None:
        """双腿 Straddle 盈亏汇总"""
        call_leg = _make_leg(
            vt_symbol="m2509-C-2800.DCE",
            direction="short",
            volume=1,
            open_price=120.0,
            option_type="call",
        )
        put_leg = _make_leg(
            vt_symbol="m2509-P-2800.DCE",
            direction="short",
            volume=1,
            open_price=95.0,
            option_type="put",
            strike_price=2800.0,
        )
        combo = _make_combination([call_leg, put_leg])
        prices = {
            "m2509-C-2800.DCE": 110.0,
            "m2509-P-2800.DCE": 100.0,
        }
        multiplier = 10.0

        result = self.calculator.calculate(combo, prices, multiplier)

        # call short: (110 - 120) × 1 × 10 × (-1) = 100
        # put short:  (100 - 95)  × 1 × 10 × (-1) = -50
        assert result.total_unrealized_pnl == 50.0
        assert len(result.leg_details) == 2
        assert all(d.price_available for d in result.leg_details)

    def test_price_unavailable_leg(self) -> None:
        """价格不可用的腿：pnl=0, price_available=False"""
        leg = _make_leg(direction="long", volume=1, open_price=100.0)
        combo = _make_combination([leg])
        prices: dict[str, float] = {}  # 无价格

        result = self.calculator.calculate(combo, prices, multiplier=10.0)

        assert result.total_unrealized_pnl == 0.0
        assert len(result.leg_details) == 1
        assert result.leg_details[0].unrealized_pnl == 0.0
        assert result.leg_details[0].price_available is False

    def test_partial_price_unavailable(self) -> None:
        """部分腿价格不可用：只计算有价格的腿"""
        leg1 = _make_leg(
            vt_symbol="m2509-C-2800.DCE",
            direction="long",
            volume=1,
            open_price=100.0,
        )
        leg2 = _make_leg(
            vt_symbol="m2509-P-2800.DCE",
            direction="short",
            volume=1,
            open_price=90.0,
            option_type="put",
        )
        combo = _make_combination([leg1, leg2])
        prices = {"m2509-C-2800.DCE": 130.0}  # 只有 leg1 有价格

        result = self.calculator.calculate(combo, prices, multiplier=10.0)

        # leg1 long: (130 - 100) × 1 × 10 × 1 = 300
        # leg2: 无价格, pnl = 0
        assert result.total_unrealized_pnl == 300.0
        assert result.leg_details[0].price_available is True
        assert result.leg_details[1].price_available is False
        assert result.leg_details[1].unrealized_pnl == 0.0

    def test_empty_legs(self) -> None:
        """空腿列表（CUSTOM 允许至少 1 腿，但 calculate 本身不验证）"""
        combo = Combination(
            combination_id="empty",
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol="m2509.DCE",
            legs=[],
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 15),
        )
        result = self.calculator.calculate(combo, {}, multiplier=10.0)

        assert result.total_unrealized_pnl == 0.0
        assert result.leg_details == []

    def test_timestamp_is_set(self) -> None:
        """结果包含计算时间戳"""
        leg = _make_leg()
        combo = _make_combination([leg])
        prices = {"m2509-C-2800.DCE": 110.0}

        result = self.calculator.calculate(combo, prices, multiplier=10.0)

        assert isinstance(result.timestamp, datetime)

    def test_zero_multiplier(self) -> None:
        """乘数为 0 时盈亏为 0"""
        leg = _make_leg(direction="long", volume=1, open_price=100.0)
        combo = _make_combination([leg])
        prices = {"m2509-C-2800.DCE": 200.0}

        result = self.calculator.calculate(combo, prices, multiplier=0.0)

        assert result.total_unrealized_pnl == 0.0

    def test_leg_details_order_matches_legs(self) -> None:
        """leg_details 顺序与 combination.legs 一致"""
        leg1 = _make_leg(vt_symbol="A.DCE", open_price=10.0)
        leg2 = _make_leg(vt_symbol="B.DCE", open_price=20.0, option_type="put")
        combo = _make_combination([leg1, leg2])
        prices = {"A.DCE": 15.0, "B.DCE": 25.0}

        result = self.calculator.calculate(combo, prices, multiplier=1.0)

        assert result.leg_details[0].vt_symbol == "A.DCE"
        assert result.leg_details[1].vt_symbol == "B.DCE"


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Reusable Hypothesis strategies
_option_type = st.sampled_from(["call", "put"])
_strike_price = st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
_expiry_date = st.from_regex(r"20[2-3][0-9](0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])", fullmatch=True)
_direction = st.sampled_from(["long", "short"])
_volume = st.integers(min_value=1, max_value=100)
_open_price = st.floats(min_value=0.01, max_value=5000.0, allow_nan=False, allow_infinity=False)
_current_price = st.floats(min_value=0.01, max_value=5000.0, allow_nan=False, allow_infinity=False)
_multiplier = st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False)

_DIRECTION_SIGN = {"long": 1.0, "short": -1.0}


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


# ---------------------------------------------------------------------------
# Feature: combination-strategy-management, Property 4: 盈亏计算正确性
# ---------------------------------------------------------------------------

class TestProperty4PnLCalculation:
    """
    Property 4: 盈亏计算正确性

    *For any* Combination 及其每个 Leg 的当前市场价，CombinationPnLCalculator
    计算的总未实现盈亏应等于所有 Leg 的
    `(current_price - open_price) × volume × multiplier × direction_sign` 之和，
    且每腿盈亏明细应与公式一致。

    **Validates: Requirements 4.1, 4.3**
    """

    def setup_method(self) -> None:
        self.calculator = CombinationPnLCalculator()

    @given(data=_combination_with_prices_data())
    @settings(max_examples=100)
    def test_total_pnl_equals_sum_of_leg_formulas(self, data):
        """Feature: combination-strategy-management, Property 4: 盈亏计算正确性
        对于任意 Combination（所有价格可用），总盈亏应等于各腿公式之和。
        **Validates: Requirements 4.1, 4.3**
        """
        symbols, opt_types, strikes, expiries, directions, volumes, open_prices, cur_prices, multiplier = data

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
        combo = Combination(
            combination_id="prop4-test",
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )
        current_prices = {symbols[i]: cur_prices[i] for i in range(n)}

        result = self.calculator.calculate(combo, current_prices, multiplier)

        # 手动计算期望总盈亏
        expected_total = 0.0
        for i in range(n):
            sign = _DIRECTION_SIGN[directions[i]]
            expected_leg_pnl = (cur_prices[i] - open_prices[i]) * volumes[i] * multiplier * sign
            expected_total += expected_leg_pnl

        assert result.total_unrealized_pnl == pytest.approx(expected_total, abs=1e-6)
        assert len(result.leg_details) == n
        assert all(d.price_available for d in result.leg_details)

    @given(data=_combination_with_prices_data())
    @settings(max_examples=100)
    def test_each_leg_pnl_matches_formula(self, data):
        """Feature: combination-strategy-management, Property 4: 盈亏计算正确性
        对于任意 Combination（所有价格可用），每腿盈亏明细应与公式一致。
        **Validates: Requirements 4.1, 4.3**
        """
        symbols, opt_types, strikes, expiries, directions, volumes, open_prices, cur_prices, multiplier = data

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
        combo = Combination(
            combination_id="prop4-leg-detail",
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )
        current_prices = {symbols[i]: cur_prices[i] for i in range(n)}

        result = self.calculator.calculate(combo, current_prices, multiplier)

        for i in range(n):
            sign = _DIRECTION_SIGN[directions[i]]
            expected_pnl = (cur_prices[i] - open_prices[i]) * volumes[i] * multiplier * sign
            assert result.leg_details[i].vt_symbol == symbols[i]
            assert result.leg_details[i].unrealized_pnl == pytest.approx(expected_pnl, abs=1e-6)
            assert result.leg_details[i].price_available is True

    @given(data=_combination_with_partial_prices())
    @settings(max_examples=100)
    def test_missing_prices_use_zero_pnl(self, data):
        """Feature: combination-strategy-management, Property 4: 盈亏计算正确性
        当部分 Leg 价格不可用时，缺失价格的腿盈亏为 0 且 price_available=False，
        总盈亏仅包含有价格的腿。
        **Validates: Requirements 4.1, 4.3**
        """
        symbols, opt_types, strikes, expiries, directions, volumes, open_prices, cur_prices, multiplier, avail_flags = data

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
        combo = Combination(
            combination_id="prop4-partial",
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )
        # Only include prices for legs where avail_flags[i] is True
        current_prices = {
            symbols[i]: cur_prices[i]
            for i in range(n)
            if avail_flags[i]
        }

        result = self.calculator.calculate(combo, current_prices, multiplier)

        # 手动计算期望总盈亏（仅有价格的腿）
        expected_total = 0.0
        for i in range(n):
            if avail_flags[i]:
                sign = _DIRECTION_SIGN[directions[i]]
                expected_total += (cur_prices[i] - open_prices[i]) * volumes[i] * multiplier * sign

        assert result.total_unrealized_pnl == pytest.approx(expected_total, abs=1e-6)
        assert len(result.leg_details) == n

        for i in range(n):
            detail = result.leg_details[i]
            assert detail.vt_symbol == symbols[i]
            if avail_flags[i]:
                sign = _DIRECTION_SIGN[directions[i]]
                expected_pnl = (cur_prices[i] - open_prices[i]) * volumes[i] * multiplier * sign
                assert detail.unrealized_pnl == pytest.approx(expected_pnl, abs=1e-6)
                assert detail.price_available is True
            else:
                assert detail.unrealized_pnl == 0.0
                assert detail.price_available is False
