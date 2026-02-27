"""
选择服务集成测试

测试期货选择器和期权选择器的完整端到端流程：
1. 期货选择器流程：选择主力 → 检查移仓 → 过滤到期日
2. 期权选择器流程：评分 → 组合选择 → Delta 选择

Validates: Requirements 全部 (1-6)
"""

import sys
from enum import Enum
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing
# ---------------------------------------------------------------------------


class _Exchange(str, Enum):
    SHFE = "SHFE"
    CFFEX = "CFFEX"


class _Product(str, Enum):
    FUTURES = "期货"
    OPTION = "期权"


class _ContractData:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def vt_symbol(self) -> str:
        return f"{self.symbol}.{self.exchange.value}"


_const_mod = MagicMock()
_const_mod.Exchange = _Exchange
_const_mod.Product = _Product

_obj_mod = MagicMock()
_obj_mod.ContractData = _ContractData

for _name in [
    "vnpy",
    "vnpy.event",
    "vnpy.trader",
    "vnpy.trader.setting",
    "vnpy.trader.engine",
    "vnpy.trader.database",
    "vnpy_mysql",
]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

sys.modules["vnpy.trader.constant"] = _const_mod
sys.modules["vnpy.trader.object"] = _obj_mod

# ---------------------------------------------------------------------------
# Now safe to import
# ---------------------------------------------------------------------------

import pytest  # noqa: E402
from datetime import date  # noqa: E402

import pandas as pd  # noqa: E402

