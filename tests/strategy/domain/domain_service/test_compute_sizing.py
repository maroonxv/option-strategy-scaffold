"""
compute_sizing 单元测试

覆盖所有拒绝场景和正常计算路径。
"""
import pytest
from src.strategy.domain.domain_service.risk.position_sizing_service import PositionSizingService
from src.strategy.domain.value_object.config.position_sizing_config import PositionSizingConfig
from src.strategy.domain.value_object.pricing.greeks import GreeksResult
from src.strategy.domain.value_object.risk.risk import PortfolioGreeks, RiskThresholds
from src.strategy.domain.value_object.risk.sizing import SizingResult


def _make_greeks(delta=-0.3, gamma=0.05, vega=0.15, theta=-0.02):
    return GreeksResult(delta=delta, gamma=gamma, vega=vega, theta=theta, success=True)


def _make_portfolio_greeks(total_delta=0.0, total_gamma=0.0, total_vega=0.0):
    return PortfolioGreeks(
        total_delta=total_delta, total_gamma=total_gamma,
        total_theta=0.0, total_vega=total_vega,
    )


def _make_thresholds(delta_limit=100.0, gamma_limit=50.0, vega_limit=200.0):
    return RiskThresholds(
        portfolio_delta_limit=delta_limit,
        portfolio_gamma_limit=gamma_limit,
        portfolio_vega_limit=vega_limit,
        position_delta_limit=10.0,
        position_gamma_limit=5.0,
        position_vega_limit=20.0,
    )


# 默认参数：充足资金、宽松阈值
DEFAULT_KWARGS = dict(
    account_balance=500_000.0,
    total_equity=1_000_000.0,
    used_margin=100_000.0,
    contract_price=200.0,
    underlying_price=4000.0,
    strike_price=3800.0,
    option_type="put",
    multiplier=10.0,
)


class TestComputeSizingRejections:
    """测试所有拒绝场景"""

    def test_reject_margin_le_zero(self):
        """保证金 <= 0 时拒绝"""
        svc = PositionSizingService()
        result = svc.compute_sizing(
            account_balance=100_000.0,
            total_equity=200_000.0,
            used_margin=0.0,
            contract_price=0.0,       # 权利金为 0
            underlying_price=0.0,     # 标的价格为 0 → 保证金为 0
            strike_price=0.0,
            option_type="put",
            multiplier=10.0,
            greeks=_make_greeks(),
            portfolio_greeks=_make_portfolio_greeks(),
            risk_thresholds=_make_thresholds(),
        )
        assert not result.passed
        assert result.reject_reason == "保证金估算异常"
        assert result.final_volume == 0

    def test_reject_insufficient_funds(self):
        """可用资金不足一手"""
        svc = PositionSizingService()
        result = svc.compute_sizing(
            account_balance=100.0,    # 极少资金
            total_equity=1_000_000.0,
            used_margin=0.0,
            contract_price=200.0,
            underlying_price=4000.0,
            strike_price=3800.0,
            option_type="put",
            multiplier=10.0,
            greeks=_make_greeks(),
            portfolio_greeks=_make_portfolio_greeks(),
            risk_thresholds=_make_thresholds(),
        )
        assert not result.passed
        assert result.reject_reason == "可用资金不足"

    def test_reject_usage_limit_exceeded(self):
        """保证金使用率已超限"""
        svc = PositionSizingService(config=PositionSizingConfig(margin_usage_limit=0.6))
        result = svc.compute_sizing(
            account_balance=500_000.0,
            total_equity=100_000.0,
            used_margin=90_000.0,     # 已用 90% > 60% 限制
            contract_price=200.0,
            underlying_price=4000.0,
            strike_price=3800.0,
            option_type="put",
            multiplier=10.0,
            greeks=_make_greeks(),
            portfolio_greeks=_make_portfolio_greeks(),
            risk_thresholds=_make_thresholds(),
        )
        assert not result.passed
        assert result.reject_reason == "保证金使用率超限"

    def test_reject_greeks_delta_exceeded(self):
        """Delta 超限"""
        svc = PositionSizingService()
        result = svc.compute_sizing(
            **DEFAULT_KWARGS,
            greeks=_make_greeks(delta=-0.5, gamma=0.001, vega=0.001),
            portfolio_greeks=_make_portfolio_greeks(total_delta=99.0),
            risk_thresholds=_make_thresholds(delta_limit=100.0),
        )
        assert not result.passed
        assert "Greeks 超限" in result.reject_reason
        assert "Delta" in result.reject_reason

    def test_reject_greeks_gamma_exceeded(self):
        """Gamma 超限"""
        svc = PositionSizingService()
        result = svc.compute_sizing(
            **DEFAULT_KWARGS,
            greeks=_make_greeks(delta=-0.001, gamma=0.5, vega=0.001),
            portfolio_greeks=_make_portfolio_greeks(total_gamma=49.0),
            risk_thresholds=_make_thresholds(gamma_limit=50.0),
        )
        assert not result.passed
        assert "Greeks 超限" in result.reject_reason
        assert "Gamma" in result.reject_reason

    def test_reject_greeks_vega_exceeded(self):
        """Vega 超限"""
        svc = PositionSizingService()
        result = svc.compute_sizing(
            **DEFAULT_KWARGS,
            greeks=_make_greeks(delta=-0.001, gamma=0.001, vega=5.0),
            portfolio_greeks=_make_portfolio_greeks(total_vega=199.0),
            risk_thresholds=_make_thresholds(vega_limit=200.0),
        )
        assert not result.passed
        assert "Greeks 超限" in result.reject_reason
        assert "Vega" in result.reject_reason

    def test_reject_greeks_multiple_exceeded(self):
        """多个 Greeks 维度同时超限"""
        svc = PositionSizingService()
        result = svc.compute_sizing(
            **DEFAULT_KWARGS,
            greeks=_make_greeks(delta=-0.5, gamma=0.5, vega=0.001),
            portfolio_greeks=_make_portfolio_greeks(total_delta=99.5, total_gamma=49.5),
            risk_thresholds=_make_thresholds(delta_limit=100.0, gamma_limit=50.0),
        )
        assert not result.passed
        assert "Greeks 超限" in result.reject_reason
        assert "Delta" in result.reject_reason
        assert "Gamma" in result.reject_reason


