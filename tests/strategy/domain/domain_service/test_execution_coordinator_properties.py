"""
ExecutionCoordinator 属性测试

Feature: execution-service-enhancement, Property 6: 协调器使用自适应价格计算
Feature: execution-service-enhancement, Property 7: 协调器注册子单到超时管理

**Validates: Requirements 4.2, 4.3**
"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing domain modules
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

from src.strategy.domain.domain_service.execution.execution_coordinator import (  # noqa: E402
    ExecutionCoordinator,
)
from src.strategy.domain.domain_service.execution.smart_order_executor import (  # noqa: E402
    SmartOrderExecutor,
)
from src.strategy.domain.domain_service.execution.advanced_order_scheduler import (  # noqa: E402
    AdvancedOrderScheduler,
)
from src.strategy.domain.value_object.trading.order_execution import (  # noqa: E402
    OrderExecutionConfig,
    AdvancedSchedulerConfig,
)
from src.strategy.domain.value_object.trading.order_instruction import (  # noqa: E402
    OrderInstruction,
    Direction,
    Offset,
    OrderType,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_directions = st.sampled_from([Direction.LONG, Direction.SHORT])
_offsets = st.sampled_from([Offset.OPEN, Offset.CLOSE])
_order_types = st.sampled_from([OrderType.LIMIT, OrderType.MARKET, OrderType.FAK, OrderType.FOK])

_positive_price = st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
_price_tick = st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)
_slippage_ticks = st.integers(min_value=0, max_value=10)
_volume = st.integers(min_value=1, max_value=1000)
_batch_size = st.integers(min_value=1, max_value=100)

_vt_symbol = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="._"),
    min_size=3,
    max_size=20,
)


@st.composite
def _order_instruction(draw):
    """Generate a random OrderInstruction with positive volume and price."""
    return OrderInstruction(
        vt_symbol=draw(_vt_symbol),
        direction=draw(_directions),
        offset=draw(_offsets),
        volume=draw(_volume),
        price=draw(_positive_price),
        signal="test_signal",
        order_type=draw(_order_types),
    )


# ---------------------------------------------------------------------------
# Property 6: 协调器使用自适应价格计算
# Feature: execution-service-enhancement, Property 6: 协调器使用自适应价格计算
# **Validates: Requirements 4.2**
# ---------------------------------------------------------------------------


class TestProperty6CoordinatorUsesAdaptivePricing:
    """
    对于任意待提交子单和有效的 bid/ask 价格，
    ExecutionCoordinator.process_pending_children 返回的指令价格
    应等于 SmartOrderExecutor.calculate_adaptive_price 对该子单计算的结果
    （经 round_price_to_tick 对齐后）。
    """

    @given(
        instruction=_order_instruction(),
        batch_size=_batch_size,
        bid_price=_positive_price,
        ask_price=_positive_price,
        price_tick=_price_tick,
        slippage_ticks=_slippage_ticks,
    )
    @settings(max_examples=100)
    def test_coordinator_uses_adaptive_pricing(
        self,
        instruction: OrderInstruction,
        batch_size: int,
        bid_price: float,
        ask_price: float,
        price_tick: float,
        slippage_ticks: int,
    ):
        # Setup executor with specific slippage
        config = OrderExecutionConfig(slippage_ticks=slippage_ticks, price_tick=price_tick)
        executor = SmartOrderExecutor(config)
        scheduler = AdvancedOrderScheduler()
        coordinator = ExecutionCoordinator(executor=executor, scheduler=scheduler)

        # Submit an iceberg order to create child orders
        order = scheduler.submit_iceberg(instruction, batch_size)

        # Use a time that makes all iceberg children eligible (first child is always pending)
        current_time = datetime.now()
        instructions, events = coordinator.process_pending_children(
            current_time=current_time,
            bid_price=bid_price,
            ask_price=ask_price,
            price_tick=price_tick,
        )

        # Get the same pending children the coordinator would have seen
        pending_children = scheduler.get_pending_children(current_time)

        # Each returned instruction's price should match the adaptive price calculation
        for i, final_instr in enumerate(instructions):
            # Build the child instruction as the coordinator does internally
            child = pending_children[i]
            parent_order = scheduler.get_order(child.parent_id)
            original = parent_order.request.instruction

            child_instruction = OrderInstruction(
                vt_symbol=original.vt_symbol,
                direction=original.direction,
                offset=original.offset,
                volume=child.volume,
                price=original.price,
                signal=original.signal,
                order_type=original.order_type,
            )

            expected_adaptive = executor.calculate_adaptive_price(
                child_instruction, bid_price, ask_price, price_tick
            )
            expected_rounded = executor.round_price_to_tick(expected_adaptive, price_tick)

            assert final_instr.price == pytest.approx(expected_rounded, abs=1e-9), (
                f"Instruction price {final_instr.price} != expected {expected_rounded} "
                f"(adaptive={expected_adaptive}, tick={price_tick})"
            )


# ---------------------------------------------------------------------------
# Property 7: 协调器注册子单到超时管理
# Feature: execution-service-enhancement, Property 7: 协调器注册子单到超时管理
# **Validates: Requirements 4.3**
# ---------------------------------------------------------------------------


class TestProperty7CoordinatorRegistersChildrenToTimeout:
    """
    对于任意通过 ExecutionCoordinator.on_child_order_submitted 注册的子单，
    该子单对应的 vt_orderid 应出现在 SmartOrderExecutor 的 _orders 字典中。
    """

    @given(
        child_id=st.text(min_size=1, max_size=30),
        vt_orderid=st.text(min_size=1, max_size=30),
        instruction=_order_instruction(),
    )
    @settings(max_examples=100)
    def test_coordinator_registers_children_to_timeout(
        self,
        child_id: str,
        vt_orderid: str,
        instruction: OrderInstruction,
    ):
        config = OrderExecutionConfig()
        executor = SmartOrderExecutor(config)
        scheduler = AdvancedOrderScheduler()
        coordinator = ExecutionCoordinator(executor=executor, scheduler=scheduler)

        # Register a child order via the coordinator
        coordinator.on_child_order_submitted(child_id, vt_orderid, instruction)

        # The vt_orderid should now be tracked in executor._orders
        assert vt_orderid in executor._orders, (
            f"vt_orderid '{vt_orderid}' not found in executor._orders after registration"
        )

        # Verify the registered order has the correct instruction
        managed = executor._orders[vt_orderid]
        assert managed.instruction == instruction
        assert managed.is_active is True
