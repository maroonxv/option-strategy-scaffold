"""
订单拆分算法属性测试

Feature: order-splitting-algorithms
"""
import math
from datetime import datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.domain_service.advanced_order_scheduler import AdvancedOrderScheduler
from src.strategy.domain.value_object.advanced_order import AdvancedOrder
from src.strategy.domain.value_object.order_instruction import OrderInstruction, Direction, Offset


def make_instruction(volume: int) -> OrderInstruction:
    return OrderInstruction(
        vt_symbol="rb2501.SHFE",
        direction=Direction.LONG,
        offset=Offset.OPEN,
        volume=volume,
        price=4000.0,
    )


class TestTimedSplitProperty:
    """Feature: order-splitting-algorithms, Property 1: 定时拆单拆分正确性"""

    @given(
        total_volume=st.integers(min_value=1, max_value=10000),
        per_order_volume=st.integers(min_value=1, max_value=1000),
        interval_seconds=st.integers(min_value=1, max_value=3600),
    )
    @settings(max_examples=100)
    def test_property1_timed_split_correctness(self, total_volume, per_order_volume, interval_seconds):
        """
        **Validates: Requirements 1.1, 1.2**

        For any valid total_volume and per_order_volume:
        - 每笔子单 volume <= per_order_volume
        - 所有子单 volume 之和 == total_volume
        - 子单数量 == ceil(total_volume / per_order_volume)
        - 第 i 笔子单的 scheduled_time == start_time + i * interval_seconds
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        start_time = datetime(2025, 1, 1, 10, 0, 0)

        order = scheduler.submit_timed_split(instruction, interval_seconds, per_order_volume, start_time)

        # 每笔子单 volume <= per_order_volume
        for child in order.child_orders:
            assert child.volume <= per_order_volume

        # 所有子单 volume 之和 == total_volume
        assert sum(c.volume for c in order.child_orders) == total_volume

        # 子单数量 == ceil(total_volume / per_order_volume)
        expected_count = math.ceil(total_volume / per_order_volume)
        assert len(order.child_orders) == expected_count

        # 第 i 笔子单的 scheduled_time == start_time + i * interval_seconds
        for i, child in enumerate(order.child_orders):
            expected_time = start_time + timedelta(seconds=interval_seconds * i)
            assert child.scheduled_time == expected_time


class TestEnhancedTWAPProperty:
    """Feature: order-splitting-algorithms, Property 6: 增强型 TWAP 拆分正确性"""

    @given(
        total_volume=st.integers(min_value=1, max_value=10000),
        time_window_seconds=st.integers(min_value=1, max_value=86400),
        num_slices=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100)
    def test_property6_enhanced_twap_correctness(self, total_volume, time_window_seconds, num_slices):
        """
        **Validates: Requirements 3.1, 3.2**

        For any valid total_volume, time_window_seconds and num_slices:
        - 各片数量差异不超过 1（max - min ≤ 1）
        - 所有子单 volume 之和 == total_volume
        - 相邻时间片间隔 == time_window_seconds / num_slices（±1 秒舍入误差）
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        start_time = datetime(2025, 1, 1, 10, 0, 0)

        order = scheduler.submit_enhanced_twap(instruction, time_window_seconds, num_slices, start_time)

        children = order.child_orders
        assert len(children) == num_slices

        volumes = [c.volume for c in children]

        # 各片数量差异不超过 1（max - min ≤ 1）
        assert max(volumes) - min(volumes) <= 1

        # 所有子单 volume 之和 == total_volume
        assert sum(volumes) == total_volume

        # 相邻时间片间隔 == time_window_seconds / num_slices（±1 秒舍入误差）
        expected_interval = time_window_seconds / num_slices
        for i in range(1, len(children)):
            actual_interval = (children[i].scheduled_time - children[i - 1].scheduled_time).total_seconds()
            assert abs(actual_interval - expected_interval) <= 1.0, (
                f"Slice {i}: actual_interval={actual_interval}, expected={expected_interval}"
            )

# --- Strategies for Property 7 ---

