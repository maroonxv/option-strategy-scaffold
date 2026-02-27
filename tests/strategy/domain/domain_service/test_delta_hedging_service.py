"""

DeltaHedgingService 属性测试和单元测试


使用 hypothesis 验证 Delta 对冲逻辑。
"""

import pytest

from hypothesis import given, strategies as st, settings, assume


from src.strategy.domain.domain_service.hedging.delta_hedging_service import DeltaHedgingService

from src.strategy.domain.value_object.risk.hedging import HedgingConfig, HedgeResult

from src.strategy.domain.value_object.risk.risk import PortfolioGreeks

from src.strategy.domain.value_object.trading.order_instruction import Direction

from src.strategy.domain.event.event_types import HedgeExecutedEvent



# ========== 生成器 ==========


hedging_config_st = st.builds(

    HedgingConfig,

    target_delta=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),

    hedging_band=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),

    hedge_instrument_vt_symbol=st.just("IF2506.CFFEX"),

    hedge_instrument_delta=st.just(1.0),

    hedge_instrument_multiplier=st.floats(min_value=1.0, max_value=300.0, allow_nan=False, allow_infinity=False),

)


portfolio_greeks_st = st.builds(

    PortfolioGreeks,

    total_delta=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),

    total_gamma=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),

)



class TestDeltaHedgingProperty:

    """Property 7: Delta 对冲正确性"""


    # Feature: advanced-order-hedging-volsurface, Property 7: Delta 对冲正确性

    # Validates: Requirements 5.1, 5.2, 5.3, 5.4

    @settings(max_examples=200)

    @given(config=hedging_config_st, greeks=portfolio_greeks_st)

    def test_property7_delta_hedging_correctness(self, config, greeks):

        """Property 7: should_hedge iff |delta - target| > band; volume = round formula; volume==0 => no hedge"""

        engine = DeltaHedgingService(config)

        result, events = engine.check_and_hedge(greeks, 100.0)


        delta_diff = abs(greeks.total_delta - config.target_delta)

        denominator = config.hedge_instrument_delta * config.hedge_instrument_multiplier


        if delta_diff <= config.hedging_band:

            assert result.should_hedge is False

            assert len(events) == 0

        else:

            raw = (config.target_delta - greeks.total_delta) / denominator

            expected_vol = round(raw)

            if expected_vol == 0:

                assert result.should_hedge is False

                assert len(events) == 0

            else:

                assert result.should_hedge is True

                assert result.hedge_volume == abs(expected_vol)

                assert len(events) == 1

                assert isinstance(events[0], HedgeExecutedEvent)



# ========== 单元测试 ==========


class TestDeltaHedgingServiceUnit:

    """DeltaHedgingService 单元测试"""


    def test_hedge_known_delta(self):

        """已知 Delta 偏离的对冲手数: delta=3.0, target=0, band=0.5, multiplier=10 -> volume=round(-3/10)=0? No, round(-3/(1*10))=round(-0.3)=0"""

        # 更大偏离: delta=5.0, target=0, band=0.5, multiplier=1.0 -> volume=round(-5/1)=-5 -> 5 SHORT

        config = HedgingConfig(

            target_delta=0.0, hedging_band=0.5,

            hedge_instrument_vt_symbol="IF2506.CFFEX",

            hedge_instrument_delta=1.0, hedge_instrument_multiplier=1.0,

        )

        engine = DeltaHedgingService(config)

        greeks = PortfolioGreeks(total_delta=5.0)

        result, events = engine.check_and_hedge(greeks, 4000.0)

        assert result.should_hedge is True

        assert result.hedge_volume == 5

        assert result.hedge_direction == Direction.SHORT

        assert len(events) == 1


    def test_no_hedge_within_band(self):

        """Delta 偏离在容忍带内不对冲"""

        config = HedgingConfig(target_delta=0.0, hedging_band=1.0)

        engine = DeltaHedgingService(config)

        greeks = PortfolioGreeks(total_delta=0.5)

        result, events = engine.check_and_hedge(greeks, 4000.0)

        assert result.should_hedge is False

        assert len(events) == 0


    def test_invalid_multiplier(self):

        """无效配置: multiplier <= 0"""

        config = HedgingConfig(hedge_instrument_multiplier=0.0)

        engine = DeltaHedgingService(config)

        greeks = PortfolioGreeks(total_delta=5.0)

        result, events = engine.check_and_hedge(greeks, 4000.0)

        assert result.should_hedge is False

        assert "无效配置" in result.reason


    def test_invalid_delta_zero(self):

        """无效配置: hedge_instrument_delta == 0"""

        config = HedgingConfig(hedge_instrument_delta=0.0)

        engine = DeltaHedgingService(config)

        greeks = PortfolioGreeks(total_delta=5.0)

        result, events = engine.check_and_hedge(greeks, 4000.0)

        assert result.should_hedge is False

        assert "Delta 为零" in result.reason


    def test_from_yaml_config_defaults(self):

        """from_yaml_config 缺失字段使用默认值"""

        engine = DeltaHedgingService.from_yaml_config({})

        defaults = HedgingConfig()
        assert engine.config.target_delta == defaults.target_delta

        assert engine.config.hedging_band == defaults.hedging_band

        assert engine.config.hedge_instrument_multiplier == defaults.hedge_instrument_multiplier


    def test_from_yaml_config_override(self):

        """from_yaml_config 覆盖字段"""

        engine = DeltaHedgingService.from_yaml_config({

            "target_delta": 1.0,

            "hedging_band": 2.0,

        })

        assert engine.config.target_delta == 1.0

        assert engine.config.hedging_band == 2.0

