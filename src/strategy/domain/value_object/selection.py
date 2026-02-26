"""
Selection 选择服务相关值对象

定义合约选择服务所需的值对象：
- MarketData: 行情数据（用于期货主力合约选择）
- RolloverRecommendation: 移仓换月建议
- CombinationSelectionResult: 组合策略选择结果
- SelectionScore: 合约选择评分
"""
from dataclasses import dataclass
from typing import List

from src.strategy.domain.value_object.combination import CombinationType
from src.strategy.domain.value_object.option_contract import OptionContract


@dataclass(frozen=True)
class MarketData:
    """行情数据（用于期货主力合约选择）"""
    vt_symbol: str           # 合约代码
    volume: int              # 成交量
    open_interest: float     # 持仓量


@dataclass(frozen=True)
class RolloverRecommendation:
    """移仓换月建议"""
    current_contract_symbol: str   # 当前合约代码
    target_contract_symbol: str    # 建议目标合约代码（可为空）
    remaining_days: int            # 当前合约剩余交易日
    reason: str                    # 移仓原因描述
    has_target: bool               # 是否找到合适目标合约


@dataclass(frozen=True)
class CombinationSelectionResult:
    """组合策略选择结果"""
    combination_type: CombinationType  # 组合策略类型
    legs: List[OptionContract]         # 选中的各腿
    success: bool                      # 是否选择成功
    failure_reason: str = ""           # 失败原因


@dataclass(frozen=True)
class SelectionScore:
    """合约选择评分"""
    option_contract: OptionContract    # 期权合约
    liquidity_score: float             # 流动性得分 [0, 1]
    otm_score: float                   # 虚值程度得分 [0, 1]
    expiry_score: float                # 到期日得分 [0, 1]
    total_score: float                 # 加权总分 [0, 1]
