"""
跨定价器属性测试

Property 5: 无效输入返回错误
验证 BAWPricer、CRRPricer、BlackScholesPricer 对无效输入均返回 success=False。

# Feature: option-pricing-engine, Property 5: 无效输入返回错误
"""
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.domain_service.pricing import BAWPricer, CRRPricer, BlackScholesPricer, GreeksCalculator
from src.strategy.domain.value_object.pricing import (
    ExerciseStyle,
    PricingInput,
)


# ---------------------------------------------------------------------------
# 策略：生成至少包含一个无效参数的 PricingInput
# 无效条件: spot_price <= 0 | strike_price <= 0 | volatility <= 0 | time_to_expiry < 0
# ---------------------------------------------------------------------------

# 有效范围参数（用于非无效字段）
_valid_positive = st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)
_valid_vol = st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False)
_valid_time = st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
_valid_rate = st.floats(min_value=-0.5, max_value=1.0, allow_nan=False, allow_infinity=False)

# 无效值策略
_invalid_non_positive = st.floats(max_value=0.0, allow_nan=False, allow_infinity=False)
_invalid_negative = st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False)


def _invalid_pricing_input_strategy():
    """
    生成至少包含一个无效参数的 PricingInput。

    随机选择一个或多个参数设为无效值，其余保持有效。
    """
    return st.one_of(
        # Case 1: spot_price <= 0
        st.builds(
            PricingInput,
            spot_price=_invalid_non_positive,
            strike_price=_valid_positive,
            time_to_expiry=_valid_time,
            risk_free_rate=_valid_rate,
            volatility=_valid_vol,
            option_type=st.sampled_from(["call", "put"]),
            exercise_style=st.sampled_from([ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN]),
        ),
        # Case 2: strike_price <= 0
        st.builds(
            PricingInput,
            spot_price=_valid_positive,
            strike_price=_invalid_non_positive,
            time_to_expiry=_valid_time,
            risk_free_rate=_valid_rate,
            volatility=_valid_vol,
            option_type=st.sampled_from(["call", "put"]),
            exercise_style=st.sampled_from([ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN]),
        ),
        # Case 3: volatility <= 0
        st.builds(
            PricingInput,
            spot_price=_valid_positive,
            strike_price=_valid_positive,
            time_to_expiry=_valid_time,
            risk_free_rate=_valid_rate,
            volatility=_invalid_non_positive,
            option_type=st.sampled_from(["call", "put"]),
            exercise_style=st.sampled_from([ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN]),
        ),
        # Case 4: time_to_expiry < 0
        st.builds(
            PricingInput,
            spot_price=_valid_positive,
            strike_price=_valid_positive,
            time_to_expiry=_invalid_negative,
            risk_free_rate=_valid_rate,
            volatility=_valid_vol,
            option_type=st.sampled_from(["call", "put"]),
            exercise_style=st.sampled_from([ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN]),
        ),
    )


# Feature: option-pricing-engine, Property 5: 无效输入返回错误
class TestProperty5InvalidInputReturnsError:
    """
    Property 5: 无效输入返回错误

    *For any* 包含无效参数的 PricingInput（spot_price <= 0 或 strike_price <= 0
    或 volatility <= 0 或 time_to_expiry < 0），调用任意定价器的 price 方法
    应返回 success 为 False 的 PricingResult。

    **Validates: Requirements 2.5, 3.6, 4.3**
    """

    @given(invalid_input=_invalid_pricing_input_strategy())
    @settings(max_examples=200)
    def test_baw_pricer_rejects_invalid_input(self, invalid_input: PricingInput):
        """BAWPricer 对无效输入应返回 success=False"""
        pricer = BAWPricer()
        result = pricer.price(invalid_input)
        assert not result.success, (
            f"BAWPricer 应拒绝无效输入但返回 success=True: "
            f"S={invalid_input.spot_price}, K={invalid_input.strike_price}, "
            f"σ={invalid_input.volatility}, T={invalid_input.time_to_expiry}"
        )
        assert result.error_message, "error_message 不应为空"

    @given(invalid_input=_invalid_pricing_input_strategy())
    @settings(max_examples=200)
    def test_crr_pricer_rejects_invalid_input(self, invalid_input: PricingInput):
        """CRRPricer 对无效输入应返回 success=False"""
        pricer = CRRPricer()
        result = pricer.price(invalid_input)
        assert not result.success, (
            f"CRRPricer 应拒绝无效输入但返回 success=True: "
            f"S={invalid_input.spot_price}, K={invalid_input.strike_price}, "
            f"σ={invalid_input.volatility}, T={invalid_input.time_to_expiry}"
        )
        assert result.error_message, "error_message 不应为空"

    @given(invalid_input=_invalid_pricing_input_strategy())
    @settings(max_examples=200)
    def test_bs_pricer_rejects_invalid_input(self, invalid_input: PricingInput):
        """BlackScholesPricer 对无效输入应返回 success=False"""
        pricer = BlackScholesPricer(GreeksCalculator())
        result = pricer.price(invalid_input)
        assert not result.success, (
            f"BlackScholesPricer 应拒绝无效输入但返回 success=True: "
            f"S={invalid_input.spot_price}, K={invalid_input.strike_price}, "
            f"σ={invalid_input.volatility}, T={invalid_input.time_to_expiry}"
        )
        assert result.error_message, "error_message 不应为空"
