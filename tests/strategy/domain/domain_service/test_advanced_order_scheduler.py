"""
AdvancedOrderScheduler 属性测试和单元测试

使用 hypothesis 验证冰山单、TWAP、VWAP 拆分逻辑和生命周期管理。
"""
import json
import math
import pytest
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings, assume

from src.strategy.domain.domain_service.execution.advanced_order_scheduler import AdvancedOrderScheduler
from src.strategy.domain.value_object.trading.order_instruction import (
    OrderInstruction, Direction, Offset, OrderType,
)
from src.strategy.domain.value_object.trading.advanced_order import (
    AdvancedOrder, AdvancedOrderStatus, AdvancedOrderType,
)
from src.strategy.domain.event.event_types import (
    IcebergCompleteEvent, IcebergCancelledEvent,
    TWAPCompleteEvent, VWAPCompleteEvent,
    ClassicIcebergCompleteEvent, ClassicIcebergCancelledEvent,
    EnhancedTWAPCompleteEvent,
)


# ========== 生成器 ==========

def make_instruction(volume: int) -> OrderInstruction:
    return OrderInstruction(
        vt_symbol="IO2506-C-4000.CFFEX",
        direction=Direction.LONG,
        offset=Offset.OPEN,
        volume=volume,
        price=100.0,
        signal="test",
    )


instruction_st = st.builds(
    OrderInstruction,
    vt_symbol=st.just("IO2506-C-4000.CFFEX"),
    direction=st.sampled_from([Direction.LONG, Direction.SHORT]),
    offset=st.sampled_from([Offset.OPEN, Offset.CLOSE]),
    volume=st.integers(min_value=1, max_value=1000),
    price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    signal=st.just("test_signal"),
    order_type=st.just(OrderType.LIMIT),
)


class TestIcebergSplitProperty:
    """Property 1: 冰山单拆分正确性"""

    # Feature: advanced-order-hedging-volsurface, Property 1: 冰山单拆分正确性
    # Validates: Requirements 1.1, 1.5
    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=1, max_value=1000),
        batch_size=st.integers(min_value=1, max_value=100),
    )
    def test_property1_iceberg_split_correctness(self, total_volume, batch_size):
        """Property 1: 每个子单 volume <= batch_size, sum == total_volume, count == ceil(total/batch)"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        order = scheduler.submit_iceberg(instruction, batch_size)

        # 每个子单 volume <= batch_size
        for child in order.child_orders:
            assert child.volume <= batch_size

        # sum == total_volume
        assert sum(c.volume for c in order.child_orders) == total_volume

        # count == ceil(total_volume / batch_size)
        expected_count = math.ceil(total_volume / batch_size)
        assert len(order.child_orders) == expected_count


class TestTWAPScheduleProperty:
    """Property 3: TWAP 调度正确性"""

    # Feature: advanced-order-hedging-volsurface, Property 3: TWAP 调度正确性
    # Validates: Requirements 2.1, 2.3, 2.4
    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=1, max_value=1000),
        time_window=st.integers(min_value=10, max_value=3600),
        num_slices=st.integers(min_value=2, max_value=50),
    )
    def test_property3_twap_schedule_correctness(self, total_volume, time_window, num_slices):
        """Property 3: 各片量差<=1, sum==total, 时间间隔==window/slices (±1s)"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        start = datetime(2025, 1, 1, 9, 0, 0)
        order = scheduler.submit_twap(instruction, time_window, num_slices, start)

        volumes = [c.volume for c in order.child_orders]

        # 各片量差 <= 1 (均匀分配的整数舍入)
        assert max(volumes) - min(volumes) <= 1

        # sum == total_volume
        assert sum(volumes) == total_volume

        # 时间间隔 == time_window / num_slices (±1s)
        expected_interval = time_window / num_slices
        for i in range(1, len(order.child_orders)):
            t0 = order.child_orders[i - 1].scheduled_time
            t1 = order.child_orders[i].scheduled_time
            actual_interval = (t1 - t0).total_seconds()
            assert abs(actual_interval - expected_interval) <= 1.0


