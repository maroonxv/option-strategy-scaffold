"""
CombinationRecognizer - 组合策略识别服务

根据持仓结构自动识别组合策略类型。
按优先级匹配：IRON_CONDOR → STRADDLE → STRANGLE → VERTICAL_SPREAD → CALENDAR_SPREAD → CUSTOM
"""
from dataclasses import dataclass
from typing import Callable, Dict, List

from src.strategy.domain.entity.position import Position
from src.strategy.domain.value_object.combination import CombinationType
from src.strategy.domain.value_object.option_contract import OptionContract


@dataclass(frozen=True)
class MatchRule:
    """组合类型匹配规则"""
    combination_type: CombinationType
    leg_count: int
    predicate: Callable[[List[OptionContract]], bool]


# ------------------------------------------------------------------
# 静态谓词函数
# ------------------------------------------------------------------


def _is_straddle(option_contracts: List[OptionContract]) -> bool:
    """STRADDLE: 2腿, 同标的, 同到期日, 同行权价, 一Call一Put"""
    if len(option_contracts) != 2:
        return False
    c0, c1 = option_contracts[0], option_contracts[1]
    return (
        c0.underlying_symbol == c1.underlying_symbol
        and c0.expiry_date == c1.expiry_date
        and c0.strike_price == c1.strike_price
        and {c0.option_type, c1.option_type} == {"call", "put"}
    )


def _is_strangle(option_contracts: List[OptionContract]) -> bool:
    """STRANGLE: 2腿, 同标的, 同到期日, 不同行权价, 一Call一Put"""
    if len(option_contracts) != 2:
        return False
    c0, c1 = option_contracts[0], option_contracts[1]
    return (
        c0.underlying_symbol == c1.underlying_symbol
        and c0.expiry_date == c1.expiry_date
        and c0.strike_price != c1.strike_price
        and {c0.option_type, c1.option_type} == {"call", "put"}
    )


def _is_vertical_spread(option_contracts: List[OptionContract]) -> bool:
    """VERTICAL_SPREAD: 2腿, 同标的, 同到期日, 同期权类型, 不同行权价"""
    if len(option_contracts) != 2:
        return False
    c0, c1 = option_contracts[0], option_contracts[1]
    return (
        c0.underlying_symbol == c1.underlying_symbol
        and c0.expiry_date == c1.expiry_date
        and c0.option_type == c1.option_type
        and c0.strike_price != c1.strike_price
    )


def _is_calendar_spread(option_contracts: List[OptionContract]) -> bool:
    """CALENDAR_SPREAD: 2腿, 同标的, 不同到期日, 同行权价, 同期权类型"""
    if len(option_contracts) != 2:
        return False
    c0, c1 = option_contracts[0], option_contracts[1]
    return (
        c0.underlying_symbol == c1.underlying_symbol
        and c0.expiry_date != c1.expiry_date
        and c0.strike_price == c1.strike_price
        and c0.option_type == c1.option_type
    )


def _is_iron_condor(option_contracts: List[OptionContract]) -> bool:
    """
    IRON_CONDOR: 4腿, 同标的, 同到期日,
    2 Puts 不同行权价 + 2 Calls 不同行权价
    """
    if len(option_contracts) != 4:
        return False

    # 同标的、同到期日
    underlyings = {c.underlying_symbol for c in option_contracts}
    expiries = {c.expiry_date for c in option_contracts}
    if len(underlyings) != 1 or len(expiries) != 1:
        return False

    puts = [c for c in option_contracts if c.option_type == "put"]
    calls = [c for c in option_contracts if c.option_type == "call"]

    if len(puts) != 2 or len(calls) != 2:
        return False

    # 每对行权价必须不同
    if puts[0].strike_price == puts[1].strike_price:
        return False
    if calls[0].strike_price == calls[1].strike_price:
        return False

    return True


# ------------------------------------------------------------------
# 按优先级排序的规则列表
# 优先级: IRON_CONDOR → STRADDLE → STRANGLE → VERTICAL_SPREAD → CALENDAR_SPREAD
# ------------------------------------------------------------------

_RULES: List[MatchRule] = [
    MatchRule(CombinationType.IRON_CONDOR, 4, _is_iron_condor),
    MatchRule(CombinationType.STRADDLE, 2, _is_straddle),
    MatchRule(CombinationType.STRANGLE, 2, _is_strangle),
    MatchRule(CombinationType.VERTICAL_SPREAD, 2, _is_vertical_spread),
    MatchRule(CombinationType.CALENDAR_SPREAD, 2, _is_calendar_spread),
]


class CombinationRecognizer:
    """组合策略识别服务"""

    def recognize(
        self,
        positions: List[Position],
        contracts: Dict[str, OptionContract],
    ) -> CombinationType:
        """
        分析持仓结构，返回匹配的组合类型。

        使用表驱动逻辑遍历 _RULES 列表，返回第一个匹配的组合类型。
        优先级: IRON_CONDOR → STRADDLE → STRANGLE → VERTICAL_SPREAD → CALENDAR_SPREAD

        Args:
            positions: 待识别的持仓列表
            contracts: vt_symbol → OptionContract 映射

        Returns:
            匹配的 CombinationType，无匹配时返回 CUSTOM
        """
        if not positions:
            return CombinationType.CUSTOM

        # 获取所有持仓对应的期权合约
        option_contracts = [contracts.get(p.vt_symbol) for p in positions]
        if any(c is None for c in option_contracts):
            return CombinationType.CUSTOM

        # 遍历规则列表，返回第一个匹配的组合类型
        for rule in _RULES:
            if len(positions) == rule.leg_count and rule.predicate(option_contracts):
                return rule.combination_type

        return CombinationType.CUSTOM
