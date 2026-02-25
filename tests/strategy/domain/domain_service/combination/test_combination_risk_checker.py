"""
CombinationRiskChecker 单元测试

测试组合级 Greeks 风控检查逻辑。
"""
import pytest

from src.strategy.domain.domain_service.combination.combination_risk_checker import (
    CombinationRiskChecker,
)
from src.strategy.domain.value_object.combination import (
    CombinationGreeks,
    CombinationRiskConfig,
)


class TestCombinationRiskChecker:
    """CombinationRiskChecker 单元测试"""

    def setup_method(self) -> None:
        self.config = CombinationRiskConfig(
            delta_limit=2.0, gamma_limit=0.5, vega_limit=200.0
        )
        self.checker = CombinationRiskChecker(self.config)

    def test_all_within_limits_passes(self) -> None:
        greeks = CombinationGreeks(delta=1.0, gamma=0.3, vega=100.0)
        result = self.checker.check(greeks)
        assert result.passed is True
        assert result.reject_reason == ""

    def test_zero_greeks_passes(self) -> None:
        greeks = CombinationGreeks(delta=0.0, gamma=0.0, vega=0.0)
        result = self.checker.check(greeks)
        assert result.passed is True

    def test_at_exact_limits_passes(self) -> None:
        greeks = CombinationGreeks(delta=2.0, gamma=0.5, vega=200.0)
        result = self.checker.check(greeks)
        assert result.passed is True

    def test_negative_at_exact_limits_passes(self) -> None:
        greeks = CombinationGreeks(delta=-2.0, gamma=-0.5, vega=-200.0)
        result = self.checker.check(greeks)
        assert result.passed is True

    def test_delta_exceeds_limit_fails(self) -> None:
        greeks = CombinationGreeks(delta=2.5, gamma=0.3, vega=100.0)
        result = self.checker.check(greeks)
        assert result.passed is False
        assert "delta" in result.reject_reason
        assert "2.5" in result.reject_reason

    def test_negative_delta_exceeds_limit_fails(self) -> None:
        greeks = CombinationGreeks(delta=-2.5, gamma=0.3, vega=100.0)
        result = self.checker.check(greeks)
        assert result.passed is False
        assert "delta" in result.reject_reason

    def test_gamma_exceeds_limit_fails(self) -> None:
        greeks = CombinationGreeks(delta=1.0, gamma=0.8, vega=100.0)
        result = self.checker.check(greeks)
        assert result.passed is False
        assert "gamma" in result.reject_reason
        assert "0.8" in result.reject_reason

    def test_vega_exceeds_limit_fails(self) -> None:
        greeks = CombinationGreeks(delta=1.0, gamma=0.3, vega=300.0)
        result = self.checker.check(greeks)
        assert result.passed is False
        assert "vega" in result.reject_reason
        assert "300" in result.reject_reason

    def test_multiple_greeks_exceed_limits(self) -> None:
        greeks = CombinationGreeks(delta=3.0, gamma=1.0, vega=500.0)
        result = self.checker.check(greeks)
        assert result.passed is False
        assert "delta" in result.reject_reason
        assert "gamma" in result.reject_reason
        assert "vega" in result.reject_reason

    def test_custom_config_limits(self) -> None:
        config = CombinationRiskConfig(
            delta_limit=10.0, gamma_limit=5.0, vega_limit=1000.0
        )
        checker = CombinationRiskChecker(config)
        greeks = CombinationGreeks(delta=8.0, gamma=4.0, vega=900.0)
        result = checker.check(greeks)
        assert result.passed is True

    def test_reject_reason_contains_limit_value(self) -> None:
        greeks = CombinationGreeks(delta=3.0, gamma=0.3, vega=100.0)
        result = self.checker.check(greeks)
        assert "limit=2.0" in result.reject_reason


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------
from hypothesis import given, settings
from hypothesis import strategies as st

# Hypothesis strategies for generating random Greeks and risk config values
_greek_value = st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
_limit_value = st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False)


def _greeks_and_config():
    """生成随机 CombinationGreeks 和 CombinationRiskConfig。"""
    return st.tuples(
        _greek_value,  # delta
        _greek_value,  # gamma
        _greek_value,  # vega
        _limit_value,  # delta_limit
        _limit_value,  # gamma_limit
        _limit_value,  # vega_limit
    )


# ---------------------------------------------------------------------------
# Feature: combination-strategy-management, Property 5: 风控检查正确性
# ---------------------------------------------------------------------------

class TestProperty5RiskCheckCorrectness:
    """
    Property 5: 风控检查正确性

    *For any* CombinationGreeks 和 CombinationRiskConfig，CombinationRiskChecker
    返回通过当且仅当 |delta| ≤ delta_limit 且 |gamma| ≤ gamma_limit 且 |vega| ≤ vega_limit。

    **Validates: Requirements 5.2, 5.3**
    """

    @given(data=_greeks_and_config())
    @settings(max_examples=100)
    def test_risk_check_passed_iff_all_within_limits(self, data):
        """Feature: combination-strategy-management, Property 5: 风控检查正确性
        对于任意 CombinationGreeks 和阈值，通过当且仅当所有 Greeks 绝对值在阈值内。
        **Validates: Requirements 5.2, 5.3**
        """
        delta, gamma, vega, delta_limit, gamma_limit, vega_limit = data

        greeks = CombinationGreeks(delta=delta, gamma=gamma, vega=vega)
        config = CombinationRiskConfig(
            delta_limit=delta_limit,
            gamma_limit=gamma_limit,
            vega_limit=vega_limit,
        )
        checker = CombinationRiskChecker(config)
        result = checker.check(greeks)

        expected_passed = (
            abs(delta) <= delta_limit
            and abs(gamma) <= gamma_limit
            and abs(vega) <= vega_limit
        )

        assert result.passed == expected_passed

    @given(data=_greeks_and_config())
    @settings(max_examples=100)
    def test_violation_details_match_exceeded_greeks(self, data):
        """Feature: combination-strategy-management, Property 5: 风控检查正确性
        当风控检查失败时，reject_reason 应包含所有超限的 Greek 名称。
        **Validates: Requirements 5.2, 5.3**
        """
        delta, gamma, vega, delta_limit, gamma_limit, vega_limit = data

        greeks = CombinationGreeks(delta=delta, gamma=gamma, vega=vega)
        config = CombinationRiskConfig(
            delta_limit=delta_limit,
            gamma_limit=gamma_limit,
            vega_limit=vega_limit,
        )
        checker = CombinationRiskChecker(config)
        result = checker.check(greeks)

        if not result.passed:
            if abs(delta) > delta_limit:
                assert "delta" in result.reject_reason
            if abs(gamma) > gamma_limit:
                assert "gamma" in result.reject_reason
            if abs(vega) > vega_limit:
                assert "vega" in result.reject_reason
        else:
            assert result.reject_reason == ""
