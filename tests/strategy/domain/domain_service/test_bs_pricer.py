"""
BlackScholesPricer 单元测试

验证 BlackScholesPricer 的输入校验、委托计算和异常处理。
"""
import math
import pytest
from unittest.mock import MagicMock

from src.strategy.domain.domain_service.pricing.bs_pricer import BlackScholesPricer
from src.strategy.domain.domain_service.pricing.greeks_calculator import GreeksCalculator
from src.strategy.domain.value_object.greeks import GreeksInput
from src.strategy.domain.value_object.pricing import (
    ExerciseStyle,
    PricingInput,
    PricingResult,
)


@pytest.fixture
def calculator():
    return GreeksCalculator()


@pytest.fixture
def pricer(calculator):
    return BlackScholesPricer(calculator)


def _make_input(
    spot_price=100.0,
    strike_price=100.0,
    time_to_expiry=0.5,
    risk_free_rate=0.05,
    volatility=0.2,
    option_type="call",
    exercise_style=ExerciseStyle.EUROPEAN,
) -> PricingInput:
    return PricingInput(
        spot_price=spot_price,
        strike_price=strike_price,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=volatility,
        option_type=option_type,
        exercise_style=exercise_style,
    )


class TestBlackScholesPricerValidation:
    """输入校验测试"""

    def test_spot_price_zero(self, pricer):
        result = pricer.price(_make_input(spot_price=0))
        assert not result.success
        assert "spot_price" in result.error_message

    def test_spot_price_negative(self, pricer):
        result = pricer.price(_make_input(spot_price=-1.0))
        assert not result.success
        assert "spot_price" in result.error_message

    def test_strike_price_zero(self, pricer):
        result = pricer.price(_make_input(strike_price=0))
        assert not result.success
        assert "strike_price" in result.error_message

    def test_strike_price_negative(self, pricer):
        result = pricer.price(_make_input(strike_price=-5.0))
        assert not result.success
        assert "strike_price" in result.error_message

    def test_volatility_zero(self, pricer):
        result = pricer.price(_make_input(volatility=0))
        assert not result.success
        assert "volatility" in result.error_message

    def test_volatility_negative(self, pricer):
        result = pricer.price(_make_input(volatility=-0.1))
        assert not result.success
        assert "volatility" in result.error_message

    def test_time_to_expiry_negative(self, pricer):
        result = pricer.price(_make_input(time_to_expiry=-0.01))
        assert not result.success
        assert "time_to_expiry" in result.error_message

    def test_time_to_expiry_zero_is_valid(self, pricer):
        """T=0 是合法输入，应返回内在价值"""
        result = pricer.price(_make_input(time_to_expiry=0, spot_price=110, strike_price=100))
        assert result.success
        assert result.price == pytest.approx(10.0)

    def test_error_result_has_model_used(self, pricer):
        result = pricer.price(_make_input(spot_price=-1))
        assert result.model_used == "black_scholes"


class TestBlackScholesPricerPricing:
    """定价计算测试"""

    def test_call_price_positive(self, pricer):
        result = pricer.price(_make_input(option_type="call"))
        assert result.success
        assert result.price > 0
        assert result.model_used == "black_scholes"

    def test_put_price_positive(self, pricer):
        result = pricer.price(_make_input(option_type="put"))
        assert result.success
        assert result.price > 0
        assert result.model_used == "black_scholes"

    def test_delegation_matches_direct_call(self, pricer, calculator):
        """BlackScholesPricer 结果应与直接调用 GreeksCalculator.bs_price 一致"""
        params = _make_input()
        result = pricer.price(params)

        greeks_input = GreeksInput(
            spot_price=params.spot_price,
            strike_price=params.strike_price,
            time_to_expiry=params.time_to_expiry,
            risk_free_rate=params.risk_free_rate,
            volatility=params.volatility,
            option_type=params.option_type,
        )
        expected_price = calculator.bs_price(greeks_input)

        assert result.success
        assert result.price == expected_price

    def test_deep_itm_call(self, pricer):
        """深度实值看涨期权价格应接近 S - K*e^(-rT)"""
        result = pricer.price(_make_input(spot_price=200, strike_price=100))
        assert result.success
        assert result.price > 95  # 应远大于内在价值的折现

    def test_deep_otm_call(self, pricer):
        """深度虚值看涨期权价格应接近 0"""
        result = pricer.price(_make_input(spot_price=50, strike_price=200))
        assert result.success
        assert result.price < 1.0

    def test_atm_call_at_expiry(self, pricer):
        """到期时 ATM 期权价值为 0"""
        result = pricer.price(_make_input(time_to_expiry=0, spot_price=100, strike_price=100))
        assert result.success
        assert result.price == 0.0

    def test_itm_put_at_expiry(self, pricer):
        """到期时实值看跌期权返回内在价值"""
        result = pricer.price(
            _make_input(time_to_expiry=0, spot_price=80, strike_price=100, option_type="put")
        )
        assert result.success
        assert result.price == pytest.approx(20.0)


