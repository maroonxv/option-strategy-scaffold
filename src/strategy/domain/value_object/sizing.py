"""
Sizing Value Object

仓位计算综合结果值对象。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SizingResult:
    """仓位计算综合结果"""
    final_volume: int          # 最终手数（0 表示拒绝）
    margin_volume: int         # 保证金维度允许手数
    usage_volume: int          # 使用率维度允许手数
    greeks_volume: int         # Greeks 维度允许手数
    delta_budget: float        # Delta 剩余空间
    gamma_budget: float        # Gamma 剩余空间
    vega_budget: float         # Vega 剩余空间
    passed: bool               # 是否通过
    reject_reason: str = ""    # 拒绝原因
