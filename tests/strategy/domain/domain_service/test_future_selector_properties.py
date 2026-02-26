"""
BaseFutureSelector.select_dominant_contract 属性测试

# Feature: selection-service-enhancement, Property 1: 主力合约得分最高

**Validates: Requirements 1.1, 1.2**

Property 1: 主力合约得分最高
For any 非空期货合约列表和对应的行情数据，select_dominant_contract 返回的合约的
加权得分（volume × volume_weight + open_interest × oi_weight）应大于等于列表中
所有其他合约的加权得分。当得分相同时，返回的合约到期日应最近。
"""

import sys
from enum import Enum
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing (same pattern as unit tests)
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

# Generate unique contract symbols like "rb2501", "rb2506", etc.
_contract_symbol = _valid_yymm.map(lambda yymm: f"rb{yymm}")


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


# Strategy: list of unique contract symbols (1 to 10)
_unique_symbols = st.lists(
    _contract_symbol,
    min_size=1,
    max_size=10,
    unique=True,
)

# Strategy: market data values
_volume = st.integers(min_value=0, max_value=1_000_000)
_open_interest = st.floats(min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False)

# Strategy: weights (positive, summing to something meaningful)
_weight = st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


# Feature: selection-service-enhancement, Property 1: 主力合约得分最高
@settings(max_examples=100)
@given(
    symbols=_unique_symbols,
    volumes=st.lists(_volume, min_size=10, max_size=10),
    ois=st.lists(_open_interest, min_size=10, max_size=10),
    volume_weight=_weight,
    oi_weight=_weight,
)
def test_dominant_contract_has_highest_score(
    symbols, volumes, ois, volume_weight, oi_weight
):
    """
    Property 1: 主力合约得分最高

    **Validates: Requirements 1.1, 1.2**

    For any non-empty contract list with market data, the contract returned by
    select_dominant_contract should have a weighted score >= all other contracts.
    When scores are tied, the returned contract should have the earliest expiry.
    """
    selector = BaseFutureSelector()

    # Build contracts and market data
    contracts = [_make_contract(s) for s in symbols]
    market_data = {}
    for i, c in enumerate(contracts):
        market_data[c.vt_symbol] = MarketData(
            vt_symbol=c.vt_symbol,
            volume=volumes[i % len(volumes)],
            open_interest=ois[i % len(ois)],
        )

    # Compute scores manually
    def calc_score(contract):
        md = market_data.get(contract.vt_symbol)
        if md is None:
            return 0.0
        return md.volume * volume_weight + md.open_interest * oi_weight

    scores = [(c, calc_score(c)) for c in contracts]
    all_zero = all(s == 0.0 for _, s in scores)

    # If all scores are zero, the method falls back to expiry sorting —
    # that's a different path, still valid for Property 1 since all scores equal
    result = selector.select_dominant_contract(
        contracts,
        date.today(),
        market_data=market_data,
        volume_weight=volume_weight,
        oi_weight=oi_weight,
    )

    assert result is not None, "Non-empty list should never return None"

    result_score = calc_score(result)

    # Verify: returned contract score >= all other scores
    for contract in contracts:
        other_score = calc_score(contract)
        assert result_score >= other_score, (
            f"Selected {result.symbol} (score={result_score}) "
            f"has lower score than {contract.symbol} (score={other_score})"
        )

    # Verify tie-breaking: among contracts with the same max score,
    # the returned contract should have the earliest expiry date
    max_score = result_score
    tied_contracts = [c for c, s in scores if s == max_score]

    if len(tied_contracts) > 1:
        def get_expiry(contract):
            expiry = ContractHelper.get_expiry_from_symbol(contract.symbol)
            return expiry if expiry is not None else date.max

        result_expiry = get_expiry(result)
        for c in tied_contracts:
            c_expiry = get_expiry(c)
            assert result_expiry <= c_expiry, (
                f"Tie-break failed: selected {result.symbol} "
                f"(expiry={result_expiry}) should have earliest expiry, "
                f"but {c.symbol} (expiry={c_expiry}) is earlier"
            )


# ---------------------------------------------------------------------------
# Property 2: 到期日过滤正确性
# Feature: selection-service-enhancement, Property 2: 到期日过滤正确性
# ---------------------------------------------------------------------------

