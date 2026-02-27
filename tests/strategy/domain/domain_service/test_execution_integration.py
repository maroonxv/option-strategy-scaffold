"""
执行服务集成测试

测试 ExecutionCoordinator 协调 SmartOrderExecutor 与 AdvancedOrderScheduler 的完整工作流程：
1. 高级订单子单使用自适应价格计算后的价格
2. 子单超时后触发重试流程
3. 重试耗尽时产生 OrderRetryExhaustedEvent 事件
4. 高级订单全部子单成交后产生完成事件

Validates: Requirements 8.1, 8.2, 8.3, 8.4
"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

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
from src.strategy.domain.event.event_types import (  # noqa: E402
    OrderRetryExhaustedEvent,
    IcebergCompleteEvent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_instruction(
    vt_symbol: str = "rb2501.SHFE",
    direction: Direction = Direction.LONG,
    offset: Offset = Offset.OPEN,
    volume: int = 10,
    price: float = 4000.0,
) -> OrderInstruction:
    return OrderInstruction(
        vt_symbol=vt_symbol,
        direction=direction,
        offset=offset,
        volume=volume,
        price=price,
        signal="test",
        order_type=OrderType.LIMIT,
    )


# ===========================================================================
# Test 1: 子单使用自适应价格 (Req 8.1)
# ===========================================================================


class TestChildOrdersUseAdaptivePricing:
    """Validates: Requirements 8.1"""

    def test_child_orders_use_adaptive_pricing(self):
        """高级订单子单经 coordinator 处理后，价格应为自适应计算结果而非原始价格。"""
        slippage_ticks = 3
        price_tick = 0.2
        bid_price = 4000.0
        ask_price = 4002.0

        config = OrderExecutionConfig(slippage_ticks=slippage_ticks, price_tick=price_tick)
        executor = SmartOrderExecutor(config)
        scheduler = AdvancedOrderScheduler()
        coordinator = ExecutionCoordinator(executor=executor, scheduler=scheduler)

        # 提交一个买入冰山单 (LONG)，volume=10, batch_size=5 → 2 个子单
        instruction = _make_instruction(direction=Direction.LONG, volume=10, price=4000.0)
        order = scheduler.submit_iceberg(instruction, batch_size=5)

        # 处理待提交子单
        current_time = datetime.now()
        instructions, events = coordinator.process_pending_children(
            current_time=current_time,
            bid_price=bid_price,
            ask_price=ask_price,
            price_tick=price_tick,
        )

        # 冰山单一次只提交一个子单
        assert len(instructions) == 1

        # 买入方向自适应价格 = ask_price + slippage_ticks * price_tick
        expected_adaptive = ask_price + slippage_ticks * price_tick  # 4002.0 + 3*0.2 = 4002.6
        expected_rounded = executor.round_price_to_tick(expected_adaptive, price_tick)

        assert instructions[0].price == pytest.approx(expected_rounded, abs=1e-9)
        # 价格不应等于原始价格
        assert instructions[0].price != instruction.price

    def test_sell_child_orders_use_adaptive_pricing(self):
        """卖出方向子单的自适应价格 = bid_price - slippage_ticks * price_tick。"""
        slippage_ticks = 2
        price_tick = 0.5
        bid_price = 5000.0
        ask_price = 5002.0

        config = OrderExecutionConfig(slippage_ticks=slippage_ticks, price_tick=price_tick)
        executor = SmartOrderExecutor(config)
        scheduler = AdvancedOrderScheduler()
        coordinator = ExecutionCoordinator(executor=executor, scheduler=scheduler)

        instruction = _make_instruction(direction=Direction.SHORT, volume=5, price=5000.0)
        scheduler.submit_iceberg(instruction, batch_size=5)

        instructions, _ = coordinator.process_pending_children(
            current_time=datetime.now(),
            bid_price=bid_price,
            ask_price=ask_price,
            price_tick=price_tick,
        )

        assert len(instructions) == 1
        # 卖出方向: bid_price - slippage_ticks * price_tick = 5000.0 - 2*0.5 = 4999.0
        expected_adaptive = bid_price - slippage_ticks * price_tick
        expected_rounded = executor.round_price_to_tick(expected_adaptive, price_tick)
        assert instructions[0].price == pytest.approx(expected_rounded, abs=1e-9)


# ===========================================================================
# Test 2: 子单超时触发重试 (Req 8.2)
# ===========================================================================


class TestChildTimeoutTriggersRetry:
    """Validates: Requirements 8.2"""

    def test_child_timeout_triggers_retry(self):
        """子单注册后超时，check_timeouts_and_retry 应返回撤销 ID 和重试指令。"""
        timeout_seconds = 1
        price_tick = 0.2

        config = OrderExecutionConfig(
            timeout_seconds=timeout_seconds,
            max_retries=3,
            slippage_ticks=2,
            price_tick=price_tick,
        )
        executor = SmartOrderExecutor(config)
        scheduler = AdvancedOrderScheduler()
        coordinator = ExecutionCoordinator(executor=executor, scheduler=scheduler)

        # 注册一个子单
        instruction = _make_instruction(price=4000.0)
        vt_orderid = "order_001"
        coordinator.on_child_order_submitted("child_001", vt_orderid, instruction)

        # 确认已注册
        assert vt_orderid in executor._orders

        # 手动设置提交时间为 2 秒前，使其超时
        managed = executor._orders[vt_orderid]
        managed.submit_time = datetime.now() - timedelta(seconds=2)

        # 检查超时和重试
        cancel_ids, retry_instructions, events = coordinator.check_timeouts_and_retry(
            current_time=datetime.now(),
            price_tick=price_tick,
        )

        # 应有一个需撤销的订单
        assert vt_orderid in cancel_ids
        # 应有一个重试指令（因为 max_retries=3，第一次超时还可以重试）
        assert len(retry_instructions) == 1
        assert retry_instructions[0].vt_symbol == instruction.vt_symbol


# ===========================================================================
# Test 3: 重试耗尽产生 OrderRetryExhaustedEvent (Req 8.3)
# ===========================================================================


class TestRetryExhaustedProducesEvent:
    """Validates: Requirements 8.3"""

    def test_retry_exhausted_produces_event(self):
        """max_retries=0 时，第一次超时即耗尽重试，应产生 OrderRetryExhaustedEvent。"""
        timeout_seconds = 1
        price_tick = 0.2

        config = OrderExecutionConfig(
            timeout_seconds=timeout_seconds,
            max_retries=0,  # 不允许重试
            slippage_ticks=2,
            price_tick=price_tick,
        )
        executor = SmartOrderExecutor(config)
        scheduler = AdvancedOrderScheduler()
        coordinator = ExecutionCoordinator(executor=executor, scheduler=scheduler)

        # 注册子单
        instruction = _make_instruction(
            vt_symbol="IF2506.CFFEX", price=3800.0
        )
        vt_orderid = "order_exhausted"
        coordinator.on_child_order_submitted("child_ex", vt_orderid, instruction)

        # 设置提交时间为过去，使其超时
        managed = executor._orders[vt_orderid]
        managed.submit_time = datetime.now() - timedelta(seconds=2)

        # 检查超时和重试
        cancel_ids, retry_instructions, events = coordinator.check_timeouts_and_retry(
            current_time=datetime.now(),
            price_tick=price_tick,
        )

        # 应有撤销 ID
        assert vt_orderid in cancel_ids
        # 不应有重试指令（重试已耗尽）
        assert len(retry_instructions) == 0

        # 应产生 OrderRetryExhaustedEvent
        retry_exhausted_events = [
            e for e in events if isinstance(e, OrderRetryExhaustedEvent)
        ]
        assert len(retry_exhausted_events) == 1

        evt = retry_exhausted_events[0]
        assert evt.vt_symbol == "IF2506.CFFEX"
        assert evt.total_retries == 0
        assert evt.original_price == 3800.0
        assert evt.final_price == 3800.0


# ===========================================================================
# Test 4: 全部子单成交产生完成事件 (Req 8.4)
# ===========================================================================


class TestAllChildrenFilledProducesCompleteEvent:
    """Validates: Requirements 8.4"""

    def test_all_children_filled_produces_complete_event(self):
        """冰山单全部子单成交后，on_child_filled 应返回 IcebergCompleteEvent。"""
        scheduler = AdvancedOrderScheduler()
        executor = SmartOrderExecutor(OrderExecutionConfig())
        coordinator = ExecutionCoordinator(executor=executor, scheduler=scheduler)

        # 提交冰山单: volume=5, batch_size=5 → 只有 1 个子单
        instruction = _make_instruction(
            vt_symbol="rb2501.SHFE", volume=5, price=4000.0
        )
        order = scheduler.submit_iceberg(instruction, batch_size=5)

        assert len(order.child_orders) == 1
        child = order.child_orders[0]

        # 子单成交
        events = coordinator.on_child_filled(child.child_id)

        # 应产生 IcebergCompleteEvent
        assert len(events) == 1
        assert isinstance(events[0], IcebergCompleteEvent)

        evt = events[0]
        assert evt.order_id == order.order_id
        assert evt.vt_symbol == "rb2501.SHFE"
        assert evt.total_volume == 5
        assert evt.filled_volume == 5

    def test_multiple_children_filled_sequentially(self):
        """多个子单依次成交，只有最后一个成交时才产生完成事件。"""
        scheduler = AdvancedOrderScheduler()
        executor = SmartOrderExecutor(OrderExecutionConfig())
        coordinator = ExecutionCoordinator(executor=executor, scheduler=scheduler)

        # 提交冰山单: volume=10, batch_size=3 → 4 个子单 (3+3+3+1)
        instruction = _make_instruction(volume=10, price=4000.0)
        order = scheduler.submit_iceberg(instruction, batch_size=3)

        assert len(order.child_orders) == 4

        # 前 3 个子单成交，不应产生完成事件
        for child in order.child_orders[:3]:
            events = coordinator.on_child_filled(child.child_id)
            assert not any(isinstance(e, IcebergCompleteEvent) for e in events)

        # 最后一个子单成交，应产生完成事件
        events = coordinator.on_child_filled(order.child_orders[3].child_id)
        complete_events = [e for e in events if isinstance(e, IcebergCompleteEvent)]
        assert len(complete_events) == 1
        assert complete_events[0].filled_volume == 10
