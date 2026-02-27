"""
domain_service_config_loader.py - 领域服务 TOML 配置加载器

从 config/domain_service/ 目录下的 TOML 文件加载领域服务配置，
并转换为对应的配置值对象。
"""
import tomllib
from pathlib import Path
from typing import Optional

from src.strategy.domain.value_object.config.position_sizing_config import PositionSizingConfig
from src.strategy.domain.value_object.config.pricing_engine_config import PricingEngineConfig
from src.strategy.domain.value_object.config.future_selector_config import FutureSelectorConfig
from src.strategy.domain.value_object.selection.option_selector_config import OptionSelectorConfig
from src.strategy.domain.value_object.pricing.pricing import PricingModel


# 项目根目录 (从 src/main/config/ 向上 3 级)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DOMAIN_SERVICE_CONFIG_DIR = _PROJECT_ROOT / "config" / "domain_service"


def _load_toml(path: Path) -> dict:
    """加载 TOML 文件，文件不存在时返回空字典"""
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_position_sizing_config(
    overrides: Optional[dict] = None,
) -> PositionSizingConfig:
    """
    加载仓位管理配置

    优先级: overrides > TOML 文件 > dataclass 默认值

    Args:
        overrides: 运行时覆盖值 (如来自 strategy_config.yaml 的 position_sizing 节)
    """
    data = _load_toml(_DOMAIN_SERVICE_CONFIG_DIR / "risk" / "position_sizing.toml")
    overrides = overrides or {}

    pos_limit = data.get("position_limit", {})
    margin = data.get("margin", {})
    order = data.get("order", {})

    kwargs = {}

    # position_limit
    if "max_positions" in overrides:
        kwargs["max_positions"] = overrides["max_positions"]
    elif "max_positions" in pos_limit:
        kwargs["max_positions"] = pos_limit["max_positions"]

    if "global_daily_limit" in overrides:
        kwargs["global_daily_limit"] = overrides["global_daily_limit"]
    elif "global_daily_limit" in pos_limit:
        kwargs["global_daily_limit"] = pos_limit["global_daily_limit"]

    if "contract_daily_limit" in overrides:
        kwargs["contract_daily_limit"] = overrides["contract_daily_limit"]
    elif "contract_daily_limit" in pos_limit:
        kwargs["contract_daily_limit"] = pos_limit["contract_daily_limit"]

    # margin
    if "margin_ratio" in overrides:
        kwargs["margin_ratio"] = overrides["margin_ratio"]
    elif "ratio" in margin:
        kwargs["margin_ratio"] = margin["ratio"]

    if "min_margin_ratio" in overrides:
        kwargs["min_margin_ratio"] = overrides["min_margin_ratio"]
    elif "min_ratio" in margin:
        kwargs["min_margin_ratio"] = margin["min_ratio"]

    if "margin_usage_limit" in overrides:
        kwargs["margin_usage_limit"] = overrides["margin_usage_limit"]
    elif "usage_limit" in margin:
        kwargs["margin_usage_limit"] = margin["usage_limit"]

    # order
    if "max_volume_per_order" in overrides:
        kwargs["max_volume_per_order"] = overrides["max_volume_per_order"]
    elif "max_volume_per_order" in order:
        kwargs["max_volume_per_order"] = order["max_volume_per_order"]

    return PositionSizingConfig(**kwargs)


def load_pricing_engine_config(
    overrides: Optional[dict] = None,
) -> PricingEngineConfig:
    """
    加载定价引擎配置

    优先级: overrides > TOML 文件 > dataclass 默认值
    """
    data = _load_toml(_DOMAIN_SERVICE_CONFIG_DIR / "pricing" / "pricing_engine.toml")
    overrides = overrides or {}

    american = data.get("american", {})
    crr = data.get("crr", {})

    kwargs = {}

    # american_model
    if "american_model" in overrides:
        kwargs["american_model"] = overrides["american_model"]
    elif "model" in american:
        model_str = american["model"].upper()
        kwargs["american_model"] = PricingModel[model_str]

    # crr_steps
    if "crr_steps" in overrides:
        kwargs["crr_steps"] = overrides["crr_steps"]
    elif "steps" in crr:
        kwargs["crr_steps"] = crr["steps"]

    return PricingEngineConfig(**kwargs)


