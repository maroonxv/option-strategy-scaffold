"""
OptionDiscoveryService 单元测试

验证期权合约发现服务的数据库查询、前缀匹配和错误处理。
Validates: Requirements 6.1, 6.2, 6.3, 6.4
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
    DCE = "DCE"
    CZCE = "CZCE"
    INE = "INE"


class _Interval(str, Enum):
    MINUTE = "1m"
    HOUR = "1h"
    DAILY = "d"


class _BarOverview:
    """模拟数据库 Bar 概览记录。"""

    def __init__(self, symbol: str, exchange: _Exchange, interval: _Interval):
        self.symbol = symbol
        self.exchange = exchange
        self.interval = interval


_const_mod = MagicMock()
_const_mod.Interval = _Interval
_const_mod.Exchange = _Exchange

_db_mod = MagicMock()

for _name in [
    "vnpy",
    "vnpy.event",
    "vnpy.trader",
    "vnpy.trader.setting",
    "vnpy.trader.engine",
    "vnpy.trader.object",
    "vnpy_mysql",
]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

sys.modules["vnpy.trader.constant"] = _const_mod
sys.modules["vnpy.trader.database"] = _db_mod

# ---------------------------------------------------------------------------
# Now safe to import
# ---------------------------------------------------------------------------

from src.backtesting.discovery.option_discovery import OptionDiscoveryService  # noqa: E402


def _make_overview(symbol: str, exchange: _Exchange, interval: _Interval = _Interval.MINUTE) -> _BarOverview:
    return _BarOverview(symbol=symbol, exchange=exchange, interval=interval)


class TestDiscoverEmpty:
    """空输入和空结果场景。"""

    def test_empty_input_returns_empty(self):
        """空 vt_symbol 列表返回空列表。"""
        assert OptionDiscoveryService.discover([]) == []

    def test_invalid_vt_symbol_skipped(self):
        """无法解析的 vt_symbol（无 '.'）被跳过。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.return_value = []
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(["INVALID_NO_DOT"])
        assert result == []


class TestDiscoverDatabaseFailure:
    """数据库失败场景。Validates: Requirement 6.4"""

    def test_database_exception_returns_empty(self):
        """数据库查询异常时返回空列表。"""
        _db_mod.get_database.side_effect = Exception("DB connection failed")

        result = OptionDiscoveryService.discover(["IF2501.CFFEX"])
        assert result == []

        # 清理
        _db_mod.get_database.side_effect = None

    def test_get_bar_overview_exception_returns_empty(self):
        """get_bar_overview 抛异常时返回空列表。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.side_effect = Exception("Query failed")
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(["IF2501.CFFEX"])
        assert result == []

        # 清理
        mock_db.get_bar_overview.side_effect = None


class TestDiscoverPrefixMatching:
    """前缀匹配逻辑。Validates: Requirements 6.1, 6.2"""

    def test_future_option_map_matching(self):
        """IF→IO 映射：匹配 IO 前缀的期权合约。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.return_value = [
            _make_overview("IO2501-C-4000", _Exchange.CFFEX, _Interval.MINUTE),
            _make_overview("IO2501-P-3800", _Exchange.CFFEX, _Interval.MINUTE),
        ]
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(["IF2501.CFFEX"])
        assert len(result) == 2
        assert "IO2501-C-4000.CFFEX" in result
        assert "IO2501-P-3800.CFFEX" in result

    def test_im_to_mo_mapping(self):
        """IM→MO 映射：匹配 MO 前缀的期权合约。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.return_value = [
            _make_overview("MO2601-C-6300", _Exchange.CFFEX, _Interval.MINUTE),
        ]
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(["IM2601.CFFEX"])
        assert result == ["MO2601-C-6300.CFFEX"]

    def test_ih_to_ho_mapping(self):
        """IH→HO 映射：匹配 HO 前缀的期权合约。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.return_value = [
            _make_overview("HO2501-P-2500", _Exchange.CFFEX, _Interval.MINUTE),
        ]
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(["IH2501.CFFEX"])
        assert result == ["HO2501-P-2500.CFFEX"]

    def test_commodity_option_self_prefix(self):
        """商品期权：无映射时使用自身前缀匹配（如 rb→rb）。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.return_value = [
            _make_overview("rb2505C3000", _Exchange.SHFE, _Interval.MINUTE),
            _make_overview("rb2505P2800", _Exchange.SHFE, _Interval.MINUTE),
        ]
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(["rb2505.SHFE"])
        assert len(result) == 2
        assert "rb2505C3000.SHFE" in result
        assert "rb2505P2800.SHFE" in result


class TestDiscoverFiltering:
    """过滤逻辑。Validates: Requirements 6.3"""

    def test_only_minute_interval(self):
        """仅返回 1 分钟 K 线数据的期权合约。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.return_value = [
            _make_overview("IO2501-C-4000", _Exchange.CFFEX, _Interval.MINUTE),
            _make_overview("IO2501-P-3800", _Exchange.CFFEX, _Interval.HOUR),
            _make_overview("IO2501-C-4200", _Exchange.CFFEX, _Interval.DAILY),
        ]
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(["IF2501.CFFEX"])
        assert result == ["IO2501-C-4000.CFFEX"]

    def test_exchange_mismatch_excluded(self):
        """交易所不匹配的合约被排除。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.return_value = [
            _make_overview("IO2501-C-4000", _Exchange.SHFE, _Interval.MINUTE),
        ]
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(["IF2501.CFFEX"])
        assert result == []

    def test_no_cp_suffix_excluded(self):
        """后缀不含 C 或 P 的合约被排除（非期权）。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.return_value = [
            # 前缀匹配但后缀无 C/P — 这是期货而非期权
            _make_overview("IF250106", _Exchange.CFFEX, _Interval.MINUTE),
        ]
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(["IF2501.CFFEX"])
        assert result == []

    def test_exact_prefix_not_matched(self):
        """symbol 与前缀完全相同（无后缀）不匹配。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.return_value = [
            _make_overview("IF2501", _Exchange.CFFEX, _Interval.MINUTE),
        ]
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(["IF2501.CFFEX"])
        assert result == []


class TestDiscoverMultipleUnderlyings:
    """多个标的期货场景。"""

    def test_multiple_underlyings(self):
        """同时查找多个期货的关联期权。"""
        mock_db = MagicMock()
        mock_db.get_bar_overview.return_value = [
            _make_overview("IO2501-C-4000", _Exchange.CFFEX, _Interval.MINUTE),
            _make_overview("MO2601-P-5000", _Exchange.CFFEX, _Interval.MINUTE),
            _make_overview("rb2505C3000", _Exchange.SHFE, _Interval.MINUTE),
        ]
        _db_mod.get_database.return_value = mock_db

        result = OptionDiscoveryService.discover(
            ["IF2501.CFFEX", "IM2601.CFFEX", "rb2505.SHFE"]
        )
        assert len(result) == 3
        assert "IO2501-C-4000.CFFEX" in result
        assert "MO2601-P-5000.CFFEX" in result
        assert "rb2505C3000.SHFE" in result
