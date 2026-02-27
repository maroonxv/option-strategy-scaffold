"""
CombinationFacade 编排层

组合策略编排层，提供高层评估接口。
依次调用 GreeksCalculator、PnLCalculator、RiskChecker，返回综合评估结果。
子服务异常直接传播，不进行静默吞没。
"""
from typing import Dict, Optional

from src.strategy.domain.domain_service.combination.combination_greeks_calculator import (
    CombinationGreeksCalculator,
)
from src.strategy.domain.domain_service.combination.combination_pnl_calculator import (
    CombinationPnLCalculator,
)
from src.strategy.domain.domain_service.combination.combination_risk_checker import (
    CombinationRiskChecker,
)
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination.combination import CombinationEvaluation
from src.strategy.domain.value_object.pricing.greeks import GreeksResult


class CombinationFacade:
    """组合策略编排层，提供高层评估接口"""

    def __init__(
        self,
        greeks_calculator: CombinationGreeksCalculator,
        pnl_calculator: CombinationPnLCalculator,
        risk_checker: CombinationRiskChecker,
    ) -> None:
        self._greeks_calculator = greeks_calculator
        self._pnl_calculator = pnl_calculator
        self._risk_checker = risk_checker

    def evaluate(
        self,
        combination: Combination,
        greeks_map: Dict[str, GreeksResult],
        current_prices: Dict[str, float],
        multiplier: float,
        realized_pnl_map: Optional[Dict[str, float]] = None,
    ) -> CombinationEvaluation:
        """依次调用 Greeks 计算、PnL 计算、风控检查，返回综合评估结果。"""
        greeks = self._greeks_calculator.calculate(combination, greeks_map, multiplier)
        pnl = self._pnl_calculator.calculate(
            combination, current_prices, multiplier, realized_pnl_map
        )
        risk_result = self._risk_checker.check(greeks)
        return CombinationEvaluation(greeks=greeks, pnl=pnl, risk_result=risk_result)