class TestVWAPAllocationProperty:
    """Property 4: VWAP 分配正确性"""

    # Feature: advanced-order-hedging-volsurface, Property 4: VWAP 分配正确性
    # Validates: Requirements 3.1, 3.2, 3.3, 3.4
    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=1, max_value=1000),
        volume_profile=st.lists(
            st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=20,
        ),
    )
    def test_property4_vwap_allocation_correctness(self, total_volume, volume_profile):
        """Property 4: 各片按权重比例分配, sum==total"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        start = datetime(2025, 1, 1, 9, 0, 0)
        order = scheduler.submit_vwap(instruction, 300, volume_profile, start)

        volumes = [c.volume for c in order.child_orders]

        # sum == total_volume
        assert sum(volumes) == total_volume

        # 各片按权重比例分配 (允许整数舍入误差 ±1)
        total_weight = sum(volume_profile)
        for i, w in enumerate(volume_profile):
            expected = total_volume * w / total_weight
            assert abs(volumes[i] - expected) <= 1.0

        # 片数 == profile 长度
        assert len(volumes) == len(volume_profile)


class TestIcebergLifecycleProperty:
    """Property 2: 冰山单生命周期"""

    # Feature: advanced-order-hedging-volsurface, Property 2: 冰山单生命周期
    # Validates: Requirements 1.2, 1.3, 1.4
    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=1, max_value=200),
        batch_size=st.integers(min_value=1, max_value=50),
    )
    def test_property2_iceberg_lifecycle(self, total_volume, batch_size):
        """Property 2: 逐批成交后下一批可用, 全部成交产生完成事件, 取消产生取消事件"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        order = scheduler.submit_iceberg(instruction, batch_size)
        now = datetime(2025, 1, 1, 9, 0, 0)
        n = len(order.child_orders)

        all_events = []
        for i in range(n):
            # 当前应有 1 个 pending child
            pending = scheduler.get_pending_children(now)
            assert len(pending) == 1
            child = pending[0]
            child.is_submitted = True

            # 成交
            events = scheduler.on_child_filled(child.child_id)
            all_events.extend(events)

        # 全部成交后状态为 COMPLETED
        final_order = scheduler.get_order(order.order_id)
        assert final_order.status == AdvancedOrderStatus.COMPLETED
        assert final_order.filled_volume == total_volume

        # 恰好产生 1 个 IcebergCompleteEvent
        complete_events = [e for e in all_events if isinstance(e, IcebergCompleteEvent)]
        assert len(complete_events) == 1

    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=2, max_value=200),
        batch_size=st.integers(min_value=1, max_value=50),
        cancel_after=st.integers(min_value=0, max_value=10),
    )
    def test_property2_iceberg_cancel(self, total_volume, batch_size, cancel_after):
        """Property 2: 取消后产生 IcebergCancelledEvent，filled + remaining == total"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        order = scheduler.submit_iceberg(instruction, batch_size)
        n = len(order.child_orders)
        now = datetime(2025, 1, 1, 9, 0, 0)

        # 成交前 cancel_after 个子单 (不超过 n-1 以确保有剩余)
        fills = min(cancel_after, n - 1)
        for i in range(fills):
            pending = scheduler.get_pending_children(now)
            if pending:
                pending[0].is_submitted = True
                scheduler.on_child_filled(pending[0].child_id)

        cancel_ids, events = scheduler.cancel_order(order.order_id)
        final_order = scheduler.get_order(order.order_id)
        assert final_order.status == AdvancedOrderStatus.CANCELLED

        cancel_events = [e for e in events if isinstance(e, IcebergCancelledEvent)]
        assert len(cancel_events) == 1
        evt = cancel_events[0]
        assert evt.filled_volume + evt.remaining_volume == total_volume


class TestFilledVolumeTrackingProperty:
    """Property 5: 高级订单成交量追踪"""

    # Feature: advanced-order-hedging-volsurface, Property 5: 高级订单成交量追踪
    # Validates: Requirements 4.2, 4.3
    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=1, max_value=500),
        batch_size=st.integers(min_value=1, max_value=50),
        fill_count=st.integers(min_value=0, max_value=50),
    )
    def test_property5_filled_volume_tracking(self, total_volume, batch_size, fill_count):
        """Property 5: filled_volume == sum of filled child volumes"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        order = scheduler.submit_iceberg(instruction, batch_size)
        now = datetime(2025, 1, 1, 9, 0, 0)

        fills = min(fill_count, len(order.child_orders))
        for _ in range(fills):
            pending = scheduler.get_pending_children(now)
            if not pending:
                break
            pending[0].is_submitted = True
            scheduler.on_child_filled(pending[0].child_id)

        final = scheduler.get_order(order.order_id)
        filled_child_sum = sum(c.volume for c in final.child_orders if c.is_filled)
        assert final.filled_volume == filled_child_sum


