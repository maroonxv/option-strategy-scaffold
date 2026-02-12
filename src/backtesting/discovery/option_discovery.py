"""
期权合约发现服务

从数据库中查找与期货合约关联的期权合约。
"""

import logging
import re
from typing import Dict, List, Tuple

from vnpy.trader.constant import Interval
from vnpy.trader.database import get_database

from src.backtesting.config import FUTURE_OPTION_MAP

logger = logging.getLogger(__name__)


class OptionDiscoveryService:
    """期权发现服务，从数据库中查找与期货合约关联的期权合约。"""

    @classmethod
    def discover(cls, underlying_vt_symbols: List[str]) -> List[str]:
        """
        从数据库中查找关联期权合约。

        对每个期货 vt_symbol，解析品种代码并通过 FUTURE_OPTION_MAP 获取
        对应的期权品种前缀，然后在数据库 1 分钟 K 线数据中匹配期权合约。

        Args:
            underlying_vt_symbols: 期货合约 vt_symbol 列表（如 ["IF2501.CFFEX"]）

        Returns:
            匹配到的期权 vt_symbol 列表；数据库失败时返回空列表。
        """
        if not underlying_vt_symbols:
            return []

        # 1. 解析期货代码，构建前缀匹配映射
        target_map = cls._build_target_map(underlying_vt_symbols)
        if not target_map:
            return []

        # 2. 从数据库获取 Bar 概览
        try:
            database = get_database()
            overviews = database.get_bar_overview()
        except Exception as e:
            logger.error(f"查询数据库失败: {e}")
            return []

        # 3. 筛选匹配的期权合约
        option_vt_symbols = cls._match_options(overviews, target_map)

        logger.info(f"从数据库发现关联期权合约: {len(option_vt_symbols)} 个")
        return option_vt_symbols

    @classmethod
    def _build_target_map(
        cls, underlying_vt_symbols: List[str]
    ) -> Dict[str, Tuple[str, List[str]]]:
        """
        解析期货 vt_symbol 列表，构建前缀匹配映射。

        Returns:
            {symbol: (exchange, [prefix1, prefix2, ...])} 映射
        """
        target_map: Dict[str, Tuple[str, List[str]]] = {}

        for vt_symbol in underlying_vt_symbols:
            try:
                symbol, exchange = vt_symbol.split(".")
            except ValueError:
                continue

            match = re.match(r"^([a-zA-Z]+)(\d+)", symbol)
            if match:
                product_code = match.group(1).upper()
                contract_suffix = match.group(2)

                # 默认包含自身前缀（用于商品期权匹配）
                prefixes = [symbol]

                # 如果存在期货→期权映射，追加期权前缀
                if product_code in FUTURE_OPTION_MAP:
                    option_product = FUTURE_OPTION_MAP[product_code]
                    option_prefix = f"{option_product}{contract_suffix}"
                    prefixes.append(option_prefix)

                target_map[symbol] = (exchange, prefixes)
            else:
                target_map[symbol] = (exchange, [symbol])

        return target_map

    @staticmethod
    def _match_options(
        overviews, target_map: Dict[str, Tuple[str, List[str]]]
    ) -> List[str]:
        """
        从数据库概览中筛选匹配的期权合约。

        仅返回存在 1 分钟 K 线数据且 symbol 后缀包含 C 或 P 的合约。
        """
        option_vt_symbols: List[str] = []

        for overview in overviews:
            if overview.interval != Interval.MINUTE:
                continue

            symbol = overview.symbol
            exchange = overview.exchange.value

            for _future_symbol, (future_exchange, prefixes) in target_map.items():
                if exchange != future_exchange:
                    continue

                matched_prefix = None
                for prefix in prefixes:
                    if symbol.startswith(prefix) and len(symbol) > len(prefix):
                        matched_prefix = prefix
                        break

                if not matched_prefix:
                    continue

                suffix = symbol[len(matched_prefix):]
                if "C" in suffix or "P" in suffix:
                    option_vt_symbols.append(f"{symbol}.{exchange}")

        return option_vt_symbols