@st.composite
def order_type_strategy(draw):
    """随机选择一种新订单类型并生成对应的有效参数和订单"""
    order_type = draw(st.sampled_from(["timed_split", "classic_iceberg", "enhanced_twap"]))
    total_volume = draw(st.integers(min_value=1, max_value=500))
    instruction = make_instruction(total_volume)
    scheduler = AdvancedOrderScheduler()
    start_time = datetime(2025, 1, 1, 10, 0, 0)

    if order_type == "timed_split":
        per_order_volume = draw(st.integers(min_value=1, max_value=max(1, total_volume)))
        interval_seconds = draw(st.integers(min_value=1, max_value=3600))
        order = scheduler.submit_timed_split(instruction, interval_seconds, per_order_volume, start_time)
    elif order_type == "classic_iceberg":
        per_order_volume = draw(st.integers(min_value=1, max_value=max(1, total_volume)))
        order = scheduler.submit_classic_iceberg(instruction, per_order_volume)
    else:  # enhanced_twap
        num_slices = draw(st.integers(min_value=1, max_value=min(100, total_volume)))
        time_window_seconds = draw(st.integers(min_value=1, max_value=86400))
        order = scheduler.submit_enhanced_twap(instruction, time_window_seconds, num_slices, start_time)

    return scheduler, order


class TestFilledVolumeTrackingProperty:
    """Feature: order-splitting-algorithms, Property 7: 成交量追踪不变量"""

    @given(data=st.data())
    @settings(max_examples=100)
    def test_property7_filled_volume_invariant(self, data):
        """
        **Validates: Requirements 4.1, 4.2**

        For any order type and any child fill sequence,
        filled_volume always equals the sum of volumes of all filled children.
        """
        scheduler, order = data.draw(order_type_strategy())
        child_ids = [c.child_id for c in order.child_orders]

        # 随机选择一个子集并打乱顺序作为成交序列
        num_to_fill = data.draw(st.integers(min_value=0, max_value=len(child_ids)))
        fill_indices = data.draw(
            st.permutations(range(len(child_ids))).map(lambda p: list(p[:num_to_fill]))
        )

        filled_set = set()
        for idx in fill_indices:
            child_id = child_ids[idx]
            scheduler.on_child_filled(child_id)
            filled_set.add(idx)

            # 不变量: filled_volume == 所有已成交子单的 volume 之和
            expected_filled = sum(
                order.child_orders[i].volume for i in filled_set
            )
            assert order.filled_volume == expected_filled, (
                f"After filling child {idx} ({child_id}): "
                f"filled_volume={order.filled_volume}, expected={expected_filled}"
            )



# --- Strategies for Property 7 ---

@st.composite
def order_type_strategy(draw):
    """随机选择一种新订单类型并生成对应的有效参数和订单"""
    order_type = draw(st.sampled_from(["timed_split", "classic_iceberg", "enhanced_twap"]))
    total_volume = draw(st.integers(min_value=1, max_value=500))
    instruction = make_instruction(total_volume)
    scheduler = AdvancedOrderScheduler()
    start_time = datetime(2025, 1, 1, 10, 0, 0)

    if order_type == "timed_split":
        per_order_volume = draw(st.integers(min_value=1, max_value=max(1, total_volume)))
        interval_seconds = draw(st.integers(min_value=1, max_value=3600))
        order = scheduler.submit_timed_split(instruction, interval_seconds, per_order_volume, start_time)
    elif order_type == "classic_iceberg":
        per_order_volume = draw(st.integers(min_value=1, max_value=max(1, total_volume)))
        order = scheduler.submit_classic_iceberg(instruction, per_order_volume)
    else:  # enhanced_twap
        num_slices = draw(st.integers(min_value=1, max_value=min(100, total_volume)))
        time_window_seconds = draw(st.integers(min_value=1, max_value=86400))
        order = scheduler.submit_enhanced_twap(instruction, time_window_seconds, num_slices, start_time)

    return scheduler, order


