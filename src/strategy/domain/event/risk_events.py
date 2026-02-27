"""
Risk Domain Events - 风险监控领域事件

定义风险管理相关的领域事件。
用于解耦风险监控和后续处理（如告警、平仓指令生成）。
"""
from dataclasses import dataclass, field
from typing import List

from .event_types import DomainEvent


# ========== 止损相关事件 ==========
@dataclass
class StopLossTriggeredEvent(DomainEvent):
    """
    止损触发事件
    
    触发时机: StopLossManager 检测到持仓触发止损条件。
    
    用途:
    - 生成平仓指令
    - 触发飞书告警通知交易员
    - 记录止损触发历史
    """
    vt_symbol: str = ""
    trigger_type: str = ""                       # "fixed" | "trailing" | "portfolio"
    current_loss: float = 0.0
    threshold: float = 0.0
    message: str = ""


# ========== 风险预算相关事件 ==========
@dataclass
class RiskBudgetExceededEvent(DomainEvent):
    """
    风险预算超限事件
    
    触发时机: RiskBudgetAllocator 检测到某品种或策略的 Greeks 使用量超过分配额度。
    
    用途:
    - 阻止新开仓
    - 触发告警通知风险管理人员
    - 记录预算超限历史
    """
    dimension: str = ""                          # "underlying" | "strategy"
    key: str = ""                                # 品种或策略名称
    exceeded_greeks: List[str] = field(default_factory=list)  # ["delta", "gamma"]
    message: str = ""


# ========== 流动性监控相关事件 ==========
@dataclass
class LiquidityDeterioratedEvent(DomainEvent):
    """
    流动性恶化事件
    
    触发时机: LiquidityRiskMonitor 检测到持仓合约的流动性评分低于阈值。
    
    用途:
    - 提醒交易员关注流动性风险
    - 考虑提前平仓或调整持仓
    - 记录流动性变化历史
    """
    vt_symbol: str = ""
    current_score: float = 0.0
    threshold: float = 0.0
    trend: str = ""
    message: str = ""


# ========== 集中度监控相关事件 ==========
@dataclass
class ConcentrationExceededEvent(DomainEvent):
    """
    集中度超限事件
    
    触发时机: ConcentrationMonitor 检测到某维度的集中度超过阈值。
    
    用途:
    - 阻止在该维度继续开仓
    - 提醒风险管理人员调整持仓结构
    - 记录集中度超限历史
    """
    dimension: str = ""                          # "underlying" | "expiry" | "strike" | "hhi"
    key: str = ""
    concentration: float = 0.0
    limit: float = 0.0
    message: str = ""


# ========== 时间衰减监控相关事件 ==========
@dataclass
class ExpiryWarningEvent(DomainEvent):
    """
    到期提醒事件
    
    触发时机: TimeDecayMonitor 检测到持仓距离到期日少于配置的临界天数。
    
    用途:
    - 提醒交易员及时处理临近到期的持仓
    - 避免到期日被动行权或放弃
    - 记录到期提醒历史
    """
    vt_symbol: str = ""
    expiry_date: str = ""
    days_to_expiry: int = 0
    urgency: str = ""                            # "warning" | "critical"
    message: str = ""
