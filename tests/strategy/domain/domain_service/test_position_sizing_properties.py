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


# Feature: dynamic-position-sizing, Property 2: 保证金使用率不变量
class TestProperty2UsageVolumeInvariant:
    """
    Property 2: 保证金使用率不变量

    *For any* 总权益（> 0）、已用保证金（>= 0）、单手保证金（> 0）和
    margin_usage_limit（0 < limit <= 1），_calc_usage_volume 返回的手数 n 应满足：
    (used_margin + n * margin_per_lot) / total_equity <= margin_usage_limit，
    且 (used_margin + (n+1) * margin_per_lot) / total_equity > margin_usage_limit
    （即 n 是满足约束的最大整数）。

    **Validates: Requirements 2.2**
    """

    @given(
        total_equity=st.floats(min_value=1000.0, max_value=10_000_000.0, allow_nan=False, allow_infinity=False),
        used_margin=st.floats(min_value=0.0, max_value=5_000_000.0, allow_nan=False, allow_infinity=False),
        margin_per_lot=st.floats(min_value=100.0, max_value=500_000.0, allow_nan=False, allow_infinity=False),
        margin_usage_limit=st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_usage_volume_invariant(self, total_equity, used_margin, margin_per_lot, margin_usage_limit):
        """Feature: dynamic-position-sizing, Property 2: 保证金使用率不变量
        **Validates: Requirements 2.2**
        """
        service = PositionSizingService(margin_usage_limit=margin_usage_limit)
        n = service._calc_usage_volume(total_equity, used_margin, margin_per_lot)

        # n should be non-negative
        assert n >= 0

        available = total_equity * margin_usage_limit - used_margin

        if available <= 0:
            # 已用保证金已超限，应返回 0
            assert n == 0, f"available={available} <= 0 但 n={n}"
        else:
            # If n > 0: adding n lots should not exceed limit
            if n > 0:
                ratio_with_n = (used_margin + n * margin_per_lot) / total_equity
                assert ratio_with_n <= margin_usage_limit + 1e-9, (
                    f"n={n} 手后使用率 {ratio_with_n} 超过限制 {margin_usage_limit}"
                )

            # Adding n+1 lots should exceed limit (n is the maximum)
            ratio_with_n_plus_1 = (used_margin + (n + 1) * margin_per_lot) / total_equity
            assert ratio_with_n_plus_1 > margin_usage_limit - 1e-9, (
                f"n+1={n+1} 手后使用率 {ratio_with_n_plus_1} 仍未超限 {margin_usage_limit}，"
                f"说明 n 不是最大值"
            )
