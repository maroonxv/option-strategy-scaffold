"""
PortfolioRiskAggregator 属性测试

使用 hypothesis 验证持仓级风控、组合级聚合和序列化的正确性。
"""
import json
import pytest
from hypothesis import given, strategies as st, settings

from src.strategy.domain.domain_service.portfolio_risk_aggregator import PortfolioRiskAggregator
from src.strategy.domain.value_object.greeks import GreeksResult
from src.strategy.domain.value_object.risk import (
    RiskThresholds,
    RiskCheckResult,
    PortfolioGreeks,
    PositionGreeksEntry,
)
from src.strategy.domain.event.event_types import GreeksRiskBreachEvent


# ========== 生成器 ==========

greeks_result_st = st.builds(
    GreeksResult,
    delta=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    gamma=st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False),
    theta=st.floats(min_value=-10.0, max_value=0.0, allow_nan=False, allow_infinity=False),
    vega=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    success=st.just(True),
    error_message=st.just(""),
)

thresholds_st = st.builds(
    RiskThresholds,
    position_delta_limit=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    position_gamma_limit=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
    position_vega_limit=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    portfolio_delta_limit=st.floats(min_value=0.5, max_value=50.0, allow_nan=False, allow_infinity=False),
    portfolio_gamma_limit=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    portfolio_vega_limit=st.floats(min_value=10.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
)

position_entry_st = st.builds(
    PositionGreeksEntry,
    vt_symbol=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    greeks=greeks_result_st,
    volume=st.integers(min_value=1, max_value=100),
    multiplier=st.floats(min_value=1.0, max_value=300.0, allow_nan=False, allow_infinity=False),
)


class TestPortfolioRiskAggregatorProperties:

    # Feature: greeks-risk-portfolio-execution, Property 5: 持仓级风控检查正确性
    # Validates: Requirements 3.1, 3.2, 3.3, 3.4
    @settings(max_examples=200)
    @given(greeks=greeks_result_st, thresholds=thresholds_st,
           volume=st.integers(min_value=1, max_value=100),
           multiplier=st.floats(min_value=1.0, max_value=300.0, allow_nan=False, allow_infinity=False))
    def test_property5_position_risk_check(self, greeks, thresholds, volume, multiplier):
        """Property 5: 风控通过当且仅当所有加权 Greeks 在阈值内"""
        agg = PortfolioRiskAggregator(thresholds)
        result = agg.check_position_risk(greeks, volume, multiplier)

        wd = abs(greeks.delta * volume * multiplier)
        wg = abs(greeks.gamma * volume * multiplier)
        wv = abs(greeks.vega * volume * multiplier)

        expected_pass = (
            wd <= thresholds.position_delta_limit
            and wg <= thresholds.position_gamma_limit
            and wv <= thresholds.position_vega_limit
        )
        assert result.passed == expected_pass, (
            f"Expected passed={expected_pass}, got {result.passed}. "
            f"wd={wd}, wg={wg}, wv={wv}, thresholds={thresholds}"
        )


    # Feature: greeks-risk-portfolio-execution, Property 6: 组合级 Greeks 聚合为正确的加权求和
    # Validates: Requirements 4.1, 4.2
    @settings(max_examples=200)
    @given(positions=st.lists(position_entry_st, min_size=0, max_size=20))
    def test_property6_portfolio_greeks_weighted_sum(self, positions):
        """Property 6: 组合 Greeks = Σ(entry.greeks.greek * volume * multiplier)"""
        thresholds = RiskThresholds(
            portfolio_delta_limit=1e12,
            portfolio_gamma_limit=1e12,
            portfolio_vega_limit=1e12,
        )
        agg = PortfolioRiskAggregator(thresholds)
        snapshot, _ = agg.aggregate_portfolio_greeks(positions)

        expected_delta = sum(e.greeks.delta * e.volume * e.multiplier for e in positions)
        expected_gamma = sum(e.greeks.gamma * e.volume * e.multiplier for e in positions)
        expected_theta = sum(e.greeks.theta * e.volume * e.multiplier for e in positions)
        expected_vega = sum(e.greeks.vega * e.volume * e.multiplier for e in positions)

        assert abs(snapshot.total_delta - expected_delta) < 1e-6
        assert abs(snapshot.total_gamma - expected_gamma) < 1e-6
        assert abs(snapshot.total_theta - expected_theta) < 1e-6
        assert abs(snapshot.total_vega - expected_vega) < 1e-6
        assert snapshot.position_count == len(positions)

    # Feature: greeks-risk-portfolio-execution, Property 7: 组合级阈值突破事件产生
    # Validates: Requirements 4.3, 4.4, 4.5
    @settings(max_examples=200)
    @given(positions=st.lists(position_entry_st, min_size=0, max_size=20), thresholds=thresholds_st)
    def test_property7_portfolio_breach_events(self, positions, thresholds):
        """Property 7: 突破事件当且仅当组合 Greeks 绝对值超过阈值"""
        agg = PortfolioRiskAggregator(thresholds)
        snapshot, events = agg.aggregate_portfolio_greeks(positions)

        breach_names = {e.greek_name for e in events if isinstance(e, GreeksRiskBreachEvent)}

        if abs(snapshot.total_delta) > thresholds.portfolio_delta_limit:
            assert "delta" in breach_names
        else:
            assert "delta" not in breach_names

        if abs(snapshot.total_gamma) > thresholds.portfolio_gamma_limit:
            assert "gamma" in breach_names
        else:
            assert "gamma" not in breach_names

        if abs(snapshot.total_vega) > thresholds.portfolio_vega_limit:
            assert "vega" in breach_names
        else:
            assert "vega" not in breach_names

    # Feature: greeks-risk-portfolio-execution, Property 12: PortfolioGreeks 序列化 Round-Trip
    # Validates: Requirements 9.2
    @settings(max_examples=200)
    @given(
        total_delta=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        total_gamma=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        total_theta=st.floats(min_value=-1000.0, max_value=0.0, allow_nan=False, allow_infinity=False),
        total_vega=st.floats(min_value=-5000.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
        position_count=st.integers(min_value=0, max_value=100),
    )
    def test_property12_portfolio_greeks_serialization_round_trip(
        self, total_delta, total_gamma, total_theta, total_vega, position_count
    ):
        """Property 12: PortfolioGreeks to_dict → from_dict 恢复等价对象"""
        original = PortfolioGreeks(
            total_delta=total_delta,
            total_gamma=total_gamma,
            total_theta=total_theta,
            total_vega=total_vega,
            position_count=position_count,
        )
        data = original.to_dict()
        # 确保可以 JSON 序列化
        json_str = json.dumps(data)
        restored_data = json.loads(json_str)
        restored = PortfolioGreeks.from_dict(restored_data)

        assert abs(restored.total_delta - original.total_delta) < 1e-10
        assert abs(restored.total_gamma - original.total_gamma) < 1e-10
        assert abs(restored.total_theta - original.total_theta) < 1e-10
        assert abs(restored.total_vega - original.total_vega) < 1e-10
        assert restored.position_count == original.position_count
        assert restored.timestamp == original.timestamp
