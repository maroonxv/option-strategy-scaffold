"""
Property-Based Tests for bar-generator-decoupling

Feature: bar-generator-decoupling

Uses hypothesis to verify correctness properties across randomized inputs.
"""

import sys
from unittest.mock import MagicMock

# ── Mock vnpy ecosystem (same pattern as test_strategy_entry_bar_pipeline.py) ──
_vnpy_mods = [
    "vnpy", "vnpy.event", "vnpy.event.engine",
    "vnpy.trader", "vnpy.trader.setting", "vnpy.trader.engine",
    "vnpy.trader.constant", "vnpy.trader.object", "vnpy.trader.database",
    "vnpy_mysql",
    "vnpy_portfoliostrategy", "vnpy_portfoliostrategy.utility",
    "vnpy_portfoliostrategy.template",
]
for _mod in _vnpy_mods:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Set up mock Interval enum
mock_interval = MagicMock()
mock_interval.MINUTE = "MINUTE"
mock_interval.HOUR = "HOUR"
mock_interval.DAILY = "DAILY"
sys.modules["vnpy.trader.constant"].Interval = mock_interval

# Make StrategyTemplate a plain class that sets attributes StrategyEntry expects
def _mock_template_init(self, strategy_engine, strategy_name, vt_symbols, setting):
    self.strategy_engine = strategy_engine
    self.strategy_name = strategy_name
    self.vt_symbols = list(vt_symbols)
    self.setting = dict(setting)
    self.trading = False
    self.inited = False

_MockStrategyTemplate = type("StrategyTemplate", (), {
    "__init__": _mock_template_init,
})
sys.modules["vnpy_portfoliostrategy"].StrategyTemplate = _MockStrategyTemplate
sys.modules["vnpy_portfoliostrategy"].StrategyEngine = MagicMock

# ── Mock src.main (external to strategy package) ──
for _mod in [
    "src.main", "src.main.bootstrap", "src.main.bootstrap.database_factory",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# ── Mock strategy domain & infrastructure leaf modules ──
_leaf_mods = [
    "src.strategy.domain.aggregate.target_instrument_aggregate",
    "src.strategy.domain.aggregate.position_aggregate",
    "src.strategy.domain.domain_service.indicator_service",
    "src.strategy.domain.domain_service.signal_service",
    "src.strategy.domain.domain_service.position_sizing_service",
    "src.strategy.domain.domain_service.option_selector_service",
    "src.strategy.domain.domain_service.future_selection_service",
    "src.strategy.domain.domain_service.greeks_calculator",
    "src.strategy.domain.domain_service.portfolio_risk_aggregator",
    "src.strategy.domain.domain_service.smart_order_executor",
    "src.strategy.domain.entity.position",
    "src.strategy.domain.event.event_types",
    "src.strategy.domain.value_object.risk",
    "src.strategy.domain.value_object.order_execution",
    "src.strategy.infrastructure.gateway.vnpy_market_data_gateway",
    "src.strategy.infrastructure.gateway.vnpy_account_gateway",
    "src.strategy.infrastructure.gateway.vnpy_trade_execution_gateway",
    "src.strategy.infrastructure.reporting.feishu_handler",
    "src.strategy.infrastructure.logging.logging_utils",
    "src.strategy.infrastructure.monitoring.strategy_monitor",
    "src.strategy.infrastructure.persistence.state_repository",
    "src.strategy.infrastructure.persistence.json_serializer",
    "src.strategy.infrastructure.persistence.migration_chain",
    "src.strategy.infrastructure.persistence.auto_save_service",
    "src.strategy.infrastructure.persistence.exceptions",
    "src.strategy.infrastructure.persistence.history_data_repository",
    "src.strategy.infrastructure.utils.contract_helper",
]
for _mod in _leaf_mods:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Now import StrategyEntry — all heavy deps are mocked
from src.strategy.strategy_entry import StrategyEntry

import hypothesis.strategies as st
from hypothesis import given, settings


# ── Hypothesis strategies ──

def st_vt_symbol() -> st.SearchStrategy[str]:
    """Generate valid vt_symbol strings like 'ABC123.LOCAL'."""
    return st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=10,
    ).map(lambda s: s + ".LOCAL")


def st_bars_dict() -> st.SearchStrategy[dict]:
    """Generate Dict[str, BarData] with 0~5 entries using MagicMock as BarData stand-ins."""
    return st.dictionaries(
        keys=st_vt_symbol(),
        values=st.builds(MagicMock),
        min_size=0,
        max_size=5,
    )


def _make_entry() -> StrategyEntry:
    """Create a minimal StrategyEntry without BarPipeline, bypassing on_init."""
    engine = MagicMock()
    entry = StrategyEntry(
        strategy_engine=engine,
        strategy_name="test",
        vt_symbols=["TEST.LOCAL"],
        setting={},
    )
    entry.target_aggregate = None
    entry.warming_up = True
    entry.auto_save_service = None
    entry.bar_pipeline = None
    return entry


# ═══════════════════════════════════════════════════════════════════
#  Property 1: 直通路径恒等传递
#  Feature: bar-generator-decoupling, Property 1: 直通路径恒等传递
#  **Validates: Requirements 1.1**
# ═══════════════════════════════════════════════════════════════════

class TestPassthroughIdentityProperty:
    """
    For any bars dict, when StrategyEntry has no BarPipeline,
    on_bars() passes the EXACT SAME object to _process_bars().

    Feature: bar-generator-decoupling, Property 1: 直通路径恒等传递
    **Validates: Requirements 1.1**
    """

    @given(bars=st_bars_dict())
    @settings(max_examples=100)
    def test_on_bars_passes_identical_object_to_process_bars(self, bars: dict) -> None:
        """_process_bars receives the exact same bars object (identity check)."""
        entry = _make_entry()
        received = []
        entry._process_bars = lambda b: received.append(b)

        entry.on_bars(bars)

        assert len(received) == 1
        assert received[0] is bars
