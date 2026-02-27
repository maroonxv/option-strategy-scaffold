"""
执行服务配置加载属性测试

Feature: execution-service-enhancement, Property 1: SmartOrderExecutor 配置加载优先级
Feature: execution-service-enhancement, Property 2: AdvancedScheduler 配置加载优先级
Feature: execution-service-enhancement, Property 5: AdvancedSchedulerConfig 不可变性

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 3.2**
"""

import dataclasses
import sys
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing domain_service_config_loader
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

from src.main.config.domain_service_config_loader import (  # noqa: E402
    load_advanced_scheduler_config,
    load_smart_order_executor_config,
)
from src.strategy.domain.value_object.trading.order_execution import (  # noqa: E402
    AdvancedSchedulerConfig,
    OrderExecutionConfig,
)

# ---------------------------------------------------------------------------
# Hypothesis 策略：SmartOrderExecutor 配置字段
# ---------------------------------------------------------------------------

# OrderExecutionConfig 字段范围
_timeout_seconds = st.integers(min_value=1, max_value=300)
_max_retries = st.integers(min_value=0, max_value=20)
_slippage_ticks = st.integers(min_value=0, max_value=50)
_price_tick_soe = st.floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False)

# AdvancedSchedulerConfig 字段范围
_default_batch_size = st.integers(min_value=1, max_value=500)
_default_interval_seconds = st.integers(min_value=1, max_value=3600)
_default_num_slices = st.integers(min_value=1, max_value=100)
_default_volume_randomize_ratio = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_default_price_offset_ticks = st.integers(min_value=0, max_value=50)
_default_price_tick_as = st.floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False)

# ---------------------------------------------------------------------------
# 辅助：生成 overrides 子集和 TOML 子集
# ---------------------------------------------------------------------------

# SmartOrderExecutor: 每个字段独立决定是否出现在 overrides / TOML 中
_SOE_FIELDS = {
    "timeout_seconds": ("timeout_seconds", "timeout", "seconds", _timeout_seconds),
    "max_retries": ("max_retries", "retry", "max_retries", _max_retries),
    "slippage_ticks": ("slippage_ticks", "price", "slippage_ticks", _slippage_ticks),
    "price_tick": ("price_tick", "price", "price_tick", _price_tick_soe),
}

_AS_FIELDS = {
    "default_batch_size": ("default_batch_size", "iceberg", "default_batch_size", _default_batch_size),
    "default_interval_seconds": ("default_interval_seconds", "split", "default_interval_seconds", _default_interval_seconds),
    "default_num_slices": ("default_num_slices", "split", "default_num_slices", _default_num_slices),
    "default_volume_randomize_ratio": ("default_volume_randomize_ratio", "randomize", "default_volume_randomize_ratio", _default_volume_randomize_ratio),
    "default_price_offset_ticks": ("default_price_offset_ticks", "price", "default_price_offset_ticks", _default_price_offset_ticks),
    "default_price_tick": ("default_price_tick", "price", "default_price_tick", _default_price_tick_as),
}


@st.composite
def _soe_overrides_and_toml(draw):
    """
    为 SmartOrderExecutor 生成 (overrides, toml_data) 组合。
    每个字段独立决定是否出现在 overrides 和/或 TOML 中。
    """
    overrides = {}
    toml_data = {}

    for config_key, (override_key, toml_section, toml_key, value_st) in _SOE_FIELDS.items():
        in_overrides = draw(st.booleans())
        in_toml = draw(st.booleans())

        if in_overrides:
            overrides[override_key] = draw(value_st)
        if in_toml:
            toml_data.setdefault(toml_section, {})[toml_key] = draw(value_st)

    return overrides, toml_data


@st.composite
def _as_overrides_and_toml(draw):
    """
    为 AdvancedScheduler 生成 (overrides, toml_data) 组合。
    每个字段独立决定是否出现在 overrides 和/或 TOML 中。
    """
    overrides = {}
    toml_data = {}

    for config_key, (override_key, toml_section, toml_key, value_st) in _AS_FIELDS.items():
        in_overrides = draw(st.booleans())
        in_toml = draw(st.booleans())

        if in_overrides:
            overrides[override_key] = draw(value_st)
        if in_toml:
            toml_data.setdefault(toml_section, {})[toml_key] = draw(value_st)

    return overrides, toml_data


# ===========================================================================
# Feature: execution-service-enhancement, Property 1: SmartOrderExecutor 配置加载优先级
# ===========================================================================


