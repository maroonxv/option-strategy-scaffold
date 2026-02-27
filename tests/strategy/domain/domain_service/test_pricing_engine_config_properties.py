"""
PricingEngine 配置行为一致性属性测试

Feature: domain-service-config-enhancement, Property 3: PricingEngine 行为一致性

对于任意有效的 PricingInput（spot_price > 0, strike_price > 0, volatility > 0,
time_to_expiry >= 0），使用默认配置实例化的 PricingEngine 调用 price 方法，
应该产生与重构前使用默认参数实例化的引擎相同的 PricingResult。

**Validates: Requirements 3.6, 5.2**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.domain_service.pricing import PricingEngine
from src.strategy.domain.value_object.config.pricing_engine_config import PricingEngineConfig
from src.strategy.domain.value_object.pricing.pricing import (
    ExerciseStyle,
    PricingInput,
    PricingModel,
)

# ---------------------------------------------------------------------------
# 共用策略 — 生成有效的定价输入
# ---------------------------------------------------------------------------

_spot = st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False)
_strike = st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False)
_time = st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False)
_rate = st.floats(min_value=0.0, max_value=0.15, allow_nan=False, allow_infinity=False)
_vol = st.floats(min_value=0.05, max_value=3.0, allow_nan=False, allow_infinity=False)
_opt_type = st.sampled_from(["call", "put"])
_exercise_style = st.sampled_from([ExerciseStyle.EUROPEAN, ExerciseStyle.AMERICAN])


def _valid_pricing_input():
    """生成有效的 PricingInput 策略"""
    return st.builds(
        PricingInput,
        spot_price=_spot,
        strike_price=_strike,
        time_to_expiry=_time,
        risk_free_rate=_rate,
        volatility=_vol,
        option_type=_opt_type,
        exercise_style=_exercise_style,
    )


# ---------------------------------------------------------------------------
# 两种实例化方式：显式默认配置 vs 无参数（隐式默认）
# ---------------------------------------------------------------------------

_engine_with_config = PricingEngine(config=PricingEngineConfig())
_engine_no_config = PricingEngine()


# ===========================================================================
# Feature: domain-service-config-enhancement, Property 3: PricingEngine 行为一致性
# ===========================================================================


class TestProperty3PricingBehaviorConsistency:
    """
    Property 3: PricingEngine 行为一致性

    使用默认配置 PricingEngineConfig() 实例化的 PricingEngine 与
    不传配置实例化的 PricingEngine，对同一输入应产生完全相同的 PricingResult。

    同时验证默认配置值与重构前默认值一致：
    - american_model = PricingModel.BAW
    - crr_steps = 100

    **Validates: Requirements 3.6, 5.2**
    """

    def test_default_config_matches_pre_refactor_defaults(self):
        """默认 PricingEngineConfig 字段值与重构前默认参数一致"""
        config = PricingEngineConfig()
        assert config.american_model == PricingModel.BAW, (
            f"american_model 默认值应为 BAW, 实际为 {config.american_model}"
        )
        assert config.crr_steps == 100, (
            f"crr_steps 默认值应为 100, 实际为 {config.crr_steps}"
        )

    @given(params=_valid_pricing_input())
    @settings(max_examples=200)
    def test_pricing_consistency_with_and_without_config(self, params: PricingInput):
        """
        Feature: domain-service-config-enhancement, Property 3: PricingEngine 行为一致性

        PricingEngine(config=PricingEngineConfig()) 与 PricingEngine()
        对同一有效输入产生完全相同的 PricingResult。
        """
        result_with_config = _engine_with_config.price(params)
        result_no_config = _engine_no_config.price(params)

        assert result_with_config.success == result_no_config.success, (
            f"success 不一致: with_config={result_with_config.success}, "
            f"no_config={result_no_config.success}, input={params}"
        )
        assert result_with_config.model_used == result_no_config.model_used, (
            f"model_used 不一致: with_config={result_with_config.model_used}, "
            f"no_config={result_no_config.model_used}, input={params}"
        )
        assert result_with_config.price == result_no_config.price, (
            f"price 不一致: with_config={result_with_config.price}, "
            f"no_config={result_no_config.price}, input={params}"
        )
        assert result_with_config.error_message == result_no_config.error_message, (
            f"error_message 不一致: with_config={result_with_config.error_message}, "
            f"no_config={result_no_config.error_message}, input={params}"
        )
