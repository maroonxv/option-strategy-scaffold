"""
ContractRegistry 单元测试

验证合约注册表的注册、查询、批量注册和引擎注入功能。
Validates: Requirements 7.1, 7.2, 7.3, 7.4
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
    DCE = "DCE"
    CZCE = "CZCE"
    INE = "INE"


class _Product(str, Enum):
    FUTURES = "期货"
    OPTION = "期权"


class _OptionType(str, Enum):
    CALL = "看涨期权"
    PUT = "看跌期权"


class _ContractData:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        for attr in (
            "option_strike",
            "option_underlying",
            "option_type",
            "option_expiry",
        ):
            if not hasattr(self, attr):
                setattr(self, attr, None)

    @property
    def vt_symbol(self) -> str:
        return f"{self.symbol}.{self.exchange.value}"


_const_mod = MagicMock()
_const_mod.Exchange = _Exchange
_const_mod.Product = _Product
_const_mod.OptionType = _OptionType

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

from src.backtesting.contract.contract_registry import ContractRegistry  # noqa: E402


def _make_contract(symbol: str, exchange: _Exchange) -> _ContractData:
    """创建测试用 ContractData。"""
    return _ContractData(
        symbol=symbol,
        exchange=exchange,
        name=symbol,
        product=_Product.FUTURES,
        size=10,
        pricetick=1.0,
        min_volume=1,
        gateway_name="BACKTESTING",
    )


class TestContractRegistryBasic:
    """测试 register / get / get_all 基本接口。"""

    def test_register_and_get(self):
        """注册后可通过 vt_symbol 查询到合约。"""
        registry = ContractRegistry()
        contract = _make_contract("rb2505", _Exchange.SHFE)

        registry.register(contract)

        result = registry.get("rb2505.SHFE")
        assert result is contract

    def test_get_nonexistent_returns_none(self):
        """查询不存在的合约返回 None。"""
        registry = ContractRegistry()
        assert registry.get("rb2505.SHFE") is None

    def test_get_all_empty(self):
        """空注册表返回空列表。"""
        registry = ContractRegistry()
        assert registry.get_all() == []

    def test_get_all_returns_all_registered(self):
        """get_all 返回所有已注册合约。"""
        registry = ContractRegistry()
        c1 = _make_contract("rb2505", _Exchange.SHFE)
        c2 = _make_contract("IF2506", _Exchange.CFFEX)

        registry.register(c1)
        registry.register(c2)

        all_contracts = registry.get_all()
        assert len(all_contracts) == 2
        assert c1 in all_contracts
        assert c2 in all_contracts

    def test_register_overwrites_same_vt_symbol(self):
        """重复注册同一 vt_symbol 会覆盖旧合约。"""
        registry = ContractRegistry()
        c1 = _make_contract("rb2505", _Exchange.SHFE)
        c2 = _make_contract("rb2505", _Exchange.SHFE)
        c2.size = 20  # 不同的 size

        registry.register(c1)
        registry.register(c2)

        assert registry.get("rb2505.SHFE").size == 20
        assert len(registry.get_all()) == 1


class TestContractRegistryRegisterMany:
    """测试 register_many 批量注册。"""

    def test_register_many_valid_symbols(self):
        """批量注册有效的 vt_symbols。"""
        registry = ContractRegistry()
        count = registry.register_many(["rb2505.SHFE", "IF2506.CFFEX"])

        assert count == 2
        assert len(registry.get_all()) == 2
        assert registry.get("rb2505.SHFE") is not None
        assert registry.get("IF2506.CFFEX") is not None

    def test_register_many_with_invalid_symbol(self):
        """批量注册中包含无效 symbol，跳过无效的，返回成功数量。"""
        registry = ContractRegistry()
        count = registry.register_many(["rb2505.SHFE", "INVALID", "IF2506.CFFEX"])

        assert count == 2
        assert len(registry.get_all()) == 2

    def test_register_many_empty_list(self):
        """空列表返回 0。"""
        registry = ContractRegistry()
        count = registry.register_many([])
        assert count == 0
        assert len(registry.get_all()) == 0


class TestContractRegistryInjectIntoEngine:
    """测试 inject_into_engine 引擎注入。"""

    def test_inject_sets_engine_attributes(self):
        """注入后引擎具有 all_contracts_map、get_all_contracts、get_contract。"""
        registry = ContractRegistry()
        c1 = _make_contract("rb2505", _Exchange.SHFE)
        c2 = _make_contract("IF2506", _Exchange.CFFEX)
        registry.register(c1)
        registry.register(c2)

        engine = MagicMock()
        registry.inject_into_engine(engine)

        # all_contracts_map 被设置
        assert hasattr(engine, "all_contracts_map")
        assert "rb2505.SHFE" in engine.all_contracts_map
        assert "IF2506.CFFEX" in engine.all_contracts_map

        # get_all_contracts 返回所有合约
        all_contracts = engine.get_all_contracts()
        assert len(all_contracts) == 2

        # get_contract 查询单个合约
        assert engine.get_contract("rb2505.SHFE") is c1
        assert engine.get_contract("IF2506.CFFEX") is c2
        assert engine.get_contract("nonexistent.SHFE") is None

    def test_inject_empty_registry(self):
        """空注册表注入后引擎返回空结果。"""
        registry = ContractRegistry()
        engine = MagicMock()
        registry.inject_into_engine(engine)

        assert engine.all_contracts_map == {}
        assert engine.get_all_contracts() == []
        assert engine.get_contract("rb2505.SHFE") is None
