"""
CRRPricer 属性测试

验证 CRR 二叉树定价器的属性：欧式定价收敛到 Black-Scholes。
"""
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.domain_service.pricing.crr_pricer import CRRPricer
from src.strategy.domain.domain_service.pricing.bs_pricer import BlackScholesPricer
from src.strategy.domain.domain_service.pricing.greeks_calculator import GreeksCalculator
from src.strategy.domain.value_object.pricing import (
    ExerciseStyle,
    PricingInput,
)


# Feature: option-pricing-engine, Property 3: CRR 欧式定价收敛到 BS
class TestCRRProperty3EuropeanConvergesToBS:
    """
    Property 3: CRR 欧式定价收敛到 BS

    For any 有效欧式参数，|CRR_price - BS_price| < max(BS_price * 0.02, 0.05)

    **Validates: Requirements 3.2**
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
    def test_crr_european_converges_to_bs(
        self, spot_price, strike_price, volatility, time_to_expiry, risk_free_rate, option_type
    ):
        """
        CRR 欧式定价结果应与 BS 价格在合理误差范围内一致。

        **Validates: Requirements 3.2**
        """
        crr_pricer = CRRPricer(steps=100)
        bs_pricer = BlackScholesPricer(GreeksCalculator())

        european_input = PricingInput(
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=volatility,
            option_type=option_type,
            exercise_style=ExerciseStyle.EUROPEAN,
        )

        crr_result = crr_pricer.price(european_input)
        bs_result = bs_pricer.price(european_input)

        # Skip cases where either pricer fails
        assume(crr_result.success)
        assume(bs_result.success)

        tolerance = max(bs_result.price * 0.02, 0.05)

        assert abs(crr_result.price - bs_result.price) < tolerance, (
            f"|CRR_price ({crr_result.price}) - BS_price ({bs_result.price})| = "
            f"{abs(crr_result.price - bs_result.price):.6f} >= tolerance ({tolerance:.6f}) "
            f"for {option_type} with S={spot_price}, K={strike_price}, "
            f"T={time_to_expiry}, r={risk_free_rate}, σ={volatility}"
        )
