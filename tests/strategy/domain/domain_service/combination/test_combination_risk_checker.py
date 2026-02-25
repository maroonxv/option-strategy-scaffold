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
