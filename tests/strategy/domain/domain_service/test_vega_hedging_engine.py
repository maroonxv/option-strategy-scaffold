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


# ========== Property 4: 附带 Greeks 影响计算正确性 ==========


class TestVegaHedgingProperty4:
    """Property 4: 附带 Greeks 影响计算正确性

    *For any* 触发对冲的输入，VegaHedgeResult 中的 delta_impact 应等于
    hedge_volume * hedge_instrument_delta * multiplier * direction_sign，
    gamma_impact 和 theta_impact 同理。

    **Validates: Requirements 3.1**
    """

    @settings(max_examples=100)
    @given(config=vega_hedging_config_st, data=st.data())
    def test_property4_greeks_impact_correctness(self, config, data):
        """附带 Greeks 影响 = hedge_volume * instrument_greek * multiplier * direction_sign

        **Validates: Requirements 3.1**
        """
        from src.strategy.domain.value_object.order_instruction import Direction

        greeks = data.draw(portfolio_greeks_exceeding_band_st(config))
        current_price = 100.0

        raw_volume = (config.target_vega - greeks.total_vega) / (
            config.hedge_instrument_vega * config.hedge_instrument_multiplier
        )
        # 只关注对冲确实触发的情况
        assume(round(raw_volume) != 0)

        engine = VegaHedgingEngine(config)
        result, events = engine.check_and_hedge(greeks, current_price)

        assert result.should_hedge is True

        # 确定 direction_sign
        direction_sign = 1 if result.hedge_direction == Direction.LONG else -1

        multiplier = config.hedge_instrument_multiplier
        vol = result.hedge_volume

        # 验证 delta_impact
        expected_delta = vol * config.hedge_instrument_delta * multiplier * direction_sign
        assert result.delta_impact == pytest.approx(expected_delta)

        # 验证 gamma_impact
        expected_gamma = vol * config.hedge_instrument_gamma * multiplier * direction_sign
        assert result.gamma_impact == pytest.approx(expected_gamma)

        # 验证 theta_impact
        expected_theta = vol * config.hedge_instrument_theta * multiplier * direction_sign
        assert result.theta_impact == pytest.approx(expected_theta)


# ========== Property 5: 事件数据一致性 ==========


class TestVegaHedgingProperty5:
    """Property 5: 事件数据一致性

    *For any* 触发对冲的输入，VegaHedgeExecutedEvent 中的 portfolio_vega_after 应等于
    portfolio_vega_before + hedge_volume * hedge_instrument_vega * multiplier * direction_sign，
    且事件中的 delta_impact、gamma_impact、theta_impact 与 VegaHedgeResult 中的值一致。

    **Validates: Requirements 3.2**
    """

    @settings(max_examples=100)
    @given(config=vega_hedging_config_st, data=st.data())
    def test_property5_event_data_consistency(self, config, data):
        """事件数据与计算结果一致

        **Validates: Requirements 3.2**
        """
        from src.strategy.domain.value_object.order_instruction import Direction

        greeks = data.draw(portfolio_greeks_exceeding_band_st(config))
        current_price = 100.0

        raw_volume = (config.target_vega - greeks.total_vega) / (
            config.hedge_instrument_vega * config.hedge_instrument_multiplier
        )
        # 只关注对冲确实触发的情况
        assume(round(raw_volume) != 0)

        engine = VegaHedgingEngine(config)
        result, events = engine.check_and_hedge(greeks, current_price)

        assert result.should_hedge is True
        assert len(events) == 1

        event = events[0]
        direction_sign = 1 if result.hedge_direction == Direction.LONG else -1

        # portfolio_vega_after == portfolio_vega_before + hedge_volume * vega * multiplier * direction_sign
        expected_vega_after = event.portfolio_vega_before + (
            result.hedge_volume
            * config.hedge_instrument_vega
            * config.hedge_instrument_multiplier
            * direction_sign
        )
        assert event.portfolio_vega_after == pytest.approx(expected_vega_after)

        # 事件中的 Greeks 影响与 result 一致
        assert event.delta_impact == pytest.approx(result.delta_impact)
        assert event.gamma_impact == pytest.approx(result.gamma_impact)
        assert event.theta_impact == pytest.approx(result.theta_impact)

        # portfolio_vega_before == portfolio_greeks.total_vega
        assert event.portfolio_vega_before == pytest.approx(greeks.total_vega)

        # hedge_instrument == config.hedge_instrument_vt_symbol
        assert event.hedge_instrument == config.hedge_instrument_vt_symbol


