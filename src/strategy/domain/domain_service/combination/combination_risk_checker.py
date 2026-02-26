"""
组合级风控检查服务

基于组合级 Greeks 和阈值配置，判断组合是否超限。
独立于 PortfolioRiskAggregator 运行，不影响整体组合级风控。
"""
from src.strategy.domain.value_object.combination import (
    CombinationGreeks,
    CombinationRiskConfig,
)
from src.strategy.domain.value_object.risk import RiskCheckResult


class CombinationRiskChecker:
    """组合级 Greeks 风控检查器"""

    def __init__(self, config: CombinationRiskConfig) -> None:
        self._config = config

    def check(self, greeks: CombinationGreeks) -> RiskCheckResult:
        """
        检查组合级 Greeks 是否超限。

        通过条件: |delta| ≤ delta_limit AND |gamma| ≤ gamma_limit AND |vega| ≤ vega_limit AND |theta| ≤ theta_limit
        失败时 reject_reason 包含超限的 Greek 名称和数值。
        """
        violations: list[str] = []

        if abs(greeks.delta) > self._config.delta_limit:
            violations.append(
                f"delta={greeks.delta:.4f}(limit={self._config.delta_limit})"
            )
        if abs(greeks.gamma) > self._config.gamma_limit:
            violations.append(
                f"gamma={greeks.gamma:.4f}(limit={self._config.gamma_limit})"
            )
        if abs(greeks.vega) > self._config.vega_limit:
            violations.append(
                f"vega={greeks.vega:.4f}(limit={self._config.vega_limit})"
            )
        if abs(greeks.theta) > self._config.theta_limit:
            violations.append(
                f"theta={greeks.theta:.4f}(limit={self._config.theta_limit})"
            )

        if violations:
            return RiskCheckResult(
                passed=False,
                reject_reason="组合Greeks超限: " + ", ".join(violations),
            )

        return RiskCheckResult(passed=True)
