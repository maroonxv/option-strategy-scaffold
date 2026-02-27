"""
RiskBudgetAllocator - 风险预算分配服务

负责在不同策略或品种间分配 Greeks 预算，计算使用量，检查预算限额。
"""

from typing import Dict, List

from ...entity.position import Position
from ...value_object.pricing.greeks import GreeksResult
from ...value_object.risk.risk import (
    RiskBudgetConfig,
    RiskThresholds,
    GreeksBudget,
    GreeksUsage,
    BudgetCheckResult,
)


class RiskBudgetAllocator:
    """
    风险预算分配服务
    
    职责:
    1. 按品种或策略分配 Greeks 预算
    2. 计算当前 Greeks 使用量
    3. 检查是否超过分配额度
    4. 计算剩余预算
    """
    
    def __init__(self, config: RiskBudgetConfig) -> None:
        """
        初始化风险预算分配器
        
        Args:
            config: 风险预算配置对象
        """
        self._config = config
        
        # 验证分配比例
        if self._config.allocation_ratios:
            self._validate_allocation_ratios()
    
    def allocate_budget_by_underlying(
        self,
        total_limits: RiskThresholds
    ) -> Dict[str, GreeksBudget]:
        """
        按品种分配 Greeks 预算
        
        Args:
            total_limits: 组合级 Greeks 限额
            
        Returns:
            品种 -> GreeksBudget 映射
        """
        if not self._config.allocation_ratios:
            return {}
        
        budget_map: Dict[str, GreeksBudget] = {}
        
        for underlying, ratio in self._config.allocation_ratios.items():
            budget_map[underlying] = GreeksBudget(
                delta_budget=total_limits.portfolio_delta_limit * ratio,
                gamma_budget=total_limits.portfolio_gamma_limit * ratio,
                vega_budget=total_limits.portfolio_vega_limit * ratio
            )
        
        return budget_map
    
    def calculate_usage(
        self,
        positions: List[Position],
        greeks_map: Dict[str, GreeksResult],
        dimension: str = "underlying"
    ) -> Dict[str, GreeksUsage]:
        """
        计算当前 Greeks 使用量
        
        Args:
            positions: 活跃持仓列表
            greeks_map: 合约代码 -> Greeks 映射
            dimension: "underlying" 或 "strategy"
            
        Returns:
            维度键 -> GreeksUsage 映射
        """
        usage_map: Dict[str, GreeksUsage] = {}
        
        for position in positions:
            if not position.is_active or position.volume <= 0:
                continue
            
            # 获取合约的 Greeks
            greeks = greeks_map.get(position.vt_symbol)
            if not greeks or not greeks.success:
                continue
            
            # 确定维度键
            if dimension == "underlying":
                key = position.underlying_vt_symbol
            elif dimension == "strategy":
                key = position.signal
            else:
                continue
            
            # 初始化使用量
            if key not in usage_map:
                usage_map[key] = GreeksUsage()
            
            # 计算合约乘数（期权合约通常为 10000）
            multiplier = 10000.0
            
            # 累加 Greeks 使用量（greek × volume × multiplier）
            usage_map[key].delta_used += abs(greeks.delta * position.volume * multiplier)
            usage_map[key].gamma_used += abs(greeks.gamma * position.volume * multiplier)
            usage_map[key].vega_used += abs(greeks.vega * position.volume * multiplier)
            usage_map[key].position_count += 1
        
        return usage_map
    
    def check_budget_limit(
        self,
        usage: GreeksUsage,
        budget: GreeksBudget
    ) -> BudgetCheckResult:
        """
        检查是否超过预算限额
        
        Args:
            usage: 当前使用量
            budget: 分配的预算
            
        Returns:
            BudgetCheckResult
        """
        exceeded_dimensions: List[str] = []
        
        # 检查 Delta
        if usage.delta_used > budget.delta_budget:
            exceeded_dimensions.append("delta")
        
        # 检查 Gamma
        if usage.gamma_used > budget.gamma_budget:
            exceeded_dimensions.append("gamma")
        
        # 检查 Vega
        if usage.vega_used > budget.vega_budget:
            exceeded_dimensions.append("vega")
        
        passed = len(exceeded_dimensions) == 0
        
        if passed:
            message = "预算检查通过"
        else:
            message = f"预算超限: {', '.join(exceeded_dimensions)}"
        
        return BudgetCheckResult(
            passed=passed,
            exceeded_dimensions=exceeded_dimensions,
            usage=usage,
            budget=budget,
            message=message
        )
    
    def _validate_allocation_ratios(self) -> None:
        """
        验证分配比例的有效性
        
        Raises:
            ValueError: 如果分配比例无效
        """
        if not self._config.allocation_ratios:
            return
        
        # 检查所有比例是否为正数
        for key, ratio in self._config.allocation_ratios.items():
            if ratio < 0:
                raise ValueError(f"分配比例不能为负数: {key} = {ratio}")
        
        # 检查总和是否接近 1.0（允许小误差）
        total_ratio = sum(self._config.allocation_ratios.values())
        if abs(total_ratio - 1.0) > 0.01:
            raise ValueError(
                f"分配比例总和应为 1.0，当前为 {total_ratio:.4f}"
            )
    
    def _calculate_remaining_budget(
        self,
        usage: GreeksUsage,
        budget: GreeksBudget
    ) -> GreeksBudget:
        """
        计算剩余预算
        
        Args:
            usage: 当前使用量
            budget: 分配的预算
            
        Returns:
            剩余预算（不为负数）
        """
        return GreeksBudget(
            delta_budget=max(0.0, budget.delta_budget - usage.delta_used),
            gamma_budget=max(0.0, budget.gamma_budget - usage.gamma_used),
            vega_budget=max(0.0, budget.vega_budget - usage.vega_used)
        )
