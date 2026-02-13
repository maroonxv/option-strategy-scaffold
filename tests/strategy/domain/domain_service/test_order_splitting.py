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
