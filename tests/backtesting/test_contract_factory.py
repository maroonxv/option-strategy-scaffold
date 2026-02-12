"""ContractFactory 单元测试"""

import sys
from enum import Enum
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing contract_factory
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
    """Minimal ContractData stand-in for testing."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        # Ensure option fields have defaults
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


# Patch sys.modules so that `from vnpy.trader.constant import ...` works
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

import pytest  # noqa: E402

from src.backtesting.config import DEFAULT_PRODUCT_SPEC, PRODUCT_SPECS  # noqa: E402
from src.backtesting.contract.contract_factory import ContractFactory  # noqa: E402


class TestParseVtSymbol:
    """ContractFactory.parse_vt_symbol() 测试"""

    def test_futures_symbol(self):
        result = ContractFactory.parse_vt_symbol("rb2505.SHFE")
        assert result == ("rb2505", "SHFE", "rb")

    def test_option_symbol_with_dashes(self):
        result = ContractFactory.parse_vt_symbol("MO2601-C-6300.CFFEX")
        assert result == ("MO2601-C-6300", "CFFEX", "MO")

    def test_option_symbol_without_dashes(self):
        result = ContractFactory.parse_vt_symbol("rb2505C3000.SHFE")
        assert result == ("rb2505C3000", "SHFE", "rb")

    def test_missing_dot_returns_none(self):
        assert ContractFactory.parse_vt_symbol("rb2505SHFE") is None

    def test_empty_string_returns_none(self):
        assert ContractFactory.parse_vt_symbol("") is None

    def test_no_alpha_prefix_returns_none(self):
        assert ContractFactory.parse_vt_symbol("2505.SHFE") is None


class TestCreateFutures:
    """ContractFactory.create() 期货合约测试"""

    def test_basic_futures(self):
        contract = ContractFactory.create("rb2505.SHFE")
        assert contract is not None
        assert contract.symbol == "rb2505"
        assert contract.exchange == _Exchange.SHFE
        assert contract.product == _Product.FUTURES
        assert contract.size == PRODUCT_SPECS["rb"][0]
        assert contract.pricetick == PRODUCT_SPECS["rb"][1]
        assert contract.min_volume == 1
        assert contract.gateway_name == "BACKTESTING"

    def test_cffex_futures(self):
        contract = ContractFactory.create("IF2501.CFFEX")
        assert contract is not None
        assert contract.product == _Product.FUTURES
        assert contract.size == 300
        assert contract.pricetick == 0.2

    def test_unknown_product_uses_default_spec(self):
        """未知品种使用默认规格 (Req 5.4)"""
        contract = ContractFactory.create("XX2501.SHFE")
        assert contract is not None
        assert contract.size == DEFAULT_PRODUCT_SPEC[0]
        assert contract.pricetick == DEFAULT_PRODUCT_SPEC[1]

    def test_custom_gateway_name(self):
        contract = ContractFactory.create("rb2505.SHFE", gateway_name="TEST")
        assert contract is not None
        assert contract.gateway_name == "TEST"


class TestCreateOption:
    """ContractFactory.create() 期权合约测试"""

    def test_cffex_option_with_dashes(self):
        """中金所期权格式：MO2601-C-6300.CFFEX (Req 5.2)"""
        contract = ContractFactory.create("MO2601-C-6300.CFFEX")
        assert contract is not None
        assert contract.product == _Product.OPTION
        assert contract.option_type == _OptionType.CALL
        assert contract.option_strike == 6300.0
        assert contract.size == PRODUCT_SPECS["MO"][0]
        assert contract.pricetick == PRODUCT_SPECS["MO"][1]

    def test_option_reverse_mapping_mo_to_im(self):
        """期权反向映射：MO → IM (Req 5.3)"""
        contract = ContractFactory.create("MO2601-C-6300.CFFEX")
        assert contract is not None
        assert contract.option_underlying == "IM2601"

    def test_option_reverse_mapping_io_to_if(self):
        """期权反向映射：IO → IF (Req 5.3)"""
        contract = ContractFactory.create("IO2501-P-4000.CFFEX")
        assert contract is not None
        assert contract.option_underlying == "IF2501"
        assert contract.option_type == _OptionType.PUT

    def test_option_reverse_mapping_ho_to_ih(self):
        """期权反向映射：HO → IH (Req 5.3)"""
        contract = ContractFactory.create("HO2503-C-3000.CFFEX")
        assert contract is not None
        assert contract.option_underlying == "IH2503"

    def test_shfe_option_without_dashes(self):
        """上期所期权格式：rb2505C3000.SHFE (Req 5.2)"""
        contract = ContractFactory.create("rb2505C3000.SHFE")
        assert contract is not None
        assert contract.product == _Product.OPTION
        assert contract.option_type == _OptionType.CALL
        assert contract.option_strike == 3000.0
        assert contract.option_underlying == "rb2505"

    def test_put_option(self):
        contract = ContractFactory.create("rb2505P2800.SHFE")
        assert contract is not None
        assert contract.option_type == _OptionType.PUT
        assert contract.option_strike == 2800.0

    def test_option_with_decimal_strike(self):
        """行权价带小数"""
        contract = ContractFactory.create("sc2602C540.5.INE")
        assert contract is not None
        assert contract.option_strike == 540.5

    def test_option_expiry_is_set(self):
        """期权到期日应被计算并设置 (Req 5.2)"""
        contract = ContractFactory.create("MO2601-C-6300.CFFEX")
        assert contract is not None
        assert contract.option_expiry is not None

    def test_no_reverse_mapping_keeps_original(self):
        """无反向映射时保留原始 underlying"""
        contract = ContractFactory.create("rb2505C3000.SHFE")
        assert contract is not None
        assert contract.option_underlying == "rb2505"


class TestCreateInvalid:
    """ContractFactory.create() 无效输入测试 (Req 5.5)"""

    def test_invalid_format_returns_none(self):
        assert ContractFactory.create("invalid") is None

    def test_invalid_exchange_returns_none(self):
        assert ContractFactory.create("rb2505.INVALID") is None

    def test_empty_string_returns_none(self):
        assert ContractFactory.create("") is None

    def test_numeric_only_symbol_returns_none(self):
        assert ContractFactory.create("2505.SHFE") is None