class TestFilledVolumeTrackingProperty:
    """Feature: order-splitting-algorithms, Property 7: 成交量追踪不变量"""

    @given(data=st.data())
    @settings(max_examples=100)
    def test_property7_filled_volume_invariant(self, data):
        """
        **Validates: Requirements 4.1, 4.2**

        For any order type and any child fill sequence,
        filled_volume always equals the sum of volumes of all filled children.
        """
        scheduler, order = data.draw(order_type_strategy())
        child_ids = [c.child_id for c in order.child_orders]

        # 随机选择一个子集并打乱顺序作为成交序列
        num_to_fill = data.draw(st.integers(min_value=0, max_value=len(child_ids)))
        fill_indices = data.draw(
            st.permutations(range(len(child_ids))).map(lambda p: list(p[:num_to_fill]))
        )

        filled_set = set()
        for idx in fill_indices:
            child_id = child_ids[idx]
            scheduler.on_child_filled(child_id)
            filled_set.add(idx)

            # 不变量: filled_volume == 所有已成交子单的 volume 之和
            expected_filled = sum(
                order.child_orders[i].volume for i in filled_set
            )
            assert order.filled_volume == expected_filled, (
                f"After filling child {idx} ({child_id}): "
                f"filled_volume={order.filled_volume}, expected={expected_filled}"
            )


class TestSerializationRoundTripProperty:
    """Feature: order-splitting-algorithms, Property 8: 序列化 Round-Trip"""

    @given(data=st.data())
    @settings(max_examples=100)
    def test_property8_serialization_round_trip(self, data):
        """
        **Validates: Requirements 5.1, 5.2, 5.3**

        For any valid AdvancedOrder (timed_split, classic_iceberg, enhanced_twap),
        serializing to dict then deserializing should produce an equivalent object.
        """
        _scheduler, order = data.draw(order_type_strategy())

        # Round-trip: to_dict -> from_dict
        d = order.to_dict()
        restored = AdvancedOrder.from_dict(d)

        # Verify top-level fields
        assert restored.order_id == order.order_id
        assert restored.status == order.status
        assert restored.filled_volume == order.filled_volume

        # Verify request fields
        assert restored.request.order_type == order.request.order_type
        assert restored.request.instruction.vt_symbol == order.request.instruction.vt_symbol
        assert restored.request.instruction.direction == order.request.instruction.direction
        assert restored.request.instruction.offset == order.request.instruction.offset
        assert restored.request.instruction.volume == order.request.instruction.volume
        assert restored.request.instruction.price == order.request.instruction.price
        assert restored.request.instruction.signal == order.request.instruction.signal
        assert restored.request.instruction.order_type == order.request.instruction.order_type
        assert restored.request.batch_size == order.request.batch_size
        assert restored.request.time_window_seconds == order.request.time_window_seconds
        assert restored.request.num_slices == order.request.num_slices
        assert restored.request.volume_profile == order.request.volume_profile
        assert restored.request.interval_seconds == order.request.interval_seconds
        assert restored.request.per_order_volume == order.request.per_order_volume
        assert restored.request.volume_randomize_ratio == order.request.volume_randomize_ratio
        assert restored.request.price_offset_ticks == order.request.price_offset_ticks
        assert restored.request.price_tick == order.request.price_tick

        # Verify child_orders
        assert len(restored.child_orders) == len(order.child_orders)
        for orig, rest in zip(order.child_orders, restored.child_orders):
            assert rest.child_id == orig.child_id
            assert rest.parent_id == orig.parent_id
            assert rest.volume == orig.volume
            assert rest.scheduled_time == orig.scheduled_time
            assert rest.is_submitted == orig.is_submitted
            assert rest.is_filled == orig.is_filled
            assert rest.price_offset == orig.price_offset

        # Verify slice_schedule
        assert len(restored.slice_schedule) == len(order.slice_schedule)
        for orig_s, rest_s in zip(order.slice_schedule, restored.slice_schedule):
            assert rest_s.scheduled_time == orig_s.scheduled_time
            assert rest_s.volume == orig_s.volume


