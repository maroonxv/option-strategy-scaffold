"""
执行服务序列化 round-trip 属性测试

Feature: execution-service-enhancement, Property 10: SmartOrderExecutor 序列化 round-trip
Feature: execution-service-enhancement, Property 11: AdvancedOrderScheduler 序列化 round-trip

**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**
"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

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

from src.strategy.domain.domain_service.execution.smart_order_executor import (  # noqa: E402
    SmartOrderExecutor,
)
from src.strategy.domain.domain_service.execution.advanced_order_scheduler import (  # noqa: E402
    AdvancedOrderScheduler,
)
from src.strategy.domain.value_object.trading.order_execution import (  # noqa: E402
    OrderExecutionConfig,
    AdvancedSchedulerConfig,
    ManagedOrder,
)
from src.strategy.domain.value_object.trading.order_instruction import (  # noqa: E402
    OrderInstruction,
    Direction,
    Offset,
    OrderType,
)


# ---------------------------------------------------------------------------
# Hypothesis 策略
# ---------------------------------------------------------------------------

_vt_symbols = st.sampled_from(["IO2506-C-4000.CFFEX", "rb2501.SHFE", "IF2506.CFFEX"])
_directions = st.sampled_from([Direction.LONG, Direction.SHORT])
_offsets = st.sampled_from([Offset.OPEN, Offset.CLOSE])
_order_types = st.sampled_from([OrderType.LIMIT, OrderType.MARKET, OrderType.FAK, OrderType.FOK])
_volumes = st.integers(min_value=1, max_value=1000)
_prices = st.floats(min_value=0.1, max_value=100000.0, allow_nan=False, allow_infinity=False)

_order_instructions = st.builds(
    OrderInstruction,
    vt_symbol=_vt_symbols,
    direction=_directions,
    offset=_offsets,
    volume=_volumes,
    price=_prices,
    signal=st.just("test"),
    order_type=_order_types,
)

# 固定的 submit_time 列表（避免 hypothesis 生成不可序列化的 datetime）
_submit_times = st.builds(
    datetime,
    year=st.just(2026),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
)

_managed_orders = st.builds(
    ManagedOrder,
    vt_orderid=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
        min_size=1,
        max_size=20,
    ),
    instruction=_order_instructions,
    submit_time=_submit_times,
    retry_count=st.integers(min_value=0, max_value=10),
    is_active=st.booleans(),
)

# OrderExecutionConfig 策略
_exec_configs = st.builds(
    OrderExecutionConfig,
    timeout_seconds=st.integers(min_value=1, max_value=300),
    max_retries=st.integers(min_value=0, max_value=20),
    slippage_ticks=st.integers(min_value=0, max_value=50),
    price_tick=st.floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False),
)

# AdvancedSchedulerConfig 策略
_scheduler_configs = st.builds(
    AdvancedSchedulerConfig,
    default_batch_size=st.integers(min_value=1, max_value=500),
    default_interval_seconds=st.integers(min_value=1, max_value=3600),
    default_num_slices=st.integers(min_value=1, max_value=100),
    default_volume_randomize_ratio=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    default_price_offset_ticks=st.integers(min_value=0, max_value=50),
    default_price_tick=st.floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False),
)


# ===========================================================================
# Feature: execution-service-enhancement, Property 10: SmartOrderExecutor 序列化 round-trip
# ===========================================================================


class TestProperty10SmartOrderExecutorRoundTrip:
    """
    Property 10: SmartOrderExecutor 序列化 round-trip

    对于任意有效的 SmartOrderExecutor 内部状态（包含任意数量的 ManagedOrder），
    from_dict(executor.to_dict()) 应产生等价的内部状态：config 字段相同，
    _orders 字典中每个 ManagedOrder 的所有字段相同。

    **Validates: Requirements 9.1, 9.2, 9.3**
    """

    @given(
        config=_exec_configs,
        orders=st.lists(_managed_orders, min_size=0, max_size=5),
    )
    @settings(max_examples=100)
    def test_smart_order_executor_round_trip(
        self,
        config: OrderExecutionConfig,
        orders: list,
    ):
        """
        # Feature: execution-service-enhancement, Property 10: SmartOrderExecutor 序列化 round-trip

        **Validates: Requirements 9.1, 9.2, 9.3**
        """
        # 构建 executor 并填充 _orders
        executor = SmartOrderExecutor(config)
        for order in orders:
            executor._orders[order.vt_orderid] = order

        # 序列化 → 反序列化
        data = executor.to_dict()
        restored = SmartOrderExecutor.from_dict(data)

        # 验证 config 字段相同
        assert restored.config.timeout_seconds == config.timeout_seconds
        assert restored.config.max_retries == config.max_retries
        assert restored.config.slippage_ticks == config.slippage_ticks
        assert restored.config.price_tick == config.price_tick

        # 验证 _orders 数量相同
        assert len(restored._orders) == len(executor._orders), (
            f"订单数量不匹配: 期望 {len(executor._orders)}, 实际 {len(restored._orders)}"
        )

        # 验证每个 ManagedOrder 的所有字段相同
        for oid, original_order in executor._orders.items():
            assert oid in restored._orders, f"缺少订单 {oid}"
            restored_order = restored._orders[oid]

            assert restored_order.vt_orderid == original_order.vt_orderid
            assert restored_order.retry_count == original_order.retry_count
            assert restored_order.is_active == original_order.is_active
            assert restored_order.submit_time == original_order.submit_time

            # 验证 instruction 字段
            orig_instr = original_order.instruction
            rest_instr = restored_order.instruction
            assert rest_instr.vt_symbol == orig_instr.vt_symbol
            assert rest_instr.direction == orig_instr.direction
            assert rest_instr.offset == orig_instr.offset
            assert rest_instr.volume == orig_instr.volume
            assert abs(rest_instr.price - orig_instr.price) < 1e-10
            assert rest_instr.signal == orig_instr.signal
            assert rest_instr.order_type == orig_instr.order_type


# ===========================================================================
# Feature: execution-service-enhancement, Property 11: AdvancedOrderScheduler 序列化 round-trip
# ===========================================================================


class TestProperty11AdvancedOrderSchedulerRoundTrip:
    """
    Property 11: AdvancedOrderScheduler 序列化 round-trip

    对于任意有效的 AdvancedOrderScheduler 内部状态（包含任意数量的 AdvancedOrder），
    from_dict(scheduler.to_dict()) 应产生等价的内部状态：config 字段相同，
    _orders 字典中每个 AdvancedOrder 的所有字段相同。

    **Validates: Requirements 9.4, 9.5**
    """

    @given(
        config=_scheduler_configs,
        instruction=_order_instructions,
        batch_size=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100)
    def test_advanced_order_scheduler_round_trip(
        self,
        config: AdvancedSchedulerConfig,
        instruction: OrderInstruction,
        batch_size: int,
    ):
        """
        # Feature: execution-service-enhancement, Property 11: AdvancedOrderScheduler 序列化 round-trip

        **Validates: Requirements 9.4, 9.5**
        """
        # 创建 scheduler 并通过 submit_iceberg 填充 _orders
        scheduler = AdvancedOrderScheduler(config)
        scheduler.submit_iceberg(instruction=instruction, batch_size=batch_size)

        # 序列化 → 反序列化
        data = scheduler.to_dict()
        restored = AdvancedOrderScheduler.from_dict(data)

        # 验证 config 字段相同
        assert restored.config.default_batch_size == config.default_batch_size
        assert restored.config.default_interval_seconds == config.default_interval_seconds
        assert restored.config.default_num_slices == config.default_num_slices
        assert restored.config.default_volume_randomize_ratio == config.default_volume_randomize_ratio
        assert restored.config.default_price_offset_ticks == config.default_price_offset_ticks
        assert restored.config.default_price_tick == config.default_price_tick

        # 验证 _orders 数量相同
        assert len(restored._orders) == len(scheduler._orders), (
            f"订单数量不匹配: 期望 {len(scheduler._orders)}, 实际 {len(restored._orders)}"
        )

        # 验证每个 AdvancedOrder 的所有字段相同
        for oid, original_order in scheduler._orders.items():
            assert oid in restored._orders, f"缺少订单 {oid}"
            rest_order = restored._orders[oid]

            assert rest_order.order_id == original_order.order_id
            assert rest_order.status == original_order.status
            assert rest_order.filled_volume == original_order.filled_volume
            assert rest_order.created_time == original_order.created_time

            # 验证 request 字段
            assert rest_order.request.order_type == original_order.request.order_type
            assert rest_order.request.batch_size == original_order.request.batch_size
            assert rest_order.request.time_window_seconds == original_order.request.time_window_seconds
            assert rest_order.request.num_slices == original_order.request.num_slices
            assert rest_order.request.volume_profile == original_order.request.volume_profile
            assert rest_order.request.interval_seconds == original_order.request.interval_seconds
            assert rest_order.request.per_order_volume == original_order.request.per_order_volume

            # 验证 request.instruction 字段
            orig_instr = original_order.request.instruction
            rest_instr = rest_order.request.instruction
            assert rest_instr.vt_symbol == orig_instr.vt_symbol
            assert rest_instr.direction == orig_instr.direction
            assert rest_instr.offset == orig_instr.offset
            assert rest_instr.volume == orig_instr.volume
            assert abs(rest_instr.price - orig_instr.price) < 1e-10
            assert rest_instr.signal == orig_instr.signal
            assert rest_instr.order_type == orig_instr.order_type

            # 验证 child_orders
            assert len(rest_order.child_orders) == len(original_order.child_orders), (
                f"子单数量不匹配: 期望 {len(original_order.child_orders)}, "
                f"实际 {len(rest_order.child_orders)}"
            )
            for orig_child, rest_child in zip(original_order.child_orders, rest_order.child_orders):
                assert rest_child.child_id == orig_child.child_id
                assert rest_child.parent_id == orig_child.parent_id
                assert rest_child.volume == orig_child.volume
                assert rest_child.scheduled_time == orig_child.scheduled_time
                assert rest_child.is_submitted == orig_child.is_submitted
                assert rest_child.is_filled == orig_child.is_filled
                assert abs(rest_child.price_offset - orig_child.price_offset) < 1e-10

            # 验证 slice_schedule
            assert len(rest_order.slice_schedule) == len(original_order.slice_schedule), (
                f"调度计划数量不匹配: 期望 {len(original_order.slice_schedule)}, "
                f"实际 {len(rest_order.slice_schedule)}"
            )
            for orig_slice, rest_slice in zip(original_order.slice_schedule, rest_order.slice_schedule):
                assert rest_slice.scheduled_time == orig_slice.scheduled_time
                assert rest_slice.volume == orig_slice.volume
