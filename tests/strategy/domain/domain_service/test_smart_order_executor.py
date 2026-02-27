"""
SmartOrderExecutor 属性测试

使用 hypothesis 验证自适应价格、超时管理、重试逻辑和序列化的正确性。
"""
import json
import pytest
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings, assume

from src.strategy.domain.domain_service.execution.smart_order_executor import SmartOrderExecutor
from src.strategy.domain.value_object.trading.order_instruction import (
    OrderInstruction, Direction, Offset, OrderType,
)
from src.strategy.domain.value_object.trading.order_execution import OrderExecutionConfig, ManagedOrder
from src.strategy.domain.event.event_types import OrderTimeoutEvent, OrderRetryExhaustedEvent


# ========== 生成器 ==========

instruction_st = st.builds(
    OrderInstruction,
    vt_symbol=st.just("IO2506-C-4000.CFFEX"),
    direction=st.sampled_from([Direction.LONG, Direction.SHORT]),
    offset=st.sampled_from([Offset.OPEN, Offset.CLOSE]),
    volume=st.integers(min_value=1, max_value=100),
    price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    signal=st.just("test_signal"),
    order_type=st.just(OrderType.LIMIT),
)

config_st = st.builds(
    OrderExecutionConfig,
    timeout_seconds=st.integers(min_value=1, max_value=300),
    max_retries=st.integers(min_value=0, max_value=10),
    slippage_ticks=st.integers(min_value=0, max_value=10),
    price_tick=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
)