class TestComputeSizingHappyPath:
    """测试正常计算路径"""

    def test_basic_pass(self):
        """基本通过场景"""
        svc = PositionSizingService()
        result = svc.compute_sizing(
            **DEFAULT_KWARGS,
            greeks=_make_greeks(),
            portfolio_greeks=_make_portfolio_greeks(),
            risk_thresholds=_make_thresholds(),
        )
        assert result.passed
        assert result.final_volume >= 1
        assert result.final_volume <= svc._config.max_volume_per_order
        assert result.reject_reason == ""

    def test_final_volume_is_min_of_three(self):
        """最终手数是三维度最小值"""
        svc = PositionSizingService(config=PositionSizingConfig(max_volume_per_order=100))
        result = svc.compute_sizing(
            **DEFAULT_KWARGS,
            greeks=_make_greeks(),
            portfolio_greeks=_make_portfolio_greeks(),
            risk_thresholds=_make_thresholds(),
        )
        assert result.passed
        expected_min = min(result.margin_volume, result.usage_volume, result.greeks_volume)
        assert result.final_volume == min(expected_min, svc._config.max_volume_per_order)

    def test_clamp_to_max_volume(self):
        """手数被 clamp 到 max_volume_per_order"""
        svc = PositionSizingService(config=PositionSizingConfig(max_volume_per_order=2))
        result = svc.compute_sizing(
            **DEFAULT_KWARGS,
            greeks=_make_greeks(),
            portfolio_greeks=_make_portfolio_greeks(),
            risk_thresholds=_make_thresholds(),
        )
        assert result.passed
        assert result.final_volume <= 2

    def test_sizing_result_fields_populated(self):
        """SizingResult 所有字段都被正确填充"""
        svc = PositionSizingService()
        result = svc.compute_sizing(
            **DEFAULT_KWARGS,
            greeks=_make_greeks(),
            portfolio_greeks=_make_portfolio_greeks(),
            risk_thresholds=_make_thresholds(),
        )
        assert result.passed
        assert result.margin_volume >= 1
        assert result.usage_volume >= 1
        assert result.greeks_volume >= 1
        assert isinstance(result.delta_budget, float)
        assert isinstance(result.gamma_budget, float)
        assert isinstance(result.vega_budget, float)

    def test_call_option(self):
        """call 期权也能正常计算"""
        svc = PositionSizingService()
        result = svc.compute_sizing(
            account_balance=500_000.0,
            total_equity=1_000_000.0,
            used_margin=100_000.0,
            contract_price=150.0,
            underlying_price=4000.0,
            strike_price=4200.0,
            option_type="call",
            multiplier=10.0,
            greeks=_make_greeks(delta=0.3),
            portfolio_greeks=_make_portfolio_greeks(),
            risk_thresholds=_make_thresholds(),
        )
        assert result.passed
        assert result.final_volume >= 1
