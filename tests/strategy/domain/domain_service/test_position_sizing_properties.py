"""
PositionSizingService 属性测试

Feature: dynamic-position-sizing
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.domain_service.risk.position_sizing_service import PositionSizingService
from src.strategy.domain.value_object.config.position_sizing_config import PositionSizingConfig


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
        service = PositionSizingService(config=PositionSizingConfig(margin_ratio=0.12, min_margin_ratio=0.07))
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
        service = PositionSizingService(config=PositionSizingConfig(margin_usage_limit=margin_usage_limit))
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


# ---------------------------------------------------------------------------
# 策略：Greeks 相关参数
# ---------------------------------------------------------------------------
from src.strategy.domain.value_object.greeks import GreeksResult
from src.strategy.domain.value_object.risk import PortfolioGreeks, RiskThresholds


# Feature: dynamic-position-sizing, Property 3: Greeks 预算计算正确性
class TestProperty3GreeksBudgetCalculation:
    """
    Property 3: Greeks 预算计算正确性

    *For any* 有效的组合 Greeks、风控阈值和单手 Greeks（至少一个维度非零），
    `_calc_greeks_volume` 返回的手数应等于各非零维度
    `floor((limit - |current|) / |greek × multiplier|)` 的最小值，
    且返回的 delta_budget、gamma_budget、vega_budget 应分别等于 `limit - |current|`。

    **Validates: Requirements 3.1, 3.2**
    """

    @given(
        delta=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        gamma=st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False),
        vega=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        multiplier=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        portfolio_delta=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
        portfolio_gamma=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        portfolio_vega=st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        delta_limit=st.floats(min_value=1.0, max_value=20.0, allow_nan=False, allow_infinity=False),
        gamma_limit=st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
        vega_limit=st.floats(min_value=50.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_greeks_budget_calculation(
        self, delta, gamma, vega, multiplier,
        portfolio_delta, portfolio_gamma, portfolio_vega,
        delta_limit, gamma_limit, vega_limit,
    ):
        """Feature: dynamic-position-sizing, Property 3: Greeks 预算计算正确性
        **Validates: Requirements 3.1, 3.2**
        """
        import math
        from hypothesis import assume

        # At least one greek must be non-zero
        assume(delta != 0 or gamma != 0 or vega != 0)

        # Filter out subnormal floats that cause overflow in floor(budget / per_lot)
        for g_val in [delta, gamma, vega]:
            per_lot = abs(g_val * multiplier)
            if per_lot != 0:
                assume(per_lot > 1e-15)

        greeks = GreeksResult(delta=delta, gamma=gamma, vega=vega)
        portfolio = PortfolioGreeks(
            total_delta=portfolio_delta,
            total_gamma=portfolio_gamma,
            total_vega=portfolio_vega,
        )
        thresholds = RiskThresholds(
            portfolio_delta_limit=delta_limit,
            portfolio_gamma_limit=gamma_limit,
            portfolio_vega_limit=vega_limit,
        )

        service = PositionSizingService()
        volume, d_budget, g_budget, v_budget = service._calc_greeks_volume(
            greeks, multiplier, portfolio, thresholds
        )

        # Verify budgets: limit - |current|
        assert d_budget == pytest.approx(delta_limit - abs(portfolio_delta), rel=1e-9)
        assert g_budget == pytest.approx(gamma_limit - abs(portfolio_gamma), rel=1e-9)
        assert v_budget == pytest.approx(vega_limit - abs(portfolio_vega), rel=1e-9)

        # Verify volume: min of floor(budget / per_lot) across non-zero dimensions
        expected_volumes = []
        dims = [
            (delta, d_budget),
            (gamma, g_budget),
            (vega, v_budget),
        ]
        for greek_val, budget in dims:
            per_lot = abs(greek_val * multiplier)
            if per_lot == 0:
                continue
            expected_volumes.append(math.floor(budget / per_lot))

        if expected_volumes:
            expected_volume = min(min(expected_volumes), 999999)
        else:
            expected_volume = 999999

        assert volume == expected_volume, (
            f"volume={volume}, expected={expected_volume}. "
            f"delta={delta}, gamma={gamma}, vega={vega}, multiplier={multiplier}, "
            f"budgets=({d_budget}, {g_budget}, {v_budget})"
        )


# Feature: dynamic-position-sizing, Property 4: 综合决策不变量
class TestProperty4ComputeSizingInvariant:
    """
    Property 4: 综合决策不变量

    *For any* 有效输入使得三个维度手数均 >= 1，`compute_sizing` 返回的
    `final_volume` 应等于 `min(margin_volume, usage_volume, greeks_volume)`
    clamped 到 `[1, max_volume_per_order]`，且 `passed` 为 True，
    且 SizingResult 中的 margin_volume、usage_volume、greeks_volume 字段
    与各维度独立计算结果一致。

    **Validates: Requirements 4.1, 4.2, 4.4**
    """

    @given(
        account_balance=st.floats(min_value=50_000.0, max_value=10_000_000.0, allow_nan=False, allow_infinity=False),
        total_equity=st.floats(min_value=100_000.0, max_value=10_000_000.0, allow_nan=False, allow_infinity=False),
        used_margin_ratio=st.floats(min_value=0.0, max_value=0.3, allow_nan=False, allow_infinity=False),
        contract_price=st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        underlying_price=st.floats(min_value=1000.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        strike_price=st.floats(min_value=1000.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        option_type=st.sampled_from(["call", "put"]),
        multiplier=st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        max_volume_per_order=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=200)
    def test_compute_sizing_invariant(
        self, account_balance, total_equity, used_margin_ratio, contract_price,
        underlying_price, strike_price, option_type, multiplier, max_volume_per_order,
    ):
        """Feature: dynamic-position-sizing, Property 4: 综合决策不变量
        **Validates: Requirements 4.1, 4.2, 4.4**
        """
        from hypothesis import assume

        used_margin = total_equity * used_margin_ratio

        # Use small greeks and generous limits to ensure all dimensions pass
        greeks = GreeksResult(delta=-0.3, gamma=0.05, vega=10.0)
        portfolio_greeks = PortfolioGreeks(total_delta=0.0, total_gamma=0.0, total_vega=0.0)
        risk_thresholds = RiskThresholds(
            portfolio_delta_limit=100.0, portfolio_gamma_limit=50.0, portfolio_vega_limit=5000.0
        )

        svc = PositionSizingService(
            config=PositionSizingConfig(
                margin_usage_limit=0.6,
                max_volume_per_order=max_volume_per_order,
            )
        )

        # Pre-check: estimate margin and verify all dimensions >= 1
        margin_per_lot = svc.estimate_margin(contract_price, underlying_price, strike_price, option_type, multiplier)
        assume(margin_per_lot > 0)

        margin_vol = svc._calc_margin_volume(account_balance, margin_per_lot)
        usage_vol = svc._calc_usage_volume(total_equity, used_margin, margin_per_lot)
        greeks_vol, _, _, _ = svc._calc_greeks_volume(greeks, multiplier, portfolio_greeks, risk_thresholds)

        assume(margin_vol >= 1)
        assume(usage_vol >= 1)
        assume(greeks_vol >= 1)

        result = svc.compute_sizing(
            account_balance=account_balance,
            total_equity=total_equity,
            used_margin=used_margin,
            contract_price=contract_price,
            underlying_price=underlying_price,
            strike_price=strike_price,
            option_type=option_type,
            multiplier=multiplier,
            greeks=greeks,
            portfolio_greeks=portfolio_greeks,
            risk_thresholds=risk_thresholds,
        )

        # Property assertions
        assert result.passed, f"Expected passed=True but got reject_reason={result.reject_reason}"

        # final_volume == min(three dimensions) clamped to [1, max_volume_per_order]
        expected_min = min(margin_vol, usage_vol, greeks_vol)
        expected_final = min(max(expected_min, 1), max_volume_per_order)
        assert result.final_volume == expected_final

        # Individual dimension volumes match independent calculations
        assert result.margin_volume == margin_vol
        assert result.usage_volume == usage_vol
        assert result.greeks_volume == greeks_vol
