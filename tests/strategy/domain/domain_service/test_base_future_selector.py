"""
BaseFutureSelector.select_dominant_contract 单元测试

验证基于成交量/持仓量加权得分的主力合约选择逻辑。
Validates: Requirements 1.1, 1.2, 1.3, 1.4
"""

import sys
from enum import Enum
from unittest.mock import MagicMock

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

from src.strategy.domain.domain_service.selection.future_selection_service import (  # noqa: E402
    BaseFutureSelector,
)
from src.strategy.domain.value_object.config.future_selector_config import FutureSelectorConfig  # noqa: E402
from src.strategy.domain.value_object.selection.selection import MarketData, RolloverRecommendation  # noqa: E402


def _make_contract(symbol: str, exchange: _Exchange = _Exchange.SHFE) -> _ContractData:
    """创建测试用 ContractData。"""
    return _ContractData(
        symbol=symbol,
        exchange=exchange,
        name=symbol,
        product=_Product.FUTURES,
        size=10,
        pricetick=1.0,
        gateway_name="test",
    )


class TestSelectDominantContract:

    @pytest.fixture
    def selector(self):
        return BaseFutureSelector()

    def test_empty_list_returns_none(self, selector):
        """空列表返回 None (Req 1.4)"""
        assert selector.select_dominant_contract([], date.today()) is None

    def test_no_market_data_fallback_to_expiry(self, selector):
        """无行情数据时回退到按到期日排序 (Req 1.3)"""
        contracts = [_make_contract("rb2506"), _make_contract("rb2501")]
        selected = selector.select_dominant_contract(contracts, date.today())
        # rb2501 到期日 2025-01-15 < rb2506 到期日 2025-06-15
        assert selected.symbol == "rb2501"

    def test_none_market_data_fallback(self, selector):
        """market_data=None 时回退到按到期日排序"""
        contracts = [_make_contract("rb2506"), _make_contract("rb2503")]
        selected = selector.select_dominant_contract(
            contracts, date.today(), market_data=None
        )
        assert selected.symbol == "rb2503"

    def test_empty_market_data_fallback(self, selector):
        """market_data 为空字典时回退到按到期日排序"""
        contracts = [_make_contract("rb2506"), _make_contract("rb2503")]
        selected = selector.select_dominant_contract(
            contracts, date.today(), market_data={}
        )
        assert selected.symbol == "rb2503"

    def test_select_by_weighted_score(self, selector):
        """按加权得分选择得分最高的合约 (Req 1.1)"""
        c1 = _make_contract("rb2501")
        c2 = _make_contract("rb2506")
        market_data = {
            c1.vt_symbol: MarketData(vt_symbol=c1.vt_symbol, volume=100, open_interest=200.0),
            c2.vt_symbol: MarketData(vt_symbol=c2.vt_symbol, volume=500, open_interest=800.0),
        }
        selected = selector.select_dominant_contract(
            [c1, c2], date.today(), market_data=market_data
        )
        # c2 得分: 500*0.6 + 800*0.4 = 620, c1 得分: 100*0.6 + 200*0.4 = 140
        assert selected.symbol == "rb2506"

    def test_tie_break_by_expiry(self, selector):
        """得分相同时按到期日升序选择 (Req 1.2)"""
        c1 = _make_contract("rb2501")
        c2 = _make_contract("rb2506")
        market_data = {
            c1.vt_symbol: MarketData(vt_symbol=c1.vt_symbol, volume=100, open_interest=100.0),
            c2.vt_symbol: MarketData(vt_symbol=c2.vt_symbol, volume=100, open_interest=100.0),
        }
        selected = selector.select_dominant_contract(
            [c1, c2], date.today(), market_data=market_data
        )
        # 得分相同，rb2501 到期日更近
        assert selected.symbol == "rb2501"

    def test_all_zero_volume_oi_fallback(self, selector):
        """所有合约成交量和持仓量均为零时回退 (Req 1.3)"""
        c1 = _make_contract("rb2506")
        c2 = _make_contract("rb2501")
        market_data = {
            c1.vt_symbol: MarketData(vt_symbol=c1.vt_symbol, volume=0, open_interest=0.0),
            c2.vt_symbol: MarketData(vt_symbol=c2.vt_symbol, volume=0, open_interest=0.0),
        }
        selected = selector.select_dominant_contract(
            [c1, c2], date.today(), market_data=market_data
        )
        assert selected.symbol == "rb2501"

    def test_custom_weights(self, selector):
        """自定义权重参数"""
        c1 = _make_contract("rb2501")
        c2 = _make_contract("rb2506")
        market_data = {
            c1.vt_symbol: MarketData(vt_symbol=c1.vt_symbol, volume=1000, open_interest=10.0),
            c2.vt_symbol: MarketData(vt_symbol=c2.vt_symbol, volume=100, open_interest=500.0),
        }
        # volume_weight=0.1, oi_weight=0.9 -> c1: 1000*0.1+10*0.9=109, c2: 100*0.1+500*0.9=460
        custom_selector = BaseFutureSelector(
            config=FutureSelectorConfig(volume_weight=0.1, oi_weight=0.9)
        )
        selected = custom_selector.select_dominant_contract(
            [c1, c2], date.today(), market_data=market_data
        )
        assert selected.symbol == "rb2506"

    def test_missing_market_data_for_some_contracts(self, selector):
        """部分合约无行情数据时，缺失的得分为 0"""
        c1 = _make_contract("rb2501")
        c2 = _make_contract("rb2506")
        market_data = {
            c2.vt_symbol: MarketData(vt_symbol=c2.vt_symbol, volume=100, open_interest=200.0),
        }
        selected = selector.select_dominant_contract(
            [c1, c2], date.today(), market_data=market_data
        )
        # c1 无行情得分 0, c2 得分 100*0.6+200*0.4=140
        assert selected.symbol == "rb2506"

    def test_single_contract_with_market_data(self, selector):
        """单个合约直接返回"""
        c1 = _make_contract("rb2501")
        market_data = {
            c1.vt_symbol: MarketData(vt_symbol=c1.vt_symbol, volume=100, open_interest=200.0),
        }
        selected = selector.select_dominant_contract(
            [c1], date.today(), market_data=market_data
        )
        assert selected.symbol == "rb2501"

    def test_log_func_called_with_market_data(self, selector):
        """有行情数据时 log_func 记录选择结果"""
        logs = []
        c1 = _make_contract("rb2501")
        market_data = {
            c1.vt_symbol: MarketData(vt_symbol=c1.vt_symbol, volume=100, open_interest=200.0),
        }
        selector.select_dominant_contract(
            [c1], date.today(), market_data=market_data, log_func=logs.append
        )
        assert len(logs) == 1
        assert "选择主力合约" in logs[0]

    def test_log_func_called_on_fallback(self, selector):
        """无行情数据回退时 log_func 记录回退信息"""
        logs = []
        contracts = [_make_contract("rb2501")]
        selector.select_dominant_contract(
            contracts, date.today(), log_func=logs.append
        )
        assert len(logs) == 1
        assert "回退" in logs[0]


