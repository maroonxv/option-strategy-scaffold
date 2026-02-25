"""
组合策略集成测试

测试完整流程：
1. 创建 Combination（STRADDLE 或 CUSTOM）
2. 注册到 CombinationAggregate
3. 计算 Greeks（CombinationGreeksCalculator）
4. 计算 PnL（CombinationPnLCalculator）
5. 风控检查（CombinationRiskChecker）
6. 生成平仓指令（CombinationLifecycleService）
7. 状态同步并验证 CombinationStatusChangedEvent

**Validates: Requirements 7.2, 7.3, 7.4**
"""
from datetime import datetime
from typing import Dict, Set

import pytest

from src.strategy.domain.aggregate.combination_aggregate import CombinationAggregate
from src.strategy.domain.domain_service.combination.combination_greeks_calculator import (
    CombinationGreeksCalculator,
)
from src.strategy.domain.domain_service.combination.combination_lifecycle_service import (
    CombinationLifecycleService,
)
from src.strategy.domain.domain_service.combination.combination_pnl_calculator import (
    CombinationPnLCalculator,
)
from src.strategy.domain.domain_service.combination.combination_risk_checker import (
    CombinationRiskChecker,
)
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.event.event_types import CombinationStatusChangedEvent
from src.strategy.domain.value_object.combination import (
    CombinationGreeks,
    CombinationRiskConfig,
    CombinationStatus,
    CombinationType,
    Leg,
)
from src.strategy.domain.value_object.greeks import GreeksResult
from src.strategy.domain.value_object.order_instruction import Direction, Offset