import calendar  # noqa: E402

# Strategy: generate a current_date for filter_by_maturity
_current_date = st.dates(min_value=date(2025, 1, 1), max_value=date(2035, 12, 28))

# Strategy: filter mode
_filter_mode = st.sampled_from(["current_month", "next_month", "custom"])

# Strategy: product prefixes to add variety
_product_prefix = st.sampled_from(["rb", "hc", "cu", "al", "zn", "ni"])

# Strategy: generate a single valid contract symbol with random product prefix
_contract_symbol_varied = st.tuples(
    _product_prefix,
    st.integers(min_value=25, max_value=35),
    st.integers(min_value=1, max_value=12),
).map(lambda t: f"{t[0]}{t[1]:02d}{t[2]:02d}")

# Strategy: list of unique varied contract symbols (1 to 15)
_unique_symbols_varied = st.lists(
    _contract_symbol_varied,
    min_size=1,
    max_size=15,
    unique=True,
)


def _compute_target_range(current_date: date, mode: str, date_range=None):
    """Compute the expected target date range for a given mode."""
    if mode == "current_month":
        range_start = date(current_date.year, current_date.month, 1)
        last_day = calendar.monthrange(current_date.year, current_date.month)[1]
        range_end = date(current_date.year, current_date.month, last_day)
    elif mode == "next_month":
        if current_date.month == 12:
            next_year = current_date.year + 1
            next_month = 1
        else:
            next_year = current_date.year
            next_month = current_date.month + 1
        range_start = date(next_year, next_month, 1)
        last_day = calendar.monthrange(next_year, next_month)[1]
        range_end = date(next_year, next_month, last_day)
    elif mode == "custom":
        range_start, range_end = date_range
    else:
        raise ValueError(f"Unknown mode: {mode}")
    return range_start, range_end


# Feature: selection-service-enhancement, Property 2: 到期日过滤正确性
@settings(max_examples=100)
@given(
    symbols=_unique_symbols_varied,
    current_dt=_current_date,
    mode=_filter_mode,
    custom_offset_start=st.integers(min_value=0, max_value=180),
    custom_offset_end=st.integers(min_value=0, max_value=180),
)
def test_filter_by_maturity_correctness(
    symbols, current_dt, mode, custom_offset_start, custom_offset_end
):
    """
    Property 2: 到期日过滤正确性

    **Validates: Requirements 2.1, 2.2, 2.3**

    For any contract list, current date, and filter mode (current_month / next_month / custom),
    filter_by_maturity should return contracts whose parsed expiry falls within the target
    date range, and all parseable contracts with expiry in range should be included.
    """
    selector = BaseFutureSelector()
    contracts = [_make_contract(s) for s in symbols]

    # Build date_range for custom mode
    date_range = None
    if mode == "custom":
        from datetime import timedelta
        start = current_dt - timedelta(days=custom_offset_start)
        end = current_dt + timedelta(days=custom_offset_end)
        # Ensure start <= end
        if start > end:
            start, end = end, start
        date_range = (start, end)

    # Call filter_by_maturity
    result = selector.filter_by_maturity(
        contracts, current_dt, mode=mode, date_range=date_range
    )

    # Compute expected target range
    range_start, range_end = _compute_target_range(current_dt, mode, date_range)

    # --- Soundness: every returned contract's expiry is in range ---
    for contract in result:
        expiry = ContractHelper.get_expiry_from_symbol(contract.symbol)
        assert expiry is not None, (
            f"Returned contract {contract.symbol} has unparseable expiry"
        )
        assert range_start <= expiry <= range_end, (
            f"Contract {contract.symbol} expiry {expiry} is outside "
            f"target range [{range_start}, {range_end}]"
        )

    # --- Completeness: all parseable contracts with expiry in range are included ---
    result_symbols = {c.symbol for c in result}
    for contract in contracts:
        expiry = ContractHelper.get_expiry_from_symbol(contract.symbol)
        if expiry is not None and range_start <= expiry <= range_end:
            assert contract.symbol in result_symbols, (
                f"Contract {contract.symbol} with expiry {expiry} is in range "
                f"[{range_start}, {range_end}] but was not included in result"
            )
