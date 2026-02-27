"""
tests for src/backtesting/config.py
静态配置数据完整性 + BacktestConfig 数据类行为
"""

import argparse
from datetime import date

from src.backtesting.config import (
    EXCHANGE_MAP,
    FUTURE_OPTION_MAP,
    OPTION_FUTURE_MAP,
    PRODUCT_SPECS,
    DEFAULT_PRODUCT_SPEC,
    MANUAL_EXPIRY_CONFIG,
    BacktestConfig,
)


# ---------------------------------------------------------------------------
# 静态配置数据测试
# ---------------------------------------------------------------------------

class TestStaticConfig:
    """验证从 vt_symbol_generator.py 提取的静态数据完整性。"""

    def test_exchange_map_contains_all_exchanges(self):
        exchanges = set(EXCHANGE_MAP.values())
        assert exchanges == {"SHFE", "CZCE", "DCE", "CFFEX", "INE"}

    def test_exchange_map_shfe_samples(self):
        for code in ("ag", "rb", "cu", "au", "hc"):
            assert EXCHANGE_MAP[code] == "SHFE"

    def test_exchange_map_czce_samples(self):
        for code in ("FG", "SA", "MA", "AP"):
            assert EXCHANGE_MAP[code] == "CZCE"

    def test_exchange_map_dce_samples(self):
        for code in ("m", "i", "jd", "pp"):
            assert EXCHANGE_MAP[code] == "DCE"

    def test_exchange_map_cffex_samples(self):
        for code in ("IF", "IH", "IC", "IM", "IO", "HO", "MO"):
            assert EXCHANGE_MAP[code] == "CFFEX"

    def test_exchange_map_ine_samples(self):
        for code in ("sc", "lu", "nr", "bc"):
            assert EXCHANGE_MAP[code] == "INE"

    def test_future_option_map(self):
        assert FUTURE_OPTION_MAP == {"IF": "IO", "IM": "MO", "IH": "HO"}

    def test_option_future_map_is_reverse(self):
        assert OPTION_FUTURE_MAP == {"IO": "IF", "MO": "IM", "HO": "IH"}

    def test_product_specs_known_products(self):
        assert PRODUCT_SPECS["IF"] == (300, 0.2)
        assert PRODUCT_SPECS["rb"] == (10, 1.0)
        assert PRODUCT_SPECS["au"] == (1000, 0.02)
        assert PRODUCT_SPECS["i"] == (100, 0.5)

    def test_default_product_spec(self):
        assert DEFAULT_PRODUCT_SPEC == (10, 1.0)

    def test_manual_expiry_config_initially_empty(self):
        assert MANUAL_EXPIRY_CONFIG == {}


# ---------------------------------------------------------------------------
# BacktestConfig 测试
# ---------------------------------------------------------------------------

class TestBacktestConfig:
    """验证 BacktestConfig 数据类行为。"""

    def test_defaults(self):
        cfg = BacktestConfig()
        assert cfg.config_path == "config/strategy_config.toml"
        assert cfg.start_date is None
        assert cfg.end_date is None
        assert cfg.capital == 1_000_000
        assert cfg.rate == 2.5e-5
        assert cfg.slippage == 0.2
        assert cfg.default_size == 10
        assert cfg.default_pricetick == 1.0
        assert cfg.show_chart is True

    def test_no_hardcoded_dates(self):
        """Req 8.5: 不包含任何硬编码日期值。"""
        cfg = BacktestConfig()
        assert cfg.start_date is None
        assert cfg.end_date is None

    def test_get_end_date_defaults_to_today(self):
        """Req 8.2: 未指定结束日期时默认使用当前日期。"""
        cfg = BacktestConfig()
        assert cfg.get_end_date() == date.today().strftime("%Y-%m-%d")

    def test_get_end_date_returns_explicit_value(self):
        cfg = BacktestConfig(end_date="2025-06-01")
        assert cfg.get_end_date() == "2025-06-01"

    def test_from_args_full_override(self):
        """Req 8.4: CLI 参数覆盖默认值。"""
        args = argparse.Namespace(
            config="custom.yaml",
            start="2025-01-01",
            end="2025-06-30",
            capital=500_000,
            rate=1e-4,
            slippage=0.5,
            size=100,
            pricetick=0.1,
            no_chart=True,
        )
        cfg = BacktestConfig.from_args(args)
        assert cfg.config_path == "custom.yaml"
        assert cfg.start_date == "2025-01-01"
        assert cfg.end_date == "2025-06-30"
        assert cfg.capital == 500_000
        assert cfg.rate == 1e-4
        assert cfg.slippage == 0.5
        assert cfg.default_size == 100
        assert cfg.default_pricetick == 0.1
        assert cfg.show_chart is False

    def test_from_args_none_preserves_defaults(self):
        """Req 8.4: CLI 参数为 None 时保留默认值。"""
        args = argparse.Namespace(
            config=None,
            start=None,
            end=None,
            capital=None,
            rate=None,
            slippage=None,
            size=None,
            pricetick=None,
            no_chart=None,
        )
        cfg = BacktestConfig.from_args(args)
        default = BacktestConfig()
        assert cfg.config_path == default.config_path
        assert cfg.start_date == default.start_date
        assert cfg.end_date == default.end_date
        assert cfg.capital == default.capital
        assert cfg.rate == default.rate
        assert cfg.slippage == default.slippage
        assert cfg.default_size == default.default_size
        assert cfg.default_pricetick == default.default_pricetick
        assert cfg.show_chart == default.show_chart

    def test_from_args_partial_override(self):
        """部分 CLI 参数覆盖，其余保留默认。"""
        args = argparse.Namespace(
            config=None,
            start="2025-03-01",
            end=None,
            capital=2_000_000,
            rate=None,
            slippage=None,
            size=None,
            pricetick=None,
            no_chart=None,
        )
        cfg = BacktestConfig.from_args(args)
        assert cfg.start_date == "2025-03-01"
        assert cfg.capital == 2_000_000
        # 其余保持默认
        assert cfg.config_path == "config/strategy_config.toml"
        assert cfg.rate == 2.5e-5

    def test_from_args_missing_attrs_uses_defaults(self):
        """args 对象缺少某些属性时不报错，保留默认值。"""
        args = argparse.Namespace(start="2025-05-01")
        cfg = BacktestConfig.from_args(args)
        assert cfg.start_date == "2025-05-01"
        assert cfg.config_path == "config/strategy_config.toml"
        assert cfg.show_chart is True
