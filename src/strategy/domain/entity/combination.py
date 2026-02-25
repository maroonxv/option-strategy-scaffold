"""
Combination 实体

组合策略实体，管理多个期权 Leg 的结构约束、生命周期状态和序列化。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.strategy.domain.value_object.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)


@dataclass
class Combination:
    """组合策略实体"""

    combination_id: str
    combination_type: CombinationType
    underlying_vt_symbol: str
    legs: List[Leg]
    status: CombinationStatus
    create_time: datetime
    close_time: Optional[datetime] = None

    # ========== 验证 ==========

    def validate(self) -> None:
        """验证 Leg 结构是否满足 CombinationType 约束，不满足时抛出 ValueError。"""
        validators = {
            CombinationType.STRADDLE: self._validate_straddle,
            CombinationType.STRANGLE: self._validate_strangle,
            CombinationType.VERTICAL_SPREAD: self._validate_vertical_spread,
            CombinationType.CALENDAR_SPREAD: self._validate_calendar_spread,
            CombinationType.IRON_CONDOR: self._validate_iron_condor,
            CombinationType.CUSTOM: self._validate_custom,
        }
        validators[self.combination_type]()

    def _validate_straddle(self) -> None:
        """STRADDLE: 恰好 2 腿，同到期日、同行权价、一 Call 一 Put"""
        if len(self.legs) != 2:
            raise ValueError(
                f"STRADDLE 需要恰好 2 腿，当前 {len(self.legs)} 腿"
            )
        l0, l1 = self.legs
        if l0.expiry_date != l1.expiry_date:
            raise ValueError("STRADDLE 要求所有腿到期日相同")
        if l0.strike_price != l1.strike_price:
            raise ValueError("STRADDLE 要求所有腿行权价相同")
        types = {l0.option_type, l1.option_type}
        if types != {"call", "put"}:
            raise ValueError("STRADDLE 要求一个 Call 和一个 Put")

    def _validate_strangle(self) -> None:
        """STRANGLE: 恰好 2 腿，同到期日、不同行权价、一 Call 一 Put"""
        if len(self.legs) != 2:
            raise ValueError(
                f"STRANGLE 需要恰好 2 腿，当前 {len(self.legs)} 腿"
            )
        l0, l1 = self.legs
        if l0.expiry_date != l1.expiry_date:
            raise ValueError("STRANGLE 要求所有腿到期日相同")
        if l0.strike_price == l1.strike_price:
            raise ValueError("STRANGLE 要求两腿行权价不同")
        types = {l0.option_type, l1.option_type}
        if types != {"call", "put"}:
            raise ValueError("STRANGLE 要求一个 Call 和一个 Put")

    def _validate_vertical_spread(self) -> None:
        """VERTICAL_SPREAD: 恰好 2 腿，同到期日、同类型、不同行权价"""
        if len(self.legs) != 2:
            raise ValueError(
                f"VERTICAL_SPREAD 需要恰好 2 腿，当前 {len(self.legs)} 腿"
            )
        l0, l1 = self.legs
        if l0.expiry_date != l1.expiry_date:
            raise ValueError("VERTICAL_SPREAD 要求所有腿到期日相同")
        if l0.option_type != l1.option_type:
            raise ValueError("VERTICAL_SPREAD 要求所有腿期权类型相同")
        if l0.strike_price == l1.strike_price:
            raise ValueError("VERTICAL_SPREAD 要求两腿行权价不同")

    def _validate_calendar_spread(self) -> None:
        """CALENDAR_SPREAD: 恰好 2 腿，不同到期日、同行权价、同类型"""
        if len(self.legs) != 2:
            raise ValueError(
                f"CALENDAR_SPREAD 需要恰好 2 腿，当前 {len(self.legs)} 腿"
            )
        l0, l1 = self.legs
        if l0.expiry_date == l1.expiry_date:
            raise ValueError("CALENDAR_SPREAD 要求两腿到期日不同")
        if l0.strike_price != l1.strike_price:
            raise ValueError("CALENDAR_SPREAD 要求所有腿行权价相同")
        if l0.option_type != l1.option_type:
            raise ValueError("CALENDAR_SPREAD 要求所有腿期权类型相同")

    def _validate_iron_condor(self) -> None:
        """IRON_CONDOR: 恰好 4 腿，同到期日，构成 1 个 Put Spread + 1 个 Call Spread"""
        if len(self.legs) != 4:
            raise ValueError(
                f"IRON_CONDOR 需要恰好 4 腿，当前 {len(self.legs)} 腿"
            )
        expiry_dates = {leg.expiry_date for leg in self.legs}
        if len(expiry_dates) != 1:
            raise ValueError("IRON_CONDOR 要求所有腿到期日相同")

        puts = [leg for leg in self.legs if leg.option_type == "put"]
        calls = [leg for leg in self.legs if leg.option_type == "call"]

        if len(puts) != 2 or len(calls) != 2:
            raise ValueError(
                "IRON_CONDOR 要求恰好 2 个 Put 和 2 个 Call"
            )
        # Put Spread: 2 puts 不同行权价
        if puts[0].strike_price == puts[1].strike_price:
            raise ValueError(
                "IRON_CONDOR 的 Put Spread 要求两个 Put 行权价不同"
            )
        # Call Spread: 2 calls 不同行权价
        if calls[0].strike_price == calls[1].strike_price:
            raise ValueError(
                "IRON_CONDOR 的 Call Spread 要求两个 Call 行权价不同"
            )

    def _validate_custom(self) -> None:
        """CUSTOM: 至少 1 腿，无结构约束"""
        if len(self.legs) < 1:
            raise ValueError("CUSTOM 组合至少需要 1 腿")

    # ========== 状态管理 ==========

    def update_status(
        self, closed_vt_symbols: Set[str]
    ) -> Optional[CombinationStatus]:
        """
        根据已平仓的 vt_symbol 集合判定状态转换。

        - 所有 Leg 都在 closed_vt_symbols 中 → CLOSED
        - 部分 Leg 在 closed_vt_symbols 中 → PARTIALLY_CLOSED
        - 没有 Leg 在 closed_vt_symbols 中 → 不变 (return None)
        """
        leg_symbols = {leg.vt_symbol for leg in self.legs}
        closed_in_combo = leg_symbols & closed_vt_symbols

        if len(closed_in_combo) == 0:
            return None

        if closed_in_combo == leg_symbols:
            new_status = CombinationStatus.CLOSED
        else:
            new_status = CombinationStatus.PARTIALLY_CLOSED

        if new_status != self.status:
            self.status = new_status
            if new_status == CombinationStatus.CLOSED:
                self.close_time = datetime.now()
            return new_status
        return None

    def get_active_legs(self) -> List[Leg]:
        """返回所有活跃（volume > 0）的 Leg。"""
        return [leg for leg in self.legs if leg.volume > 0]

    # ========== 序列化 ==========

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 Python 字典。"""
        return {
            "combination_id": self.combination_id,
            "combination_type": self.combination_type.value,
            "underlying_vt_symbol": self.underlying_vt_symbol,
            "legs": [
                {
                    "vt_symbol": leg.vt_symbol,
                    "option_type": leg.option_type,
                    "strike_price": leg.strike_price,
                    "expiry_date": leg.expiry_date,
                    "direction": leg.direction,
                    "volume": leg.volume,
                    "open_price": leg.open_price,
                }
                for leg in self.legs
            ],
            "status": self.status.value,
            "create_time": self.create_time.isoformat(),
            "close_time": self.close_time.isoformat()
            if self.close_time
            else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Combination":
        """从 Python 字典反序列化恢复实例。"""
        legs = [
            Leg(
                vt_symbol=leg_data["vt_symbol"],
                option_type=leg_data["option_type"],
                strike_price=leg_data["strike_price"],
                expiry_date=leg_data["expiry_date"],
                direction=leg_data["direction"],
                volume=leg_data["volume"],
                open_price=leg_data["open_price"],
            )
            for leg_data in data["legs"]
        ]
        close_time = (
            datetime.fromisoformat(data["close_time"])
            if data.get("close_time")
            else None
        )
        return cls(
            combination_id=data["combination_id"],
            combination_type=CombinationType(data["combination_type"]),
            underlying_vt_symbol=data["underlying_vt_symbol"],
            legs=legs,
            status=CombinationStatus(data["status"]),
            create_time=datetime.fromisoformat(data["create_time"]),
            close_time=close_time,
        )