# ========== Property 6: 无效输入拒绝 ==========


class TestVegaHedgingProperty6:
    """Property 6: 无效输入拒绝

    *For any* 配置中 hedge_instrument_multiplier ≤ 0 或 hedge_instrument_vega = 0 的输入，
    或 current_price ≤ 0 的输入，返回的 rejected 应为 True、should_hedge 为 False，且事件列表为空。

    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    @settings(max_examples=100)
    @given(
        multiplier=st.floats(min_value=-100.0, max_value=0.0, allow_nan=False, allow_infinity=False),
        target_vega=st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        hedging_band=st.floats(min_value=0.01, max_value=200.0, allow_nan=False, allow_infinity=False),
        hedge_vega=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
        total_vega=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    )
    def test_multiplier_le_zero_rejected(self, multiplier, target_vega, hedging_band, hedge_vega, total_vega):
        """乘数 <= 0 时应拒绝: rejected=True, should_hedge=False, 事件为空

        **Validates: Requirements 4.1**
        """
        config = VegaHedgingConfig(
            target_vega=target_vega,
            hedging_band=hedging_band,
            hedge_instrument_vega=hedge_vega,
            hedge_instrument_multiplier=multiplier,
        )
        greeks = PortfolioGreeks(total_vega=total_vega)

        engine = VegaHedgingEngine(config)
        result, events = engine.check_and_hedge(greeks, current_price=100.0)

        assert result.rejected is True
        assert result.should_hedge is False
        assert len(events) == 0

    @settings(max_examples=100)
    @given(
        target_vega=st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        hedging_band=st.floats(min_value=0.01, max_value=200.0, allow_nan=False, allow_infinity=False),
        multiplier=st.floats(min_value=1.0, max_value=300.0, allow_nan=False, allow_infinity=False),
        total_vega=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    )
    def test_hedge_vega_zero_rejected(self, target_vega, hedging_band, multiplier, total_vega):
        """对冲工具 Vega = 0 时应拒绝: rejected=True, should_hedge=False, 事件为空

        **Validates: Requirements 4.2**
        """
        config = VegaHedgingConfig(
            target_vega=target_vega,
            hedging_band=hedging_band,
            hedge_instrument_vega=0.0,
            hedge_instrument_multiplier=multiplier,
        )
        greeks = PortfolioGreeks(total_vega=total_vega)

        engine = VegaHedgingEngine(config)
        result, events = engine.check_and_hedge(greeks, current_price=100.0)

        assert result.rejected is True
        assert result.should_hedge is False
        assert len(events) == 0

    @settings(max_examples=100)
    @given(
        config=vega_hedging_config_st,
        total_vega=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=-100.0, max_value=0.0, allow_nan=False, allow_infinity=False),
    )
    def test_current_price_le_zero_rejected(self, config, total_vega, current_price):
        """当前价格 <= 0 时应拒绝: rejected=True, should_hedge=False, 事件为空

        **Validates: Requirements 4.3**
        """
        greeks = PortfolioGreeks(total_vega=total_vega)

        engine = VegaHedgingEngine(config)
        result, events = engine.check_and_hedge(greeks, current_price)

        assert result.rejected is True
        assert result.should_hedge is False
        assert len(events) == 0


# ========== Property 7: YAML 配置加载一致性 ==========


# VegaHedgingConfig 所有字段名及其对应的 hypothesis 策略
_CONFIG_FIELDS = {
    "target_vega": st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    "hedging_band": st.floats(min_value=0.01, max_value=200.0, allow_nan=False, allow_infinity=False),
    "hedge_instrument_vt_symbol": st.text(min_size=0, max_size=30),
    "hedge_instrument_vega": st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    "hedge_instrument_delta": st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "hedge_instrument_gamma": st.floats(min_value=-0.1, max_value=0.1, allow_nan=False, allow_infinity=False),
    "hedge_instrument_theta": st.floats(min_value=-1.0, max_value=0.0, allow_nan=False, allow_infinity=False),
    "hedge_instrument_multiplier": st.floats(min_value=1.0, max_value=300.0, allow_nan=False, allow_infinity=False),
}

# 完整配置字典生成器
_full_config_dict_st = st.fixed_dictionaries(
    {field: strategy for field, strategy in _CONFIG_FIELDS.items()}
)

# 要删除的键子集生成器（可能为空 → 全部保留，也可能全部删除）
_keys_to_remove_st = st.lists(
    st.sampled_from(list(_CONFIG_FIELDS.keys())),
    unique=True,
    min_size=0,
    max_size=len(_CONFIG_FIELDS),
)


class TestVegaHedgingProperty7:
    """Property 7: YAML 配置加载一致性

    *For any* 配置字典（可能缺少部分字段），from_yaml_config 生成的 VegaHedgingConfig 中，
    已提供的字段应与字典值一致，缺失的字段应等于 VegaHedgingConfig 的默认值。

    **Validates: Requirements 5.1, 5.2**
    """

    @settings(max_examples=100)
    @given(full_dict=_full_config_dict_st, keys_to_remove=_keys_to_remove_st)
    def test_property7_yaml_config_load_consistency(self, full_dict, keys_to_remove):
        """from_yaml_config 已提供字段与字典一致，缺失字段等于默认值

        **Validates: Requirements 5.1, 5.2**
        """
        # 构造可能缺少部分字段的配置字典
        partial_dict = {k: v for k, v in full_dict.items() if k not in keys_to_remove}

        engine = VegaHedgingEngine.from_yaml_config(partial_dict)
        config = engine.config
        defaults = VegaHedgingConfig()

        for field in _CONFIG_FIELDS:
            actual = getattr(config, field)
            if field in partial_dict:
                # 需求 5.1: 已提供的字段应与字典值一致
                assert actual == partial_dict[field], (
                    f"字段 {field}: 期望 {partial_dict[field]}，实际 {actual}"
                )
            else:
                # 需求 5.2: 缺失的字段应等于默认值
                expected = getattr(defaults, field)
                assert actual == expected, (
                    f"字段 {field}: 期望默认值 {expected}，实际 {actual}"
                )


# ========== Property 8: 事件列表与对冲结果一致性 ==========

# 广泛配置生成器：包含有效和无效配置
_broad_config_st = st.builds(
    VegaHedgingConfig,
    target_vega=st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    hedging_band=st.floats(min_value=0.01, max_value=200.0, allow_nan=False, allow_infinity=False),
    hedge_instrument_vt_symbol=st.just("IO2506-C-4000.CFFEX"),
    hedge_instrument_vega=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),  # 包含 0
    hedge_instrument_delta=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    hedge_instrument_gamma=st.floats(min_value=-0.1, max_value=0.1, allow_nan=False, allow_infinity=False),
    hedge_instrument_theta=st.floats(min_value=-1.0, max_value=0.0, allow_nan=False, allow_infinity=False),
    hedge_instrument_multiplier=st.floats(min_value=-50.0, max_value=300.0, allow_nan=False, allow_infinity=False),  # 包含 <= 0
)


class TestVegaHedgingProperty8:
    """Property 8: 事件列表与对冲结果一致性

    *For any* 输入，事件列表非空当且仅当 should_hedge 为 True；
    事件列表为空当且仅当 should_hedge 为 False 或 rejected 为 True。

    **Validates: Requirements 6.1, 6.2**
    """

    @settings(max_examples=100)
    @given(
        config=_broad_config_st,
        total_vega=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        current_price=st.floats(min_value=-100.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    )
    def test_property8_events_consistent_with_hedge_result(self, config, total_vega, current_price):
        """事件列表非空 ↔ should_hedge=True；事件列表为空 ↔ should_hedge=False 或 rejected=True

        **Validates: Requirements 6.1, 6.2**
        """
        greeks = PortfolioGreeks(total_vega=total_vega)

        engine = VegaHedgingEngine(config)
        result, events = engine.check_and_hedge(greeks, current_price)

        if result.should_hedge:
            # 需求 6.1: 执行对冲时，事件列表非空
            assert len(events) > 0, (
                f"should_hedge=True 但事件列表为空"
            )
        else:
            # 需求 6.2: 不需要对冲或被拒绝时，事件列表为空
            assert len(events) == 0, (
                f"should_hedge=False (rejected={result.rejected}) 但事件列表非空: {len(events)} 个事件"
            )
