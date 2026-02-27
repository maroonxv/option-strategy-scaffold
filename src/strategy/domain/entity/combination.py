"""
Combination 实体

组合策略实体，管理多个期权 Leg 的结构约束、生命周期状态和序列化。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.strategy.domain.value_object.combination.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)
from src.strategy.domain.value_object.combination.combination_rules import (
    LegStructure,
    VALIDATION_RULES,
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
        # 将 Leg 转换为 LegStructure
        leg_structures = [
            LegStructure(
                option_type=leg.option_type,
                strike_price=leg.strike_price,
                expiry_date=leg.expiry_date,
            )
            for leg in self.legs
        ]
        # 调用共享验证规则
        error_message = VALIDATION_RULES[self.combination_type](leg_structures)
        if error_message is not None:
            raise ValueError(error_message)

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
