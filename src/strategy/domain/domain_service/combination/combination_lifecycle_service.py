"""
CombinationLifecycleService 领域服务

负责组合策略的生命周期操作：建仓、平仓、调整。
为每个操作生成对应的 OrderInstruction 列表。
"""
from typing import Dict, List

from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.order_instruction import (
    Direction,
    Offset,
    OrderInstruction,
)


class CombinationLifecycleService:
    """组合策略生命周期服务"""

    def generate_open_instructions(
        self,
        combination: Combination,
        price_map: Dict[str, float],
    ) -> List[OrderInstruction]:
        """
        为组合的每个 Leg 生成开仓指令。

        方向映射：leg.direction "long" → Direction.LONG，"short" → Direction.SHORT
        偏移：统一为 Offset.OPEN
        """
        instructions: List[OrderInstruction] = []
        for leg in combination.legs:
            direction = (
                Direction.LONG if leg.direction == "long" else Direction.SHORT
            )
            price = price_map.get(leg.vt_symbol, 0.0)
            instructions.append(
                OrderInstruction(
                    vt_symbol=leg.vt_symbol,
                    direction=direction,
                    offset=Offset.OPEN,
                    volume=leg.volume,
                    price=price,
                )
            )
        return instructions

    def generate_close_instructions(
        self,
        combination: Combination,
        price_map: Dict[str, float],
    ) -> List[OrderInstruction]:
        """
        为组合的所有活跃 Leg 生成平仓指令。

        已平仓 Leg（volume == 0）跳过。
        方向取反：leg.direction "long" → Direction.SHORT，"short" → Direction.LONG
        偏移：统一为 Offset.CLOSE
        """
        instructions: List[OrderInstruction] = []
        for leg in combination.get_active_legs():
            direction = (
                Direction.SHORT if leg.direction == "long" else Direction.LONG
            )
            price = price_map.get(leg.vt_symbol, 0.0)
            instructions.append(
                OrderInstruction(
                    vt_symbol=leg.vt_symbol,
                    direction=direction,
                    offset=Offset.CLOSE,
                    volume=leg.volume,
                    price=price,
                )
            )
        return instructions

    def generate_adjust_instruction(
        self,
        combination: Combination,
        leg_vt_symbol: str,
        new_volume: int,
        current_price: float,
    ) -> OrderInstruction:
        """
        为指定 Leg 生成调整指令。

        - new_volume > 当前 volume → 开仓指令（差额部分）
        - new_volume < 当前 volume → 平仓指令（差额部分）
        - Leg 不存在 → 抛出 ValueError
        """
        target_leg = None
        for leg in combination.legs:
            if leg.vt_symbol == leg_vt_symbol:
                target_leg = leg
                break

        if target_leg is None:
            raise ValueError(
                f"Leg {leg_vt_symbol} 不存在于组合 {combination.combination_id} 中"
            )

        diff = new_volume - target_leg.volume

        if diff > 0:
            # 增仓：开仓指令，方向与 Leg 方向一致
            direction = (
                Direction.LONG
                if target_leg.direction == "long"
                else Direction.SHORT
            )
            return OrderInstruction(
                vt_symbol=leg_vt_symbol,
                direction=direction,
                offset=Offset.OPEN,
                volume=diff,
                price=current_price,
            )
        elif diff < 0:
            # 减仓：平仓指令，方向与 Leg 方向相反
            direction = (
                Direction.SHORT
                if target_leg.direction == "long"
                else Direction.LONG
            )
            return OrderInstruction(
                vt_symbol=leg_vt_symbol,
                direction=direction,
                offset=Offset.CLOSE,
                volume=abs(diff),
                price=current_price,
            )
        else:
            raise ValueError(
                f"新持仓量 {new_volume} 与当前持仓量 {target_leg.volume} 相同，无需调整"
            )