class TestProperty1SmartOrderExecutorConfigPriority:
    """
    Property 1: SmartOrderExecutor 配置加载优先级

    对于任意 overrides 字典和 TOML 文件内容组合，load_smart_order_executor_config(overrides)
    返回的 OrderExecutionConfig 中，overrides 中存在的字段应等于 overrides 值，
    不在 overrides 中但在 TOML 中的字段应等于 TOML 值，
    两者都不存在的字段应等于 OrderExecutionConfig 的 dataclass 默认值。

    **Validates: Requirements 1.1, 1.3, 1.4**
    """

    @given(data=_soe_overrides_and_toml())
    @settings(max_examples=100)
    def test_smart_order_executor_config_loading_priority(self, data):
        """
        # Feature: execution-service-enhancement, Property 1: SmartOrderExecutor 配置加载优先级

        **Validates: Requirements 1.1, 1.3, 1.4**
        """
        overrides, toml_data = data
        defaults = OrderExecutionConfig()

        with patch(
            "src.main.config.domain_service_config_loader._load_toml",
            return_value=toml_data,
        ):
            result = load_smart_order_executor_config(overrides if overrides else None)

        # 逐字段验证优先级: overrides > TOML > defaults
        for config_key, (override_key, toml_section, toml_key, _) in _SOE_FIELDS.items():
            actual = getattr(result, config_key)

            if override_key in overrides:
                expected = overrides[override_key]
            elif toml_section in toml_data and toml_key in toml_data[toml_section]:
                expected = toml_data[toml_section][toml_key]
            else:
                expected = getattr(defaults, config_key)

            assert actual == expected, (
                f"字段 {config_key}: 期望 {expected}, 实际 {actual}. "
                f"overrides={overrides}, toml={toml_data}"
            )


# ===========================================================================
# Feature: execution-service-enhancement, Property 2: AdvancedScheduler 配置加载优先级
# ===========================================================================


class TestProperty2AdvancedSchedulerConfigPriority:
    """
    Property 2: AdvancedScheduler 配置加载优先级

    对于任意 overrides 字典和 TOML 文件内容组合，load_advanced_scheduler_config(overrides)
    返回的 AdvancedSchedulerConfig 中，overrides 中存在的字段应等于 overrides 值，
    不在 overrides 中但在 TOML 中的字段应等于 TOML 值，
    两者都不存在的字段应等于 AdvancedSchedulerConfig 的 dataclass 默认值。

    **Validates: Requirements 1.2, 1.3, 1.4**
    """

    @given(data=_as_overrides_and_toml())
    @settings(max_examples=100)
    def test_advanced_scheduler_config_loading_priority(self, data):
        """
        # Feature: execution-service-enhancement, Property 2: AdvancedScheduler 配置加载优先级

        **Validates: Requirements 1.2, 1.3, 1.4**
        """
        overrides, toml_data = data
        defaults = AdvancedSchedulerConfig()

        with patch(
            "src.main.config.domain_service_config_loader._load_toml",
            return_value=toml_data,
        ):
            result = load_advanced_scheduler_config(overrides if overrides else None)

        # 逐字段验证优先级: overrides > TOML > defaults
        for config_key, (override_key, toml_section, toml_key, _) in _AS_FIELDS.items():
            actual = getattr(result, config_key)

            if override_key in overrides:
                expected = overrides[override_key]
            elif toml_section in toml_data and toml_key in toml_data[toml_section]:
                expected = toml_data[toml_section][toml_key]
            else:
                expected = getattr(defaults, config_key)

            assert actual == expected, (
                f"字段 {config_key}: 期望 {expected}, 实际 {actual}. "
                f"overrides={overrides}, toml={toml_data}"
            )


# ===========================================================================
# Feature: execution-service-enhancement, Property 5: AdvancedSchedulerConfig 不可变性
# ===========================================================================

_advanced_scheduler_configs = st.builds(
    AdvancedSchedulerConfig,
    default_batch_size=_default_batch_size,
    default_interval_seconds=_default_interval_seconds,
    default_num_slices=_default_num_slices,
    default_volume_randomize_ratio=_default_volume_randomize_ratio,
    default_price_offset_ticks=_default_price_offset_ticks,
    default_price_tick=_default_price_tick_as,
)


