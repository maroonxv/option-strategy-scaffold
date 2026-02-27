"""
BaseFutureSelector 配置行为一致性属性测试

Feature: domain-service-config-enhancement, Property 4: BaseFutureSelector 主力合约选择一致性
Feature: domain-service-config-enhancement, Property 5: BaseFutureSelector 移仓检查一致性

**Validates: Requirements 5.3**
"""

import sys
from enum import Enum
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing (same pattern as existing tests)
# ---------------------------------------------------------------------------


class _Exchange(str, Enum):
    SHFE = "SHFE"
    CFFEX = "CFFEX"


class _Product(str, Enum):
    FUTURES = "期货"


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

from datetime import date  # noqa: E402

from hypothesis import given, settings, assume  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from src.strategy.domain.domain_service.selection.future_selection_service import (  # noqa: E402
    BaseFutureSelector,
)
from src.strategy.domain.value_object.config.future_selector_config import FutureSelectorConfig  # noqa: E402
from src.strategy.domain.value_object.selection import MarketData  # noqa: E402
from src.strategy.infrastructure.parsing.contract_helper import ContractHelper  # noqa: E402


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Generate valid YYMM suffixes: year 25-35, month 01-12
_valid_yymm = st.tuples(
    st.integers(min_value=25, max_value=35),
    st.integers(min_value=1, max_value=12),
).map(lambda ym: f"{ym[0]:02d}{ym[1]:02d}")

_contract_symbol = _valid_yymm.map(lambda yymm: f"rb{yymm}")

_unique_symbols = st.lists(
    _contract_symbol,
    min_size=1,
    max_size=10,
    unique=True,
)

_volume = st.integers(min_value=0, max_value=1_000_000)
_open_interest = st.floats(
    min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
)

_current_date = st.dates(min_value=date(2025, 1, 1), max_value=date(2035, 12, 28))


def _make_contract(symbol: str) -> _ContractData:
    return _ContractData(
        symbol=symbol,
        exchange=_Exchange.SHFE,
        name=symbol,
        product=_Product.FUTURES,
        size=10,
        pricetick=1.0,
        gateway_name="test",
    )


# ===========================================================================
# Feature: domain-service-config-enhancement, Property 4: BaseFutureSelector 主力合约选择一致性
# ===========================================================================


class TestProperty4DominantSelectionConsistency:
    """
    Property 4: BaseFutureSelector 主力合约选择一致性

    对于任意合约列表和行情数据组合，使用默认配置实例化的 BaseFutureSelector
    调用 select_dominant_contract 方法，应该选择与使用显式默认参数
    (volume_weight=0.6, oi_weight=0.4) 实例化时相同的合约。

    **Validates: Requirements 5.3**
    """

    def test_default_config_matches_pre_refactor_defaults(self):
        """默认 FutureSelectorConfig 字段值与重构前默认参数一致"""
        config = FutureSelectorConfig()
        assert config.volume_weight == 0.6, (
            f"volume_weight 默认值应为 0.6, 实际为 {config.volume_weight}"
        )
        assert config.oi_weight == 0.4, (
            f"oi_weight 默认值应为 0.4, 实际为 {config.oi_weight}"
        )
        assert config.rollover_days == 5, (
            f"rollover_days 默认值应为 5, 实际为 {config.rollover_days}"
        )

    @given(
        symbols=_unique_symbols,
        volumes=st.lists(_volume, min_size=10, max_size=10),
        ois=st.lists(_open_interest, min_size=10, max_size=10),
        current_dt=_current_date,
    )
    @settings(max_examples=100)
    def test_dominant_selection_consistency(
        self, symbols, volumes, ois, current_dt
    ):
        """
        Feature: domain-service-config-enhancement, Property 4: BaseFutureSelector 主力合约选择一致性

        BaseFutureSelector(config=FutureSelectorConfig()) 与
        BaseFutureSelector(config=FutureSelectorConfig(volume_weight=0.6, oi_weight=0.4))
        对同一输入应选择完全相同的合约。

        **Validates: Requirements 5.3**
        """
        # 服务 A：不传配置（内部回退到默认配置）
        selector_implicit = BaseFutureSelector()
        # 服务 B：显式传入默认值配置
        selector_explicit = BaseFutureSelector(
            config=FutureSelectorConfig(volume_weight=0.6, oi_weight=0.4)
        )

        contracts = [_make_contract(s) for s in symbols]
        market_data = {}
        for i, c in enumerate(contracts):
            market_data[c.vt_symbol] = MarketData(
                vt_symbol=c.vt_symbol,
                volume=volumes[i % len(volumes)],
                open_interest=ois[i % len(ois)],
            )

        result_implicit = selector_implicit.select_dominant_contract(
            contracts, current_dt, market_data=market_data,
        )
        result_explicit = selector_explicit.select_dominant_contract(
            contracts, current_dt, market_data=market_data,
        )

        # 两者应选择完全相同的合约
        assert result_implicit is not None
        assert result_explicit is not None
        assert result_implicit.symbol == result_explicit.symbol, (
            f"主力合约选择不一致: implicit={result_implicit.symbol}, "
            f"explicit={result_explicit.symbol}"
        )

    @given(
        symbols=_unique_symbols,
        current_dt=_current_date,
    )
    @settings(max_examples=100)
    def test_dominant_selection_consistency_no_market_data(
        self, symbols, current_dt
    ):
        """
        Feature: domain-service-config-enhancement, Property 4: BaseFutureSelector 主力合约选择一致性

        无行情数据时，两种实例化方式也应返回相同合约。

        **Validates: Requirements 5.3**
        """
        selector_implicit = BaseFutureSelector()
        selector_explicit = BaseFutureSelector(
            config=FutureSelectorConfig(volume_weight=0.6, oi_weight=0.4)
        )

        contracts = [_make_contract(s) for s in symbols]

        result_implicit = selector_implicit.select_dominant_contract(
            contracts, current_dt,
        )
        result_explicit = selector_explicit.select_dominant_contract(
            contracts, current_dt,
        )

        assert result_implicit is not None
        assert result_explicit is not None
        assert result_implicit.symbol == result_explicit.symbol, (
            f"无行情数据时主力合约选择不一致: implicit={result_implicit.symbol}, "
            f"explicit={result_explicit.symbol}"
        )


