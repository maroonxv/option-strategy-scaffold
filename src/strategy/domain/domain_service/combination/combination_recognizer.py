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


class CombinationRecognizer:
    """组合策略识别服务"""

    def recognize(
        self,
        positions: List[Position],
        contracts: Dict[str, OptionContract],
    ) -> CombinationType:
        """
        分析持仓结构，返回匹配的组合类型。

        Args:
            positions: 待识别的持仓列表
            contracts: vt_symbol → OptionContract 映射

        Returns:
            匹配的 CombinationType
        """
        if not positions:
            return CombinationType.CUSTOM

        # 按优先级依次尝试匹配
        if self._is_iron_condor(positions, contracts):
            return CombinationType.IRON_CONDOR
        if self._is_straddle(positions, contracts):
            return CombinationType.STRADDLE
        if self._is_strangle(positions, contracts):
            return CombinationType.STRANGLE
        if self._is_vertical_spread(positions, contracts):
            return CombinationType.VERTICAL_SPREAD
        if self._is_calendar_spread(positions, contracts):
            return CombinationType.CALENDAR_SPREAD

        return CombinationType.CUSTOM

    # ------------------------------------------------------------------
    # 私有匹配方法
    # ------------------------------------------------------------------

    def _is_straddle(
        self, positions: List[Position], contracts: Dict[str, OptionContract]
    ) -> bool:
        """STRADDLE: 2腿, 同标的, 同到期日, 同行权价, 一Call一Put"""
        if len(positions) != 2:
            return False
        c0, c1 = self._get_contracts(positions, contracts)
        if c0 is None or c1 is None:
            return False
        return (
            c0.underlying_symbol == c1.underlying_symbol
            and c0.expiry_date == c1.expiry_date
            and c0.strike_price == c1.strike_price
            and {c0.option_type, c1.option_type} == {"call", "put"}
        )

    def _is_strangle(
        self, positions: List[Position], contracts: Dict[str, OptionContract]
    ) -> bool:
        """STRANGLE: 2腿, 同标的, 同到期日, 不同行权价, 一Call一Put"""
        if len(positions) != 2:
            return False
        c0, c1 = self._get_contracts(positions, contracts)
        if c0 is None or c1 is None:
            return False
        return (
            c0.underlying_symbol == c1.underlying_symbol
            and c0.expiry_date == c1.expiry_date
            and c0.strike_price != c1.strike_price
            and {c0.option_type, c1.option_type} == {"call", "put"}
        )

    def _is_vertical_spread(
        self, positions: List[Position], contracts: Dict[str, OptionContract]
    ) -> bool:
        """VERTICAL_SPREAD: 2腿, 同标的, 同到期日, 同期权类型, 不同行权价"""
        if len(positions) != 2:
            return False
        c0, c1 = self._get_contracts(positions, contracts)
        if c0 is None or c1 is None:
            return False
        return (
            c0.underlying_symbol == c1.underlying_symbol
            and c0.expiry_date == c1.expiry_date
            and c0.option_type == c1.option_type
            and c0.strike_price != c1.strike_price
        )

    def _is_calendar_spread(
        self, positions: List[Position], contracts: Dict[str, OptionContract]
    ) -> bool:
        """CALENDAR_SPREAD: 2腿, 同标的, 不同到期日, 同行权价, 同期权类型"""
        if len(positions) != 2:
            return False
        c0, c1 = self._get_contracts(positions, contracts)
        if c0 is None or c1 is None:
            return False
        return (
            c0.underlying_symbol == c1.underlying_symbol
            and c0.expiry_date != c1.expiry_date
            and c0.strike_price == c1.strike_price
            and c0.option_type == c1.option_type
        )

    def _is_iron_condor(
        self, positions: List[Position], contracts: Dict[str, OptionContract]
    ) -> bool:
        """
        IRON_CONDOR: 4腿, 同标的, 同到期日,
        2 Puts 不同行权价 + 2 Calls 不同行权价
        """
        if len(positions) != 4:
            return False
        option_contracts = [contracts.get(p.vt_symbol) for p in positions]
        if any(c is None for c in option_contracts):
            return False

        # 同标的、同到期日
        underlyings = {c.underlying_symbol for c in option_contracts}  # type: ignore[union-attr]
        expiries = {c.expiry_date for c in option_contracts}  # type: ignore[union-attr]
        if len(underlyings) != 1 or len(expiries) != 1:
            return False

        puts = [c for c in option_contracts if c.option_type == "put"]  # type: ignore[union-attr]
        calls = [c for c in option_contracts if c.option_type == "call"]  # type: ignore[union-attr]

        if len(puts) != 2 or len(calls) != 2:
            return False

        # 每对行权价必须不同
        if puts[0].strike_price == puts[1].strike_price:
            return False
        if calls[0].strike_price == calls[1].strike_price:
            return False

        return True

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _get_contracts(
        positions: List[Position],
        contracts: Dict[str, OptionContract],
    ):
        """获取两个 Position 对应的 OptionContract，任一缺失返回 (None, None)"""
        c0 = contracts.get(positions[0].vt_symbol)
        c1 = contracts.get(positions[1].vt_symbol)
        return c0, c1
