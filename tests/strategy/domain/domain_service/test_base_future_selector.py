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
from src.strategy.domain.value_object.selection import MarketData  # noqa: E402


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
        selected = selector.select_dominant_contract(
            [c1, c2], date.today(), market_data=market_data,
            volume_weight=0.1, oi_weight=0.9
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
    """保留原有 filter_by_maturity 测试"""

    @pytest.fixture
    def selector(self):
        return BaseFutureSelector()

    def test_filter_current_month(self, selector):
        contracts = [_make_contract("rb2505"), _make_contract("rb2501")]
        filtered = selector.filter_by_maturity(contracts, date.today(), mode="current_month")
        assert len(filtered) == 1
        assert filtered[0].symbol == "rb2501"

    def test_filter_next_month(self, selector):
        contracts = [_make_contract("rb2505"), _make_contract("rb2501")]
        filtered = selector.filter_by_maturity(contracts, date.today(), mode="next_month")
        assert len(filtered) == 1
        assert filtered[0].symbol == "rb2505"

    def test_filter_next_month_empty(self, selector):
        contracts = [_make_contract("rb2501")]
        filtered = selector.filter_by_maturity(contracts, date.today(), mode="next_month")
        assert len(filtered) == 0
