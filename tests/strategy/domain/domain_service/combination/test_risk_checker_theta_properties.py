"""
Property 9: 风控检查 theta 集成正确性 — 属性测试

Feature: combination-service-optimization, Property 9: 风控检查 theta 集成正确性

*For any* CombinationGreeks 和 CombinationRiskConfig，RiskChecker 应在
|theta| > theta_limit 时将 theta 超限信息加入 reject_reason，且不影响现有
delta/gamma/vega 检查逻辑。当所有 Greeks 均未超限时返回 passed=True。

**Validates: Requirements 5.2, 5.3, 5.4, 5.5**
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.domain_service.combination.combination_risk_checker import (
    CombinationRiskChecker,
)
from src.strategy.domain.value_object.combination import (
    CombinationGreeks,
    CombinationRiskConfig,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------
_greek_value = st.floats(
    min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False
)
_limit_value = st.floats(
    min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False
)


def _greeks_and_config():
    """生成随机 CombinationGreeks 和 CombinationRiskConfig。"""
    return st.tuples(
        _greek_value,  # delta
        _greek_value,  # gamma
        _greek_value,  # vega
        _greek_value,  # theta
        _limit_value,  # delta_limit
        _limit_value,  # gamma_limit
        _limit_value,  # vega_limit
        _limit_value,  # theta_limit
    )


# ---------------------------------------------------------------------------
# Feature: combination-service-optimization, Property 9: 风控检查 theta 集成正确性
# ---------------------------------------------------------------------------


class TestProperty9ThetaIntegration:
    """
    Property 9: 风控检查 theta 集成正确性

    *For any* CombinationGreeks 和 CombinationRiskConfig，RiskChecker 应在
    |theta| > theta_limit 时将 theta 超限信息加入 reject_reason，且不影响现有
    delta/gamma/vega 检查逻辑。当所有 Greeks 均未超限时返回 passed=True。

    **Validates: Requirements 5.2, 5.3, 5.4, 5.5**
    """

    @given(data=_greeks_and_config())
    @settings(max_examples=100)
    def test_theta_violation_in_reject_reason(self, data):
        """Feature: combination-service-optimization, Property 9: 风控检查 theta 集成正确性
        当 |theta| > theta_limit 时，reject_reason 中应包含 theta 超限信息。
        **Validates: Requirements 5.2, 5.3**
        """
        delta, gamma, vega, theta, d_lim, g_lim, v_lim, t_lim = data
        greeks = CombinationGreeks(delta=delta, gamma=gamma, vega=vega, theta=theta)
        config = CombinationRiskConfig(
            delta_limit=d_lim, gamma_limit=g_lim, vega_limit=v_lim, theta_limit=t_lim
        )
        result = CombinationRiskChecker(config).check(greeks)

        if abs(theta) > t_lim:
            assert not result.passed
            assert "theta" in result.reject_reason

    @given(data=_greeks_and_config())
    @settings(max_examples=100)
    def test_theta_does_not_affect_delta_gamma_vega(self, data):
        """Feature: combination-service-optimization, Property 9: 风控检查 theta 集成正确性
        theta 检查不影响现有 delta/gamma/vega 检查逻辑：超限的 Greek 始终出现在
        reject_reason 中，无论 theta 是否超限。
        **Validates: Requirements 5.5**
        """
        delta, gamma, vega, theta, d_lim, g_lim, v_lim, t_lim = data
        greeks = CombinationGreeks(delta=delta, gamma=gamma, vega=vega, theta=theta)
        config = CombinationRiskConfig(
            delta_limit=d_lim, gamma_limit=g_lim, vega_limit=v_lim, theta_limit=t_lim
        )
        result = CombinationRiskChecker(config).check(greeks)

        # delta/gamma/vega 超限判定独立于 theta
        if abs(delta) > d_lim:
            assert "delta" in result.reject_reason
        if abs(gamma) > g_lim:
            assert "gamma" in result.reject_reason
        if abs(vega) > v_lim:
            assert "vega" in result.reject_reason

    @given(data=_greeks_and_config())
    @settings(max_examples=100)
    def test_all_within_limits_passed(self, data):
        """Feature: combination-service-optimization, Property 9: 风控检查 theta 集成正确性
        当所有 Greeks（含 theta）均未超限时返回 passed=True。
        **Validates: Requirements 5.4**
        """
        delta, gamma, vega, theta, d_lim, g_lim, v_lim, t_lim = data
        greeks = CombinationGreeks(delta=delta, gamma=gamma, vega=vega, theta=theta)
        config = CombinationRiskConfig(
            delta_limit=d_lim, gamma_limit=g_lim, vega_limit=v_lim, theta_limit=t_lim
        )
        result = CombinationRiskChecker(config).check(greeks)

        all_within = (
            abs(delta) <= d_lim
            and abs(gamma) <= g_lim
            and abs(vega) <= v_lim
            and abs(theta) <= t_lim
        )
        if all_within:
            assert result.passed
            assert result.reject_reason == ""

    @given(data=_greeks_and_config())
    @settings(max_examples=100)
    def test_theta_violation_format_matches_others(self, data):
        """Feature: combination-service-optimization, Property 9: 风控检查 theta 集成正确性
        theta 超限信息格式与 delta/gamma/vega 一致：'theta=<value>(limit=<limit>)'。
        **Validates: Requirements 5.3**
        """
        delta, gamma, vega, theta, d_lim, g_lim, v_lim, t_lim = data
        greeks = CombinationGreeks(delta=delta, gamma=gamma, vega=vega, theta=theta)
        config = CombinationRiskConfig(
            delta_limit=d_lim, gamma_limit=g_lim, vega_limit=v_lim, theta_limit=t_lim
        )
        result = CombinationRiskChecker(config).check(greeks)

        if abs(theta) > t_lim:
            expected_fragment = f"theta={theta:.4f}(limit={t_lim})"
            assert expected_fragment in result.reject_reason
