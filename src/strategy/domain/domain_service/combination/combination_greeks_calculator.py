"""
CombinationGreeksCalculator 领域服务

计算组合级 Greeks 聚合：对组合内所有活跃 Leg 的 Greeks 进行加权求和。
加权公式：greek_total += greek_per_unit × volume × multiplier × direction_sign
- direction_sign: long = +1, short = -1（通过 Leg.direction_sign 属性获取）
- 某个 Leg 的 GreeksResult.success 为 False 时，记入 failed_legs 并继续计算其余 Leg
"""
from typing import Dict

from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import CombinationGreeks
from src.strategy.domain.value_object.greeks import GreeksResult


class CombinationGreeksCalculator:
    """组合级 Greeks 计算服务"""

    def calculate(
        self,
        combination: Combination,
        greeks_map: Dict[str, GreeksResult],
        multiplier: float,
    ) -> CombinationGreeks:
        """
        计算组合级 Greeks 聚合。

        Args:
            combination: 组合实体
            greeks_map: vt_symbol → GreeksResult 的映射
            multiplier: 合约乘数

        Returns:
            CombinationGreeks 聚合结果（含 failed_legs 列表）
        """
        delta = 0.0
        gamma = 0.0
        theta = 0.0
        vega = 0.0
        failed_legs: list[str] = []

        for leg in combination.legs:
            greeks_result = greeks_map.get(leg.vt_symbol)

            if greeks_result is None or not greeks_result.success:
                failed_legs.append(leg.vt_symbol)
                continue

            sign = leg.direction_sign
            weight = leg.volume * multiplier * sign

            delta += greeks_result.delta * weight
            gamma += greeks_result.gamma * weight
            theta += greeks_result.theta * weight
            vega += greeks_result.vega * weight

        return CombinationGreeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            failed_legs=failed_legs,
        )
