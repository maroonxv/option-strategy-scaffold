"""
Tests for StrategyEntry bar pipeline integration — 单元测试

Feature: bar-generator-decoupling

Validates: Requirements 1.1, 1.2, 1.3, 3.1, 3.2, 3.3, 3.4, 4.1
"""

import sys
from unittest.mock import MagicMock

import pytest

# ── Mock vnpy ecosystem ──
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
# We must NOT mock parent packages (src.strategy, src.strategy.infrastructure, etc.)
# because real sub-packages (bar_pipeline) live there.
# Instead, mock only the leaf modules that strategy_entry.py imports from.
_leaf_mods = [
    # domain aggregates
    "src.strategy.domain.aggregate.target_instrument_aggregate",
    "src.strategy.domain.aggregate.position_aggregate",
    # domain services
    "src.strategy.domain.domain_service.indicator_service",
    "src.strategy.domain.domain_service.signal_service",
    "src.strategy.domain.domain_service.position_sizing_service",
    "src.strategy.domain.domain_service.option_selector_service",
    "src.strategy.domain.domain_service.future_selection_service",
    "src.strategy.domain.domain_service.greeks_calculator",
    "src.strategy.domain.domain_service.portfolio_risk_aggregator",
    "src.strategy.domain.domain_service.smart_order_executor",
    # domain entity / event / value_object
    "src.strategy.domain.entity.position",
    "src.strategy.domain.event.event_types",
    "src.strategy.domain.value_object.risk",
    "src.strategy.domain.value_object.order_execution",
    # infrastructure gateways
    "src.strategy.infrastructure.gateway.vnpy_market_data_gateway",
    "src.strategy.infrastructure.gateway.vnpy_account_gateway",
    "src.strategy.infrastructure.gateway.vnpy_trade_execution_gateway",
    # infrastructure misc
    "src.strategy.infrastructure.reporting.feishu_handler",
    "src.strategy.infrastructure.logging.logging_utils",
    "src.strategy.infrastructure.monitoring.strategy_monitor",
    # infrastructure persistence
    "src.strategy.infrastructure.persistence.state_repository",
    "src.strategy.infrastructure.persistence.json_serializer",
    "src.strategy.infrastructure.persistence.migration_chain",
    "src.strategy.infrastructure.persistence.auto_save_service",
    "src.strategy.infrastructure.persistence.exceptions",
    "src.strategy.infrastructure.persistence.history_data_repository",
    # infrastructure utils
    "src.strategy.infrastructure.utils.contract_helper",
]
for _mod in _leaf_mods:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Now import StrategyEntry — all heavy deps are mocked
from src.strategy.strategy_entry import StrategyEntry


def _make_entry(setting: dict | None = None) -> StrategyEntry:
    """Create a minimal StrategyEntry with mocked engine, bypassing on_init."""
    engine = MagicMock()
    entry = StrategyEntry(
        strategy_engine=engine,
        strategy_name="test",
        vt_symbols=["TEST.LOCAL"],
        setting=setting or {},
    )
    # Ensure minimal state so on_bars doesn't blow up
    entry.target_aggregate = None
    entry.warming_up = True  # skip rollover / universe checks
    entry.auto_save_service = None
    return entry


# ═══════════════════════════════════════════════════════════════════
#  Test 1: 参数隔离 — Validates: Requirements 4.1
# ═══════════════════════════════════════════════════════════════════

class TestParameterIsolation:
    """bar_window / bar_interval 不在策略级 parameters 列表中。"""

    def test_bar_window_not_in_parameters(self):
        assert "bar_window" not in StrategyEntry.parameters

    def test_bar_interval_not_in_parameters(self):
        assert "bar_interval" not in StrategyEntry.parameters


# ═══════════════════════════════════════════════════════════════════
#  Test 2 & 3: 无 bar_window 时直通 — Validates: Requirements 1.1, 1.2
# ═══════════════════════════════════════════════════════════════════

class TestNoPipelinePassthrough:
    """未配置 bar_window 时，on_bars 直接调用 _process_bars。"""

    def test_on_bars_calls_process_bars_directly(self):
        """无 bar_window → on_bars 直接调用 _process_bars(bars)。"""
        entry = _make_entry(setting={})
        entry.bar_pipeline = None
        entry._process_bars = MagicMock()

        bars = {"SYM.LOCAL": MagicMock()}
        entry.on_bars(bars)

        entry._process_bars.assert_called_once_with(bars)

    def test_on_bars_with_bar_window_zero(self):
        """bar_window=0 → on_bars 直接调用 _process_bars(bars)。"""
        entry = _make_entry(setting={"bar_window": 0})
        entry.bar_pipeline = None
        entry._process_bars = MagicMock()

        bars = {"SYM.LOCAL": MagicMock()}
        entry.on_bars(bars)

        entry._process_bars.assert_called_once_with(bars)

    def test_bar_pipeline_is_none_without_bar_window(self):
        """未配置 bar_window 时 bar_pipeline 应为 None。"""
        entry = _make_entry(setting={})
        assert entry.bar_pipeline is None

    def test_bar_pipeline_is_none_with_bar_window_zero(self):
        """bar_window=0 时 bar_pipeline 应为 None。"""
        entry = _make_entry(setting={"bar_window": 0})
        assert entry.bar_pipeline is None


# ═══════════════════════════════════════════════════════════════════
#  Test 4: 有 bar_window 时委托 — Validates: Requirements 3.1, 3.2
# ═══════════════════════════════════════════════════════════════════

class TestPipelineDelegation:
    """配置了 bar_window 时，on_bars 委托给 bar_pipeline.handle_bars。"""

    def test_on_bars_delegates_to_bar_pipeline(self):
        entry = _make_entry(setting={"bar_window": 15})
        mock_pipeline = MagicMock()
        entry.bar_pipeline = mock_pipeline
        entry._process_bars = MagicMock()

        bars = {"SYM.LOCAL": MagicMock()}
        entry.on_bars(bars)

        mock_pipeline.handle_bars.assert_called_once_with(bars)
        entry._process_bars.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
#  Test 5: 有 bar_window 时 on_tick 委托 — Validates: Requirements 3.3
# ═══════════════════════════════════════════════════════════════════

class TestOnTickWithPipeline:
    """配置了 BarPipeline 时，on_tick 委托给 bar_pipeline.handle_tick。"""

    def test_on_tick_delegates_to_bar_pipeline(self):
        entry = _make_entry(setting={"bar_window": 15})
        mock_pipeline = MagicMock()
        entry.bar_pipeline = mock_pipeline

        tick = MagicMock()
        entry.on_tick(tick)

        mock_pipeline.handle_tick.assert_called_once_with(tick)


# ═══════════════════════════════════════════════════════════════════
#  Test 6: 无 bar_window 时 on_tick 无操作 — Validates: Requirements 1.3
# ═══════════════════════════════════════════════════════════════════

class TestOnTickWithoutPipeline:
    """未配置 BarPipeline 时，on_tick 不做任何K线相关处理。"""

    def test_on_tick_does_nothing_without_pipeline(self):
        entry = _make_entry(setting={})
        entry.bar_pipeline = None
        entry._process_bars = MagicMock()

        tick = MagicMock()
        entry.on_tick(tick)

        entry._process_bars.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
#  Test 7: on_window_bars 不存在 — Validates: Requirements 3.4
# ═══════════════════════════════════════════════════════════════════

class TestOnWindowBarsRemoved:
    """StrategyEntry 不再有 on_window_bars 方法。"""

    def test_on_window_bars_not_defined(self):
        entry = _make_entry(setting={})
        assert not hasattr(entry, "on_window_bars")
