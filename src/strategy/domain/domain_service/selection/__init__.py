"""
Selection 合约选择领域服务

导出：
- BaseFutureSelector: 期货合约选择器（主力合约选择、到期日过滤、移仓换月）
- OptionSelectorService: 期权选择服务（组合选择、Delta 感知选择、评分排名）
- MarketData: 行情数据值对象
- RolloverRecommendation: 移仓换月建议值对象
- CombinationSelectionResult: 组合策略选择结果值对象
- SelectionScore: 合约选择评分值对象
"""

from src.strategy.domain.domain_service.selection.future_selection_service import BaseFutureSelector
from src.strategy.domain.domain_service.selection.option_selector_service import OptionSelectorService
from src.strategy.domain.value_object.selection.selection import (
    MarketData,
    RolloverRecommendation,
    CombinationSelectionResult,
    SelectionScore,
)

__all__ = [
    "BaseFutureSelector",
    "OptionSelectorService",
    "MarketData",
    "RolloverRecommendation",
    "CombinationSelectionResult",
    "SelectionScore",
]