class TestInvalidParameterRejectionProperty:
    """Feature: order-splitting-algorithms, Property 9: 无效参数拒绝"""

    # ---- 定时拆单 (Req 1.5) ----

    @given(total_volume=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_timed_split_rejects_invalid_total_volume(self, total_volume):
        """
        **Validates: Requirements 1.5**

        定时拆单：total_volume <= 0 应抛出 ValueError
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        start_time = datetime(2025, 1, 1, 10, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_timed_split(instruction, interval_seconds=10, per_order_volume=5, start_time=start_time)

    @given(interval_seconds=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_timed_split_rejects_invalid_interval_seconds(self, interval_seconds):
        """
        **Validates: Requirements 1.5**

        定时拆单：interval_seconds <= 0 应抛出 ValueError
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(100)
        start_time = datetime(2025, 1, 1, 10, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_timed_split(instruction, interval_seconds=interval_seconds, per_order_volume=10, start_time=start_time)

    @given(per_order_volume=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_timed_split_rejects_invalid_per_order_volume(self, per_order_volume):
        """
        **Validates: Requirements 1.5**

        定时拆单：per_order_volume <= 0 应抛出 ValueError
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(100)
        start_time = datetime(2025, 1, 1, 10, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_timed_split(instruction, interval_seconds=10, per_order_volume=per_order_volume, start_time=start_time)

    # ---- 经典冰山单 (Req 2.7, 2.8) ----

    @given(total_volume=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_classic_iceberg_rejects_invalid_total_volume(self, total_volume):
        """
        **Validates: Requirements 2.7**

        经典冰山单：total_volume <= 0 应抛出 ValueError
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        with pytest.raises(ValueError):
            scheduler.submit_classic_iceberg(instruction, per_order_volume=10)

    @given(per_order_volume=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_classic_iceberg_rejects_invalid_per_order_volume(self, per_order_volume):
        """
        **Validates: Requirements 2.7**

        经典冰山单：per_order_volume <= 0 应抛出 ValueError
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(100)
        with pytest.raises(ValueError):
            scheduler.submit_classic_iceberg(instruction, per_order_volume=per_order_volume)

    @given(volume_randomize_ratio=st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_classic_iceberg_rejects_negative_randomize_ratio(self, volume_randomize_ratio):
        """
        **Validates: Requirements 2.8**

        经典冰山单：volume_randomize_ratio < 0 应抛出 ValueError
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(100)
        with pytest.raises(ValueError):
            scheduler.submit_classic_iceberg(instruction, per_order_volume=10, volume_randomize_ratio=volume_randomize_ratio)

    @given(volume_randomize_ratio=st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_classic_iceberg_rejects_ratio_gte_one(self, volume_randomize_ratio):
        """
        **Validates: Requirements 2.8**

        经典冰山单：volume_randomize_ratio >= 1 应抛出 ValueError
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(100)
        with pytest.raises(ValueError):
            scheduler.submit_classic_iceberg(instruction, per_order_volume=10, volume_randomize_ratio=volume_randomize_ratio)

    # ---- 增强型 TWAP (Req 3.6) ----

    @given(total_volume=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_enhanced_twap_rejects_invalid_total_volume(self, total_volume):
        """
        **Validates: Requirements 3.6**

        增强型 TWAP：total_volume <= 0 应抛出 ValueError
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(total_volume)
        start_time = datetime(2025, 1, 1, 10, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_enhanced_twap(instruction, time_window_seconds=300, num_slices=5, start_time=start_time)

    @given(time_window_seconds=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_enhanced_twap_rejects_invalid_time_window(self, time_window_seconds):
        """
        **Validates: Requirements 3.6**

        增强型 TWAP：time_window_seconds <= 0 应抛出 ValueError
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(100)
        start_time = datetime(2025, 1, 1, 10, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_enhanced_twap(instruction, time_window_seconds=time_window_seconds, num_slices=5, start_time=start_time)

    @given(num_slices=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_enhanced_twap_rejects_invalid_num_slices(self, num_slices):
        """
        **Validates: Requirements 3.6**

        增强型 TWAP：num_slices <= 0 应抛出 ValueError
        """
        scheduler = AdvancedOrderScheduler()
        instruction = make_instruction(100)
        start_time = datetime(2025, 1, 1, 10, 0, 0)
        with pytest.raises(ValueError):
            scheduler.submit_enhanced_twap(instruction, time_window_seconds=300, num_slices=num_slices, start_time=start_time)
