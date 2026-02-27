"""
配置值对象不可变性属性测试

Feature: domain-service-config-enhancement, Property 1: 配置值对象不可变性

对于任意配置值对象实例（PositionSizingConfig、PricingEngineConfig、FutureSelectorConfig），
尝试修改其任意字段都应该抛出 FrozenInstanceError 异常。

**Validates: Requirements 2.1, 3.1, 4.1**
"""

import dataclasses

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.value_object.config import (
    FutureSelectorConfig,
    PositionSizingConfig,
    PricingEngineConfig,
)
from src.strategy.domain.value_object.pricing import PricingModel


# ---------------------------------------------------------------------------
# Hypothesis 策略：为每个配置类生成随机字段值
# ---------------------------------------------------------------------------

_position_sizing_configs = st.builds(
    PositionSizingConfig,
    max_positions=st.integers(min_value=1, max_value=100),
    global_daily_limit=st.integers(min_value=1, max_value=500),
    contract_daily_limit=st.integers(min_value=1, max_value=50),
    margin_ratio=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
    min_margin_ratio=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
    margin_usage_limit=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
    max_volume_per_order=st.integers(min_value=1, max_value=1000),
)

_pricing_engine_configs = st.builds(
    PricingEngineConfig,
    american_model=st.sampled_from(list(PricingModel)),
    crr_steps=st.integers(min_value=1, max_value=1000),
)

_future_selector_configs = st.builds(
    FutureSelectorConfig,
    volume_weight=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    oi_weight=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    rollover_days=st.integers(min_value=1, max_value=30),
)


def _assert_all_fields_frozen(config, new_value) -> None:
    """验证配置对象的所有字段均不可修改。"""
    for field in dataclasses.fields(config):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(config, field.name, new_value)


# ===========================================================================
# Feature: domain-service-config-enhancement, Property 1: 配置值对象不可变性
# ===========================================================================


class TestProperty1ConfigImmutability:
    """
    Property 1: 配置值对象不可变性

    对于任意配置值对象实例（PositionSizingConfig、PricingEngineConfig、
    FutureSelectorConfig），尝试修改其任意字段都应该抛出 FrozenInstanceError。

    **Validates: Requirements 2.1, 3.1, 4.1**
    """

    @given(config=_position_sizing_configs)
    @settings(max_examples=100)
    def test_position_sizing_config_immutability(self, config: PositionSizingConfig):
        """
        Feature: domain-service-config-enhancement, Property 1: 配置值对象不可变性

        PositionSizingConfig 的所有字段均不可修改。

        **Validates: Requirements 2.1**
        """
        _assert_all_fields_frozen(config, 999)

    @given(config=_pricing_engine_configs)
    @settings(max_examples=100)
    def test_pricing_engine_config_immutability(self, config: PricingEngineConfig):
        """
        Feature: domain-service-config-enhancement, Property 1: 配置值对象不可变性

        PricingEngineConfig 的所有字段均不可修改。

        **Validates: Requirements 3.1**
        """
        _assert_all_fields_frozen(config, 999)

    @given(config=_future_selector_configs)
    @settings(max_examples=100)
    def test_future_selector_config_immutability(self, config: FutureSelectorConfig):
        """
        Feature: domain-service-config-enhancement, Property 1: 配置值对象不可变性

        FutureSelectorConfig 的所有字段均不可修改。

        **Validates: Requirements 4.1**
        """
        _assert_all_fields_frozen(config, 999)
