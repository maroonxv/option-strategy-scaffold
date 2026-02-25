"""
VegaHedgingEngine 属性测试

Feature: vega-hedging-engine
Property 1: 对冲手数公式正确性
**Validates: Requirements 1.1, 1.3**
"""
import pytest
from hypothesis import given, strategies as st, settings, assume

from src.strategy.domain.domain_service.hedging.vega_hedging_engine import VegaHedgingEngine
from src.strategy.domain.value_object.hedging import VegaHedgingConfig, VegaHedgeResult
from src.strategy.domain.value_object.risk import PortfolioGreeks


# ========== 生成器 ==========

vega_hedging_config_st = st.builds(
    VegaHedgingConfig,
    target_vega=st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    hedging_band=st.floats(min_value=0.01, max_value=200.0, allow_nan=False, allow_infinity=False),
    hedge_instrument_vt_symbol=st.just("IO2506-C-4000.CFFEX"),
    hedge_instrument_vega=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False).map(
        lambda x: st.sampled_from([x, -x])
    ).flatmap(lambda x: x),  # 允许正负 Vega，但不为零
    hedge_instrument_delta=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    hedge_instrument_gamma=st.floats(min_value=-0.1, max_value=0.1, allow_nan=False, allow_infinity=False),
    hedge_instrument_theta=st.floats(min_value=-1.0, max_value=0.0, allow_nan=False, allow_infinity=False),
    hedge_instrument_multiplier=st.floats(min_value=1.0, max_value=300.0, allow_nan=False, allow_infinity=False),
)


def portfolio_greeks_exceeding_band_st(config: VegaHedgingConfig) -> st.SearchStrategy:
    """生成 total_vega 超过容忍带的 PortfolioGreeks"""
    # 偏差必须 > hedging_band，所以 total_vega 要么 > target + band，要么 < target - band
    offset = st.floats(
        min_value=config.hedging_band + 0.01,
        max_value=config.hedging_band + 1000.0,
        allow_nan=False,
        allow_infinity=False,
    )
    sign = st.sampled_from([1.0, -1.0])
    return st.tuples(offset, sign).map(
        lambda t: PortfolioGreeks(total_vega=config.target_vega + t[0] * t[1])
    )


# ========== Property 1: 对冲手数公式正确性 ==========


class TestVegaHedgingProperty1:
    """Property 1: 对冲手数公式正确性

    *For any* 有效的 VegaHedgingConfig（乘数 > 0、对冲工具 Vega ≠ 0）和任意 PortfolioGreeks，
    当 Vega 偏差超过容忍带时，返回的 hedge_volume 应等于
    abs(round((target_vega - total_vega) / (hedge_instrument_vega * hedge_instrument_multiplier)))，
    且 should_hedge 为 True（除非四舍五入后为零）。

    **Validates: Requirements 1.1, 1.3**
    """

    @settings(max_examples=100)
    @given(config=vega_hedging_config_st, data=st.data())
    def test_property1_hedge_volume_formula(self, config, data):
        """对冲手数 = abs(round((target_vega - total_vega) / (vega * multiplier)))

        **Validates: Requirements 1.1, 1.3**
        """
        greeks = data.draw(portfolio_greeks_exceeding_band_st(config))
        current_price = 100.0

        engine = VegaHedgingEngine(config)
        result, events = engine.check_and_hedge(greeks, current_price)

        # 计算期望值
        raw_volume = (config.target_vega - greeks.total_vega) / (
            config.hedge_instrument_vega * config.hedge_instrument_multiplier
        )
        expected_volume = round(raw_volume)

        if expected_volume == 0:
            # 需求 1.3: 四舍五入后为零 → should_hedge=False
            assert result.should_hedge is False
            assert len(events) == 0
        else:
            # 需求 1.1: 超过容忍带 → should_hedge=True，手数正确
            assert result.should_hedge is True
            assert result.hedge_volume == abs(expected_volume)
            assert len(events) == 1


# ========== 生成器: 容忍带内 ==========


def portfolio_greeks_within_band_st(config: VegaHedgingConfig) -> st.SearchStrategy:
    """生成 total_vega 在容忍带内的 PortfolioGreeks: abs(total_vega - target_vega) <= hedging_band

    使用 0.99 倍容忍带作为上界，避免浮点精度导致边界值溢出容忍带。
    """
    safe_band = config.hedging_band * 0.99
    return st.floats(
        min_value=-safe_band,
        max_value=safe_band,
        allow_nan=False,
        allow_infinity=False,
    ).map(lambda offset: PortfolioGreeks(total_vega=config.target_vega + offset))


# ========== Property 2: 容忍带内不对冲 ==========


class TestVegaHedgingProperty2:
    """Property 2: 容忍带内不对冲

    *For any* 有效的 VegaHedgingConfig 和任意 PortfolioGreeks，
    当 abs(total_vega - target_vega) <= hedging_band 时，
    返回的 should_hedge 应为 False，且事件列表为空。

    **Validates: Requirements 1.2**
    """

    @settings(max_examples=100)
    @given(config=vega_hedging_config_st, data=st.data())
    def test_property2_within_band_no_hedge(self, config, data):
        """容忍带内不触发对冲，should_hedge=False 且事件为空

        **Validates: Requirements 1.2**
        """
        greeks = data.draw(portfolio_greeks_within_band_st(config))
        current_price = 100.0

        engine = VegaHedgingEngine(config)
        result, events = engine.check_and_hedge(greeks, current_price)

        assert result.should_hedge is False
        assert len(events) == 0


# ========== Property 3: 方向与指令正确性 ==========


class TestVegaHedgingProperty3:
    """Property 3: 方向与指令正确性

    *For any* 触发对冲的输入，当 (target_vega - total_vega) 与
    (hedge_instrument_vega * multiplier) 同号时方向为 LONG，异号时方向为 SHORT；
    且 OrderInstruction 的 volume 为正整数、vt_symbol 与配置一致、signal 为 "vega_hedge"。

    **Validates: Requirements 2.1, 2.2, 2.3**
    """

    @settings(max_examples=100)
    @given(config=vega_hedging_config_st, data=st.data())
    def test_property3_direction_and_instruction(self, config, data):
        """方向由 raw_volume 符号决定，指令字段正确

        **Validates: Requirements 2.1, 2.2, 2.3**
        """
        from src.strategy.domain.value_object.order_instruction import Direction

        greeks = data.draw(portfolio_greeks_exceeding_band_st(config))
        current_price = 100.0

        raw_volume = (config.target_vega - greeks.total_vega) / (
            config.hedge_instrument_vega * config.hedge_instrument_multiplier
        )
        # 只关注对冲确实触发的情况（四舍五入后非零）
        assume(round(raw_volume) != 0)

        engine = VegaHedgingEngine(config)
        result, events = engine.check_and_hedge(greeks, current_price)

        assert result.should_hedge is True

        # 需求 2.2: raw_volume > 0 → LONG
        # 需求 2.3: raw_volume < 0 → SHORT（手数取绝对值）
        if raw_volume > 0:
            assert result.hedge_direction == Direction.LONG
        else:
            assert result.hedge_direction == Direction.SHORT

        # OrderInstruction 验证
        instr = result.instruction
        assert instr is not None
        assert instr.volume > 0                                          # volume 为正整数
        assert isinstance(instr.volume, int)
        assert instr.vt_symbol == config.hedge_instrument_vt_symbol      # 合约代码一致
        assert instr.signal == "vega_hedge"                              # signal 固定