class TestSmartOrderExecutorProperties:

    # Feature: greeks-risk-portfolio-execution, Property 9: 自适应委托价格计算
    # Validates: Requirements 7.1, 7.2
    @settings(max_examples=200)
    @given(
        instruction=instruction_st,
        bid_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        ask_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        slippage_ticks=st.integers(min_value=0, max_value=10),
        price_tick=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    def test_property9_adaptive_price(self, instruction, bid_price, ask_price, slippage_ticks, price_tick):
        """Property 9: 卖出用 bid-slippage, 买入用 ask+slippage"""
        config = OrderExecutionConfig(slippage_ticks=slippage_ticks, price_tick=price_tick)
        executor = SmartOrderExecutor(config)
        result = executor.calculate_adaptive_price(instruction, bid_price, ask_price, price_tick)

        if instruction.direction == Direction.SHORT:
            expected = bid_price - slippage_ticks * price_tick
        else:
            expected = ask_price + slippage_ticks * price_tick

        assert abs(result - expected) < 1e-6, f"Expected {expected}, got {result}"


    # Feature: greeks-risk-portfolio-execution, Property 10: 价格对齐到最小变动价位
    # Validates: Requirements 7.4
    @settings(max_examples=200)
    @given(
        price=st.floats(min_value=0.1, max_value=100000.0, allow_nan=False, allow_infinity=False),
        price_tick=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    def test_property10_price_tick_alignment(self, price, price_tick):
        """Property 10: 对齐后的价格是 price_tick 的整数倍，且偏差 < price_tick"""
        config = OrderExecutionConfig()
        executor = SmartOrderExecutor(config)
        result = executor.round_price_to_tick(price, price_tick)

        # result 应该是 price_tick 的整数倍 (浮点容差)
        remainder = abs(result % price_tick)
        # 处理浮点精度: remainder 接近 0 或接近 price_tick 都算对齐
        aligned = remainder < 1e-9 or abs(remainder - price_tick) < 1e-9
        assert aligned, f"result={result} 不是 price_tick={price_tick} 的整数倍, remainder={remainder}"

        # 偏差应小于 price_tick
        assert abs(result - price) < price_tick + 1e-9, (
            f"|{result} - {price}| = {abs(result - price)} >= {price_tick}"
        )


    # Feature: greeks-risk-portfolio-execution, Property 8: 订单超时检查正确性
    # Validates: Requirements 6.1, 6.2, 6.3
    @settings(max_examples=200)
    @given(
        instructions=st.lists(instruction_st, min_size=1, max_size=10),
        timeout_seconds=st.integers(min_value=1, max_value=300),
        elapsed_offsets=st.lists(
            st.integers(min_value=-60, max_value=600), min_size=1, max_size=10
        ),
    )
    def test_property8_order_timeout_check(self, instructions, timeout_seconds, elapsed_offsets):
        """Property 8: 超时订单当且仅当 is_active 且 elapsed >= timeout"""
        # 确保列表长度一致
        n = min(len(instructions), len(elapsed_offsets))
        instructions = instructions[:n]
        elapsed_offsets = elapsed_offsets[:n]

        config = OrderExecutionConfig(timeout_seconds=timeout_seconds)
        executor = SmartOrderExecutor(config)

        base_time = datetime(2026, 1, 1, 10, 0, 0)
        expected_cancel = set()

        for i, (instr, offset) in enumerate(zip(instructions, elapsed_offsets)):
            oid = f"order_{i}"
            order = executor.register_order(oid, instr)
            order.submit_time = base_time - timedelta(seconds=offset)

            # 随机标记一些为已成交 (inactive)
            if i % 3 == 0 and i > 0:
                executor.mark_order_filled(oid)
            else:
                elapsed = (base_time - order.submit_time).total_seconds()
                if elapsed >= timeout_seconds:
                    expected_cancel.add(oid)

        cancel_ids, events = executor.check_timeouts(base_time)

        assert set(cancel_ids) == expected_cancel
        assert len(events) == len(cancel_ids)
        for event in events:
            assert isinstance(event, OrderTimeoutEvent)
            assert event.vt_orderid in expected_cancel


    # Feature: greeks-risk-portfolio-execution, Property 11: 订单重试逻辑
    # Validates: Requirements 8.1, 8.2, 8.3
    @settings(max_examples=200)
    @given(
        instruction=instruction_st,
        retry_count=st.integers(min_value=0, max_value=10),
        max_retries=st.integers(min_value=0, max_value=10),
        price_tick=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    def test_property11_order_retry_logic(self, instruction, retry_count, max_retries, price_tick):
        """Property 11: retry_count < max_retries 时返回调整后指令，否则返回 None"""
        config = OrderExecutionConfig(max_retries=max_retries, price_tick=price_tick)
        executor = SmartOrderExecutor(config)

        order = ManagedOrder(
            vt_orderid="test_order",
            instruction=instruction,
            submit_time=datetime.now(),
            retry_count=retry_count,
        )

        result = executor.prepare_retry(order, price_tick)

        if retry_count >= max_retries:
            assert result is None, "应返回 None (重试耗尽)"
        else:
            assert result is not None, "应返回新指令"
            # 价格应该更激进
            if instruction.direction == Direction.SHORT:
                expected_price = executor.round_price_to_tick(
                    instruction.price - price_tick, price_tick
                )
            else:
                expected_price = executor.round_price_to_tick(
                    instruction.price + price_tick, price_tick
                )
            assert abs(result.price - expected_price) < 1e-9
            assert order.retry_count == retry_count + 1


    # Feature: greeks-risk-portfolio-execution, Property 13: ManagedOrder 序列化 Round-Trip
    # Validates: Requirements 9.4
    @settings(max_examples=200)
    @given(
        instruction=instruction_st,
        retry_count=st.integers(min_value=0, max_value=10),
        is_active=st.booleans(),
    )
    def test_property13_managed_order_serialization_round_trip(self, instruction, retry_count, is_active):
        """Property 13: ManagedOrder to_dict → from_dict 恢复等价对象"""
        original = ManagedOrder(
            vt_orderid="test_order_123",
            instruction=instruction,
            submit_time=datetime(2026, 1, 15, 10, 30, 0),
            retry_count=retry_count,
            is_active=is_active,
        )
        data = original.to_dict()
        json_str = json.dumps(data)
        restored_data = json.loads(json_str)
        restored = ManagedOrder.from_dict(restored_data)

        assert restored.vt_orderid == original.vt_orderid
        assert restored.instruction.vt_symbol == original.instruction.vt_symbol
        assert restored.instruction.direction == original.instruction.direction
        assert restored.instruction.offset == original.instruction.offset
        assert restored.instruction.volume == original.instruction.volume
        assert abs(restored.instruction.price - original.instruction.price) < 1e-10
        assert restored.submit_time == original.submit_time
        assert restored.retry_count == original.retry_count
        assert restored.is_active == original.is_active
