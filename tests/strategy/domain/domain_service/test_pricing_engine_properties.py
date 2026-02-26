"""
PricingEngine 属性测试

Property 5: PricingEngine 路由正确性
Property 6: PricingEngine 错误输入处理

# Feature: pricing-service-enhancement, Property 5-6
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.domain_service.pricing.pricing_engine import PricingEngine
from src.strategy.domain.value_object.pricing import (
    ExerciseStyle,
    PricingInput,
    PricingModel,
)


# ---------------------------------------------------------------------------
# 共用策略
# ---------------------------------------------------------------------------

_spot = st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False)
_strike = st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False)
_time = st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False)
_rate = st.floats(min_value=0.0, max_value=0.15, allow_nan=False, allow_infinity=False)
_vol = st.floats(min_value=0.05, max_value=3.0, allow_nan=False, allow_infinity=False)
_opt_type = st.sampled_from(["call", "put"])
_exercise_style = st.sampled_from([ExerciseStyle.EUROPEAN, ExerciseStyle.AMERICAN])

_engine_baw = PricingEngine(american_model=PricingModel.BAW)
_engine_crr = PricingEngine(american_model=PricingModel.CRR, crr_steps=100)


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


# ===========================================================================
# Feature: pricing-service-enhancement, Property 5: PricingEngine 路由正确性
# ===========================================================================


class TestProperty5RoutingCorrectness:
    """
    Property 5: PricingEngine 路由正确性

    *For any* 有效的 PricingInput：
    - 当 exercise_style=EUROPEAN 时，PricingResult.model_used 为 "black_scholes"
    - 当 exercise_style=AMERICAN 且配置为 BAW 时，PricingResult.model_used 为 "baw"
    - 当 exercise_style=AMERICAN 且配置为 CRR 时，PricingResult.model_used 为 "crr"

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6**
    """

    @given(params=_valid_pricing_input())
    @settings(max_examples=200)
    def test_european_routes_to_black_scholes(self, params: PricingInput):
        """EUROPEAN 期权始终路由到 black_scholes"""
        if params.exercise_style != ExerciseStyle.EUROPEAN:
            return  # 只测试欧式

        result = _engine_baw.price(params)

        assert result.success, (
            f"有效欧式输入应成功: {params}, err={result.error_message}"
        )
        assert result.model_used == "black_scholes", (
            f"欧式期权 model_used 应为 'black_scholes', 实际为 '{result.model_used}'"
        )
        assert result.price >= 0, "有效输入的价格应非负"

    @given(
        spot=_spot, strike=_strike, time=_time, rate=_rate,
        vol=_vol, opt=_opt_type,
    )
    @settings(max_examples=200)
    def test_american_baw_routes_to_baw(
        self, spot, strike, time, rate, vol, opt,
    ):
        """AMERICAN 期权 + BAW 配置路由到 baw"""
        params = PricingInput(
            spot_price=spot,
            strike_price=strike,
            time_to_expiry=time,
            risk_free_rate=rate,
            volatility=vol,
            option_type=opt,
            exercise_style=ExerciseStyle.AMERICAN,
        )

        result = _engine_baw.price(params)

        assert result.success, (
            f"有效美式输入(BAW)应成功: {params}, err={result.error_message}"
        )
        assert result.model_used == "baw", (
            f"美式(BAW) model_used 应为 'baw', 实际为 '{result.model_used}'"
        )
        assert result.price >= 0, "有效输入的价格应非负"

    @given(
        spot=_spot, strike=_strike, time=_time, rate=_rate,
        vol=_vol, opt=_opt_type,
    )
    @settings(max_examples=200)
    def test_american_crr_routes_to_crr(
        self, spot, strike, time, rate, vol, opt,
    ):
        """AMERICAN 期权 + CRR 配置路由到 crr"""
        params = PricingInput(
            spot_price=spot,
            strike_price=strike,
            time_to_expiry=time,
            risk_free_rate=rate,
            volatility=vol,
            option_type=opt,
            exercise_style=ExerciseStyle.AMERICAN,
        )

        result = _engine_crr.price(params)

        assert result.success, (
            f"有效美式输入(CRR)应成功: {params}, err={result.error_message}"
        )
        assert result.model_used == "crr", (
            f"美式(CRR) model_used 应为 'crr', 实际为 '{result.model_used}'"
        )
        assert result.price >= 0, "有效输入的价格应非负"


# ===========================================================================
# Feature: pricing-service-enhancement, Property 6: PricingEngine 错误输入处理
# ===========================================================================


class TestProperty6ErrorInputHandling:
    """
    Property 6: PricingEngine 错误输入处理

    *For any* 包含无效参数的 PricingInput（spot_price ≤ 0 或 strike_price ≤ 0
    或 volatility ≤ 0 或 time_to_expiry < 0），PricingEngine.price 应返回
    success=False 的 PricingResult 且 error_message 非空。

    **Validates: Requirements 4.5**
    """

    @given(
        spot=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
        strike=_strike, time=_time, rate=_rate, vol=_vol,
        opt=_opt_type, style=_exercise_style,
    )
    @settings(max_examples=200)
    def test_non_positive_spot_price(self, spot, strike, time, rate, vol, opt, style):
        """spot_price ≤ 0 应返回 success=False"""
        params = PricingInput(
            spot_price=spot, strike_price=strike, time_to_expiry=time,
            risk_free_rate=rate, volatility=vol, option_type=opt,
            exercise_style=style,
        )
        result = _engine_baw.price(params)

        assert not result.success, f"spot_price={spot} ≤ 0 应返回 success=False"
        assert result.error_message, "error_message 不应为空"
        assert result.model_used == "", "无效输入 model_used 应为空字符串"

    @given(
        spot=_spot,
        strike=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
        time=_time, rate=_rate, vol=_vol,
        opt=_opt_type, style=_exercise_style,
    )
    @settings(max_examples=200)
    def test_non_positive_strike_price(self, spot, strike, time, rate, vol, opt, style):
        """strike_price ≤ 0 应返回 success=False"""
        params = PricingInput(
            spot_price=spot, strike_price=strike, time_to_expiry=time,
            risk_free_rate=rate, volatility=vol, option_type=opt,
            exercise_style=style,
        )
        result = _engine_baw.price(params)

        assert not result.success, f"strike_price={strike} ≤ 0 应返回 success=False"
        assert result.error_message, "error_message 不应为空"
        assert result.model_used == "", "无效输入 model_used 应为空字符串"

    @given(
        spot=_spot, strike=_strike, time=_time, rate=_rate,
        vol=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
        opt=_opt_type, style=_exercise_style,
    )
    @settings(max_examples=200)
    def test_non_positive_volatility(self, spot, strike, time, rate, vol, opt, style):
        """volatility ≤ 0 应返回 success=False"""
        params = PricingInput(
            spot_price=spot, strike_price=strike, time_to_expiry=time,
            risk_free_rate=rate, volatility=vol, option_type=opt,
            exercise_style=style,
        )
        result = _engine_baw.price(params)

        assert not result.success, f"volatility={vol} ≤ 0 应返回 success=False"
        assert result.error_message, "error_message 不应为空"
        assert result.model_used == "", "无效输入 model_used 应为空字符串"

    @given(
        spot=_spot, strike=_strike,
        time=st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False),
        rate=_rate, vol=_vol,
        opt=_opt_type, style=_exercise_style,
    )
    @settings(max_examples=200)
    def test_negative_time_to_expiry(self, spot, strike, time, rate, vol, opt, style):
        """time_to_expiry < 0 应返回 success=False"""
        params = PricingInput(
            spot_price=spot, strike_price=strike, time_to_expiry=time,
            risk_free_rate=rate, volatility=vol, option_type=opt,
            exercise_style=style,
        )
        result = _engine_baw.price(params)

        assert not result.success, f"time_to_expiry={time} < 0 应返回 success=False"
        assert result.error_message, "error_message 不应为空"
        assert result.model_used == "", "无效输入 model_used 应为空字符串"