# ===========================================================================
# Feature: domain-service-config-enhancement, Property 5: BaseFutureSelector 移仓检查一致性
# ===========================================================================


class TestProperty5RolloverCheckConsistency:
    """
    Property 5: BaseFutureSelector 移仓检查一致性

    对于任意当前合约、合约列表和当前日期组合，使用默认配置实例化的
    BaseFutureSelector 调用 check_rollover 方法，应该产生与使用显式默认参数
    (rollover_days=5) 实例化时相同的 RolloverRecommendation。

    **Validates: Requirements 5.3**
    """

    @given(
        symbol=_contract_symbol,
        current_dt=_current_date,
    )
    @settings(max_examples=100)
    def test_rollover_check_consistency(self, symbol, current_dt):
        """
        Feature: domain-service-config-enhancement, Property 5: BaseFutureSelector 移仓检查一致性

        BaseFutureSelector() 与
        BaseFutureSelector(config=FutureSelectorConfig(rollover_days=5))
        对同一输入应产生完全相同的 RolloverRecommendation。

        **Validates: Requirements 5.3**
        """
        expiry = ContractHelper.get_expiry_from_symbol(symbol)
        assume(expiry is not None)

        selector_implicit = BaseFutureSelector()
        selector_explicit = BaseFutureSelector(
            config=FutureSelectorConfig(rollover_days=5)
        )

        contract = _make_contract(symbol)

        result_implicit = selector_implicit.check_rollover(
            current_contract=contract,
            all_contracts=[contract],
            current_date=current_dt,
        )
        result_explicit = selector_explicit.check_rollover(
            current_contract=contract,
            all_contracts=[contract],
            current_date=current_dt,
        )

        # 两者应产生完全相同的结果
        if result_implicit is None:
            assert result_explicit is None, (
                f"移仓检查不一致: implicit=None, explicit={result_explicit}"
            )
        else:
            assert result_explicit is not None, (
                f"移仓检查不一致: implicit={result_implicit}, explicit=None"
            )
            assert result_implicit.current_contract_symbol == result_explicit.current_contract_symbol
            assert result_implicit.target_contract_symbol == result_explicit.target_contract_symbol
            assert result_implicit.remaining_days == result_explicit.remaining_days
            assert result_implicit.has_target == result_explicit.has_target
            assert result_implicit.reason == result_explicit.reason

    @given(
        symbol=_contract_symbol,
        current_dt=_current_date,
        extra_symbols=_unique_symbols,
        volumes=st.lists(_volume, min_size=10, max_size=10),
        ois=st.lists(_open_interest, min_size=10, max_size=10),
    )
    @settings(max_examples=100)
    def test_rollover_check_consistency_with_market_data(
        self, symbol, current_dt, extra_symbols, volumes, ois
    ):
        """
        Feature: domain-service-config-enhancement, Property 5: BaseFutureSelector 移仓检查一致性

        有行情数据和多个合约时，两种实例化方式也应产生相同的移仓建议。

        **Validates: Requirements 5.3**
        """
        expiry = ContractHelper.get_expiry_from_symbol(symbol)
        assume(expiry is not None)

        selector_implicit = BaseFutureSelector()
        selector_explicit = BaseFutureSelector(
            config=FutureSelectorConfig(rollover_days=5)
        )

        current_contract = _make_contract(symbol)
        all_contracts = [current_contract] + [_make_contract(s) for s in extra_symbols]

        # Build market data
        market_data = {}
        for i, c in enumerate(all_contracts):
            market_data[c.vt_symbol] = MarketData(
                vt_symbol=c.vt_symbol,
                volume=volumes[i % len(volumes)],
                open_interest=ois[i % len(ois)],
            )

        result_implicit = selector_implicit.check_rollover(
            current_contract=current_contract,
            all_contracts=all_contracts,
            current_date=current_dt,
            market_data=market_data,
        )
        result_explicit = selector_explicit.check_rollover(
            current_contract=current_contract,
            all_contracts=all_contracts,
            current_date=current_dt,
            market_data=market_data,
        )

        if result_implicit is None:
            assert result_explicit is None, (
                f"移仓检查不一致: implicit=None, explicit={result_explicit}"
            )
        else:
            assert result_explicit is not None, (
                f"移仓检查不一致: implicit={result_implicit}, explicit=None"
            )
            assert result_implicit.current_contract_symbol == result_explicit.current_contract_symbol
            assert result_implicit.target_contract_symbol == result_explicit.target_contract_symbol
            assert result_implicit.remaining_days == result_explicit.remaining_days
            assert result_implicit.has_target == result_explicit.has_target
            assert result_implicit.reason == result_explicit.reason
