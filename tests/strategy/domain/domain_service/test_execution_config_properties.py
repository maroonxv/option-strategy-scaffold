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
