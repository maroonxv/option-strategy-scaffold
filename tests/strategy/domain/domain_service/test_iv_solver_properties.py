"""
IVSolver 属性测试

Property 1: IV 求解 Round-Trip（跨算法）
Property 2: IVSolver 错误输入处理
Property 3: 批量求解不变量（长度、顺序、隔离性）

# Feature: pricing-service-enhancement, Property 1-3
"""
import math

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.domain_service.pricing import IVSolver, SolveMethod
from src.strategy.domain.value_object.pricing.greeks import IVQuote, IVResult


# ---------------------------------------------------------------------------
# 共用策略
# ---------------------------------------------------------------------------

_spot = st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False)
_strike = st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False)
_time = st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False)
_rate = st.floats(min_value=0.0, max_value=0.15, allow_nan=False, allow_infinity=False)
_vol = st.floats(min_value=0.05, max_value=3.0, allow_nan=False, allow_infinity=False)
_opt_type = st.sampled_from(["call", "put"])
_method = st.sampled_from([SolveMethod.NEWTON, SolveMethod.BISECTION, SolveMethod.BRENT])

_solver = IVSolver()


def _bs_price(S, K, T, r, sigma, opt):
    """使用 IVSolver 的静态方法计算 BS 理论价格"""
    return IVSolver._bs_price(S, K, T, r, sigma, opt)


# ===========================================================================
# Feature: pricing-service-enhancement, Property 1: IV 求解 Round-Trip（跨算法）
# ===========================================================================


class TestProperty1IVRoundTrip:
    """
    Property 1: IV 求解 Round-Trip（跨算法）

    *For any* 有效的期权参数组合，先用 BS 公式计算理论价格，
    再用 IVSolver 的任意算法反推隐含波动率，恢复的 IV 与原始
    volatility 的误差应小于容差阈值。

    **Validates: Requirements 1.1, 1.2, 1.4, 1.5**
    """

    @given(
        spot=_spot,
        strike=_strike,
        time=_time,
        rate=_rate,
        vol=_vol,
        opt=_opt_type,
        method=_method,
    )
    @settings(max_examples=200)
    def test_iv_round_trip_across_methods(
        self, spot, strike, time, rate, vol, opt, method,
    ):
        # 用已知 vol 计算理论价格
        market_price = _bs_price(spot, strike, time, rate, vol, opt)

        # 过滤掉价格过小的情况（数值精度不足）
        assume(market_price > 0.01)

        # 过滤掉深度 ITM/OTM 期权（moneyness 极端时 vega 很小，IV 不可靠恢复）
        moneyness = spot / strike
        assume(0.5 <= moneyness <= 2.0)

        # 计算 vega 以确定合理的 IV 误差上界
        # 求解器的 tolerance 是价格维度的，IV 误差 ≈ price_tolerance / vega
        # 对于低 vega 的深度 OTM 期权，需要更宽松的 IV 容差
        vega = IVSolver._bs_vega_raw(spot, strike, time, rate, vol)
        assume(vega > 1.0)  # 过滤掉 vega 极小的情况（IV 对价格不敏感）

        tolerance = 0.01
        result = _solver.solve(
            market_price=market_price,
            spot_price=spot,
            strike_price=strike,
            time_to_expiry=time,
            risk_free_rate=rate,
            option_type=opt,
            method=method,
            tolerance=tolerance,
        )

        assert result.success, (
            f"IVSolver({method.value}) 应成功求解: "
            f"S={spot}, K={strike}, T={time}, r={rate}, σ={vol}, "
            f"opt={opt}, price={market_price}, err={result.error_message}"
        )

        # round-trip 误差检查
        # 求解器保证 |BS(σ_recovered) - market_price| < tolerance
        # IV 误差上界 ≈ tolerance / vega，加上安全余量
        iv_error_bound = max(tolerance / vega * 2.0, 0.02)
        assert abs(result.implied_volatility - vol) < iv_error_bound, (
            f"Round-trip 误差过大: 原始σ={vol}, "
            f"恢复σ={result.implied_volatility}, "
            f"差={abs(result.implied_volatility - vol)}, "
            f"上界={iv_error_bound}, vega={vega}, "
            f"method={method.value}"
        )


