"""
PortfolioRiskAggregator 领域服务

持仓级风控检查 + 组合级 Greeks 聚合 + 阈值突破事件产生。
"""
from datetime import datetime
from typing import List, Tuple

from ..value_object.greeks import GreeksResult
from ..value_object.risk import (
    RiskThresholds,
    RiskCheckResult,
    PortfolioGreeks,
    PositionGreeksEntry,
)
from ..event.event_types import DomainEvent, GreeksRiskBreachEvent


class PortfolioRiskAggregator:
    """
    组合风险聚合器

    职责:
    1. 开仓前单持仓 Greeks 风控检查
    2. 组合级 Greeks 加权求和聚合
    3. 组合级阈值突破事件产生
    """

    def __init__(self, thresholds: RiskThresholds) -> None:
        self.thresholds = thresholds

    def check_position_risk(
        self, greeks: GreeksResult, volume: int, multiplier: float
    ) -> RiskCheckResult:
        """
        开仓前单持仓 Greeks 风控检查

        检查 |greek * volume * multiplier| 是否超过阈值。
        """
        weighted_delta = abs(greeks.delta * volume * multiplier)
        weighted_gamma = abs(greeks.gamma * volume * multiplier)
        weighted_vega = abs(greeks.vega * volume * multiplier)

        if weighted_delta > self.thresholds.position_delta_limit:
            return RiskCheckResult(
                passed=False,
                reject_reason=f"Delta 风控超限: |{weighted_delta:.4f}| > {self.thresholds.position_delta_limit}",
            )
        if weighted_gamma > self.thresholds.position_gamma_limit:
            return RiskCheckResult(
                passed=False,
                reject_reason=f"Gamma 风控超限: |{weighted_gamma:.4f}| > {self.thresholds.position_gamma_limit}",
            )
        if weighted_vega > self.thresholds.position_vega_limit:
            return RiskCheckResult(
                passed=False,
                reject_reason=f"Vega 风控超限: |{weighted_vega:.4f}| > {self.thresholds.position_vega_limit}",
            )
        return RiskCheckResult(passed=True)

    def aggregate_portfolio_greeks(
        self, positions: List[PositionGreeksEntry]
    ) -> Tuple[PortfolioGreeks, List[DomainEvent]]:
        """
        聚合组合级 Greeks，返回快照和可能的突破事件。

        Args:
            positions: 所有活跃持仓的 Greeks 条目

        Returns:
            (PortfolioGreeks 快照, 突破事件列表)
        """
        total_delta = 0.0
        total_gamma = 0.0
        total_theta = 0.0
        total_vega = 0.0

        for entry in positions:
            weight = entry.volume * entry.multiplier
            total_delta += entry.greeks.delta * weight
            total_gamma += entry.greeks.gamma * weight
            total_theta += entry.greeks.theta * weight
            total_vega += entry.greeks.vega * weight

        snapshot = PortfolioGreeks(
            total_delta=total_delta,
            total_gamma=total_gamma,
            total_theta=total_theta,
            total_vega=total_vega,
            position_count=len(positions),
            timestamp=datetime.now(),
        )

        events: List[DomainEvent] = []

        if abs(total_delta) > self.thresholds.portfolio_delta_limit:
            events.append(GreeksRiskBreachEvent(
                level="portfolio",
                greek_name="delta",
                current_value=total_delta,
                limit_value=self.thresholds.portfolio_delta_limit,
            ))
        if abs(total_gamma) > self.thresholds.portfolio_gamma_limit:
            events.append(GreeksRiskBreachEvent(
                level="portfolio",
                greek_name="gamma",
                current_value=total_gamma,
                limit_value=self.thresholds.portfolio_gamma_limit,
            ))
        if abs(total_vega) > self.thresholds.portfolio_vega_limit:
            events.append(GreeksRiskBreachEvent(
                level="portfolio",
                greek_name="vega",
                current_value=total_vega,
                limit_value=self.thresholds.portfolio_vega_limit,
            ))

        return snapshot, events
