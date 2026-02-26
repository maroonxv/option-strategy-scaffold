"""
GreeksCalculator 属性测试

使用 hypothesis 验证 Black-Scholes Greeks 计算的正确性属性。
"""
import math
import pytest
from hypothesis import given, strategies as st, settings, assume

from src.strategy.domain.domain_service.pricing import GreeksCalculator
from src.strategy.domain.value_object.greeks import GreeksInput


# ========== 生成器 ==========

valid_greeks_input = st.builds(
    GreeksInput,
    spot_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    strike_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    time_to_expiry=st.floats(min_value=0.001, max_value=5.0, allow_nan=False, allow_infinity=False),
    risk_free_rate=st.floats(min_value=0.0, max_value=0.2, allow_nan=False, allow_infinity=False),
    volatility=st.floats(min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False),
    option_type=st.sampled_from(["call", "put"]),
)


@pytest.fixture
def calc():
    return GreeksCalculator()


class TestGreeksCalculatorProperties:

    # Feature: greeks-risk-portfolio-execution, Property 1: Greeks 计算对所有有效输入产生有效结果
    # Validates: Requirements 1.1
    @settings(max_examples=200)
    @given(params=valid_greeks_input)
    def test_property1_greeks_valid_for_all_valid_inputs(self, params):
        """Property 1: 对所有有效输入，Greeks 计算成功且 delta 在合理范围内"""
        calc = GreeksCalculator()
        result = calc.calculate_greeks(params)

        assert result.success, f"计算失败: {result.error_message}"
        if params.option_type == "call":
            assert 0.0 <= result.delta <= 1.0, f"Call delta {result.delta} 不在 [0, 1]"
        else:
            assert -1.0 <= result.delta <= 0.0, f"Put delta {result.delta} 不在 [-1, 0]"
        assert result.gamma >= 0.0, f"Gamma {result.gamma} 不应为负"
        assert result.vega >= 0.0, f"Vega {result.vega} 不应为负"


    # Feature: greeks-risk-portfolio-execution, Property 2: Put-Call Parity 不变量
    # Validates: Requirements 1.4
    @settings(max_examples=200)
    @given(
        spot_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        strike_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        time_to_expiry=st.floats(min_value=0.001, max_value=5.0, allow_nan=False, allow_infinity=False),
        risk_free_rate=st.floats(min_value=0.0, max_value=0.2, allow_nan=False, allow_infinity=False),
        volatility=st.floats(min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False),
    )
    def test_property2_put_call_parity_delta(
        self, spot_price, strike_price, time_to_expiry, risk_free_rate, volatility
    ):
        """Property 2: Call_Delta - Put_Delta ≈ 1"""
        calc = GreeksCalculator()
        call_params = GreeksInput(spot_price, strike_price, time_to_expiry, risk_free_rate, volatility, "call")
        put_params = GreeksInput(spot_price, strike_price, time_to_expiry, risk_free_rate, volatility, "put")

        call_result = calc.calculate_greeks(call_params)
        put_result = calc.calculate_greeks(put_params)

        assert call_result.success and put_result.success
        assert abs((call_result.delta - put_result.delta) - 1.0) < 1e-6, (
            f"Put-Call Parity violated: call_delta={call_result.delta}, put_delta={put_result.delta}"
        )


    # Feature: greeks-risk-portfolio-execution, Property 3: 到期时 Greeks 边界值
    # Validates: Requirements 1.3
    @settings(max_examples=200)
    @given(
        spot_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        strike_price=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        option_type=st.sampled_from(["call", "put"]),
    )
    def test_property3_expiry_boundary_greeks(self, spot_price, strike_price, option_type):
        """Property 3: 到期时 delta 为 0 或 ±1，gamma/theta/vega 为 0"""
        # 排除 ATM (spot == strike) 因为边界不确定
        assume(abs(spot_price - strike_price) > 0.01)

        calc = GreeksCalculator()
        params = GreeksInput(spot_price, strike_price, 0.0, 0.02, 0.2, option_type)
        result = calc.calculate_greeks(params)

        assert result.success
        if option_type == "call":
            expected_delta = 1.0 if spot_price > strike_price else 0.0
        else:
            expected_delta = -1.0 if spot_price < strike_price else 0.0

        assert result.delta == expected_delta, f"Expected delta={expected_delta}, got {result.delta}"
        assert result.gamma == 0.0
        assert result.theta == 0.0
        assert result.vega == 0.0


    # Feature: greeks-risk-portfolio-execution, Property 4: 隐含波动率 Round-Trip
    # Validates: Requirements 2.1, 2.3
    @settings(max_examples=200)
    @given(
        spot_price=st.floats(min_value=50.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
        moneyness=st.floats(min_value=0.7, max_value=1.3, allow_nan=False, allow_infinity=False),
        time_to_expiry=st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
        risk_free_rate=st.floats(min_value=0.0, max_value=0.1, allow_nan=False, allow_infinity=False),
        volatility=st.floats(min_value=0.1, max_value=1.5, allow_nan=False, allow_infinity=False),
        option_type=st.sampled_from(["call", "put"]),
    )
    def test_property4_iv_round_trip(
        self, spot_price, moneyness, time_to_expiry, risk_free_rate, volatility, option_type
    ):
        """Property 4: BS价格 → IV求解 → 恢复原始波动率 (误差 < 0.01)"""
        strike_price = spot_price * moneyness
        calc = GreeksCalculator()
        params = GreeksInput(spot_price, strike_price, time_to_expiry, risk_free_rate, volatility, option_type)
        market_price = calc.bs_price(params)

        # 确保期权有足够的时间价值使 IV 可辨识
        assume(market_price > 0.5)
        # 确保 vega 足够大，使得 IV 可以被精确恢复
        greeks_check = calc.calculate_greeks(params)
        assume(greeks_check.success and greeks_check.vega > 0.01)

        iv_result = calc.calculate_implied_volatility(
            market_price=market_price,
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            option_type=option_type,
            tolerance=1e-6,
        )

        assert iv_result.success, f"IV 求解失败: {iv_result.error_message}"
        assert abs(iv_result.implied_volatility - volatility) < 0.01, (
            f"Round-trip 误差过大: 原始σ={volatility}, 恢复σ={iv_result.implied_volatility}"
        )
