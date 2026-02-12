"""
ContractRegistry 属性测试

Feature: backtesting-restructure
Property 7: 合约注册表 round-trip
Validates: Requirements 7.1, 7.2, 7.3
"""

import sys
from enum import Enum
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing contract_registry
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
        for attr in ("option_strike", "option_underlying", "option_type", "option_expiry"):
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

for _name in ["vnpy", "vnpy.event", "vnpy.trader", "vnpy.trader.setting",
               "vnpy.trader.engine", "vnpy.trader.database", "vnpy_mysql"]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

sys.modules["vnpy.trader.constant"] = _const_mod
sys.modules["vnpy.trader.object"] = _obj_mod

# ---------------------------------------------------------------------------
# Now safe to import
# ---------------------------------------------------------------------------

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from src.backtesting.contract.contract_registry import ContractRegistry  # noqa: E402

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_exchanges = list(_Exchange)

_symbol_exchange_st = st.tuples(
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=2,
        max_size=8,
    ),
    st.sampled_from(_exchanges),
)

_contract_list_st = st.lists(
    _symbol_exchange_st,
    min_size=0,
    max_size=10,
    unique_by=lambda x: f"{x[0]}.{x[1].value}",
)


def _make_contract(symbol: str, exchange: _Exchange) -> _ContractData:
    """构建测试用 ContractData。"""
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


# ---------------------------------------------------------------------------
# Property 7: 合约注册表 round-trip
# ---------------------------------------------------------------------------


class TestContractRegistryRoundTrip:
    """Property 7: 合约注册表 round-trip

    *For any* 一组 ContractData 对象，注册到 ContractRegistry 后：
    - get_all() 返回的合约数量等于注册的去重数量
    - 对每个已注册的 vt_symbol，get() 返回对应的 ContractData
    - 对未注册的 vt_symbol，get() 返回 None

    **Validates: Requirements 7.1, 7.2, 7.3**
    """

    @given(pairs=_contract_list_st)
    @settings(max_examples=100)
    def test_get_all_count_equals_unique_registrations(self, pairs):
        """get_all() 返回的合约数量等于注册的去重数量。

        **Validates: Requirements 7.1**
        """
        registry = ContractRegistry()
        contracts = [_make_contract(sym, exc) for sym, exc in pairs]

        for c in contracts:
            registry.register(c)

        # pairs 已通过 unique_by 去重，所以长度就是去重数量
        assert len(registry.get_all()) == len(pairs)

    @given(pairs=_contract_list_st)
    @settings(max_examples=100)
    def test_get_returns_registered_contract(self, pairs):
        """对每个已注册的 vt_symbol，get() 返回对应的 ContractData。

        **Validates: Requirements 7.2**
        """
        registry = ContractRegistry()
        contracts = [_make_contract(sym, exc) for sym, exc in pairs]

        for c in contracts:
            registry.register(c)

        for c in contracts:
            result = registry.get(c.vt_symbol)
            assert result is c, (
                f"get({c.vt_symbol!r}) 返回 {result}, 期望 {c}"
            )

    @given(pairs=_contract_list_st)
    @settings(max_examples=100)
    def test_get_returns_none_for_unregistered(self, pairs):
        """对未注册的 vt_symbol，get() 返回 None。

        **Validates: Requirements 7.3**
        """
        registry = ContractRegistry()
        contracts = [_make_contract(sym, exc) for sym, exc in pairs]

        for c in contracts:
            registry.register(c)

        # 构造一个一定不存在的 vt_symbol
        unregistered = "ZZZZNOTEXIST9999.SHFE"
        assert registry.get(unregistered) is None
