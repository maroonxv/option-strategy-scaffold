"""
回测配置模块

集中存放交易所映射、品种规格等静态配置数据，以及回测参数数据类。
"""

import argparse
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# 静态配置数据（从 vt_symbol_generator.py 提取）
# ---------------------------------------------------------------------------

# 手动指定到期日配置
# 格式: {"IF2501": date(2025, 1, 17), ...}
MANUAL_EXPIRY_CONFIG: Dict[str, date] = {}

# 交易所映射: 品种代码 -> 交易所代码
EXCHANGE_MAP: Dict[str, str] = {
    # SHFE
    "ag": "SHFE", "rb": "SHFE", "ao": "SHFE", "cu": "SHFE", "al": "SHFE",
    "zn": "SHFE", "au": "SHFE", "ru": "SHFE", "sn": "SHFE", "ni": "SHFE",
    "bu": "SHFE", "sp": "SHFE", "fu": "SHFE", "br": "SHFE", "pb": "SHFE",
    "ss": "SHFE", "hc": "SHFE", "wr": "SHFE",
    # CZCE
    "FG": "CZCE", "SA": "CZCE", "MA": "CZCE", "SR": "CZCE", "TA": "CZCE",
    "RM": "CZCE", "CF": "CZCE", "OI": "CZCE", "PK": "CZCE", "SF": "CZCE",
    "SM": "CZCE", "PX": "CZCE", "UR": "CZCE", "CJ": "CZCE", "AP": "CZCE",
    # DCE
    "m": "DCE", "i": "DCE", "p": "DCE", "y": "DCE", "c": "DCE", "jd": "DCE",
    "a": "DCE", "b": "DCE", "pp": "DCE", "l": "DCE", "v": "DCE", "eg": "DCE",
    "eb": "DCE", "pg": "DCE", "lh": "DCE", "si": "DCE",
    # CFFEX
    "IF": "CFFEX", "IH": "CFFEX", "IC": "CFFEX", "IM": "CFFEX",
    "IO": "CFFEX", "HO": "CFFEX", "MO": "CFFEX",
    "T": "CFFEX", "TF": "CFFEX", "TS": "CFFEX",
    # INE
    "sc": "INE", "lu": "INE", "nr": "INE", "bc": "INE",
}

# 期货品种 -> 期权品种映射
FUTURE_OPTION_MAP: Dict[str, str] = {
    "IF": "IO",
    "IM": "MO",
    "IH": "HO",
}

# 期权品种 -> 期货品种反向映射
OPTION_FUTURE_MAP: Dict[str, str] = {v: k for k, v in FUTURE_OPTION_MAP.items()}

# 品种规格配置: 品种代码 -> (合约乘数 size, 最小价格变动 pricetick)
PRODUCT_SPECS: Dict[str, Tuple[int, float]] = {
    # CFFEX - 股指
    "IF": (300, 0.2),   # 沪深300期货
    "IH": (300, 0.2),   # 上证50期货
    "IC": (200, 0.2),   # 中证500期货
    "IM": (200, 0.2),   # 中证1000期货
    "IO": (100, 0.2),   # 沪深300期权
    "HO": (100, 0.2),   # 上证50期权
    "MO": (100, 0.2),   # 中证1000期权
    # SHFE
    "rb": (10, 1.0),    # 螺纹钢
    "hc": (10, 1.0),    # 热卷
    "ag": (15, 1.0),    # 白银
    "au": (1000, 0.02), # 黄金
    # INE
    "sc": (1000, 0.1),  # 原油
    "lu": (10, 1.0),    # 低硫燃料油
    # DCE
    "m": (10, 1.0),     # 豆粕
    "i": (100, 0.5),    # 铁矿石
    # CZCE
    "SA": (20, 1.0),    # 纯碱
    "MA": (10, 1.0),    # 甲醇
}

# 未配置品种的默认规格
DEFAULT_PRODUCT_SPEC: Tuple[int, float] = (10, 1.0)


# ---------------------------------------------------------------------------
# 回测配置数据类
# ---------------------------------------------------------------------------

@dataclass
class BacktestConfig:
    """回测参数配置，封装所有回测所需参数。"""

    config_path: str = "config/strategy_config.toml"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    capital: int = 1_000_000
    rate: float = 2.5e-5
    slippage: float = 0.2
    default_size: int = 10
    default_pricetick: float = 1.0
    show_chart: bool = True

    def get_end_date(self) -> str:
        """返回结束日期，未指定时默认使用当前日期。"""
        if self.end_date is not None:
            return self.end_date
        return date.today().strftime("%Y-%m-%d")

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "BacktestConfig":
        """
        从命令行参数构建配置。

        CLI 参数非 None 时覆盖默认值，为 None 时保留默认值。
        """
        config = cls()

        if getattr(args, "config", None) is not None:
            config.config_path = args.config
        if getattr(args, "start", None) is not None:
            config.start_date = args.start
        if getattr(args, "end", None) is not None:
            config.end_date = args.end
        if getattr(args, "capital", None) is not None:
            config.capital = args.capital
        if getattr(args, "rate", None) is not None:
            config.rate = args.rate
        if getattr(args, "slippage", None) is not None:
            config.slippage = args.slippage
        if getattr(args, "size", None) is not None:
            config.default_size = args.size
        if getattr(args, "pricetick", None) is not None:
            config.default_pricetick = args.pricetick
        if getattr(args, "no_chart", None) is not None:
            config.show_chart = not args.no_chart

        return config