class TestFilterByMaturity:
    """filter_by_maturity 单元测试 - 基于到期日解析的合约过滤

    Validates: Requirements 2.1, 2.2, 2.3, 2.4
    """

    @pytest.fixture
    def selector(self):
        return BaseFutureSelector()

    def test_empty_list_returns_empty(self, selector):
        """空列表返回空列表"""
        result = selector.filter_by_maturity([], date(2025, 1, 15))
        assert result == []

    def test_current_month_filter(self, selector):
        """当月过滤：仅返回到期日在当月范围内的合约 (Req 2.1)"""
        # rb2501 -> 2025-01-15, rb2502 -> 2025-02-15, rb2503 -> 2025-03-15
        contracts = [
            _make_contract("rb2501"),
            _make_contract("rb2502"),
            _make_contract("rb2503"),
        ]
        result = selector.filter_by_maturity(
            contracts, date(2025, 1, 10), mode="current_month"
        )
        assert len(result) == 1
        assert result[0].symbol == "rb2501"

    def test_next_month_filter(self, selector):
        """次月过滤：仅返回到期日在下月范围内的合约 (Req 2.2)"""
        contracts = [
            _make_contract("rb2501"),
            _make_contract("rb2502"),
            _make_contract("rb2503"),
        ]
        result = selector.filter_by_maturity(
            contracts, date(2025, 1, 10), mode="next_month"
        )
        assert len(result) == 1
        assert result[0].symbol == "rb2502"

    def test_next_month_december_wraps_to_january(self, selector):
        """12月的次月应为次年1月"""
        contracts = [
            _make_contract("rb2512"),
            _make_contract("rb2601"),
        ]
        result = selector.filter_by_maturity(
            contracts, date(2025, 12, 1), mode="next_month"
        )
        assert len(result) == 1
        assert result[0].symbol == "rb2601"

    def test_custom_date_range(self, selector):
        """自定义日期范围过滤 (Req 2.3)"""
        contracts = [
            _make_contract("rb2501"),
            _make_contract("rb2503"),
            _make_contract("rb2506"),
        ]
        result = selector.filter_by_maturity(
            contracts,
            date(2025, 1, 1),
            mode="custom",
            date_range=(date(2025, 1, 1), date(2025, 3, 31)),
        )
        assert len(result) == 2
        symbols = [c.symbol for c in result]
        assert "rb2501" in symbols
        assert "rb2503" in symbols

    def test_custom_mode_without_date_range_returns_empty(self, selector):
        """custom 模式未提供 date_range 返回空列表"""
        contracts = [_make_contract("rb2501")]
        result = selector.filter_by_maturity(
            contracts, date(2025, 1, 1), mode="custom"
        )
        assert result == []

    def test_unparseable_symbol_excluded_with_warning(self, selector):
        """无法解析到期日的合约被排除并记录警告 (Req 2.4)"""
        contracts = [
            _make_contract("rb2501"),
            _make_contract("INVALID"),  # 无法解析
        ]
        logs = []
        result = selector.filter_by_maturity(
            contracts, date(2025, 1, 10), mode="current_month", log_func=logs.append
        )
        assert len(result) == 1
        assert result[0].symbol == "rb2501"
        assert len(logs) == 1
        assert "INVALID" in logs[0]
        assert "无法解析" in logs[0]

    def test_no_matching_contracts_returns_empty(self, selector):
        """无匹配合约时返回空列表"""
        contracts = [_make_contract("rb2506"), _make_contract("rb2509")]
        result = selector.filter_by_maturity(
            contracts, date(2025, 1, 10), mode="current_month"
        )
        assert result == []

    def test_multiple_contracts_in_same_month(self, selector):
        """同月多个合约都应被返回"""
        # 假设有两个不同品种但同月到期的合约
        contracts = [
            _make_contract("rb2501"),
            _make_contract("hc2501"),
        ]
        result = selector.filter_by_maturity(
            contracts, date(2025, 1, 10), mode="current_month"
        )
        assert len(result) == 2

    def test_unknown_mode_returns_empty(self, selector):
        """未知模式返回空列表"""
        contracts = [_make_contract("rb2501")]
        logs = []
        result = selector.filter_by_maturity(
            contracts, date(2025, 1, 10), mode="unknown", log_func=logs.append
        )
        assert result == []
        assert len(logs) == 1
        assert "未知" in logs[0]