class TestAdvancedOrderSerializationProperty:
    """Property 6: 高级订单序列化 Round-Trip"""

    # Feature: advanced-order-hedging-volsurface, Property 6: 高级订单序列化 Round-Trip
    # Validates: Requirements 4.4, 4.5
    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=1, max_value=500),
        batch_size=st.integers(min_value=1, max_value=50),
    )
    def test_property6_iceberg_roundtrip(self, total_volume, batch_size):
        """Property 6: iceberg to_dict -> from_dict round-trip"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        order = scheduler.submit_iceberg(instruction, batch_size)

        d = order.to_dict()
        json_str = json.dumps(d)
        restored = AdvancedOrder.from_dict(json.loads(json_str))

        assert restored.order_id == order.order_id
        assert restored.status == order.status
        assert restored.filled_volume == order.filled_volume
        assert len(restored.child_orders) == len(order.child_orders)
        for orig, rest in zip(order.child_orders, restored.child_orders):
            assert rest.child_id == orig.child_id
            assert rest.volume == orig.volume
            assert rest.is_submitted == orig.is_submitted
            assert rest.is_filled == orig.is_filled

    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=1, max_value=500),
        time_window=st.integers(min_value=10, max_value=3600),
        num_slices=st.integers(min_value=2, max_value=20),
    )
    def test_property6_twap_roundtrip(self, total_volume, time_window, num_slices):
        """Property 6: twap to_dict -> from_dict round-trip"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        start = datetime(2025, 1, 1, 9, 0, 0)
        order = scheduler.submit_twap(instruction, time_window, num_slices, start)

        d = order.to_dict()
        json_str = json.dumps(d)
        restored = AdvancedOrder.from_dict(json.loads(json_str))

        assert restored.order_id == order.order_id
        assert len(restored.child_orders) == len(order.child_orders)
        assert len(restored.slice_schedule) == len(order.slice_schedule)
        for orig, rest in zip(order.child_orders, restored.child_orders):
            assert rest.volume == orig.volume
            assert rest.scheduled_time == orig.scheduled_time


# ========== 经典冰山单属性测试 (Property 2-5) ==========


