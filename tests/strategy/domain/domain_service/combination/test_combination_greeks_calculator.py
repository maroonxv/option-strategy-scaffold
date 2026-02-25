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
from src.strategy.domain.value_object.greeks import GreeksResult


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
