"""
PositionSizingService 行为一致性属性测试

Feature: domain-service-config-enhancement, Property 2: PositionSizingService 行为一致性

验证使用默认 PositionSizingConfig() 实例化的 PositionSizingService 调用 compute_sizing 方法，
产生的 SizingResult 与默认配置值一致——即配置对象正确捕获了所有默认值。

**Validates: Requirements 2.6, 5.1**
"""
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.domain_service.risk.position_sizing_service import PositionSizingService
from src.strategy.domain.value_object.config.position_sizing_config import PositionSizingConfig
from src.strategy.domain.value_object.pricing.greeks import GreeksResult
from src.strategy.domain.value_object.risk.risk import PortfolioGreeks, RiskThresholds


# ---------------------------------------------------------------------------
# 策略：有效的仓位计算输入
# ---------------------------------------------------------------------------
_account_balance = st.floats(min_value=10_000.0, max_value=10_000_000.0, allow_nan=False, allow_infinity=False)
_total_equity = st.floats(min_value=50_000.0, max_value=10_000_000.0, allow_nan=False, allow_infinity=False)
_used_margin_ratio = st.floats(min_value=0.0, max_value=0.3, allow_nan=False, allow_infinity=False)
_contract_price = st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False)
_underlying_price = st.floats(min_value=500.0, max_value=10_000.0, allow_nan=False, allow_infinity=False)
_strike_price = st.floats(min_value=500.0, max_value=10_000.0, allow_nan=False, allow_infinity=False)
_option_type = st.sampled_from(["call", "put"])
_multiplier = st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Greeks 策略：合理范围内的 Greeks 值
_delta = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_gamma = st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False)
_vega = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)

# 组合 Greeks 策略
_portfolio_delta = st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False)
_portfolio_gamma = st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False)
_portfolio_vega = st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False)

# 风控阈值策略
_delta_limit = st.floats(min_value=1.0, max_value=20.0, allow_nan=False, allow_infinity=False)
_gamma_limit = st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False)
_vega_limit = st.floats(min_value=50.0, max_value=2000.0, allow_nan=False, allow_infinity=False)


# Feature: domain-service-config-enhancement, Property 2: PositionSizingService 行为一致性
class TestProperty2SizingBehaviorConsistency:
    """
    Property 2: PositionSizingService 行为一致性

    *对于任意* 有效的仓位计算输入（account_balance > 0, total_equity > 0,
    contract_price > 0 等），使用默认配置实例化的 PositionSizingService 调用
    compute_sizing 方法，应该产生与重构前使用默认参数实例化的服务相同的 SizingResult。

    由于服务已完成重构，本测试通过以下方式验证行为一致性：
    - 使用 PositionSizingConfig() 默认实例（显式传入）创建的服务
    - 与不传入配置（使用 None，内部回退到默认配置）创建的服务
    两者对相同输入应产生完全相同的 SizingResult。

    同时验证默认配置的字段值与重构前的硬编码默认值完全一致。

    **Validates: Requirements 2.6, 5.1**
    """

    @given(
        account_balance=_account_balance,
        total_equity=_total_equity,
        used_margin_ratio=_used_margin_ratio,
        contract_price=_contract_price,
        underlying_price=_underlying_price,
        strike_price=_strike_price,
        option_type=_option_type,
        multiplier=_multiplier,
        delta=_delta,
        gamma=_gamma,
        vega=_vega,
        portfolio_delta=_portfolio_delta,
        portfolio_gamma=_portfolio_gamma,
        portfolio_vega=_portfolio_vega,
        delta_limit=_delta_limit,
        gamma_limit=_gamma_limit,
        vega_limit=_vega_limit,
    )
    @settings(max_examples=200)
    def test_sizing_behavior_consistency(
        self,
        account_balance, total_equity, used_margin_ratio,
        contract_price, underlying_price, strike_price, option_type, multiplier,
        delta, gamma, vega,
        portfolio_delta, portfolio_gamma, portfolio_vega,
        delta_limit, gamma_limit, vega_limit,
    ):
        """Feature: domain-service-config-enhancement, Property 2: PositionSizingService 行为一致性
        **Validates: Requirements 2.6, 5.1**
        """
        used_margin = total_equity * used_margin_ratio

        # 过滤掉极小的次正规浮点数，避免 budget / per_lot 溢出
        for g_val in [delta, gamma, vega]:
            per_lot = abs(g_val * multiplier)
            if per_lot != 0:
                assume(per_lot > 1e-15)

        greeks = GreeksResult(delta=delta, gamma=gamma, vega=vega)
        portfolio_greeks = PortfolioGreeks(
            total_delta=portfolio_delta,
            total_gamma=portfolio_gamma,
            total_vega=portfolio_vega,
        )
        risk_thresholds = RiskThresholds(
            portfolio_delta_limit=delta_limit,
            portfolio_gamma_limit=gamma_limit,
            portfolio_vega_limit=vega_limit,
        )

        # 服务 A：显式传入默认配置对象
        svc_explicit = PositionSizingService(config=PositionSizingConfig())
        # 服务 B：不传入配置（内部回退到默认配置）
        svc_implicit = PositionSizingService()

        kwargs = dict(
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

        result_explicit = svc_explicit.compute_sizing(**kwargs)
        result_implicit = svc_implicit.compute_sizing(**kwargs)

        # 两个服务的计算结果应完全一致
        assert result_explicit.final_volume == result_implicit.final_volume, (
            f"final_volume 不一致: explicit={result_explicit.final_volume}, "
            f"implicit={result_implicit.final_volume}"
        )
        assert result_explicit.margin_volume == result_implicit.margin_volume
        assert result_explicit.usage_volume == result_implicit.usage_volume
        assert result_explicit.greeks_volume == result_implicit.greeks_volume
        assert result_explicit.delta_budget == result_implicit.delta_budget
        assert result_explicit.gamma_budget == result_implicit.gamma_budget
        assert result_explicit.vega_budget == result_implicit.vega_budget
        assert result_explicit.passed == result_implicit.passed
        assert result_explicit.reject_reason == result_implicit.reject_reason

    def test_default_config_matches_pre_refactor_defaults(self):
        """验证 PositionSizingConfig 默认值与重构前硬编码默认值完全一致。

        **Validates: Requirements 2.6, 5.1**
        """
        config = PositionSizingConfig()

        # 重构前的硬编码默认值
        assert config.max_positions == 5
        assert config.global_daily_limit == 50
        assert config.contract_daily_limit == 2
        assert config.margin_ratio == 0.12
        assert config.min_margin_ratio == 0.07
        assert config.margin_usage_limit == 0.6
        assert config.max_volume_per_order == 10
