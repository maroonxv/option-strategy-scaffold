"""
配置加载与默认值回退单元测试

验证 YAML 配置解析和缺失配置时的默认值行为。
"""
import os
import yaml
import tempfile
import pytest

from src.strategy.domain.value_object.risk.risk import RiskThresholds
from src.strategy.domain.value_object.trading.order_execution import OrderExecutionConfig


def _load_config(yaml_content: str) -> dict:
    """辅助: 从 YAML 字符串加载配置"""
    return yaml.safe_load(yaml_content) or {}


def _build_risk_thresholds(config: dict) -> RiskThresholds:
    """从配置字典构建 RiskThresholds，缺失时使用默认值"""
    greeks_risk_cfg = config.get("greeks_risk", {})
    pos = greeks_risk_cfg.get("position_limits", {})
    port = greeks_risk_cfg.get("portfolio_limits", {})
    return RiskThresholds(
        position_delta_limit=pos.get("delta", 0.8),
        position_gamma_limit=pos.get("gamma", 0.1),
        position_vega_limit=pos.get("vega", 50.0),
        portfolio_delta_limit=port.get("delta", 5.0),
        portfolio_gamma_limit=port.get("gamma", 1.0),
        portfolio_vega_limit=port.get("vega", 500.0),
    )


def _build_order_config(config: dict) -> OrderExecutionConfig:
    """从配置字典构建 OrderExecutionConfig，缺失时使用默认值"""
    oe = config.get("order_execution", {})
    return OrderExecutionConfig(
        timeout_seconds=oe.get("timeout_seconds", 30),
        max_retries=oe.get("max_retries", 3),
        slippage_ticks=oe.get("slippage_ticks", 2),
    )


class TestConfigIntegration:

    def test_full_config_parsing(self):
        """完整配置正确解析"""
        yaml_str = """
greeks_risk:
  risk_free_rate: 0.03
  position_limits:
    delta: 0.9
    gamma: 0.2
    vega: 60.0
  portfolio_limits:
    delta: 6.0
    gamma: 2.0
    vega: 600.0
order_execution:
  timeout_seconds: 45
  max_retries: 5
  slippage_ticks: 3
"""
        config = _load_config(yaml_str)
        thresholds = _build_risk_thresholds(config)
        order_cfg = _build_order_config(config)

        assert thresholds.position_delta_limit == 0.9
        assert thresholds.position_gamma_limit == 0.2
        assert thresholds.position_vega_limit == 60.0
        assert thresholds.portfolio_delta_limit == 6.0
        assert thresholds.portfolio_gamma_limit == 2.0
        assert thresholds.portfolio_vega_limit == 600.0
        assert order_cfg.timeout_seconds == 45
        assert order_cfg.max_retries == 5
        assert order_cfg.slippage_ticks == 3

    def test_missing_greeks_risk_uses_defaults(self):
        """缺少 greeks_risk 节时使用默认值"""
        config = _load_config("order_execution:\n  timeout_seconds: 10\n")
        thresholds = _build_risk_thresholds(config)

        assert thresholds.position_delta_limit == 0.8
        assert thresholds.position_gamma_limit == 0.1
        assert thresholds.position_vega_limit == 50.0
        assert thresholds.portfolio_delta_limit == 5.0

    def test_missing_order_execution_uses_defaults(self):
        """缺少 order_execution 节时使用默认值"""
        config = _load_config("")
        order_cfg = _build_order_config(config)

        assert order_cfg.timeout_seconds == 30
        assert order_cfg.max_retries == 3
        assert order_cfg.slippage_ticks == 2

    def test_partial_config_fills_defaults(self):
        """部分配置时，缺失字段使用默认值"""
        yaml_str = """
greeks_risk:
  position_limits:
    delta: 0.5
order_execution:
  timeout_seconds: 60
"""
        config = _load_config(yaml_str)
        thresholds = _build_risk_thresholds(config)
        order_cfg = _build_order_config(config)

        assert thresholds.position_delta_limit == 0.5
        assert thresholds.position_gamma_limit == 0.1  # default
        assert thresholds.position_vega_limit == 50.0  # default
        assert order_cfg.timeout_seconds == 60
        assert order_cfg.max_retries == 3  # default

    def test_actual_config_file_parseable(self):
        """验证实际的 strategy_config.toml 可以正确解析"""
        config_path = os.path.join("config", "strategy_config.toml")
        if not os.path.exists(config_path):
            pytest.skip("config/strategy_config.toml not found")

        with open(config_path, "rb") as f:
            config = tomllib.load(f)

        thresholds = _build_risk_thresholds(config)
        order_cfg = _build_order_config(config)

        # 验证配置文件中的值
        assert thresholds.position_delta_limit == 0.8
        assert thresholds.portfolio_delta_limit == 5.0
        assert order_cfg.timeout_seconds == 30
        assert order_cfg.max_retries == 3


import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("config_loader", "src/main/config/config_loader.py")
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
ConfigLoader = _mod.ConfigLoader


