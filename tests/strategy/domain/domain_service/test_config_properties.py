"""
配置值对象属性测试

Feature: domain-service-config-enhancement, Property 1: 配置值对象不可变性
Feature: domain-service-config-enhancement, Property 6: 配置字段可自定义

**Validates: Requirements 2.1, 3.1, 4.1, 2.4, 3.4, 4.4**
"""

import dataclasses
import sys
from enum import Enum
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing BaseFutureSelector
# ---------------------------------------------------------------------------


class _Exchange(str, Enum):
    SHFE = "SHFE"
    CFFEX = "CFFEX"


class _Product(str, Enum):
    FUTURES = "期货"


class _ContractData:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def vt_symbol(self) -> str:
        return f"{self.symbol}.{self.exchange.value}"


_const_mod = MagicMock()
_const_mod.Exchange = _Exchange
_const_mod.Product = _Product

_obj_mod = MagicMock()
_obj_mod.ContractData = _ContractData

for _name in [
    "vnpy",
    "vnpy.event",
    "vnpy.trader",
    "vnpy.trader.setting",
    "vnpy.trader.engine",
    "vnpy.trader.database",
    "vnpy_mysql",
]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

sys.modules["vnpy.trader.constant"] = _const_mod
sys.modules["vnpy.trader.object"] = _obj_mod

# ---------------------------------------------------------------------------
# Now safe to import all modules
# ---------------------------------------------------------------------------

from src.strategy.domain.value_object.config import (  # noqa: E402
    FutureSelectorConfig,
    PositionSizingConfig,
    PricingEngineConfig,
)
from src.strategy.domain.value_object.pricing.pricing import PricingModel  # noqa: E402
from src.strategy.domain.domain_service.risk.position_sizing_service import PositionSizingService  # noqa: E402
from src.strategy.domain.domain_service.pricing.pricing_engine import PricingEngine  # noqa: E402
from src.strategy.domain.domain_service.selection.future_selection_service import BaseFutureSelector  # noqa: E402


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


# ===========================================================================
# Feature: domain-service-config-enhancement, Property 6: 配置字段可自定义
# ===========================================================================


class TestProperty6CustomConfigUsage:
    """
    Property 6: 配置字段可自定义

    对于任意配置值对象，使用非默认值创建实例后，服务应该使用自定义的配置值，
    而非默认值。

    **Validates: Requirements 2.4, 3.4, 4.4**
    """

    @given(config=_position_sizing_configs)
    @settings(max_examples=100)
    def test_position_sizing_service_uses_custom_config(self, config: PositionSizingConfig):
        """
        Feature: domain-service-config-enhancement, Property 6: 配置字段可自定义

        使用自定义 PositionSizingConfig 实例化 PositionSizingService 后，
        服务内部 _config 的每个字段应与传入的自定义值完全一致。

        **Validates: Requirements 2.4**
        """
        service = PositionSizingService(config=config)

        assert service._config.max_positions == config.max_positions
        assert service._config.global_daily_limit == config.global_daily_limit
        assert service._config.contract_daily_limit == config.contract_daily_limit
        assert service._config.margin_ratio == config.margin_ratio
        assert service._config.min_margin_ratio == config.min_margin_ratio
        assert service._config.margin_usage_limit == config.margin_usage_limit
        assert service._config.max_volume_per_order == config.max_volume_per_order

    @given(config=_pricing_engine_configs)
    @settings(max_examples=100)
    def test_pricing_engine_uses_custom_config(self, config: PricingEngineConfig):
        """
        Feature: domain-service-config-enhancement, Property 6: 配置字段可自定义

        使用自定义 PricingEngineConfig 实例化 PricingEngine 后，
        服务内部 _config 的每个字段应与传入的自定义值完全一致。

        **Validates: Requirements 3.4**
        """
        engine = PricingEngine(config=config)

        assert engine._config.american_model == config.american_model
        assert engine._config.crr_steps == config.crr_steps

    @given(config=_future_selector_configs)
    @settings(max_examples=100)
    def test_future_selector_uses_custom_config(self, config: FutureSelectorConfig):
        """
        Feature: domain-service-config-enhancement, Property 6: 配置字段可自定义

        使用自定义 FutureSelectorConfig 实例化 BaseFutureSelector 后，
        服务内部 _config 的每个字段应与传入的自定义值完全一致。

        **Validates: Requirements 4.4**
        """
        selector = BaseFutureSelector(config=config)

        assert selector._config.volume_weight == config.volume_weight
        assert selector._config.oi_weight == config.oi_weight
        assert selector._config.rollover_days == config.rollover_days