class TestProperty5AdvancedSchedulerConfigImmutability:
    """
    Property 5: AdvancedSchedulerConfig 不可变性

    对于任意 AdvancedSchedulerConfig 实例，尝试修改其任意字段都应该抛出
    FrozenInstanceError 异常。

    **Validates: Requirements 3.2**
    """

    @given(config=_advanced_scheduler_configs)
    @settings(max_examples=100)
    def test_advanced_scheduler_config_immutability(self, config: AdvancedSchedulerConfig):
        """
        # Feature: execution-service-enhancement, Property 5: AdvancedSchedulerConfig 不可变性

        **Validates: Requirements 3.2**
        """
        for field in dataclasses.fields(config):
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(config, field.name, 999)


# ---------------------------------------------------------------------------
# 导入 SmartOrderExecutor 和 AdvancedOrderScheduler
# ---------------------------------------------------------------------------
from src.strategy.domain.domain_service.execution.smart_order_executor import (  # noqa: E402
    SmartOrderExecutor,
)
from src.strategy.domain.domain_service.execution.advanced_order_scheduler import (  # noqa: E402
    AdvancedOrderScheduler,
)

# ---------------------------------------------------------------------------
# 辅助策略：生成含随机子集已知字段 + 随机未知字段的 config_dict
# ---------------------------------------------------------------------------

_unknown_keys = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
    min_size=1,
    max_size=20,
).filter(lambda k: k not in {
    "timeout_seconds", "max_retries", "slippage_ticks", "price_tick",
    "default_batch_size", "default_interval_seconds", "default_num_slices",
    "default_volume_randomize_ratio", "default_price_offset_ticks", "default_price_tick",
})

_unknown_values = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    st.text(min_size=0, max_size=10),
)


@st.composite
def _soe_yaml_config_dict(draw):
    """
    为 SmartOrderExecutor.from_yaml_config 生成配置字典。
    每个已知字段独立决定是否出现；额外附加 0~3 个未知字段。
    """
    config = {}
    if draw(st.booleans()):
        config["timeout_seconds"] = draw(_timeout_seconds)
    if draw(st.booleans()):
        config["max_retries"] = draw(_max_retries)
    if draw(st.booleans()):
        config["slippage_ticks"] = draw(_slippage_ticks)
    if draw(st.booleans()):
        config["price_tick"] = draw(_price_tick_soe)

    # 添加未知字段
    unknown = draw(st.dictionaries(_unknown_keys, _unknown_values, min_size=0, max_size=3))
    config.update(unknown)
    return config


@st.composite
def _as_yaml_config_dict(draw):
    """
    为 AdvancedOrderScheduler.from_yaml_config 生成配置字典。
    每个已知字段独立决定是否出现；额外附加 0~3 个未知字段。
    """
    config = {}
    if draw(st.booleans()):
        config["default_batch_size"] = draw(_default_batch_size)
    if draw(st.booleans()):
        config["default_interval_seconds"] = draw(_default_interval_seconds)
    if draw(st.booleans()):
        config["default_num_slices"] = draw(_default_num_slices)
    if draw(st.booleans()):
        config["default_volume_randomize_ratio"] = draw(_default_volume_randomize_ratio)
    if draw(st.booleans()):
        config["default_price_offset_ticks"] = draw(_default_price_offset_ticks)
    if draw(st.booleans()):
        config["default_price_tick"] = draw(_default_price_tick_as)

    # 添加未知字段
    unknown = draw(st.dictionaries(_unknown_keys, _unknown_values, min_size=0, max_size=3))
    config.update(unknown)
    return config


# ===========================================================================
# Feature: execution-service-enhancement, Property 3: SmartOrderExecutor from_yaml_config 一致性
# ===========================================================================


