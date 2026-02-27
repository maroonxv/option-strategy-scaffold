"""
Selection 子模块 - 选择服务相关值对象

包含行情数据、移仓建议、组合选择结果、评分和期权选择配置等。
"""
from .selection import MarketData, RolloverRecommendation, CombinationSelectionResult, SelectionScore
from .option_selector_config import OptionSelectorConfig

__all__ = [
    "MarketData",
    "RolloverRecommendation",
    "CombinationSelectionResult",
    "SelectionScore",
    "OptionSelectorConfig",
]
