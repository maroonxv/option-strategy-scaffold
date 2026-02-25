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