class TestProperty3SmartOrderExecutorFromYamlConfigConsistency:
    """
    Property 3: SmartOrderExecutor from_yaml_config 一致性

    对于任意配置字典（可能缺少部分字段或包含未知字段），
    SmartOrderExecutor.from_yaml_config(config_dict) 生成的 OrderExecutionConfig 中，
    已提供的已知字段应与字典值一致，缺失的字段应等于 OrderExecutionConfig 的默认值，
    未知字段应被忽略。

    **Validates: Requirements 2.1, 2.3, 2.4**
    """

    @given(config_dict=_soe_yaml_config_dict())
    @settings(max_examples=100)
    def test_smart_order_executor_from_yaml_config_consistency(self, config_dict: dict):
        """
        # Feature: execution-service-enhancement, Property 3: SmartOrderExecutor from_yaml_config 一致性

        **Validates: Requirements 2.1, 2.3, 2.4**
        """
        defaults = OrderExecutionConfig()
        executor = SmartOrderExecutor.from_yaml_config(config_dict)
        result = executor.config

        # 已知字段列表
        known_fields = ["timeout_seconds", "max_retries", "slippage_ticks", "price_tick"]

        for field_name in known_fields:
            actual = getattr(result, field_name)
            if field_name in config_dict:
                expected = config_dict[field_name]
            else:
                expected = getattr(defaults, field_name)
            assert actual == expected, (
                f"字段 {field_name}: 期望 {expected}, 实际 {actual}. "
                f"config_dict={config_dict}"
            )

        # 验证未知字段被忽略：结果只有已知字段，不会多出属性
        import dataclasses as _dc
        result_field_names = {f.name for f in _dc.fields(result)}
        assert result_field_names == set(known_fields), (
            f"结果字段集合不符: {result_field_names}"
        )


# ===========================================================================
# Feature: execution-service-enhancement, Property 4: AdvancedOrderScheduler from_yaml_config 一致性
# ===========================================================================


class TestProperty4AdvancedOrderSchedulerFromYamlConfigConsistency:
    """
    Property 4: AdvancedOrderScheduler from_yaml_config 一致性

    对于任意配置字典（可能缺少部分字段或包含未知字段），
    AdvancedOrderScheduler.from_yaml_config(config_dict) 生成的 AdvancedSchedulerConfig 中，
    已提供的已知字段应与字典值一致，缺失的字段应等于 AdvancedSchedulerConfig 的默认值，
    未知字段应被忽略。

    **Validates: Requirements 2.2, 2.3, 2.4**
    """

    @given(config_dict=_as_yaml_config_dict())
    @settings(max_examples=100)
    def test_advanced_scheduler_from_yaml_config_consistency(self, config_dict: dict):
        """
        # Feature: execution-service-enhancement, Property 4: AdvancedOrderScheduler from_yaml_config 一致性

        **Validates: Requirements 2.2, 2.3, 2.4**
        """
        defaults = AdvancedSchedulerConfig()
        scheduler = AdvancedOrderScheduler.from_yaml_config(config_dict)
        result = scheduler.config

        # 已知字段列表
        known_fields = [
            "default_batch_size",
            "default_interval_seconds",
            "default_num_slices",
            "default_volume_randomize_ratio",
            "default_price_offset_ticks",
            "default_price_tick",
        ]

        for field_name in known_fields:
            actual = getattr(result, field_name)
            if field_name in config_dict:
                expected = config_dict[field_name]
            else:
                expected = getattr(defaults, field_name)
            assert actual == expected, (
                f"字段 {field_name}: 期望 {expected}, 实际 {actual}. "
                f"config_dict={config_dict}"
            )

        # 验证未知字段被忽略：结果只有已知字段，不会多出属性
        import dataclasses as _dc
        result_field_names = {f.name for f in _dc.fields(result)}
        assert result_field_names == set(known_fields), (
            f"结果字段集合不符: {result_field_names}"
        )


# ---------------------------------------------------------------------------
# 导入 Property 8, 9 所需的额外模块
# ---------------------------------------------------------------------------
from datetime import datetime

from src.strategy.domain.value_object.trading.order_execution import ManagedOrder  # noqa: E402
from src.strategy.domain.event.event_types import OrderRetryExhaustedEvent  # noqa: E402
from src.strategy.domain.value_object.trading.order_instruction import (  # noqa: E402
    OrderInstruction,
    Direction,
    Offset,
    OrderType,
)

# ---------------------------------------------------------------------------
# Hypothesis 策略：OrderInstruction 生成器
# ---------------------------------------------------------------------------

_vt_symbols = st.sampled_from(["IO2506-C-4000.CFFEX", "rb2501.SHFE", "IF2506.CFFEX"])
_directions = st.sampled_from([Direction.LONG, Direction.SHORT])
_offsets = st.sampled_from([Offset.OPEN, Offset.CLOSE])
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
    order_type=st.just(OrderType.LIMIT),
)


# ===========================================================================
# Feature: execution-service-enhancement, Property 8: 重试耗尽产生正确的 OrderRetryExhaustedEvent
# ===========================================================================