class TestClassicIcebergSplitProperty:
    """
    Feature: order-splitting-algorithms, Property 2: 经典冰山单拆分正确性（含随机化不变量）
    Validates: Requirements 2.1, 2.2
    """

    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=1, max_value=1000),
        per_order_volume=st.integers(min_value=1, max_value=200),
        volume_randomize_ratio=st.just(0.0),
    )
    def test_property2_no_randomization_volume_sum_and_bounds(
        self, total_volume, per_order_volume, volume_randomize_ratio
    ):
        """
        Property 2 (ratio==0): 所有子单 volume 之和 == total_volume,
        每笔子单 volume <= per_order_volume, 每笔子单 volume >= 1
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        order = scheduler.submit_classic_iceberg(
            instruction,
            per_order_volume=per_order_volume,
            volume_randomize_ratio=volume_randomize_ratio,
        )

        volumes = [c.volume for c in order.child_orders]

        # 所有子单 volume 之和精确等于 total_volume
        assert sum(volumes) == total_volume

        # 当 ratio == 0 时，每笔子单 volume <= per_order_volume
        for v in volumes:
            assert v <= per_order_volume

        # 每笔子单 volume >= 1
        for v in volumes:
            assert v >= 1

    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=2, max_value=1000),
        per_order_volume=st.integers(min_value=1, max_value=200),
        volume_randomize_ratio=st.floats(
            min_value=0.01, max_value=0.99,
            allow_nan=False, allow_infinity=False,
        ),
    )
    def test_property2_with_randomization_volume_sum_and_range(
        self, total_volume, per_order_volume, volume_randomize_ratio
    ):
        """
        Property 2 (ratio>0): 所有子单 volume 之和 == total_volume,
        非最后一笔子单 volume 在 per_order_volume × (1 ± ratio) 范围内,
        每笔子单 volume >= 1
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        order = scheduler.submit_classic_iceberg(
            instruction,
            per_order_volume=per_order_volume,
            volume_randomize_ratio=volume_randomize_ratio,
        )

        volumes = [c.volume for c in order.child_orders]

        # 所有子单 volume 之和精确等于 total_volume
        assert sum(volumes) == total_volume

        # 每笔子单 volume >= 1
        for v in volumes:
            assert v >= 1

        # 非最后一笔子单 volume 在 per_order_volume × (1 ± ratio) 范围内
        low = per_order_volume * (1 - volume_randomize_ratio)
        high = per_order_volume * (1 + volume_randomize_ratio)
        for v in volumes[:-1]:
            # 由于 round + clamp(1, remaining)，允许边界上的整数舍入
            assert v >= max(1, math.floor(low - 0.5)), (
                f"child volume {v} < floor(low={low})"
            )
            assert v <= math.ceil(high + 0.5), (
                f"child volume {v} > ceil(high={high})"
            )