from src.strategy.domain.domain_service.selection.future_selection_service import (  # noqa: E402
    BaseFutureSelector,
)
from src.strategy.domain.domain_service.selection.option_selector_service import (  # noqa: E402
    OptionSelectorService,
)
from src.strategy.domain.value_object.option_selector_config import OptionSelectorConfig  # noqa: E402
from src.strategy.domain.value_object.selection import (  # noqa: E402
    MarketData,
    RolloverRecommendation,
    CombinationSelectionResult,
    SelectionScore,
)
from src.strategy.domain.value_object.combination import CombinationType  # noqa: E402
from src.strategy.domain.value_object.greeks import GreeksResult  # noqa: E402
from src.strategy.domain.value_object.combination_rules import (  # noqa: E402
    VALIDATION_RULES,
    LegStructure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(symbol: str, exchange: _Exchange = _Exchange.SHFE) -> _ContractData:
    """创建测试用期货 ContractData。"""
    return _ContractData(
        symbol=symbol,
        exchange=exchange,
        name=symbol,
        product=_Product.FUTURES,
        size=10,
        pricetick=1.0,
        gateway_name="test",
    )


def _build_option_chain(
    underlying_price: float,
    strikes: list[float],
    expiry: str = "2025-06-20",
) -> pd.DataFrame:
    """构建一条完整的期权链 (每个行权价都有 Call 和 Put)。"""
    rows = []
    for s in strikes:
        rows.append({
            "vt_symbol": f"IO2506-C-{int(s)}.CFFEX",
            "option_type": "call",
            "strike_price": s,
            "expiry_date": expiry,
            "bid_price": max(50.0, 200 - abs(s - underlying_price)),
            "bid_volume": 30,
            "ask_price": max(52.0, 202 - abs(s - underlying_price)),
            "ask_volume": 30,
            "days_to_expiry": 20,
            "underlying_symbol": "IO2506",
        })
        rows.append({
            "vt_symbol": f"IO2506-P-{int(s)}.CFFEX",
            "option_type": "put",
            "strike_price": s,
            "expiry_date": expiry,
            "bid_price": max(50.0, 200 - abs(s - underlying_price)),
            "bid_volume": 30,
            "ask_price": max(52.0, 202 - abs(s - underlying_price)),
            "ask_volume": 30,
            "days_to_expiry": 20,
            "underlying_symbol": "IO2506",
        })
    return pd.DataFrame(rows)


# ===========================================================================
# 期货选择器集成测试：选择主力 → 检查移仓 → 过滤到期日
# ===========================================================================


class TestFutureSelectorIntegration:
    """期货选择器完整流程集成测试

    流程：创建合约和行情 → select_dominant_contract → check_rollover → filter_by_maturity
    Validates: Requirements 1, 2, 3
    """

    @pytest.fixture
    def selector(self):
        return BaseFutureSelector()

    @pytest.fixture
    def contracts(self):
        """创建一组跨月期货合约"""
        return [
            _make_contract("rb2501"),  # 2025-01 到期
            _make_contract("rb2502"),  # 2025-02 到期
            _make_contract("rb2503"),  # 2025-03 到期
            _make_contract("rb2506"),  # 2025-06 到期
        ]

    @pytest.fixture
    def market_data(self, contracts):
        """为合约创建行情数据，rb2501 成交量最大"""
        return {
            contracts[0].vt_symbol: MarketData(
                vt_symbol=contracts[0].vt_symbol, volume=5000, open_interest=8000.0
            ),
            contracts[1].vt_symbol: MarketData(
                vt_symbol=contracts[1].vt_symbol, volume=3000, open_interest=5000.0
            ),
            contracts[2].vt_symbol: MarketData(
                vt_symbol=contracts[2].vt_symbol, volume=1000, open_interest=2000.0
            ),
            contracts[3].vt_symbol: MarketData(
                vt_symbol=contracts[3].vt_symbol, volume=200, open_interest=500.0
            ),
        }

    def test_full_pipeline_dominant_then_rollover_then_filter(
        self, selector, contracts, market_data
    ):
        """完整流程：选择主力合约 → 检查移仓 → 过滤到期日

        场景：当前日期 2025-01-12，rb2501 是主力但临近到期，
        应触发移仓建议到 rb2502，同时过滤出当月和次月合约。
        """
        current_date = date(2025, 1, 12)
        logs = []

        # Step 1: 选择主力合约 — rb2501 得分最高
        dominant = selector.select_dominant_contract(
            contracts, current_date, market_data=market_data, log_func=logs.append
        )
        assert dominant is not None
        assert dominant.symbol == "rb2501"
        # 验证得分: 5000*0.6 + 8000*0.4 = 6200
        assert len(logs) >= 1

        # Step 2: 检查移仓 — rb2501 到期日 2025-01-15，剩余 3 天 <= 阈值 5 天
        rollover = selector.check_rollover(
            dominant, contracts, current_date,
            market_data=market_data, log_func=logs.append
        )
        assert rollover is not None
        assert isinstance(rollover, RolloverRecommendation)
        assert rollover.current_contract_symbol == "rb2501"
        assert rollover.has_target is True
        # 目标应为 rb2502（下月中成交量最大的合约）
        assert rollover.target_contract_symbol == "rb2502"
        assert rollover.remaining_days <= 5

        # Step 3: 过滤当月合约 — 仅 rb2501 在 2025-01 范围内
        current_month = selector.filter_by_maturity(
            contracts, current_date, mode="current_month", log_func=logs.append
        )
        assert len(current_month) == 1
        assert current_month[0].symbol == "rb2501"

        # Step 4: 过滤次月合约 — 仅 rb2502 在 2025-02 范围内
        next_month = selector.filter_by_maturity(
            contracts, current_date, mode="next_month", log_func=logs.append
        )
        assert len(next_month) == 1
        assert next_month[0].symbol == "rb2502"

        # 验证整个流程有日志输出
        assert len(logs) >= 3

    def test_pipeline_no_rollover_needed(self, selector, contracts, market_data):
        """流程：主力合约远离到期日时不触发移仓

        场景：当前日期 2024-12-01，rb2501 到期日 2025-01-15，剩余 45 天。
        """
        current_date = date(2024, 12, 1)

        # Step 1: 选择主力
        dominant = selector.select_dominant_contract(
            contracts, current_date, market_data=market_data
        )
        assert dominant is not None
        assert dominant.symbol == "rb2501"

        # Step 2: 检查移仓 — 不应触发
        rollover = selector.check_rollover(
            dominant, contracts, current_date, market_data=market_data
        )
        assert rollover is None

        # Step 3: 过滤当月合约 — 2024-12 无合约到期
        current_month = selector.filter_by_maturity(
            contracts, current_date, mode="current_month"
        )
        assert len(current_month) == 0

    def test_pipeline_custom_date_range_filter(self, selector, contracts, market_data):
        """流程：主力选择后使用自定义日期范围过滤

        场景：选择主力后，过滤 2025-01 到 2025-03 范围内的合约。
        """
        current_date = date(2025, 1, 5)

        # Step 1: 选择主力
        dominant = selector.select_dominant_contract(
            contracts, current_date, market_data=market_data
        )
        assert dominant is not None

        # Step 2: 自定义范围过滤
        filtered = selector.filter_by_maturity(
            contracts, current_date, mode="custom",
            date_range=(date(2025, 1, 1), date(2025, 3, 31))
        )
        # rb2501, rb2502, rb2503 都在范围内
        assert len(filtered) == 3
        symbols = {c.symbol for c in filtered}
        assert symbols == {"rb2501", "rb2502", "rb2503"}

    def test_pipeline_rollover_no_target(self, selector):
        """流程：移仓时无目标合约

        场景：只有一个合约 rb2501，临近到期但无下月合约可切换。
        """
        current_date = date(2025, 1, 13)
        contracts = [_make_contract("rb2501")]
        market_data = {
            contracts[0].vt_symbol: MarketData(
                vt_symbol=contracts[0].vt_symbol, volume=5000, open_interest=8000.0
            ),
        }

        # Step 1: 选择主力
        dominant = selector.select_dominant_contract(
            contracts, current_date, market_data=market_data
        )
        assert dominant.symbol == "rb2501"

        # Step 2: 检查移仓 — 触发但无目标
        rollover = selector.check_rollover(
            dominant, contracts, current_date, market_data=market_data
        )
        assert rollover is not None
        assert rollover.has_target is False
        assert rollover.target_contract_symbol == ""

    def test_pipeline_fallback_no_market_data(self, selector, contracts):
        """流程：无行情数据时的完整回退路径

        场景：无行情数据，按到期日排序选择最近月合约。
        """
        current_date = date(2025, 1, 12)

        # Step 1: 无行情数据回退
        dominant = selector.select_dominant_contract(contracts, current_date)
        assert dominant is not None
        assert dominant.symbol == "rb2501"  # 到期日最近

        # Step 2: 检查移仓（无行情数据，目标按到期日选择）
        rollover = selector.check_rollover(
            dominant, contracts, current_date
        )
        assert rollover is not None
        assert rollover.has_target is True
        assert rollover.target_contract_symbol == "rb2502"



# ===========================================================================
# 期权选择器集成测试：评分 → 组合选择 → Delta 选择
# ===========================================================================


class TestOptionSelectorIntegration:
    """期权选择器完整流程集成测试

    流程：创建期权链 → score_candidates 评分排名 → select_combination 组合选择
          → select_by_delta Delta 感知选择
    Validates: Requirements 4, 5, 6
    """

    @pytest.fixture
    def selector(self):
        return OptionSelectorService(
            config=OptionSelectorConfig(
                strike_level=2,
                min_bid_price=10.0,
                min_bid_volume=5,
                min_trading_days=1,
                max_trading_days=50,
            )
        )

    @pytest.fixture
    def option_chain(self):
        """构建一条完整的期权链，标的价格 5000"""
        underlying_price = 5000.0
        strikes = [4700, 4800, 4900, 5000, 5100, 5200, 5300]
        return _build_option_chain(underlying_price, strikes)

    @pytest.fixture
    def greeks_data(self, option_chain):
        """为期权链构建 Greeks 数据"""
        greeks = {}
        # Call: Delta 从高到低 (ITM -> OTM)
        call_deltas = {4700: 0.90, 4800: 0.80, 4900: 0.65, 5000: 0.50,
                       5100: 0.35, 5200: 0.20, 5300: 0.10}
        # Put: Delta 从低到高 (OTM -> ITM)
        put_deltas = {4700: -0.10, 4800: -0.20, 4900: -0.35, 5000: -0.50,
                      5100: -0.65, 5200: -0.80, 5300: -0.90}

        for _, row in option_chain.iterrows():
            sym = row["vt_symbol"]
            strike = row["strike_price"]
            if row["option_type"] == "call":
                d = call_deltas.get(strike, 0.5)
            else:
                d = put_deltas.get(strike, -0.5)
            greeks[sym] = GreeksResult(delta=d, gamma=0.01, theta=-0.5, vega=0.2)

        return greeks

    def test_full_pipeline_score_then_combination_then_delta(
        self, selector, option_chain, greeks_data
    ):
        """完整流程：评分排名 → Straddle 组合选择 → Delta 选择

        场景：先对 Call 期权评分排名，再选择 Straddle 组合，
        最后用 Delta 选择最优 Call 期权。
        """
        underlying_price = 5000.0
        logs = []

        # Step 1: 评分排名 — 对 Call 期权进行多维度评分
        scores = selector.score_candidates(
            option_chain, "call", underlying_price, log_func=logs.append
        )
        assert len(scores) > 0
        assert all(isinstance(s, SelectionScore) for s in scores)
        # 验证按 total_score 降序排列
        for i in range(len(scores) - 1):
            assert scores[i].total_score >= scores[i + 1].total_score
        # 验证评分维度在 [0, 1] 范围内
        for s in scores:
            assert 0 <= s.liquidity_score <= 1
            assert 0 <= s.otm_score <= 1
            assert 0 <= s.expiry_score <= 1

        # Step 2: 组合选择 — 选择 Straddle
        straddle = selector.select_combination(
            option_chain, CombinationType.STRADDLE, underlying_price,
            log_func=logs.append
        )
        assert straddle is not None
        assert isinstance(straddle, CombinationSelectionResult)
        assert straddle.success is True
        assert straddle.combination_type == CombinationType.STRADDLE
        assert len(straddle.legs) == 2

        # 验证 Straddle 结构：同行权价、一 Call 一 Put
        call_leg = next(l for l in straddle.legs if l.option_type == "call")
        put_leg = next(l for l in straddle.legs if l.option_type == "put")
        assert call_leg.strike_price == put_leg.strike_price
        assert call_leg.strike_price == 5000.0  # ATM

        # 验证通过 VALIDATION_RULES
        leg_structs = [
            LegStructure(l.option_type, l.strike_price, l.expiry_date)
            for l in straddle.legs
        ]
        assert VALIDATION_RULES[CombinationType.STRADDLE](leg_structs) is None

        # Step 3: Delta 选择 — 选择 Delta 最接近 0.35 的 Call
        delta_result = selector.select_by_delta(
            option_chain, "call", underlying_price,
            target_delta=0.35, greeks_data=greeks_data,
            delta_tolerance=0.2, log_func=logs.append
        )
        assert delta_result is not None
        # Delta=0.35 对应 strike=5100
        assert delta_result.strike_price == 5100.0

        # 验证整个流程有日志输出
        assert len(logs) >= 3

    def test_pipeline_strangle_then_delta(self, selector, option_chain, greeks_data):
        """流程：Strangle 组合选择 → Delta 选择 Put

        场景：先选择 Strangle 组合，再用 Delta 选择虚值 Put。
        """
        underlying_price = 5000.0

        # Step 1: Strangle 组合选择
        strangle = selector.select_combination(
            option_chain, CombinationType.STRANGLE, underlying_price,
            strike_level=2
        )
        assert strangle is not None
        assert strangle.success is True
        assert len(strangle.legs) == 2

        call_leg = next(l for l in strangle.legs if l.option_type == "call")
        put_leg = next(l for l in strangle.legs if l.option_type == "put")
        # Strangle: Call 行权价 > 标的, Put 行权价 < 标的
        assert call_leg.strike_price > underlying_price
        assert put_leg.strike_price < underlying_price

        # 验证通过 VALIDATION_RULES
        leg_structs = [
            LegStructure(l.option_type, l.strike_price, l.expiry_date)
            for l in strangle.legs
        ]
        assert VALIDATION_RULES[CombinationType.STRANGLE](leg_structs) is None

        # Step 2: Delta 选择 Put — 目标 Delta=-0.20
        delta_result = selector.select_by_delta(
            option_chain, "put", underlying_price,
            target_delta=-0.20, greeks_data=greeks_data,
            delta_tolerance=0.15
        )
        assert delta_result is not None
        # Delta=-0.20 对应 strike=4800
        assert delta_result.strike_price == 4800.0

    def test_pipeline_score_then_vertical_spread(self, selector, option_chain):
        """流程：评分排名 → Vertical Spread 组合选择

        场景：先对 Call 评分，再选择 Call Vertical Spread。
        """
        underlying_price = 5000.0

        # Step 1: 评分排名
        scores = selector.score_candidates(
            option_chain, "call", underlying_price
        )
        assert len(scores) > 0
        # 最高分合约
        best = scores[0]
        assert best.total_score > 0

        # Step 2: Vertical Spread 选择
        spread = selector.select_combination(
            option_chain, CombinationType.VERTICAL_SPREAD, underlying_price,
            spread_width=1, option_type_for_spread="call"
        )
        assert spread is not None
        assert spread.success is True
        assert len(spread.legs) == 2
        # 同类型、不同行权价
        assert spread.legs[0].option_type == spread.legs[1].option_type == "call"
        assert spread.legs[0].strike_price != spread.legs[1].strike_price

        # 验证通过 VALIDATION_RULES
        leg_structs = [
            LegStructure(l.option_type, l.strike_price, l.expiry_date)
            for l in spread.legs
        ]
        assert VALIDATION_RULES[CombinationType.VERTICAL_SPREAD](leg_structs) is None

    def test_pipeline_delta_fallback_no_greeks(self, selector, option_chain):
        """流程：无 Greeks 数据时 Delta 选择回退到虚值档位选择

        场景：传入空 Greeks 数据，select_by_delta 应回退到 select_option。
        """
        underlying_price = 5000.0

        # Delta 选择 — 无 Greeks 数据
        result = selector.select_by_delta(
            option_chain, "call", underlying_price,
            target_delta=0.35, greeks_data={}
        )
        # 应回退到 select_option，仍然返回一个合约
        assert result is not None
        assert result.option_type == "call"

    def test_pipeline_score_put_then_straddle(self, selector, option_chain):
        """流程：对 Put 评分 → Straddle 组合选择

        场景：先对 Put 期权评分，再选择 Straddle 组合。
        """
        underlying_price = 5000.0

        # Step 1: 对 Put 评分
        scores = selector.score_candidates(
            option_chain, "put", underlying_price
        )
        assert len(scores) > 0
        # 验证所有评分的合约都是 Put
        for s in scores:
            assert s.option_contract.option_type == "put"

        # Step 2: Straddle 组合选择（需要 Call 和 Put）
        straddle = selector.select_combination(
            option_chain, CombinationType.STRADDLE, underlying_price
        )
        assert straddle.success is True
        types = {l.option_type for l in straddle.legs}
        assert types == {"call", "put"}

    def test_pipeline_all_three_steps_with_custom_weights(
        self, selector, option_chain, greeks_data
    ):
        """完整流程：自定义权重评分 → 组合选择 → Delta 选择

        场景：使用自定义评分权重，验证整个流程的一致性。
        """
        underlying_price = 5000.0

        # Step 1: 自定义权重评分
        scores = selector.score_candidates(
            option_chain, "call", underlying_price,
            liquidity_weight=0.5, otm_weight=0.2, expiry_weight=0.3
        )
        assert len(scores) > 0
        # 验证 total_score 计算正确
        for s in scores:
            expected = (
                s.liquidity_score * 0.5
                + s.otm_score * 0.2
                + s.expiry_score * 0.3
            )
            assert abs(s.total_score - expected) < 1e-9

        # Step 2: Straddle 组合选择
        straddle = selector.select_combination(
            option_chain, CombinationType.STRADDLE, underlying_price
        )
        assert straddle.success is True

        # Step 3: Delta 选择 — 目标 Delta=0.50 (ATM)
        delta_result = selector.select_by_delta(
            option_chain, "call", underlying_price,
            target_delta=0.50, greeks_data=greeks_data,
            delta_tolerance=0.1
        )
        assert delta_result is not None
        assert delta_result.strike_price == 5000.0  # ATM, delta=0.50