class TestCombinationIntegrationWorkflow:
    """
    组合策略完整流程集成测试

    测试场景：
    - STRADDLE 组合的完整生命周期
    - CUSTOM 组合的完整生命周期
    - 部分平仓和完全平仓的状态同步
    """

    def setup_method(self) -> None:
        """初始化所有服务和聚合根"""
        self.aggregate = CombinationAggregate()
        self.greeks_calculator = CombinationGreeksCalculator()
        self.pnl_calculator = CombinationPnLCalculator()
        self.risk_config = CombinationRiskConfig(
            delta_limit=2.0, gamma_limit=0.5, vega_limit=200.0
        )
        self.risk_checker = CombinationRiskChecker(self.risk_config)
        self.lifecycle_service = CombinationLifecycleService()
        self.multiplier = 10.0  # 合约乘数

    def _create_straddle_combination(self) -> Combination:
        """创建一个 STRADDLE 组合（同标的、同到期日、同行权价、一 Call 一 Put）"""
        legs = [
            Leg(
                vt_symbol="m2509-C-2800.DCE",
                option_type="call",
                strike_price=2800.0,
                expiry_date="20250901",
                direction="short",
                volume=1,
                open_price=120.0,
            ),
            Leg(
                vt_symbol="m2509-P-2800.DCE",
                option_type="put",
                strike_price=2800.0,
                expiry_date="20250901",
                direction="short",
                volume=1,
                open_price=95.0,
            ),
        ]
        return Combination(
            combination_id="straddle-001",
            combination_type=CombinationType.STRADDLE,
            underlying_vt_symbol="m2509.DCE",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 15, 10, 30),
        )

    def _create_custom_combination(self) -> Combination:
        """创建一个 CUSTOM 组合（3 腿）"""
        legs = [
            Leg(
                vt_symbol="m2509-C-2800.DCE",
                option_type="call",
                strike_price=2800.0,
                expiry_date="20250901",
                direction="long",
                volume=2,
                open_price=120.0,
            ),
            Leg(
                vt_symbol="m2509-C-2900.DCE",
                option_type="call",
                strike_price=2900.0,
                expiry_date="20250901",
                direction="short",
                volume=1,
                open_price=80.0,
            ),
            Leg(
                vt_symbol="m2509-P-2700.DCE",
                option_type="put",
                strike_price=2700.0,
                expiry_date="20250901",
                direction="long",
                volume=1,
                open_price=60.0,
            ),
        ]
        return Combination(
            combination_id="custom-001",
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol="m2509.DCE",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 15, 11, 0),
        )

    # ========== 完整流程测试 ==========

    def test_straddle_full_workflow(self) -> None:
        """
        STRADDLE 组合完整流程测试

        流程：创建 → 注册 → 计算 Greeks → 计算 PnL → 风控检查 → 生成平仓指令 → 状态同步
        **Validates: Requirements 7.2, 7.3, 7.4**
        """
        # Step 1: 创建 STRADDLE 组合
        combination = self._create_straddle_combination()
        assert combination.combination_type == CombinationType.STRADDLE
        assert len(combination.legs) == 2

        # Step 2: 注册到 CombinationAggregate
        self.aggregate.register_combination(combination)
        assert self.aggregate.get_combination("straddle-001") is not None
        assert len(self.aggregate.get_combinations_by_symbol("m2509-C-2800.DCE")) == 1
        assert len(self.aggregate.get_combinations_by_symbol("m2509-P-2800.DCE")) == 1

        # Step 3: 计算 Greeks
        # 使用较小的 vega 值以确保风控检查通过
        greeks_map: Dict[str, GreeksResult] = {
            "m2509-C-2800.DCE": GreeksResult(delta=0.5, gamma=0.02, theta=-0.1, vega=8.0),
            "m2509-P-2800.DCE": GreeksResult(delta=-0.4, gamma=0.03, theta=-0.05, vega=7.0),
        }
        greeks = self.greeks_calculator.calculate(combination, greeks_map, self.multiplier)

        # 验证 Greeks 加权求和（short 方向 sign = -1）
        # Call leg: 0.5 * 1 * 10 * (-1) = -5.0
        # Put leg: -0.4 * 1 * 10 * (-1) = 4.0
        # Total delta = -5.0 + 4.0 = -1.0
        # Total vega = 8.0 * 1 * 10 * (-1) + 7.0 * 1 * 10 * (-1) = -80 - 70 = -150
        assert greeks.delta == pytest.approx(-1.0, abs=1e-6)
        assert greeks.vega == pytest.approx(-150.0, abs=1e-6)
        assert greeks.failed_legs == []

        # Step 4: 计算 PnL
        current_prices: Dict[str, float] = {
            "m2509-C-2800.DCE": 130.0,  # 上涨 10
            "m2509-P-2800.DCE": 85.0,   # 下跌 10
        }
        pnl = self.pnl_calculator.calculate(combination, current_prices, self.multiplier)

        # Call leg PnL: (130 - 120) * 1 * 10 * (-1) = -100
        # Put leg PnL: (85 - 95) * 1 * 10 * (-1) = 100
        # Total PnL = -100 + 100 = 0
        assert pnl.total_unrealized_pnl == pytest.approx(0.0, abs=1e-6)
        assert len(pnl.leg_details) == 2
        assert all(leg.price_available for leg in pnl.leg_details)

        # Step 5: 风控检查
        risk_result = self.risk_checker.check(greeks)
        assert risk_result.passed is True  # |delta| = 1.0 < 2.0

        # Step 6: 生成平仓指令
        close_instructions = self.lifecycle_service.generate_close_instructions(
            combination, current_prices
        )
        assert len(close_instructions) == 2

        # 验证平仓指令方向（short 腿平仓方向为 LONG）
        for instr in close_instructions:
            assert instr.direction == Direction.LONG
            assert instr.offset == Offset.CLOSE
            assert instr.volume == 1

        # Step 7: 状态同步 - 部分平仓
        closed_symbols: Set[str] = {"m2509-C-2800.DCE"}
        self.aggregate.sync_combination_status("m2509-C-2800.DCE", closed_symbols)

        updated_combo = self.aggregate.get_combination("straddle-001")
        assert updated_combo is not None
        assert updated_combo.status == CombinationStatus.PARTIALLY_CLOSED

        # 验证产生了 CombinationStatusChangedEvent
        events = self.aggregate.pop_domain_events()
        assert len(events) == 1
        assert isinstance(events[0], CombinationStatusChangedEvent)
        assert events[0].combination_id == "straddle-001"
        assert events[0].old_status == "active"
        assert events[0].new_status == "partially_closed"

        # Step 8: 状态同步 - 完全平仓
        closed_symbols = {"m2509-C-2800.DCE", "m2509-P-2800.DCE"}
        self.aggregate.sync_combination_status("m2509-P-2800.DCE", closed_symbols)

        updated_combo = self.aggregate.get_combination("straddle-001")
        assert updated_combo is not None
        assert updated_combo.status == CombinationStatus.CLOSED
        assert updated_combo.close_time is not None

        # 验证产生了第二个 CombinationStatusChangedEvent
        events = self.aggregate.pop_domain_events()
        assert len(events) == 1
        assert events[0].new_status == "closed"

    def test_custom_combination_full_workflow(self) -> None:
        """
        CUSTOM 组合完整流程测试

        流程：创建 → 注册 → 计算 Greeks → 计算 PnL → 风控检查 → 生成平仓指令
        **Validates: Requirements 7.2, 7.3, 7.4**
        """
        # Step 1: 创建 CUSTOM 组合
        combination = self._create_custom_combination()
        assert combination.combination_type == CombinationType.CUSTOM
        assert len(combination.legs) == 3

        # Step 2: 注册到 CombinationAggregate
        self.aggregate.register_combination(combination)
        assert self.aggregate.get_combination("custom-001") is not None

        # Step 3: 计算 Greeks
        greeks_map: Dict[str, GreeksResult] = {
            "m2509-C-2800.DCE": GreeksResult(delta=0.6, gamma=0.025, theta=-0.12, vega=18.0),
            "m2509-C-2900.DCE": GreeksResult(delta=0.4, gamma=0.02, theta=-0.08, vega=14.0),
            "m2509-P-2700.DCE": GreeksResult(delta=-0.3, gamma=0.015, theta=-0.06, vega=10.0),
        }
        greeks = self.greeks_calculator.calculate(combination, greeks_map, self.multiplier)

        # 验证 Greeks 加权求和
        # Leg 1 (long, vol=2): 0.6 * 2 * 10 * 1 = 12.0
        # Leg 2 (short, vol=1): 0.4 * 1 * 10 * (-1) = -4.0
        # Leg 3 (long, vol=1): -0.3 * 1 * 10 * 1 = -3.0
        # Total delta = 12.0 - 4.0 - 3.0 = 5.0
        assert greeks.delta == pytest.approx(5.0, abs=1e-6)
        assert greeks.failed_legs == []

        # Step 4: 计算 PnL
        current_prices: Dict[str, float] = {
            "m2509-C-2800.DCE": 125.0,
            "m2509-C-2900.DCE": 75.0,
            "m2509-P-2700.DCE": 65.0,
        }
        pnl = self.pnl_calculator.calculate(combination, current_prices, self.multiplier)

        # Leg 1: (125 - 120) * 2 * 10 * 1 = 100
        # Leg 2: (75 - 80) * 1 * 10 * (-1) = 50
        # Leg 3: (65 - 60) * 1 * 10 * 1 = 50
        # Total = 100 + 50 + 50 = 200
        assert pnl.total_unrealized_pnl == pytest.approx(200.0, abs=1e-6)

        # Step 5: 风控检查（delta=5.0 超过 limit=2.0）
        risk_result = self.risk_checker.check(greeks)
        assert risk_result.passed is False
        assert "delta" in risk_result.reject_reason

        # Step 6: 生成平仓指令
        close_instructions = self.lifecycle_service.generate_close_instructions(
            combination, current_prices
        )
        assert len(close_instructions) == 3

        # 验证各腿平仓方向
        instr_map = {instr.vt_symbol: instr for instr in close_instructions}
        # long 腿平仓方向为 SHORT
        assert instr_map["m2509-C-2800.DCE"].direction == Direction.SHORT
        assert instr_map["m2509-C-2800.DCE"].volume == 2
        # short 腿平仓方向为 LONG
        assert instr_map["m2509-C-2900.DCE"].direction == Direction.LONG
        assert instr_map["m2509-C-2900.DCE"].volume == 1
        # long 腿平仓方向为 SHORT
        assert instr_map["m2509-P-2700.DCE"].direction == Direction.SHORT
        assert instr_map["m2509-P-2700.DCE"].volume == 1

    def test_multiple_combinations_workflow(self) -> None:
        """
        多组合并行管理测试

        验证 CombinationAggregate 能正确管理多个组合，
        且状态同步只影响相关组合。
        **Validates: Requirements 7.2, 7.3, 7.4**
        """
        # 创建并注册两个组合
        straddle = self._create_straddle_combination()
        custom = self._create_custom_combination()

        self.aggregate.register_combination(straddle)
        self.aggregate.register_combination(custom)

        # 验证注册
        assert len(self.aggregate.get_active_combinations()) == 2
        assert len(self.aggregate.get_combinations_by_underlying("m2509.DCE")) == 2

        # 共享的 vt_symbol 应该关联到两个组合
        combos_for_call = self.aggregate.get_combinations_by_symbol("m2509-C-2800.DCE")
        assert len(combos_for_call) == 2

        # 平仓 straddle 的一个腿，不应影响 custom 组合
        closed_symbols: Set[str] = {"m2509-P-2800.DCE"}
        self.aggregate.sync_combination_status("m2509-P-2800.DCE", closed_symbols)

        # straddle 应该变为 PARTIALLY_CLOSED
        straddle_updated = self.aggregate.get_combination("straddle-001")
        assert straddle_updated is not None
        assert straddle_updated.status == CombinationStatus.PARTIALLY_CLOSED

        # custom 组合不应受影响（它没有 m2509-P-2800.DCE 这个腿）
        custom_updated = self.aggregate.get_combination("custom-001")
        assert custom_updated is not None
        assert custom_updated.status == CombinationStatus.ACTIVE

        # 验证只产生了一个事件
        events = self.aggregate.pop_domain_events()
        assert len(events) == 1
        assert events[0].combination_id == "straddle-001"

    def test_greeks_calculation_with_failed_legs(self) -> None:
        """
        测试 Greeks 计算时部分腿失败的情况

        验证失败的腿被记录到 failed_legs，其余腿正常计算。
        **Validates: Requirements 7.2**
        """
        combination = self._create_straddle_combination()
        self.aggregate.register_combination(combination)

        # 只提供一个腿的 Greeks，另一个腿失败
        greeks_map: Dict[str, GreeksResult] = {
            "m2509-C-2800.DCE": GreeksResult(delta=0.5, gamma=0.02, theta=-0.1, vega=15.0),
            "m2509-P-2800.DCE": GreeksResult(success=False, error_message="IV calc failed"),
        }
        greeks = self.greeks_calculator.calculate(combination, greeks_map, self.multiplier)

        # 只有 Call 腿参与计算
        assert greeks.delta == pytest.approx(0.5 * 1 * 10 * (-1), abs=1e-6)
        assert greeks.failed_legs == ["m2509-P-2800.DCE"]

    def test_pnl_calculation_with_missing_prices(self) -> None:
        """
        测试 PnL 计算时部分腿价格缺失的情况

        验证价格缺失的腿 PnL 为 0，且 price_available=False。
        **Validates: Requirements 7.2**
        """
        combination = self._create_straddle_combination()
        self.aggregate.register_combination(combination)

        # 只提供一个腿的价格
        current_prices: Dict[str, float] = {
            "m2509-C-2800.DCE": 130.0,
        }
        pnl = self.pnl_calculator.calculate(combination, current_prices, self.multiplier)

        # 只有 Call 腿有 PnL
        assert len(pnl.leg_details) == 2

        call_pnl = next(
            leg for leg in pnl.leg_details if leg.vt_symbol == "m2509-C-2800.DCE"
        )
        put_pnl = next(
            leg for leg in pnl.leg_details if leg.vt_symbol == "m2509-P-2800.DCE"
        )

        assert call_pnl.price_available is True
        assert call_pnl.unrealized_pnl == pytest.approx((130 - 120) * 1 * 10 * (-1), abs=1e-6)

        assert put_pnl.price_available is False
        assert put_pnl.unrealized_pnl == 0.0

        # 总 PnL 只包含有价格的腿
        assert pnl.total_unrealized_pnl == pytest.approx(-100.0, abs=1e-6)

    def test_risk_check_boundary_conditions(self) -> None:
        """
        测试风控检查的边界条件

        验证 Greeks 恰好等于阈值时通过，超过时失败。
        **Validates: Requirements 7.2**
        """
        # 恰好等于阈值 - 应该通过
        greeks_at_limit = CombinationGreeks(
            delta=2.0, gamma=0.5, vega=200.0
        )
        result = self.risk_checker.check(greeks_at_limit)
        assert result.passed is True

        # 略微超过阈值 - 应该失败
        greeks_over_limit = CombinationGreeks(
            delta=2.01, gamma=0.5, vega=200.0
        )
        result = self.risk_checker.check(greeks_over_limit)
        assert result.passed is False
        assert "delta" in result.reject_reason

    def test_lifecycle_service_open_instructions(self) -> None:
        """
        测试生命周期服务生成开仓指令

        验证为每个腿生成正确方向的开仓指令。
        **Validates: Requirements 7.2**
        """
        combination = self._create_straddle_combination()

        price_map: Dict[str, float] = {
            "m2509-C-2800.DCE": 120.0,
            "m2509-P-2800.DCE": 95.0,
        }
        open_instructions = self.lifecycle_service.generate_open_instructions(
            combination, price_map
        )

        assert len(open_instructions) == 2

        for instr in open_instructions:
            assert instr.offset == Offset.OPEN
            # short 腿开仓方向为 SHORT
            assert instr.direction == Direction.SHORT
            assert instr.volume == 1

    def test_aggregate_snapshot_roundtrip(self) -> None:
        """
        测试聚合根快照序列化往返一致性

        验证 to_snapshot/from_snapshot 能正确保存和恢复状态。
        **Validates: Requirements 7.2**
        """
        # 注册多个组合
        straddle = self._create_straddle_combination()
        custom = self._create_custom_combination()

        self.aggregate.register_combination(straddle)
        self.aggregate.register_combination(custom)

        # 生成快照
        snapshot = self.aggregate.to_snapshot()

        # 从快照恢复
        restored = CombinationAggregate.from_snapshot(snapshot)

        # 验证恢复的状态
        assert len(restored.get_active_combinations()) == 2
        assert restored.get_combination("straddle-001") is not None
        assert restored.get_combination("custom-001") is not None

        # 验证反向索引恢复
        assert len(restored.get_combinations_by_symbol("m2509-C-2800.DCE")) == 2

    def test_status_sync_no_event_when_no_change(self) -> None:
        """
        测试状态同步时，如果状态未变化则不产生事件

        **Validates: Requirements 7.3, 7.4**
        """
        combination = self._create_straddle_combination()
        self.aggregate.register_combination(combination)

        # 同步一个不属于任何组合的 symbol
        self.aggregate.sync_combination_status("unknown-symbol.DCE", set())

        # 不应产生任何事件
        events = self.aggregate.pop_domain_events()
        assert len(events) == 0

        # 组合状态不变
        combo = self.aggregate.get_combination("straddle-001")
        assert combo is not None
        assert combo.status == CombinationStatus.ACTIVE

    def test_adjust_instruction_generation(self) -> None:
        """
        测试调整指令生成

        验证增仓生成开仓指令，减仓生成平仓指令。
        **Validates: Requirements 7.2**
        """
        combination = self._create_straddle_combination()

        # 增仓：从 1 手增加到 3 手
        increase_instr = self.lifecycle_service.generate_adjust_instruction(
            combination,
            leg_vt_symbol="m2509-C-2800.DCE",
            new_volume=3,
            current_price=125.0,
        )
        assert increase_instr.offset == Offset.OPEN
        assert increase_instr.direction == Direction.SHORT  # short 腿增仓方向为 SHORT
        assert increase_instr.volume == 2  # 差额

        # 减仓：从 1 手减少到 0 手
        decrease_instr = self.lifecycle_service.generate_adjust_instruction(
            combination,
            leg_vt_symbol="m2509-P-2800.DCE",
            new_volume=0,
            current_price=90.0,
        )
        assert decrease_instr.offset == Offset.CLOSE
        assert decrease_instr.direction == Direction.LONG  # short 腿减仓方向为 LONG
        assert decrease_instr.volume == 1

    def test_invalid_combination_registration_rejected(self) -> None:
        """
        测试无效组合注册被拒绝

        验证结构不满足约束的组合无法注册。
        **Validates: Requirements 7.2**
        """
        # 创建一个无效的 STRADDLE（只有 1 腿）
        invalid_legs = [
            Leg(
                vt_symbol="m2509-C-2800.DCE",
                option_type="call",
                strike_price=2800.0,
                expiry_date="20250901",
                direction="short",
                volume=1,
                open_price=120.0,
            ),
        ]
        invalid_combo = Combination(
            combination_id="invalid-001",
            combination_type=CombinationType.STRADDLE,
            underlying_vt_symbol="m2509.DCE",
            legs=invalid_legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 15, 10, 30),
        )

        # 注册应该失败
        with pytest.raises(ValueError, match="STRADDLE 需要恰好 2 腿"):
            self.aggregate.register_combination(invalid_combo)

        # 聚合根中不应有任何组合
        assert self.aggregate.get_combination("invalid-001") is None