class TestBlackScholesPricerExceptionHandling:
    """异常捕获测试"""

    def test_calculator_exception_caught(self):
        """GreeksCalculator 抛出异常时应返回 error PricingResult"""
        mock_calc = MagicMock(spec=GreeksCalculator)
        mock_calc.bs_price.side_effect = OverflowError("数值溢出")
        pricer = BlackScholesPricer(mock_calc)

        result = pricer.price(_make_input())
        assert not result.success
        assert "数值溢出" in result.error_message
        assert result.model_used == "black_scholes"

    def test_calculator_value_error_caught(self):
        mock_calc = MagicMock(spec=GreeksCalculator)
        mock_calc.bs_price.side_effect = ValueError("math domain error")
        pricer = BlackScholesPricer(mock_calc)

        result = pricer.price(_make_input())
        assert not result.success
        assert "math domain error" in result.error_message


# ---------------------------------------------------------------------------
# Property-Based Tests (hypothesis)
# Feature: option-pricing-engine, Property 4: BS 委托一致性
# ---------------------------------------------------------------------------
from hypothesis import given, settings, assume
import hypothesis.strategies as st


# 生成合理范围内的金融参数
valid_spot = st.floats(min_value=0.01, max_value=10000, allow_nan=False, allow_infinity=False)
valid_strike = st.floats(min_value=0.01, max_value=10000, allow_nan=False, allow_infinity=False)
valid_vol = st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False)
valid_time = st.floats(min_value=0.001, max_value=5.0, allow_nan=False, allow_infinity=False)
valid_rate = st.floats(min_value=-0.5, max_value=1.0, allow_nan=False, allow_infinity=False)
valid_option_type = st.sampled_from(["call", "put"])


class TestBSPricerProperty4:
    """
    Property 4: BS 委托一致性

    *For any* 有效欧式 PricingInput，BlackScholesPricer 结果应与
    GreeksCalculator.bs_price 完全一致。

    **Validates: Requirements 4.1**
    """

    @given(
        spot=valid_spot,
        strike=valid_strike,
        vol=valid_vol,
        t=valid_time,
        rate=valid_rate,
        opt_type=valid_option_type,
    )
    @settings(max_examples=200)
    def test_bs_pricer_delegates_to_greeks_calculator(
        self, spot, strike, vol, t, rate, opt_type
    ):
        """
        BlackScholesPricer.price().price 应与 GreeksCalculator.bs_price() 完全一致。

        **Validates: Requirements 4.1**
        """
        calculator = GreeksCalculator()
        pricer = BlackScholesPricer(calculator)

        pricing_input = PricingInput(
            spot_price=spot,
            strike_price=strike,
            time_to_expiry=t,
            risk_free_rate=rate,
            volatility=vol,
            option_type=opt_type,
            exercise_style=ExerciseStyle.EUROPEAN,
        )

        greeks_input = GreeksInput(
            spot_price=spot,
            strike_price=strike,
            time_to_expiry=t,
            risk_free_rate=rate,
            volatility=vol,
            option_type=opt_type,
        )

        result = pricer.price(pricing_input)
        expected_price = calculator.bs_price(greeks_input)

        assert result.success, f"BlackScholesPricer 应成功: {result.error_message}"
        assert result.price == expected_price, (
            f"价格不一致: pricer={result.price}, direct={expected_price}"
        )
        assert result.model_used == "black_scholes"