class TestCheckRollover:
    """check_rollover 单元测试 - 期货移仓换月逻辑

    Validates: Requirements 3.1, 3.2, 3.3, 3.4
    """

    @pytest.fixture
    def selector(self):
        return BaseFutureSelector(config=FutureSelectorConfig(rollover_days=5))

    def test_remaining_days_above_threshold_returns_none(self, selector):
        """剩余天数大于阈值时不生成移仓建议 (Req 3.3)"""
        # rb2501 到期日 2025-01-15, current_date=2025-01-01 -> 剩余14天
        current = _make_contract("rb2501")
        result = selector.check_rollover(
            current, [], date(2025, 1, 1)
        )
        assert result is None

    def test_remaining_days_equal_threshold_triggers(self, selector):
        """剩余天数等于阈值时触发移仓建议 (Req 3.1)"""
        # rb2501 到期日 2025-01-15, current_date=2025-01-10 -> 剩余5天
        current = _make_contract("rb2501")
        target = _make_contract("rb2502")
        result = selector.check_rollover(
            current, [current, target], date(2025, 1, 10)
        )
        assert result is not None
        assert result.remaining_days == 5
        assert result.has_target is True
        assert result.target_contract_symbol == "rb2502"

    def test_remaining_days_below_threshold_triggers(self, selector):
        """剩余天数小于阈值时触发移仓建议 (Req 3.1)"""
        # rb2501 到期日 2025-01-15, current_date=2025-01-13 -> 剩余2天
        current = _make_contract("rb2501")
        target = _make_contract("rb2502")
        result = selector.check_rollover(
            current, [current, target], date(2025, 1, 13)
        )
        assert result is not None
        assert result.remaining_days == 2
        assert result.has_target is True

    def test_select_highest_volume_target(self, selector):
        """目标合约选择下月中成交量最大的合约 (Req 3.2)"""
        current = _make_contract("rb2501")
        target_a = _make_contract("rb2502")
        target_b = _make_contract("hc2502")  # 同月不同品种
        market_data = {
            target_a.vt_symbol: MarketData(
                vt_symbol=target_a.vt_symbol, volume=100, open_interest=50.0
            ),
            target_b.vt_symbol: MarketData(
                vt_symbol=target_b.vt_symbol, volume=500, open_interest=200.0
            ),
        }
        result = selector.check_rollover(
            current,
            [current, target_a, target_b],
            date(2025, 1, 13),
            market_data=market_data,
        )
        assert result is not None
        assert result.target_contract_symbol == "hc2502"

    def test_no_target_contract_returns_has_target_false(self, selector):
        """无目标合约时返回 has_target=False (Req 3.4)"""
        current = _make_contract("rb2501")
        # 只有当前合约，无下月合约
        result = selector.check_rollover(
            current, [current], date(2025, 1, 13)
        )
        assert result is not None
        assert result.has_target is False
        assert result.target_contract_symbol == ""
        assert result.current_contract_symbol == "rb2501"

    def test_unparseable_symbol_returns_none(self, selector):
        """无法解析到期日的合约返回 None"""
        current = _make_contract("INVALID")
        result = selector.check_rollover(current, [], date(2025, 1, 13))
        assert result is None

    def test_unparseable_symbol_logs_warning(self, selector):
        """无法解析到期日时记录日志"""
        logs = []
        current = _make_contract("INVALID")
        selector.check_rollover(
            current, [], date(2025, 1, 13), log_func=logs.append
        )
        assert len(logs) == 1
        assert "无法解析" in logs[0]

    def test_december_rollover_to_january(self, selector):
        """12月合约移仓到次年1月"""
        current = _make_contract("rb2512")
        target = _make_contract("rb2601")
        result = selector.check_rollover(
            current,
            [current, target],
            date(2025, 12, 13),
        )
        assert result is not None
        assert result.has_target is True
        assert result.target_contract_symbol == "rb2601"

    def test_current_contract_excluded_from_targets(self, selector):
        """当前合约不会被选为目标合约"""
        current = _make_contract("rb2501")
        # 只有当前合约自身在列表中，无其他下月合约
        result = selector.check_rollover(
            current, [current], date(2025, 1, 13)
        )
        assert result is not None
        assert result.has_target is False

    def test_no_market_data_selects_first_next_month(self, selector):
        """无行情数据时选择下月合约（按到期日）"""
        current = _make_contract("rb2501")
        target = _make_contract("rb2502")
        result = selector.check_rollover(
            current,
            [current, target],
            date(2025, 1, 13),
        )
        assert result is not None
        assert result.has_target is True
        assert result.target_contract_symbol == "rb2502"

    def test_log_func_called_on_trigger(self, selector):
        """触发移仓时 log_func 记录信息"""
        logs = []
        current = _make_contract("rb2501")
        target = _make_contract("rb2502")
        selector.check_rollover(
            current,
            [current, target],
            date(2025, 1, 13),
            log_func=logs.append,
        )
        assert len(logs) >= 1
        # 应包含触发信息和建议信息
        combined = " ".join(logs)
        assert "剩余" in combined
        assert "建议移仓" in combined

    def test_negative_remaining_days_triggers(self, selector):
        """到期日已过（剩余天数为负）也触发移仓"""
        current = _make_contract("rb2501")
        target = _make_contract("rb2502")
        # current_date 在到期日之后
        result = selector.check_rollover(
            current,
            [current, target],
            date(2025, 1, 20),
        )
        assert result is not None
        assert result.remaining_days < 0
        assert result.has_target is True

    def test_recommendation_fields_populated(self, selector):
        """验证返回的 RolloverRecommendation 字段完整"""
        current = _make_contract("rb2501")
        target = _make_contract("rb2502")
        result = selector.check_rollover(
            current,
            [current, target],
            date(2025, 1, 13),
        )
        assert isinstance(result, RolloverRecommendation)
        assert result.current_contract_symbol == "rb2501"
        assert result.target_contract_symbol == "rb2502"
        assert isinstance(result.remaining_days, int)
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0