class TestHedgingConfigIntegration:
    """对冲和高级订单配置加载测试"""

    def test_full_hedging_config(self):
        """完整对冲配置正确解析"""
        yaml_str = """
hedging:
  delta_hedging:
    target_delta: 1.0
    hedging_band: 0.8
    hedge_instrument_vt_symbol: "IF2506.CFFEX"
    hedge_instrument_delta: 1.0
    hedge_instrument_multiplier: 300.0
  gamma_scalping:
    rebalance_threshold: 0.5
    hedge_instrument_vt_symbol: "IF2506.CFFEX"
    hedge_instrument_delta: 1.0
    hedge_instrument_multiplier: 300.0
"""
        config = _load_config(yaml_str)
        hedging = ConfigLoader.load_hedging_config(config)

        assert hedging["delta_hedging"]["target_delta"] == 1.0
        assert hedging["delta_hedging"]["hedging_band"] == 0.8
        assert hedging["delta_hedging"]["hedge_instrument_multiplier"] == 300.0
        assert hedging["gamma_scalping"]["rebalance_threshold"] == 0.5

    def test_missing_hedging_uses_defaults(self):
        """缺少 hedging 节时使用默认值"""
        config = _load_config("")
        hedging = ConfigLoader.load_hedging_config(config)

        assert hedging["delta_hedging"]["target_delta"] == 0.0
        assert hedging["delta_hedging"]["hedging_band"] == 0.5
        assert hedging["delta_hedging"]["hedge_instrument_multiplier"] == 10.0
        assert hedging["gamma_scalping"]["rebalance_threshold"] == 0.3

    def test_partial_hedging_fills_defaults(self):
        """部分对冲配置时，缺失字段使用默认值"""
        yaml_str = """
hedging:
  delta_hedging:
    target_delta: 2.0
"""
        config = _load_config(yaml_str)
        hedging = ConfigLoader.load_hedging_config(config)

        assert hedging["delta_hedging"]["target_delta"] == 2.0
        assert hedging["delta_hedging"]["hedging_band"] == 0.5  # default
        assert hedging["gamma_scalping"]["rebalance_threshold"] == 0.3  # default

    def test_full_advanced_orders_config(self):
        """完整高级订单配置正确解析"""
        yaml_str = """
advanced_orders:
  default_iceberg_batch_size: 10
  default_twap_slices: 20
  default_time_window_seconds: 600
"""
        config = _load_config(yaml_str)
        ao = ConfigLoader.load_advanced_orders_config(config)

        assert ao["default_iceberg_batch_size"] == 10
        assert ao["default_twap_slices"] == 20
        assert ao["default_time_window_seconds"] == 600

    def test_missing_advanced_orders_uses_defaults(self):
        """缺少 advanced_orders 节时使用默认值"""
        config = _load_config("")
        ao = ConfigLoader.load_advanced_orders_config(config)

        assert ao["default_iceberg_batch_size"] == 5
        assert ao["default_twap_slices"] == 10
        assert ao["default_time_window_seconds"] == 300

    def test_actual_config_file_hedging(self):
        """验证实际的 strategy_config.toml 中的对冲配置"""
        config_path = os.path.join("config", "strategy_config.toml")
        if not os.path.exists(config_path):
            pytest.skip("config/strategy_config.toml not found")

        with open(config_path, "rb") as f:
            config = tomllib.load(f)

        hedging = ConfigLoader.load_hedging_config(config)
        ao = ConfigLoader.load_advanced_orders_config(config)

        assert hedging["delta_hedging"]["target_delta"] == 0.0
        assert hedging["delta_hedging"]["hedging_band"] == 0.5
        assert hedging["gamma_scalping"]["rebalance_threshold"] == 0.3
        assert ao["default_iceberg_batch_size"] == 5
        assert ao["default_twap_slices"] == 10


class TestCombinationRiskConfigIntegration:
    """组合策略风控配置加载测试"""

    def test_full_combination_risk_config(self):
        """完整组合风控配置正确解析"""
        yaml_str = """
combination_risk:
  delta_limit: 3.0
  gamma_limit: 0.8
  vega_limit: 300.0
"""
        config = _load_config(yaml_str)
        risk_config = ConfigLoader.load_combination_risk_config(config)

        assert risk_config.delta_limit == 3.0
        assert risk_config.gamma_limit == 0.8
        assert risk_config.vega_limit == 300.0

    def test_missing_combination_risk_uses_defaults(self):
        """缺少 combination_risk 节时使用默认值"""
        config = _load_config("")
        risk_config = ConfigLoader.load_combination_risk_config(config)

        assert risk_config.delta_limit == 2.0
        assert risk_config.gamma_limit == 0.5
        assert risk_config.vega_limit == 200.0

    def test_partial_combination_risk_fills_defaults(self):
        """部分组合风控配置时，缺失字段使用默认值"""
        yaml_str = """
combination_risk:
  delta_limit: 5.0
"""
        config = _load_config(yaml_str)
        risk_config = ConfigLoader.load_combination_risk_config(config)

        assert risk_config.delta_limit == 5.0
        assert risk_config.gamma_limit == 0.5  # default
        assert risk_config.vega_limit == 200.0  # default

    def test_actual_config_file_combination_risk(self):
        """验证实际的 strategy_config.toml 中的组合风控配置"""
        config_path = os.path.join("config", "strategy_config.toml")
        if not os.path.exists(config_path):
            pytest.skip("config/strategy_config.toml not found")

        with open(config_path, "rb") as f:
            config = tomllib.load(f)

        risk_config = ConfigLoader.load_combination_risk_config(config)

        # 验证配置文件中的值
        assert risk_config.delta_limit == 2.0
        assert risk_config.gamma_limit == 0.5
        assert risk_config.vega_limit == 200.0

    def test_combination_risk_config_returns_frozen_dataclass(self):
        """验证返回的是 CombinationRiskConfig 实例（frozen dataclass）"""
        from src.strategy.domain.value_object.combination import CombinationRiskConfig

        config = _load_config("")
        risk_config = ConfigLoader.load_combination_risk_config(config)

        assert isinstance(risk_config, CombinationRiskConfig)
        # 验证是 frozen dataclass（不可变）
        with pytest.raises(AttributeError):
            risk_config.delta_limit = 10.0