# ===========================================================================
# Feature: pricing-service-enhancement, Property 2: IVSolver 错误输入处理
# ===========================================================================


class TestProperty2ErrorInputHandling:
    """
    Property 2: IVSolver 错误输入处理

    *For any* 非正市场价格（market_price ≤ 0）或市场价格低于期权内在价值的输入，
    IVSolver.solve 应返回 success=False 的 IVResult 且 error_message 非空。

    **Validates: Requirements 1.6, 1.7**
    """

    # --- Sub-strategy (a): market_price ≤ 0 ---

    @given(
        market_price=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
        spot=_spot,
        strike=_strike,
        time=_time,
        rate=_rate,
        opt=_opt_type,
    )
    @settings(max_examples=200)
    def test_non_positive_market_price_returns_failure(
        self, market_price, spot, strike, time, rate, opt,
    ):
        result = _solver.solve(
            market_price=market_price,
            spot_price=spot,
            strike_price=strike,
            time_to_expiry=time,
            risk_free_rate=rate,
            option_type=opt,
        )

        assert not result.success, (
            f"market_price={market_price} ≤ 0 应返回 success=False"
        )
        assert result.error_message, "error_message 不应为空"

    # --- Sub-strategy (b): market_price 低于内在价值 ---

    @given(
        spot=_spot,
        strike=_strike,
        time=_time,
        rate=_rate,
        opt=_opt_type,
        discount=st.floats(min_value=0.02, max_value=0.5, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_market_price_below_intrinsic_returns_failure(
        self, spot, strike, time, rate, opt, discount,
    ):
        # 计算内在价值
        if opt == "call":
            intrinsic = max(spot - strike * math.exp(-rate * time), 0.0)
        else:
            intrinsic = max(strike * math.exp(-rate * time) - spot, 0.0)

        # 只在内在价值足够大时测试（否则 market_price 会 ≤ 0，已被 sub-strategy a 覆盖）
        tolerance = 0.01
        assume(intrinsic > tolerance + 0.1)

        # 设置 market_price 明显低于内在价值
        market_price = intrinsic * (1.0 - discount)
        assume(market_price > 0)
        assume(market_price < intrinsic - tolerance)

        result = _solver.solve(
            market_price=market_price,
            spot_price=spot,
            strike_price=strike,
            time_to_expiry=time,
            risk_free_rate=rate,
            option_type=opt,
            tolerance=tolerance,
        )

        assert not result.success, (
            f"market_price={market_price} < intrinsic={intrinsic} 应返回 success=False"
        )
        assert result.error_message, "error_message 不应为空"


# ===========================================================================
# Feature: pricing-service-enhancement, Property 3: 批量求解不变量（长度、顺序、隔离性）
# ===========================================================================


def _valid_iv_quote_strategy():
    """生成有效的 IVQuote（从已知 vol 计算 BS 价格）"""
    return st.tuples(_spot, _strike, _time, _rate, _vol, _opt_type).map(
        lambda t: IVQuote(
            market_price=_bs_price(t[0], t[1], t[2], t[3], t[4], t[5]),
            spot_price=t[0],
            strike_price=t[1],
            time_to_expiry=t[2],
            risk_free_rate=t[3],
            option_type=t[5],
        )
    ).filter(lambda q: q.market_price > 0.01)


def _invalid_iv_quote_strategy():
    """生成无效的 IVQuote（market_price ≤ 0）"""
    return st.builds(
        IVQuote,
        market_price=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
        spot_price=_spot,
        strike_price=_strike,
        time_to_expiry=_time,
        risk_free_rate=_rate,
        option_type=_opt_type,
    )


def _mixed_quote_list_strategy():
    """
    生成混合有效/无效 IVQuote 列表，同时记录每个 quote 的预期有效性。
    返回 (quotes, expected_valid_flags) 元组。
    """
    tagged_valid = _valid_iv_quote_strategy().map(lambda q: (q, True))
    tagged_invalid = _invalid_iv_quote_strategy().map(lambda q: (q, False))
    tagged_quote = st.one_of(tagged_valid, tagged_invalid)

    return st.lists(tagged_quote, min_size=1, max_size=10).filter(
        # 确保至少有一个有效和一个无效
        lambda items: any(v for _, v in items) and any(not v for _, v in items)
    )


class TestProperty3BatchInvariants:
    """
    Property 3: 批量求解不变量（长度、顺序、隔离性）

    *For any* IVQuote 列表（包含有效和无效报价的混合），
    IVSolver.solve_batch 返回的 IVResult 列表长度等于输入列表长度，
    且有效报价对应的结果 success=True，无效报价对应的结果 success=False，
    互不影响。

    **Validates: Requirements 2.1, 2.2, 2.3**
    """

    @given(tagged_items=_mixed_quote_list_strategy())
    @settings(max_examples=200)
    def test_batch_length_order_isolation(self, tagged_items):
        quotes = [q for q, _ in tagged_items]
        expected_valid = [v for _, v in tagged_items]

        results = _solver.solve_batch(quotes)

        # 长度不变量
        assert len(results) == len(quotes), (
            f"结果长度 {len(results)} != 输入长度 {len(quotes)}"
        )

        # 顺序与隔离性不变量
        for i, (result, is_valid) in enumerate(zip(results, expected_valid)):
            if is_valid:
                assert result.success, (
                    f"有效报价 #{i} 应返回 success=True, "
                    f"quote={quotes[i]}, err={result.error_message}"
                )
            else:
                assert not result.success, (
                    f"无效报价 #{i} (market_price={quotes[i].market_price}) "
                    f"应返回 success=False"
                )


# ===========================================================================
# Feature: pricing-service-enhancement, Property 4: GreeksCalculator 向后兼容（行为等价）
# ===========================================================================


class TestProperty4GreeksCalculatorBackwardCompat:
    """
    Property 4: GreeksCalculator 向后兼容（行为等价）

    *For any* 有效的 IV 求解输入，GreeksCalculator.calculate_implied_volatility
    的返回结果应与直接调用 IVSolver.solve（使用默认牛顿法）的结果完全一致
    （implied_volatility 和 success 字段相同）。

    **Validates: Requirements 3.1, 3.2, 3.3**
    """

    @given(
        spot=_spot,
        strike=_strike,
        time=_time,
        rate=_rate,
        vol=_vol,
        opt=_opt_type,
    )
    @settings(max_examples=200)
    def test_greeks_calculator_delegates_to_iv_solver(
        self, spot, strike, time, rate, vol, opt,
    ):
        from src.strategy.domain.domain_service.pricing.iv.greeks_calculator import (
            GreeksCalculator,
        )

        # 用已知 vol 计算 BS 理论价格作为 market_price
        market_price = _bs_price(spot, strike, time, rate, vol, opt)
        assume(market_price > 0.01)

        greeks_calc = GreeksCalculator()

        # 通过 GreeksCalculator 接口求解
        gc_result = greeks_calc.calculate_implied_volatility(
            market_price=market_price,
            spot_price=spot,
            strike_price=strike,
            time_to_expiry=time,
            risk_free_rate=rate,
            option_type=opt,
        )

        # 直接通过 IVSolver 求解（默认牛顿法）
        iv_result = _solver.solve(
            market_price=market_price,
            spot_price=spot,
            strike_price=strike,
            time_to_expiry=time,
            risk_free_rate=rate,
            option_type=opt,
        )

        # 两者的 success 状态必须一致
        assert gc_result.success == iv_result.success, (
            f"success 不一致: GreeksCalculator={gc_result.success}, "
            f"IVSolver={iv_result.success}"
        )

        # 两者的 implied_volatility 必须完全一致
        assert gc_result.implied_volatility == iv_result.implied_volatility, (
            f"implied_volatility 不一致: "
            f"GreeksCalculator={gc_result.implied_volatility}, "
            f"IVSolver={iv_result.implied_volatility}"
        )
