"""
Combination Rules 共享结构约束规则集

定义统一的腿结构描述和各组合类型的验证函数，供 CombinationRecognizer 和 Combination.validate() 共享使用。
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from src.strategy.domain.value_object.combination.combination import CombinationType


@dataclass(frozen=True)
class LegStructure:
    """统一的腿结构描述，用于规则匹配和验证"""
    option_type: str      # "call" 或 "put"
    strike_price: float
    expiry_date: str


def validate_straddle(legs: List[LegStructure]) -> Optional[str]:
    """STRADDLE: 恰好 2 腿，同到期日、同行权价、一 Call 一 Put"""
    if len(legs) != 2:
        return f"STRADDLE 需要恰好 2 腿，当前 {len(legs)} 腿"
    l0, l1 = legs
    if l0.expiry_date != l1.expiry_date:
        return "STRADDLE 要求所有腿到期日相同"
    if l0.strike_price != l1.strike_price:
        return "STRADDLE 要求所有腿行权价相同"
    if {l0.option_type, l1.option_type} != {"call", "put"}:
        return "STRADDLE 要求一个 Call 和一个 Put"
    return None


def validate_strangle(legs: List[LegStructure]) -> Optional[str]:
    """STRANGLE: 恰好 2 腿，同到期日、不同行权价、一 Call 一 Put"""
    if len(legs) != 2:
        return f"STRANGLE 需要恰好 2 腿，当前 {len(legs)} 腿"
    l0, l1 = legs
    if l0.expiry_date != l1.expiry_date:
        return "STRANGLE 要求所有腿到期日相同"
    if l0.strike_price == l1.strike_price:
        return "STRANGLE 要求两腿行权价不同"
    if {l0.option_type, l1.option_type} != {"call", "put"}:
        return "STRANGLE 要求一个 Call 和一个 Put"
    return None


def validate_vertical_spread(legs: List[LegStructure]) -> Optional[str]:
    """VERTICAL_SPREAD: 恰好 2 腿，同到期日、同类型、不同行权价"""
    if len(legs) != 2:
        return f"VERTICAL_SPREAD 需要恰好 2 腿，当前 {len(legs)} 腿"
    l0, l1 = legs
    if l0.expiry_date != l1.expiry_date:
        return "VERTICAL_SPREAD 要求所有腿到期日相同"
    if l0.option_type != l1.option_type:
        return "VERTICAL_SPREAD 要求所有腿期权类型相同"
    if l0.strike_price == l1.strike_price:
        return "VERTICAL_SPREAD 要求两腿行权价不同"
    return None


def validate_calendar_spread(legs: List[LegStructure]) -> Optional[str]:
    """CALENDAR_SPREAD: 恰好 2 腿，不同到期日、同行权价、同类型"""
    if len(legs) != 2:
        return f"CALENDAR_SPREAD 需要恰好 2 腿，当前 {len(legs)} 腿"
    l0, l1 = legs
    if l0.expiry_date == l1.expiry_date:
        return "CALENDAR_SPREAD 要求两腿到期日不同"
    if l0.strike_price != l1.strike_price:
        return "CALENDAR_SPREAD 要求所有腿行权价相同"
    if l0.option_type != l1.option_type:
        return "CALENDAR_SPREAD 要求所有腿期权类型相同"
    return None


def validate_iron_condor(legs: List[LegStructure]) -> Optional[str]:
    """IRON_CONDOR: 恰好 4 腿，同到期日，构成 1 个 Put Spread + 1 个 Call Spread"""
    if len(legs) != 4:
        return f"IRON_CONDOR 需要恰好 4 腿，当前 {len(legs)} 腿"
    
    expiry_dates = {leg.expiry_date for leg in legs}
    if len(expiry_dates) != 1:
        return "IRON_CONDOR 要求所有腿到期日相同"
    
    puts = [leg for leg in legs if leg.option_type == "put"]
    calls = [leg for leg in legs if leg.option_type == "call"]
    
    if len(puts) != 2 or len(calls) != 2:
        return "IRON_CONDOR 要求恰好 2 个 Put 和 2 个 Call"
    
    # Put Spread: 2 puts 不同行权价
    if puts[0].strike_price == puts[1].strike_price:
        return "IRON_CONDOR 的 Put Spread 要求两个 Put 行权价不同"
    
    # Call Spread: 2 calls 不同行权价
    if calls[0].strike_price == calls[1].strike_price:
        return "IRON_CONDOR 的 Call Spread 要求两个 Call 行权价不同"
    
    return None


def validate_custom(legs: List[LegStructure]) -> Optional[str]:
    """CUSTOM: 至少 1 腿，无结构约束"""
    if len(legs) < 1:
        return "CUSTOM 组合至少需要 1 腿"
    return None


VALIDATION_RULES: Dict[CombinationType, Callable[[List[LegStructure]], Optional[str]]] = {
    CombinationType.STRADDLE: validate_straddle,
    CombinationType.STRANGLE: validate_strangle,
    CombinationType.VERTICAL_SPREAD: validate_vertical_spread,
    CombinationType.CALENDAR_SPREAD: validate_calendar_spread,
    CombinationType.IRON_CONDOR: validate_iron_condor,
    CombinationType.CUSTOM: validate_custom,
}
