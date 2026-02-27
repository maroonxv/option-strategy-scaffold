"""

GammaScalpingService 属性测试和单元测试


使用 hypothesis 验证 Gamma Scalping 逻辑。
"""

import pytest

from hypothesis import given, strategies as st, settings, assume


from src.strategy.domain.domain_service.hedging.gamma_scalping_service import GammaScalpingService

from src.strategy.domain.value_object.risk.hedging import GammaScalpConfig, ScalpResult

from src.strategy.domain.value_object.risk.risk import PortfolioGreeks

from src.strategy.domain.value_object.trading.order_instruction import Direction

from src.strategy.domain.event.event_types import GammaScalpEvent



# ========== 生成器 ==========


gamma_config_st = st.builds(

    GammaScalpConfig,

    rebalance_threshold=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),

    hedge_instrument_vt_symbol=st.just("IF2506.CFFEX"),

    hedge_instrument_delta=st.just(1.0),

    hedge_instrument_multiplier=st.floats(min_value=1.0, max_value=300.0, allow_nan=False, allow_infinity=False),

)



class TestGammaScalpingProperty:

    """Property 8: Gamma Scalping 正确性"""


    # Feature: advanced-order-hedging-volsurface, Property 8: Gamma Scalping 正确性

    # Validates: Requirements 6.1, 6.3, 6.4

    @settings(max_examples=200)

    @given(
        config=gamma_config_st,

        total_delta=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),

        total_gamma=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),

    )

    def test_property8_gamma_scalping_correctness(self, config, total_delta, total_gamma):

        """Property 8: rebalance iff |delta| > threshold; volume targets delta=0; event produced"""

        greeks = PortfolioGreeks(total_delta=total_delta, total_gamma=total_gamma)

        engine = GammaScalpingService(config)

        result, events = engine.check_and_rebalance(greeks, 100.0)


        denominator = config.hedge_instrument_delta * config.hedge_instrument_multiplier


        if abs(total_delta) <= config.rebalance_threshold:

            assert result.should_rebalance is False

            assert len(events) == 0

        else:

            raw = -total_delta / denominator

            expected_vol = round(raw)

            if expected_vol == 0:

                assert result.should_rebalance is False

            else:

                assert result.should_rebalance is True

                assert result.rebalance_volume == abs(expected_vol)

                assert len(events) == 1

                assert isinstance(events[0], GammaScalpEvent)



class TestGammaScalpingNegativeGammaProperty:

    """Property 9: Gamma Scalping 负 Gamma 拒绝"""


    # Feature: advanced-order-hedging-volsurface, Property 9: Gamma Scalping 负 Gamma 拒绝

    # Validates: Requirements 6.2

    @settings(max_examples=200)

    @given(
        config=gamma_config_st,

        total_delta=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),

        total_gamma=st.floats(min_value=-1.0, max_value=0.0, allow_nan=False, allow_infinity=False),

    )

    def test_property9_negative_gamma_rejection(self, config, total_delta, total_gamma):

        """Property 9: gamma <= 0 => rejected=True, non-empty reject_reason"""

        greeks = PortfolioGreeks(total_delta=total_delta, total_gamma=total_gamma)

        engine = GammaScalpingService(config)

        result, events = engine.check_and_rebalance(greeks, 100.0)


        assert result.rejected is True

        assert result.reject_reason != ""

        assert result.should_rebalance is False

        assert len(events) == 0



# ========== 单元测试 ==========


class TestGammaScalpingServiceUnit:

    """GammaScalpingService 单元测试"""


    def test_negative_gamma_rejection(self):

        """负 Gamma 拒绝"""

        config = GammaScalpConfig(rebalance_threshold=0.3)

        engine = GammaScalpingService(config)

        greeks = PortfolioGreeks(total_delta=5.0, total_gamma=-0.1)

        result, events = engine.check_and_rebalance(greeks, 100.0)

        assert result.rejected is True

        assert "Gamma 非正" in result.reject_reason


    def test_rebalance_known_values(self):

        """具体再平衡数值: delta=3.0, multiplier=1.0 -> volume=3 SHORT"""

        config = GammaScalpConfig(

            rebalance_threshold=0.3,

            hedge_instrument_vt_symbol="IF2506.CFFEX",

            hedge_instrument_delta=1.0,

            hedge_instrument_multiplier=1.0,

        )

        engine = GammaScalpingService(config)

        greeks = PortfolioGreeks(total_delta=3.0, total_gamma=0.5)

        result, events = engine.check_and_rebalance(greeks, 4000.0)

        assert result.should_rebalance is True

        assert result.rebalance_volume == 3

        assert result.rebalance_direction == Direction.SHORT


    def test_from_yaml_config_defaults(self):

        """from_yaml_config 缺失字段使用默认值"""

        engine = GammaScalpingService.from_yaml_config({})

        defaults = GammaScalpConfig()

        assert engine.config.rebalance_threshold == defaults.rebalance_threshold

        assert engine.config.hedge_instrument_multiplier == defaults.hedge_instrument_multiplier


    def test_from_yaml_config_override(self):

        """from_yaml_config 覆盖字段"""

        engine = GammaScalpingService.from_yaml_config({"rebalance_threshold": 1.5})

        assert engine.config.rebalance_threshold == 1.5