class TestProperty8RetryExhaustedProducesCorrectEvent:
    """
    Property 8: 重试耗尽产生正确的 OrderRetryExhaustedEvent

    对于任意 retry_count >= max_retries 的 ManagedOrder，调用 prepare_retry 应返回
    (None, [event])，其中 event 为 OrderRetryExhaustedEvent，且 event.vt_symbol 等于
    原始指令的 vt_symbol，event.total_retries 等于 managed_order.retry_count，
    event.original_price 和 event.final_price 等于原始指令价格。

    **Validates: Requirements 6.1, 6.2**
    """

    @given(
        instruction=_order_instructions,
        max_retries=st.integers(min_value=0, max_value=10),
        extra_retries=st.integers(min_value=0, max_value=10),
        price_tick=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_retry_exhausted_produces_correct_event(
        self, instruction, max_retries, extra_retries, price_tick
    ):
        """
        # Feature: execution-service-enhancement, Property 8: 重试耗尽产生正确的 OrderRetryExhaustedEvent

        **Validates: Requirements 6.1, 6.2**
        """
        # retry_count >= max_retries 保证重试耗尽
        retry_count = max_retries + extra_retries

        config = OrderExecutionConfig(max_retries=max_retries, price_tick=price_tick)
        executor = SmartOrderExecutor(config)

        managed_order = ManagedOrder(
            vt_orderid="test_order",
            instruction=instruction,
            submit_time=datetime(2026, 1, 1, 10, 0, 0),
            retry_count=retry_count,
        )

        result, events = executor.prepare_retry(managed_order, price_tick)

        # 应返回 None（无新指令）
        assert result is None, (
            f"重试耗尽时应返回 None，实际返回 {result}. "
            f"retry_count={retry_count}, max_retries={max_retries}"
        )

        # 应返回恰好一个事件
        assert len(events) == 1, (
            f"重试耗尽时应返回恰好 1 个事件，实际返回 {len(events)} 个"
        )

        event = events[0]

        # 事件类型正确
        assert isinstance(event, OrderRetryExhaustedEvent), (
            f"事件类型应为 OrderRetryExhaustedEvent，实际为 {type(event)}"
        )

        # 字段验证
        assert event.vt_symbol == instruction.vt_symbol, (
            f"vt_symbol 不匹配: 期望 {instruction.vt_symbol}, 实际 {event.vt_symbol}"
        )
        assert event.total_retries == retry_count, (
            f"total_retries 不匹配: 期望 {retry_count}, 实际 {event.total_retries}"
        )
        assert event.original_price == instruction.price, (
            f"original_price 不匹配: 期望 {instruction.price}, 实际 {event.original_price}"
        )
        assert event.final_price == instruction.price, (
            f"final_price 不匹配: 期望 {instruction.price}, 实际 {event.final_price}"
        )


# ===========================================================================
# Feature: execution-service-enhancement, Property 9: 定时拆单子单总量守恒
# ===========================================================================


class TestProperty9TimedSplitVolumeConservation:
    """
    Property 9: 定时拆单子单总量守恒

    对于任意有效的 OrderInstruction（volume > 0）、正整数 interval_seconds 和
    per_order_volume，submit_timed_split 产生的所有子单 volume 之和应等于原始指令的 volume。

    **Validates: Requirements 5.2**
    """

    @given(
        instruction=_order_instructions,
        interval_seconds=st.integers(min_value=1, max_value=3600),
        per_order_volume=st.integers(min_value=1, max_value=500),
    )
    @settings(max_examples=100)
    def test_timed_split_volume_conservation(
        self, instruction, interval_seconds, per_order_volume
    ):
        """
        # Feature: execution-service-enhancement, Property 9: 定时拆单子单总量守恒

        **Validates: Requirements 5.2**
        """
        scheduler = AdvancedOrderScheduler()
        start_time = datetime(2026, 1, 1, 10, 0, 0)

        advanced_order = scheduler.submit_timed_split(
            instruction=instruction,
            interval_seconds=interval_seconds,
            per_order_volume=per_order_volume,
            start_time=start_time,
        )

        # 子单总量应等于原始指令的 volume
        total_child_volume = sum(child.volume for child in advanced_order.child_orders)
        assert total_child_volume == instruction.volume, (
            f"子单总量不守恒: 期望 {instruction.volume}, 实际 {total_child_volume}. "
            f"per_order_volume={per_order_volume}, "
            f"子单数={len(advanced_order.child_orders)}, "
            f"各子单量={[c.volume for c in advanced_order.child_orders]}"
        )