def load_future_selector_config(
    overrides: Optional[dict] = None,
) -> FutureSelectorConfig:
    """
    加载期货选择器配置

    优先级: overrides > TOML 文件 > dataclass 默认值
    """
    data = _load_toml(_DOMAIN_SERVICE_CONFIG_DIR / "selection" / "future_selector.toml")
    overrides = overrides or {}

    dominant = data.get("dominant", {})
    rollover = data.get("rollover", {})

    kwargs = {}

    if "volume_weight" in overrides:
        kwargs["volume_weight"] = overrides["volume_weight"]
    elif "volume_weight" in dominant:
        kwargs["volume_weight"] = dominant["volume_weight"]

    if "oi_weight" in overrides:
        kwargs["oi_weight"] = overrides["oi_weight"]
    elif "oi_weight" in dominant:
        kwargs["oi_weight"] = dominant["oi_weight"]

    if "rollover_days" in overrides:
        kwargs["rollover_days"] = overrides["rollover_days"]
    elif "days" in rollover:
        kwargs["rollover_days"] = rollover["days"]

    return FutureSelectorConfig(**kwargs)


def load_option_selector_config(
    overrides: Optional[dict] = None,
) -> OptionSelectorConfig:
    """
    加载期权选择服务配置

    优先级: overrides > TOML 文件 > dataclass 默认值
    """
    data = _load_toml(_DOMAIN_SERVICE_CONFIG_DIR / "selection" / "option_selector.toml")
    overrides = overrides or {}

    flt = data.get("filter", {})
    liq = data.get("liquidity", {})
    sw = data.get("score_weight", {})
    liq_detail = sw.get("liquidity_detail", {})
    delta = data.get("delta", {})
    spread = data.get("spread", {})

    kwargs = {}

    # filter
    _map_field(kwargs, "strike_level", overrides, "strike_level", flt, "strike_level")
    _map_field(kwargs, "min_bid_price", overrides, "min_bid_price", flt, "min_bid_price")
    _map_field(kwargs, "min_bid_volume", overrides, "min_bid_volume", flt, "min_bid_volume")
    _map_field(kwargs, "min_trading_days", overrides, "min_trading_days", flt, "min_trading_days")
    _map_field(kwargs, "max_trading_days", overrides, "max_trading_days", flt, "max_trading_days")

    # liquidity
    _map_field(kwargs, "liquidity_min_volume", overrides, "liquidity_min_volume", liq, "min_volume")
    _map_field(kwargs, "liquidity_min_bid_volume", overrides, "liquidity_min_bid_volume", liq, "min_bid_volume")
    _map_field(kwargs, "liquidity_max_spread_ticks", overrides, "liquidity_max_spread_ticks", liq, "max_spread_ticks")

    # score_weight
    _map_field(kwargs, "score_liquidity_weight", overrides, "score_liquidity_weight", sw, "liquidity_weight")
    _map_field(kwargs, "score_otm_weight", overrides, "score_otm_weight", sw, "otm_weight")
    _map_field(kwargs, "score_expiry_weight", overrides, "score_expiry_weight", sw, "expiry_weight")

    # liquidity detail
    _map_field(kwargs, "liq_spread_weight", overrides, "liq_spread_weight", liq_detail, "spread_weight")
    _map_field(kwargs, "liq_volume_weight", overrides, "liq_volume_weight", liq_detail, "volume_weight")

    # delta
    _map_field(kwargs, "delta_tolerance", overrides, "delta_tolerance", delta, "tolerance")

    # spread
    _map_field(kwargs, "default_spread_width", overrides, "default_spread_width", spread, "default_width")

    return OptionSelectorConfig(**kwargs)


def _map_field(
    kwargs: dict,
    config_key: str,
    overrides: dict,
    override_key: str,
    toml_section: dict,
    toml_key: str,
) -> None:
    """辅助: 按优先级填充字段 (overrides > toml > 默认值)"""
    if override_key in overrides:
        kwargs[config_key] = overrides[override_key]
    elif toml_key in toml_section:
        kwargs[config_key] = toml_section[toml_key]
