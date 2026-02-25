"""
PositionSizingService 属性测试

Feature: dynamic-position-sizing
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.domain_service.risk.position_sizing_service import PositionSizingService


# ---------------------------------------------------------------------------
# 策略：有效的期权参数
# ---------------------------------------------------------------------------
_positive_price = st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False)
_positive_multiplier = st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
_option_type = st.sampled_from(["call", "put"])


# Feature: dynamic-position-sizing, Property 1: 保证金估算公式正确性
class TestProperty1MarginEstimateFormula:
    """
    Property 1: 保证金估算公式正确性

    *For any* 有效的权利金（> 0）、标的价格（> 0）、行权价（> 0）、合约乘数（> 0），
    estimate_margin 的返回值应等于
    权利金 × 合约乘数 + max(标的价格 × 合约乘数 × margin_ratio - 虚值额,
                            标的价格 × 合约乘数 × min_margin_ratio)
    其中虚值额对 put 为 max(行权价 - 标的价格, 0) × 合约乘数，
    对 call 为 max(标的价格 - 行权价, 0) × 合约乘数。

    **Validates: Requirements 1.1**
    """

    @given(
        contract_price=_positive_price,
        underlying_price=_positive_price,
        strike_price=_positive_price,
        option_type=_option_type,
        multiplier=_positive_multiplier,
    )
    @settings(max_examples=200)
    def test_margin_estimate_formula(
        self, contract_price, underlying_price, strike_price, option_type, multiplier
    ):
        """Feature: dynamic-position-sizing, Property 1: 保证金估算公式正确性
        **Validates: Requirements 1.1**
        """
        service = PositionSizingService(margin_ratio=0.12, min_margin_ratio=0.07)
        result = service.estimate_margin(
            contract_price, underlying_price, strike_price, option_type, multiplier
        )

        # 独立计算期望值
        if option_type == "put":
            out_of_money = max(strike_price - underlying_price, 0) * multiplier
        else:
            out_of_money = max(underlying_price - strike_price, 0) * multiplier

        premium = contract_price * multiplier
        expected = premium + max(
            underlying_price * multiplier * 0.12 - out_of_money,
            underlying_price * multiplier * 0.07,
        )

        assert result == pytest.approx(expected, rel=1e-9), (
            f"estimate_margin 返回 {result}，期望 {expected}。"
            f"参数: contract_price={contract_price}, underlying_price={underlying_price}, "
            f"strike_price={strike_price}, option_type={option_type}, multiplier={multiplier}"
        )
