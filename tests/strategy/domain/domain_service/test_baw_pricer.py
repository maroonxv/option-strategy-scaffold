"""
BAWPricer 单元测试

验证 BAWPricer 的输入校验、BAW 近似定价、T=0 边界处理和异常捕获。
"""
import math
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.domain_service.pricing.baw_pricer import BAWPricer
from src.strategy.domain.domain_service.pricing.bs_pricer import BlackScholesPricer
from src.strategy.domain.domain_service.pricing.greeks_calculator import GreeksCalculator
from src.strategy.domain.value_object.pricing import (
    ExerciseStyle,
    PricingInput,
    PricingResult,
)


@pytest.fixture
def pricer():
    return BAWPricer()


@pytest.fixture
def bs_pricer():
    return BlackScholesPricer(GreeksCalculator())


def _make_input(
    spot_price=100.0,
    strike_price=100.0,
    time_to_expiry=0.5,
    risk_free_rate=0.05,
    volatility=0.2,
    option_type="call",
    exercise_style=ExerciseStyle.AMERICAN,
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


class TestBAWPricerValidation:
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

    def test_error_result_has_model_used(self, pricer):
        result = pricer.price(_make_input(spot_price=-1))
        assert result.model_used == "baw"


class TestBAWPricerBoundary:
    """T=0 边界条件测试"""

    def test_call_itm_at_expiry(self, pricer):
        """到期时实值看涨期权返回内在价值"""
        result = pricer.price(_make_input(time_to_expiry=0, spot_price=110, strike_price=100))
        assert result.success
        assert result.price == pytest.approx(10.0)
        assert result.model_used == "baw"

    def test_call_otm_at_expiry(self, pricer):
        """到期时虚值看涨期权返回 0"""
        result = pricer.price(_make_input(time_to_expiry=0, spot_price=90, strike_price=100))
        assert result.success
        assert result.price == 0.0

    def test_put_itm_at_expiry(self, pricer):
        """到期时实值看跌期权返回内在价值"""
        result = pricer.price(
            _make_input(time_to_expiry=0, spot_price=80, strike_price=100, option_type="put")
        )
        assert result.success
        assert result.price == pytest.approx(20.0)

    def test_put_otm_at_expiry(self, pricer):
        """到期时虚值看跌期权返回 0"""
        result = pricer.price(
            _make_input(time_to_expiry=0, spot_price=120, strike_price=100, option_type="put")
        )
        assert result.success
        assert result.price == 0.0

    def test_atm_at_expiry(self, pricer):
        """到期时 ATM 期权价值为 0"""
        result = pricer.price(_make_input(time_to_expiry=0, spot_price=100, strike_price=100))
        assert result.success
        assert result.price == 0.0


class TestBAWPricerCallPricing:
    """美式看涨期权定价测试"""

    def test_call_price_positive(self, pricer):
        result = pricer.price(_make_input(option_type="call"))
        assert result.success
        assert result.price > 0
        assert result.model_used == "baw"

    def test_call_price_ge_bs(self, pricer, bs_pricer):
        """美式看涨价格 >= 欧式 BS 价格"""
        params = _make_input(option_type="call")
        baw_result = pricer.price(params)
        bs_params = _make_input(option_type="call", exercise_style=ExerciseStyle.EUROPEAN)
        bs_result = bs_pricer.price(bs_params)
        assert baw_result.success and bs_result.success
        assert baw_result.price >= bs_result.price - 1e-10

    def test_deep_itm_call(self, pricer):
        """深度实值看涨期权价格应接近内在价值"""
        result = pricer.price(_make_input(spot_price=200, strike_price=100))
        assert result.success
        assert result.price >= 100.0  # 至少为内在价值

    def test_deep_otm_call(self, pricer):
        """深度虚值看涨期权价格应接近 0"""
        result = pricer.price(_make_input(spot_price=50, strike_price=200))
        assert result.success
        assert result.price < 1.0


class TestBAWPricerPutPricing:
    """美式看跌期权定价测试"""

    def test_put_price_positive(self, pricer):
        result = pricer.price(_make_input(option_type="put"))
        assert result.success
        assert result.price > 0
        assert result.model_used == "baw"

    def test_put_price_ge_intrinsic(self, pricer):
        """美式看跌价格 >= 内在价值"""
        params = _make_input(spot_price=80, strike_price=100, option_type="put")
        result = pricer.price(params)
        intrinsic = max(100.0 - 80.0, 0.0)
        assert result.success
        assert result.price >= intrinsic - 1e-10

    def test_put_price_ge_bs(self, pricer, bs_pricer):
        """美式看跌价格 >= 欧式 BS 价格"""
        params = _make_input(option_type="put")
        baw_result = pricer.price(params)
        bs_params = _make_input(option_type="put", exercise_style=ExerciseStyle.EUROPEAN)
        bs_result = bs_pricer.price(bs_params)
        assert baw_result.success and bs_result.success
        assert baw_result.price >= bs_result.price - 1e-10

    def test_deep_itm_put(self, pricer):
        """深度实值看跌期权价格应接近内在价值"""
        result = pricer.price(_make_input(spot_price=20, strike_price=100, option_type="put"))
        assert result.success
        assert result.price >= 80.0

    def test_deep_otm_put(self, pricer):
        """深度虚值看跌期权价格应接近 0"""
        result = pricer.price(_make_input(spot_price=200, strike_price=100, option_type="put"))
        assert result.success
        assert result.price < 1.0


class TestBAWPricerExceptionHandling:
    """异常捕获测试"""

    def test_extreme_volatility(self, pricer):
        """极端波动率不应崩溃"""
        result = pricer.price(_make_input(volatility=10.0))
        assert result.success or (not result.success and result.error_message)

    def test_very_small_time(self, pricer):
        """极小到期时间不应崩溃"""
        result = pricer.price(_make_input(time_to_expiry=0.0001))
        assert result.success or (not result.success and result.error_message)


# Feature: option-pricing-engine, Property 1: 美式期权价格不低于欧式 BS 价格
class TestBAWProperty1AmericanGeEuropean:
    """
    Property 1: 美式期权价格不低于欧式 BS 价格

    For any 有效参数，BAW 美式价格 >= BlackScholesPricer 欧式价格

    **Validates: Requirements 2.2, 3.3**
    """

    @given(
        spot_price=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
        strike_price=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
        volatility=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
        time_to_expiry=st.floats(min_value=0.001, max_value=5.0, allow_nan=False, allow_infinity=False),
        risk_free_rate=st.floats(min_value=-0.5, max_value=1.0, allow_nan=False, allow_infinity=False),
        option_type=st.sampled_from(["call", "put"]),
    )
    @settings(max_examples=200)
    def test_american_price_ge_european_bs_price(
        self, spot_price, strike_price, volatility, time_to_expiry, risk_free_rate, option_type
    ):
        """BAW 美式期权价格应不低于对应欧式 BS 价格"""
        baw_pricer = BAWPricer()
        bs_pricer = BlackScholesPricer(GreeksCalculator())

        american_input = PricingInput(
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=volatility,
            option_type=option_type,
            exercise_style=ExerciseStyle.AMERICAN,
        )
        european_input = PricingInput(
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=volatility,
            option_type=option_type,
            exercise_style=ExerciseStyle.EUROPEAN,
        )

        baw_result = baw_pricer.price(american_input)
        bs_result = bs_pricer.price(european_input)

        # Skip cases where either pricer fails
        assume(baw_result.success)
        assume(bs_result.success)

        assert baw_result.price >= bs_result.price - 1e-10, (
            f"BAW price ({baw_result.price}) < BS price ({bs_result.price}) "
            f"for {option_type} with S={spot_price}, K={strike_price}, "
            f"T={time_to_expiry}, r={risk_free_rate}, σ={volatility}"
        )
