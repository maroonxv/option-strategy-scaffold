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


# ═══════════════════════════════════════════════════════════════════
#  Property 2: 直通路径忽略 tick
#  Feature: bar-generator-decoupling, Property 2: 直通路径忽略 tick
#  **Validates: Requirements 1.3**
# ═══════════════════════════════════════════════════════════════════

class TestPassthroughIgnoresTickProperty:
    """
    For any tick data, when StrategyEntry has no BarPipeline,
    on_tick() does nothing — _process_bars is never called and
    no bar-related side effects occur.

    Feature: bar-generator-decoupling, Property 2: 直通路径忽略 tick
    **Validates: Requirements 1.3**
    """

    @given(tick=st.builds(MagicMock))
    @settings(max_examples=100)
    def test_on_tick_does_not_call_process_bars(self, tick: object) -> None:
        """on_tick with no BarPipeline must never invoke _process_bars."""
        entry = _make_entry()
        entry._process_bars = MagicMock()

        entry.on_tick(tick)

        entry._process_bars.assert_not_called()

    @given(tick=st.builds(MagicMock))
    @settings(max_examples=100)
    def test_on_tick_does_not_set_bar_pipeline(self, tick: object) -> None:
        """on_tick must not create or assign a bar_pipeline as a side effect."""
        entry = _make_entry()
        assert entry.bar_pipeline is None

        entry.on_tick(tick)

        assert entry.bar_pipeline is None


# ── Import BarPipeline for Property 3 ──
from src.strategy.infrastructure.bar_pipeline import BarPipeline


# ── Helper: mirrors on_init BarPipeline creation logic ──

def create_bar_pipeline_from_setting(setting: dict):
    """Mirrors the BarPipeline creation logic from StrategyEntry.on_init.

    The real on_init does:
        bar_window = int(self.setting.get("bar_window", 0))
        if bar_window > 0: ... create BarPipeline ...

    int(None) raises TypeError, so we wrap in try/except to handle
    None and other non-integer-convertible values gracefully.
    """
    try:
        bar_window = int(setting.get("bar_window", 0))
    except (TypeError, ValueError):
        bar_window = 0

    if bar_window > 0:
        bar_interval_str = setting.get("bar_interval", "MINUTE")
        interval_map = {
            "MINUTE": mock_interval.MINUTE,
            "HOUR": mock_interval.HOUR,
            "DAILY": mock_interval.DAILY,
        }
        interval = interval_map.get(bar_interval_str, mock_interval.MINUTE)
        return BarPipeline(
            bar_callback=lambda bars: None,
            window=bar_window,
            interval=interval,
        )
    return None


# ═══════════════════════════════════════════════════════════════════
#  Property 3: BarPipeline 创建条件
#  Feature: bar-generator-decoupling, Property 3: BarPipeline 创建条件
#  **Validates: Requirements 3.1, 1.2**
# ═══════════════════════════════════════════════════════════════════

class TestBarPipelineCreationConditionProperty:
    """
    For any setting dict, when bar_window is a positive integer,
    create_bar_pipeline_from_setting returns a BarPipeline instance;
    when bar_window is 0, negative, None, or missing, it returns None.

    Feature: bar-generator-decoupling, Property 3: BarPipeline 创建条件
    **Validates: Requirements 3.1, 1.2**
    """

    @given(
        bar_window=st.one_of(st.none(), st.integers()),
        bar_interval=st.sampled_from(["MINUTE", "HOUR", "DAILY", "INVALID", ""]),
    )
    @settings(max_examples=200)
    def test_positive_window_creates_pipeline_otherwise_none(
        self, bar_window, bar_interval: str,
    ) -> None:
        """bar_window > 0 → BarPipeline instance; else → None."""
        setting = {"bar_interval": bar_interval}
        if bar_window is not None:
            setting["bar_window"] = bar_window

        result = create_bar_pipeline_from_setting(setting)

        if isinstance(bar_window, int) and bar_window > 0:
            assert isinstance(result, BarPipeline), (
                f"Expected BarPipeline for bar_window={bar_window}, got {result}"
            )
        else:
            assert result is None, (
                f"Expected None for bar_window={bar_window}, got {result}"
            )
