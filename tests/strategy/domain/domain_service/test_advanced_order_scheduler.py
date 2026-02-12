"""
AdvancedOrderScheduler 属性测试和单元测试

使用 hypothesis 验证冰山单、TWAP、VWAP 拆分逻辑和生命周期管理。
"""
import json
import math
import pytest
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings, assume

from src.strategy.domain.domain_service.advanced_order_scheduler import AdvancedOrderScheduler
from src.strategy.domain.value_object.order_instruction import (
    OrderInstruction, Direction, Offset, OrderType,
)
from src.strategy.domain.value_object.advanced_order import (
    AdvancedOrder, AdvancedOrderStatus, AdvancedOrderType,
)
from src.strategy.domain.event.event_types import (
    IcebergCompleteEvent, IcebergCancelledEvent,
    TWAPCompleteEvent, VWAPCompleteEvent,
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
