"""
CombinationPnLCalculator 领域服务

计算组合级盈亏：对组合内每个 Leg 基于开仓价和当前市场价计算未实现盈亏。
单腿公式：(current_price - open_price) × volume × multiplier × direction_sign
- direction_sign: long = +1, short = -1
- 当前价格不可用时，LegPnL.price_available = False，该腿盈亏计为 0

支持已实现盈亏：通过 realized_pnl_map 传入各腿已实现盈亏，汇总到 total_realized_pnl。
"""
from datetime import datetime
from typing import Dict, Optional

from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationPnL,
    LegPnL,
)


class CombinationPnLCalculator:
    """组合级盈亏计算服务"""

    def calculate(
        self,
        combination: Combination,
        current_prices: Dict[str, float],
        multiplier: float,
        realized_pnl_map: Optional[Dict[str, float]] = None,
    ) -> CombinationPnL:
        """
        计算组合级盈亏。

        Args:
            combination: 组合实体
            current_prices: vt_symbol → 当前市场价的映射
            multiplier: 合约乘数
            realized_pnl_map: vt_symbol → 已实现盈亏的映射（可选）

        Returns:
            CombinationPnL 包含总未实现盈亏、总已实现盈亏、每腿明细和计算时间戳
        """
        realized_pnl_map = realized_pnl_map or {}
        leg_details: list[LegPnL] = []
        total_pnl = 0.0
        total_realized = 0.0

        for leg in combination.legs:
            current_price = current_prices.get(leg.vt_symbol)
            realized = realized_pnl_map.get(leg.vt_symbol, 0.0)
            total_realized += realized

            if current_price is None:
                leg_details.append(
                    LegPnL(
                        vt_symbol=leg.vt_symbol,
                        unrealized_pnl=0.0,
                        price_available=False,
                        realized_pnl=realized,
                    )
                )
                continue

            sign = leg.direction_sign
            pnl = (current_price - leg.open_price) * leg.volume * multiplier * sign
            total_pnl += pnl

            leg_details.append(
                LegPnL(
                    vt_symbol=leg.vt_symbol,
                    unrealized_pnl=pnl,
                    price_available=True,
                    realized_pnl=realized,
                )
            )

        return CombinationPnL(
            total_unrealized_pnl=total_pnl,
            leg_details=leg_details,
            timestamp=datetime.now(),
            total_realized_pnl=total_realized,
        )