class TestClassicIcebergPriceOffsetProperty:
    """
    Feature: order-splitting-algorithms, Property 3: 经典冰山单价格偏移范围
    Validates: Requirements 2.3
    """

    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=1, max_value=500),
        per_order_volume=st.integers(min_value=1, max_value=100),
        price_offset_ticks=st.integers(min_value=1, max_value=20),
        price_tick=st.floats(
            min_value=0.01, max_value=10.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    def test_property3_price_offset_within_bounds(
        self, total_volume, per_order_volume, price_offset_ticks, price_tick
    ):
        """
        Property 3: 每笔子单的 price_offset 绝对值 <= price_offset_ticks × price_tick
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        order = scheduler.submit_classic_iceberg(
            instruction,
            per_order_volume=per_order_volume,
            volume_randomize_ratio=0.0,
            price_offset_ticks=price_offset_ticks,
            price_tick=price_tick,
        )

        max_offset = price_offset_ticks * price_tick
        for child in order.child_orders:
            assert abs(child.price_offset) <= max_offset + 1e-9, (
                f"price_offset {child.price_offset} exceeds max {max_offset}"
            )


class TestClassicIcebergLifecycleProperty:
    """
    Feature: order-splitting-algorithms, Property 4: 经典冰山单生命周期——顺序执行与完成
    Validates: Requirements 2.4, 2.5
    """

    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=1, max_value=300),
        per_order_volume=st.integers(min_value=1, max_value=100),
    )
    def test_property4_sequential_execution_and_completion(
        self, total_volume, per_order_volume
    ):
        """
        Property 4: get_pending_children 每次最多返回 1 笔子单,
        仅当前面所有子单已成交时才返回下一笔,
        全部成交后父订单状态为 COMPLETED,
        恰好产生 1 个 ClassicIcebergCompleteEvent
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        order = scheduler.submit_classic_iceberg(
            instruction, per_order_volume=per_order_volume
        )
        now = datetime(2025, 1, 1, 9, 0, 0)
        n = len(order.child_orders)

        all_events = []
        for i in range(n):
            # 每次最多返回 1 笔子单
            pending = scheduler.get_pending_children(now)
            assert len(pending) <= 1, (
                f"Expected at most 1 pending child, got {len(pending)}"
            )
            assert len(pending) == 1, (
                f"Expected 1 pending child at step {i}, got 0"
            )
            child = pending[0]

            # 验证返回的是正确顺序的子单
            assert child.child_id == order.child_orders[i].child_id

            child.is_submitted = True
            events = scheduler.on_child_filled(child.child_id)
            all_events.extend(events)

        # 全部成交后父订单状态为 COMPLETED
        final_order = scheduler.get_order(order.order_id)
        assert final_order.status == AdvancedOrderStatus.COMPLETED
        assert final_order.filled_volume == total_volume

        # 恰好产生 1 个 ClassicIcebergCompleteEvent
        complete_events = [
            e for e in all_events if isinstance(e, ClassicIcebergCompleteEvent)
        ]
        assert len(complete_events) == 1
        assert complete_events[0].total_volume == total_volume
        assert complete_events[0].filled_volume == total_volume


class TestClassicIcebergCancelProperty:
    """
    Feature: order-splitting-algorithms, Property 5: 经典冰山单取消正确性
    Validates: Requirements 2.6
    """

    @settings(max_examples=200)
    @given(
        total_volume=st.integers(min_value=2, max_value=300),
        per_order_volume=st.integers(min_value=1, max_value=100),
        fill_count=st.integers(min_value=0, max_value=50),
    )
    def test_property5_cancel_after_partial_fill(
        self, total_volume, per_order_volume, fill_count
    ):
        """
        Property 5: 部分成交后取消——父订单状态为 CANCELLED,
        产生 1 个 ClassicIcebergCancelledEvent,
        事件中 filled_volume + remaining_volume == total_volume
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        order = scheduler.submit_classic_iceberg(
            instruction, per_order_volume=per_order_volume
        )
        now = datetime(2025, 1, 1, 9, 0, 0)
        n = len(order.child_orders)

        # 成交 fill_count 笔（不超过 n-1 以确保有剩余可取消）
        fills = min(fill_count, n - 1)
        for _ in range(fills):
            pending = scheduler.get_pending_children(now)
            if not pending:
                break
            pending[0].is_submitted = True
            scheduler.on_child_filled(pending[0].child_id)

        # 取消订单
        cancel_ids, events = scheduler.cancel_order(order.order_id)

        # 父订单状态为 CANCELLED
        final_order = scheduler.get_order(order.order_id)
        assert final_order.status == AdvancedOrderStatus.CANCELLED

        # 产生 1 个 ClassicIcebergCancelledEvent
        cancel_events = [
            e for e in events if isinstance(e, ClassicIcebergCancelledEvent)
        ]
        assert len(cancel_events) == 1

        # filled_volume + remaining_volume == total_volume
        evt = cancel_events[0]
        assert evt.filled_volume + evt.remaining_volume == total_volume


# ========== 单元测试 ==========

class TestAdvancedOrderSchedulerUnit:
    """AdvancedOrderScheduler 单元测试"""

    def test_iceberg_split_100_by_30(self):
        """冰山单: 100 总量 / 30 每批 = 4 子单 (30, 30, 30, 10)"""
        scheduler = AdvancedOrderScheduler()
        order = scheduler.submit_iceberg(make_instruction(100), 30)
        vols = [c.volume for c in order.child_orders]
        assert vols == [30, 30, 30, 10]
        assert len(order.child_orders) == 4

    def test_twap_300s_5slices(self):
        """TWAP: 300 秒 / 5 片 = 60 秒间隔"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        order = scheduler.submit_twap(make_instruction(100), 300, 5, start)
        assert len(order.child_orders) == 5
        for i in range(1, 5):
            t0 = order.child_orders[i - 1].scheduled_time
            t1 = order.child_orders[i].scheduled_time
            assert (t1 - t0).total_seconds() == 60.0
        assert sum(c.volume for c in order.child_orders) == 100

    def test_vwap_distribution(self):
        """VWAP: [0.1, 0.3, 0.6] 分布, 100 总量 -> [10, 30, 60]"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        order = scheduler.submit_vwap(make_instruction(100), 300, [0.1, 0.3, 0.6], start)
        vols = [c.volume for c in order.child_orders]
        assert vols == [10, 30, 60]

    def test_iceberg_invalid_volume(self):
        """参数校验: 总量 <= 0"""
        scheduler = AdvancedOrderScheduler()
        with pytest.raises(ValueError):
            scheduler.submit_iceberg(make_instruction(0), 10)

    def test_iceberg_invalid_batch_size(self):
        """参数校验: batch_size <= 0"""
        scheduler = AdvancedOrderScheduler()
        with pytest.raises(ValueError):
            scheduler.submit_iceberg(make_instruction(10), 0)

    def test_twap_invalid_slices(self):
        """参数校验: num_slices <= 0"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_twap(make_instruction(10), 300, 0, start)

    def test_vwap_empty_profile(self):
        """参数校验: 空 volume_profile"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_vwap(make_instruction(10), 300, [], start)

    def test_vwap_negative_weight(self):
        """参数校验: 负权重"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_vwap(make_instruction(10), 300, [0.5, -0.1], start)


    def test_classic_iceberg_get_pending_children_sequential(self):
        """经典冰山单: get_pending_children 仅在前一笔成交后返回下一笔"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(50)
        order = scheduler.submit_classic_iceberg(instruction, per_order_volume=20)
        # 应有 3 笔子单: 20, 20, 10
        assert len(order.child_orders) == 3

        now = datetime(2025, 1, 1, 9, 0, 0)

        # 初始状态: 只返回第一笔
        pending = scheduler.get_pending_children(now)
        assert len(pending) == 1
        assert pending[0].child_id == order.child_orders[0].child_id

        # 标记第一笔为已提交（模拟提交）
        order.child_orders[0].is_submitted = True

        # 第一笔已提交但未成交: 不返回任何子单
        pending = scheduler.get_pending_children(now)
        assert len(pending) == 0

        # 第一笔成交
        scheduler.on_child_filled(order.child_orders[0].child_id)

        # 第一笔成交后: 返回第二笔
        pending = scheduler.get_pending_children(now)
        assert len(pending) == 1
        assert pending[0].child_id == order.child_orders[1].child_id

        # 标记第二笔为已提交并成交
        order.child_orders[1].is_submitted = True
        scheduler.on_child_filled(order.child_orders[1].child_id)

        # 第二笔成交后: 返回第三笔
        pending = scheduler.get_pending_children(now)
        assert len(pending) == 1
        assert pending[0].child_id == order.child_orders[2].child_id

        # 标记第三笔为已提交并成交
        order.child_orders[2].is_submitted = True
        scheduler.on_child_filled(order.child_orders[2].child_id)

        # 全部成交后: 不再返回子单
        pending = scheduler.get_pending_children(now)
        assert len(pending) == 0
        assert order.status == AdvancedOrderStatus.COMPLETED


    def test_classic_iceberg_on_child_filled_complete_event(self):
        """经典冰山单: 全部成交时发布 ClassicIcebergCompleteEvent"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(30)
        order = scheduler.submit_classic_iceberg(instruction, per_order_volume=10)
        assert len(order.child_orders) == 3

        # 逐笔成交
        events1 = scheduler.on_child_filled(order.child_orders[0].child_id)
        assert len(events1) == 0  # 未全部成交，无完成事件

        events2 = scheduler.on_child_filled(order.child_orders[1].child_id)
        assert len(events2) == 0

        events3 = scheduler.on_child_filled(order.child_orders[2].child_id)
        assert len(events3) == 1
        evt = events3[0]
        assert isinstance(evt, ClassicIcebergCompleteEvent)
        assert evt.order_id == order.order_id
        assert evt.vt_symbol == "IO2506-C-4000.CFFEX"
        assert evt.total_volume == 30
        assert evt.filled_volume == 30
        assert order.status == AdvancedOrderStatus.COMPLETED

    def test_classic_iceberg_cancel_order_event(self):
        """经典冰山单: 取消时发布 ClassicIcebergCancelledEvent"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(50)
        order = scheduler.submit_classic_iceberg(instruction, per_order_volume=20)
        # 3 笔子单: 20, 20, 10

        # 成交第一笔
        order.child_orders[0].is_submitted = True
        scheduler.on_child_filled(order.child_orders[0].child_id)

        # 提交第二笔但未成交
        order.child_orders[1].is_submitted = True

        # 取消订单
        cancel_ids, events = scheduler.cancel_order(order.order_id)

        # 应返回已提交未成交的子单 ID
        assert order.child_orders[1].child_id in cancel_ids
        assert order.child_orders[0].child_id not in cancel_ids  # 已成交不需撤销

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, ClassicIcebergCancelledEvent)
        assert evt.order_id == order.order_id
        assert evt.vt_symbol == "IO2506-C-4000.CFFEX"
        assert evt.filled_volume == 20
        assert evt.remaining_volume == 30  # 20 + 10 未成交
        assert order.status == AdvancedOrderStatus.CANCELLED

    def test_classic_iceberg_cancel_already_completed(self):
        """经典冰山单: 取消已完成的订单不产生事件"""
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(10)
        order = scheduler.submit_classic_iceberg(instruction, per_order_volume=10)

        # 成交唯一子单
        scheduler.on_child_filled(order.child_orders[0].child_id)
        assert order.status == AdvancedOrderStatus.COMPLETED

        # 尝试取消已完成的订单
        cancel_ids, events = scheduler.cancel_order(order.order_id)
        assert cancel_ids == []
        assert events == []

    def test_enhanced_twap_300s_5slices(self):
        """增强型 TWAP: 300 秒 / 5 片, 100 总量 -> 均匀分配"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        order = scheduler.submit_enhanced_twap(make_instruction(100), 300, 5, start)
        assert len(order.child_orders) == 5
        assert order.request.order_type == AdvancedOrderType.ENHANCED_TWAP
        vols = [c.volume for c in order.child_orders]
        assert sum(vols) == 100
        assert all(v == 20 for v in vols)
        # 间隔应为 60 秒
        for i in range(1, 5):
            t0 = order.child_orders[i - 1].scheduled_time
            t1 = order.child_orders[i].scheduled_time
            assert (t1 - t0).total_seconds() == 60.0

    def test_enhanced_twap_remainder_distribution(self):
        """增强型 TWAP: 余数分配到前几片, 各片差异不超过 1"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        order = scheduler.submit_enhanced_twap(make_instruction(13), 300, 5, start)
        vols = [c.volume for c in order.child_orders]
        assert sum(vols) == 13
        assert max(vols) - min(vols) <= 1
        # 13 // 5 = 2, 余 3 -> 前 3 片各 3, 后 2 片各 2
        assert vols == [3, 3, 3, 2, 2]

    def test_enhanced_twap_invalid_volume(self):
        """增强型 TWAP: 总量 <= 0 抛出 ValueError"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_enhanced_twap(make_instruction(0), 300, 5, start)

    def test_enhanced_twap_invalid_time_window(self):
        """增强型 TWAP: time_window_seconds <= 0 抛出 ValueError"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_enhanced_twap(make_instruction(100), 0, 5, start)

    def test_enhanced_twap_invalid_num_slices(self):
        """增强型 TWAP: num_slices <= 0 抛出 ValueError"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_enhanced_twap(make_instruction(100), 300, 0, start)

    def test_enhanced_twap_get_pending_children_by_scheduled_time(self):
        """增强型 TWAP: get_pending_children 按 scheduled_time 返回可提交子单"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        order = scheduler.submit_enhanced_twap(make_instruction(100), 300, 5, start)

        # 在 start_time 之前，不应有可提交子单
        before_start = start - timedelta(seconds=1)
        pending = scheduler.get_pending_children(before_start)
        assert len(pending) == 0

        # 恰好在 start_time，应返回第一个子单
        pending = scheduler.get_pending_children(start)
        assert len(pending) == 1
        assert pending[0].child_id == order.child_orders[0].child_id

        # 在 start + 60s（第二个时间片），应返回前两个子单（第一个未提交）
        t1 = start + timedelta(seconds=60)
        pending = scheduler.get_pending_children(t1)
        assert len(pending) == 2
        child_ids = {c.child_id for c in pending}
        assert order.child_orders[0].child_id in child_ids
        assert order.child_orders[1].child_id in child_ids

        # 标记第一个子单为已提交，再查询应只返回第二个
        order.child_orders[0].is_submitted = True
        pending = scheduler.get_pending_children(t1)
        assert len(pending) == 1
        assert pending[0].child_id == order.child_orders[1].child_id

        # 在最后一个时间片之后，所有未提交子单都应返回
        t_end = start + timedelta(seconds=300)
        # 重置提交状态
        order.child_orders[0].is_submitted = False
        pending = scheduler.get_pending_children(t_end)
        assert len(pending) == 5

        # 已成交的子单不应返回
        order.child_orders[0].is_filled = True
        pending = scheduler.get_pending_children(t_end)
        assert len(pending) == 4
        assert all(c.child_id != order.child_orders[0].child_id for c in pending)

    def test_enhanced_twap_on_child_filled_complete_event(self):
        """增强型 TWAP: 全部成交时发布 EnhancedTWAPCompleteEvent"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        order = scheduler.submit_enhanced_twap(make_instruction(100), 300, 5, start)
        assert len(order.child_orders) == 5

        # 逐笔成交前 4 笔，不应产生完成事件
        for i in range(4):
            events = scheduler.on_child_filled(order.child_orders[i].child_id)
            assert len(events) == 0

        # 成交最后一笔，应产生 EnhancedTWAPCompleteEvent
        events = scheduler.on_child_filled(order.child_orders[4].child_id)
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, EnhancedTWAPCompleteEvent)
        assert evt.order_id == order.order_id
        assert evt.vt_symbol == "IO2506-C-4000.CFFEX"
        assert evt.total_volume == 100
        assert order.status == AdvancedOrderStatus.COMPLETED

    def test_enhanced_twap_cancel_after_partial_fill(self):
        """增强型 TWAP: 部分成交后取消 -> CANCELLED 状态 + 正确的子单 ID"""
        scheduler = AdvancedOrderScheduler()
        start = datetime(2025, 1, 1, 9, 0, 0)
        order = scheduler.submit_enhanced_twap(make_instruction(100), 300, 5, start)
        # 5 笔子单，每笔 20

        # 成交第一笔
        order.child_orders[0].is_submitted = True
        scheduler.on_child_filled(order.child_orders[0].child_id)

        # 提交第二笔但未成交
        order.child_orders[1].is_submitted = True

        # 取消订单
        cancel_ids, events = scheduler.cancel_order(order.order_id)

        # 应返回已提交未成交的子单 ID（仅第二笔）
        assert order.child_orders[1].child_id in cancel_ids
        assert order.child_orders[0].child_id not in cancel_ids  # 已成交不需撤销
        assert len(cancel_ids) == 1

        # ENHANCED_TWAP 取消不产生特定取消事件（需求 3.5 未要求）
        assert len(events) == 0

        assert order.status == AdvancedOrderStatus.CANCELLED





