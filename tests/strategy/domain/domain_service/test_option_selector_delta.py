"""
OptionSelectorService.select_by_delta 单元测试

验证基于目标 Delta 的期权选择逻辑。
Validates: Requirements 5.1, 5.2, 5.3
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing
# ---------------------------------------------------------------------------
for _name in [
    "vnpy",
    "vnpy.event",
    "vnpy.trader",
    "vnpy.trader.setting",
    "vnpy.trader.engine",
    "vnpy.trader.database",
    "vnpy.trader.constant",
    "vnpy.trader.object",
    "vnpy_mysql",
]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

# ---------------------------------------------------------------------------
import pytest
import pandas as pd

from src.strategy.domain.domain_service.selection.option_selector_service import (
    OptionSelectorService,
)
from src.strategy.domain.value_object.option_selector_config import OptionSelectorConfig
from src.strategy.domain.value_object.greeks import GreeksResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_option_df(rows: list[dict]) -> pd.DataFrame:
    """从字典列表构建期权合约 DataFrame。"""
    defaults = {
        "underlying_symbol": "IO2506",
        "expiry_date": "2025-06-20",
        "bid_price": 100.0,
        "bid_volume": 50,
        "ask_price": 102.0,
        "ask_volume": 50,
        "days_to_expiry": 20,
    }
    full_rows = []
    for r in rows:
        row = {**defaults, **r}
        full_rows.append(row)
    return pd.DataFrame(full_rows)


def _build_call_chain(underlying_price: float) -> tuple[pd.DataFrame, dict[str, GreeksResult]]:
    """构建一条 Call 期权链及对应的 Greeks 数据。"""
    strikes = [
        underlying_price - 200,
        underlying_price - 100,
        underlying_price,
        underlying_price + 100,
        underlying_price + 200,
    ]
    rows = []
    greeks_data = {}
    # Delta 从高到低: ITM -> ATM -> OTM
    deltas = [0.85, 0.65, 0.50, 0.35, 0.15]
    for s, d in zip(strikes, deltas):
        sym = f"IO2506-C-{int(s)}.CFFEX"
        rows.append({
            "vt_symbol": sym,
            "option_type": "call",
            "strike_price": s,
        })
        greeks_data[sym] = GreeksResult(delta=d, gamma=0.01, theta=-0.5, vega=0.2)
    df = _make_option_df(rows)
    return df, greeks_data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def selector() -> OptionSelectorService:
    return OptionSelectorService(
        config=OptionSelectorConfig(
            strike_level=3,
            min_bid_price=10.0,
            min_bid_volume=10,
            min_trading_days=1,
            max_trading_days=50,
        )
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSelectByDelta:
    """select_by_delta 单元测试"""

    def test_selects_closest_delta(self, selector: OptionSelectorService):
        """应选择 Delta 最接近目标值的合约 (Req 5.1)"""
        df, greeks = _build_call_chain(4000.0)
        result = selector.select_by_delta(
            contracts=df,
            option_type="call",
            underlying_price=4000.0,
            target_delta=0.35,
            greeks_data=greeks,
            delta_tolerance=0.2,
        )
        assert result is not None
        assert result.strike_price == 4100.0  # delta=0.35, exact match

    def test_selects_within_tolerance(self, selector: OptionSelectorService):
        """应仅返回 Delta 在容差范围内的合约 (Req 5.3)"""
        df, greeks = _build_call_chain(4000.0)
        # target=0.50, tolerance=0.10 -> only delta in [0.40, 0.60] qualify
        result = selector.select_by_delta(
            contracts=df,
            option_type="call",
            underlying_price=4000.0,
            target_delta=0.50,
            greeks_data=greeks,
            delta_tolerance=0.10,
        )
        assert result is not None
        assert result.strike_price == 4000.0  # delta=0.50, exact match

    def test_no_candidates_within_tolerance_returns_none(self, selector: OptionSelectorService):
        """容差范围内无候选合约时返回 None"""
        df, greeks = _build_call_chain(4000.0)
        # target=0.99, tolerance=0.01 -> no delta in [0.98, 1.00]
        result = selector.select_by_delta(
            contracts=df,
            option_type="call",
            underlying_price=4000.0,
            target_delta=0.99,
            greeks_data=greeks,
            delta_tolerance=0.01,
        )
        assert result is None

    def test_fallback_when_no_greeks_data(self, selector: OptionSelectorService):
        """无 Greeks 数据时回退到 select_option (Req 5.2)"""
        df, _ = _build_call_chain(4000.0)
        empty_greeks: dict[str, GreeksResult] = {}
        result = selector.select_by_delta(
            contracts=df,
            option_type="call",
            underlying_price=4000.0,
            target_delta=0.35,
            greeks_data=empty_greeks,
        )
        # 回退到 select_option，应返回虚值第3档
        assert result is not None

    def test_fallback_when_greeks_not_successful(self, selector: OptionSelectorService):
        """Greeks 计算失败时回退到 select_option (Req 5.2)"""
        df, _ = _build_call_chain(4000.0)
        # 所有 Greeks 标记为失败
        greeks = {}
        for _, row in df.iterrows():
            sym = row["vt_symbol"]
            greeks[sym] = GreeksResult(delta=0.5, success=False, error_message="计算失败")
        result = selector.select_by_delta(
            contracts=df,
            option_type="call",
            underlying_price=4000.0,
            target_delta=0.35,
            greeks_data=greeks,
        )
        # 回退到 select_option
        assert result is not None

    def test_empty_contracts_returns_none(self, selector: OptionSelectorService):
        """空合约列表返回 None"""
        result = selector.select_by_delta(
            contracts=pd.DataFrame(),
            option_type="call",
            underlying_price=4000.0,
            target_delta=0.35,
            greeks_data={},
        )
        assert result is None

    def test_invalid_underlying_price_returns_none(self, selector: OptionSelectorService):
        """无效标的价格返回 None"""
        df, greeks = _build_call_chain(4000.0)
        result = selector.select_by_delta(
            contracts=df,
            option_type="call",
            underlying_price=0,
            target_delta=0.35,
            greeks_data=greeks,
        )
        assert result is None

    def test_invalid_option_type_returns_none(self, selector: OptionSelectorService):
        """无效期权类型返回 None"""
        df, greeks = _build_call_chain(4000.0)
        result = selector.select_by_delta(
            contracts=df,
            option_type="invalid",
            underlying_price=4000.0,
            target_delta=0.35,
            greeks_data=greeks,
        )
        assert result is None

    def test_log_func_called(self, selector: OptionSelectorService):
        """日志函数应被调用"""
        df, greeks = _build_call_chain(4000.0)
        logs = []
        selector.select_by_delta(
            contracts=df,
            option_type="call",
            underlying_price=4000.0,
            target_delta=0.35,
            greeks_data=greeks,
            delta_tolerance=0.2,
            log_func=logs.append,
        )
        assert any("[DELTA]" in msg for msg in logs)

    def test_put_option_selection(self, selector: OptionSelectorService):
        """应支持 Put 期权的 Delta 选择"""
        strikes = [3800.0, 3900.0, 4000.0, 4100.0, 4200.0]
        deltas = [-0.85, -0.65, -0.50, -0.35, -0.15]
        rows = []
        greeks = {}
        for s, d in zip(strikes, deltas):
            sym = f"IO2506-P-{int(s)}.CFFEX"
            rows.append({
                "vt_symbol": sym,
                "option_type": "put",
                "strike_price": s,
            })
            greeks[sym] = GreeksResult(delta=d, gamma=0.01, theta=-0.5, vega=0.2)
        df = _make_option_df(rows)

        result = selector.select_by_delta(
            contracts=df,
            option_type="put",
            underlying_price=4000.0,
            target_delta=-0.35,
            greeks_data=greeks,
            delta_tolerance=0.1,
        )
        assert result is not None
        assert result.strike_price == 4100.0  # delta=-0.35

    def test_case_insensitive_option_type(self, selector: OptionSelectorService):
        """option_type 应大小写不敏感"""
        df, greeks = _build_call_chain(4000.0)
        result = selector.select_by_delta(
            contracts=df,
            option_type="CALL",
            underlying_price=4000.0,
            target_delta=0.50,
            greeks_data=greeks,
            delta_tolerance=0.1,
        )
        assert result is not None
