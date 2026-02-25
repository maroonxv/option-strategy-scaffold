"""
Domain Events - 领域事件

定义策略领域内的事件类型和事件数据结构。
用于解耦业务逻辑和副作用 (如通知、日志)。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


# ========== VnPy 事件类型常量 ==========
EVENT_STRATEGY_ALERT = "eStrategyAlert."    # 飞书告警事件
EVENT_STRATEGY_LOG = "eStrategyLog."        # 策略日志事件


# ========== 领域事件基类 ==========
@dataclass
class DomainEvent:
    """
    领域事件基类
    
    所有领域事件都应继承此类。
    """
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def event_name(self) -> str:
        """获取事件名称"""
        return self.__class__.__name__


# ========== 具体领域事件 ==========
@dataclass
class ManualCloseDetectedEvent(DomainEvent):
    """
    手动平仓侦测事件
    
    触发时机: PositionAggregate 检测到持仓量减少，
    且该减少并非由策略发出的订单触发。
    
    用途:
    - 修正策略内部持仓状态，避免逻辑错乱
    - 触发飞书告警通知交易员
    """
    vt_symbol: str = ""
    volume: float = 0.0


@dataclass
class ManualOpenDetectedEvent(DomainEvent):
    """
    手动开仓侦测事件
    
    触发时机: 检测到非策略发起的开仓操作。
    
    用途:
    - 提醒交易员程序不会自动平仓这部分持仓
    """
    vt_symbol: str = ""
    volume: float = 0.0


@dataclass
class SignalGeneratedEvent(DomainEvent):
    """
    信号生成事件
    
    触发时机: SignalService 检测到开仓或平仓信号。
    
    用途:
    - 记录信号产生的时间、依据
    - 用于回测分析或实时通知
    """
    vt_symbol: str = ""
    signal: str = ""  # 信号字符串
    reason: str = ""


@dataclass
class OrderInstructionGeneratedEvent(DomainEvent):
    """
    交易指令生成事件
    
    触发时机: PositionSizingService 生成了有效的交易指令。
    
    用途:
    - 记录策略的"决策"结果
    - 区别于最终的"执行"结果 (成交)
    """
    vt_symbol: str = ""
    direction: str = ""
    offset: str = ""
    volume: int = 0
    price: float = 0.0


@dataclass
class OrderStatusChangedEvent(DomainEvent):
    """
    订单状态变更事件
    
    触发时机: 订单状态发生变化 (撤单、拒单等)。
    """
    vt_orderid: str = ""
    vt_symbol: str = ""
    old_status: str = ""
    new_status: str = ""
    message: str = ""


@dataclass
class PositionClosedEvent(DomainEvent):
    """
    持仓平仓事件
    
    触发时机: 持仓完全平仓。
    """
    vt_symbol: str = ""
    signal: str = ""  # 信号字符串
    holding_seconds: float = 0.0
    pnl: float = 0.0


@dataclass
class RiskLimitExceededEvent(DomainEvent):
    """
    风控限额超标事件
    
    触发时机: 每日开仓量达到或超过阈值。
    """
    vt_symbol: str = ""
    limit_type: str = ""  # "global" or "contract"
    current_volume: int = 0
    limit_volume: int = 0


@dataclass
class GreeksRiskBreachEvent(DomainEvent):
    """
    Greeks 风控阈值突破事件

    触发时机: 持仓级或组合级 Greeks 超过配置的阈值。
    """
    level: str = ""          # "position" | "portfolio"
    greek_name: str = ""     # "delta" | "gamma" | "vega"
    current_value: float = 0.0
    limit_value: float = 0.0
    vt_symbol: str = ""


@dataclass
class OrderTimeoutEvent(DomainEvent):
    """
    订单超时事件

    触发时机: 限价单在配置的超时时间内未完全成交。
    """
    vt_orderid: str = ""
    vt_symbol: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class OrderRetryExhaustedEvent(DomainEvent):
    """
    订单重试耗尽事件

    触发时机: 订单超时撤销后重试次数达到上限。
    """
    vt_symbol: str = ""
    total_retries: int = 0
    original_price: float = 0.0
    final_price: float = 0.0


# ========== 策略告警数据 (用于飞书通知) ==========
@dataclass
class StrategyAlertData:
    """
    策略告警数据
    
    用于通过 VnPy EventEngine 发送告警通知。
    飞书 Handler 订阅此类型的事件并发送消息。
    """
    strategy_name: str
    alert_type: str           # "manual_open", "manual_close", "order_rejected", etc.
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    vt_symbol: str = ""
    volume: float = 0
    extra: dict = field(default_factory=dict)
    
    @classmethod
    def from_domain_event(
        cls,
        event: DomainEvent,
        strategy_name: str,
        alert_type: str,
        message: str
    ) -> "StrategyAlertData":
        """
        从领域事件创建告警数据
        
        Args:
            event: 领域事件
            strategy_name: 策略名称
            alert_type: 告警类型
            message: 告警消息
            
        Returns:
            StrategyAlertData 实例
        """
        vt_symbol = getattr(event, "vt_symbol", "")
        volume = getattr(event, "volume", 0)
        
        return cls(
            strategy_name=strategy_name,
            alert_type=alert_type,
            message=message,
            timestamp=event.timestamp,
            vt_symbol=vt_symbol,
            volume=volume,
        )


# ========== 高级订单事件 ==========
@dataclass
class IcebergCompleteEvent(DomainEvent):
    """冰山单完成事件"""
    order_id: str = ""
    vt_symbol: str = ""
    total_volume: int = 0
    filled_volume: int = 0


@dataclass
class IcebergCancelledEvent(DomainEvent):
    """冰山单取消事件"""
    order_id: str = ""
    vt_symbol: str = ""
    filled_volume: int = 0
    remaining_volume: int = 0


@dataclass
class TWAPCompleteEvent(DomainEvent):
    """TWAP 完成事件"""
    order_id: str = ""
    vt_symbol: str = ""
    total_volume: int = 0


@dataclass
class VWAPCompleteEvent(DomainEvent):
    """VWAP 完成事件"""
    order_id: str = ""
    vt_symbol: str = ""
    total_volume: int = 0


@dataclass
class TimedSplitCompleteEvent(DomainEvent):
    """定时拆单完成事件"""
    order_id: str = ""
    vt_symbol: str = ""
    total_volume: int = 0
    filled_volume: int = 0


@dataclass
class ClassicIcebergCompleteEvent(DomainEvent):
    """经典冰山单完成事件"""
    order_id: str = ""
    vt_symbol: str = ""
    total_volume: int = 0
    filled_volume: int = 0


@dataclass
class ClassicIcebergCancelledEvent(DomainEvent):
    """经典冰山单取消事件"""
    order_id: str = ""
    vt_symbol: str = ""
    filled_volume: int = 0
    remaining_volume: int = 0


@dataclass
class EnhancedTWAPCompleteEvent(DomainEvent):
    """增强型 TWAP 完成事件"""
    order_id: str = ""
    vt_symbol: str = ""
    total_volume: int = 0


# ========== 对冲引擎事件 ==========
@dataclass
class HedgeExecutedEvent(DomainEvent):
    """对冲执行事件"""
    hedge_volume: int = 0
    hedge_direction: str = ""
    portfolio_delta_before: float = 0.0
    portfolio_delta_after: float = 0.0
    hedge_instrument: str = ""


@dataclass
class GammaScalpEvent(DomainEvent):
    """Gamma Scalping 再平衡事件"""
    rebalance_volume: int = 0
    rebalance_direction: str = ""
    portfolio_delta_before: float = 0.0
    portfolio_gamma: float = 0.0
    hedge_instrument: str = ""


@dataclass
class VegaHedgeExecutedEvent(DomainEvent):
    """Vega 对冲执行事件"""
    hedge_volume: int = 0
    hedge_direction: str = ""
    portfolio_vega_before: float = 0.0
    portfolio_vega_after: float = 0.0
    hedge_instrument: str = ""
    delta_impact: float = 0.0
    gamma_impact: float = 0.0
    theta_impact: float = 0.0


# ========== 组合策略事件 ==========
@dataclass
class CombinationStatusChangedEvent(DomainEvent):
    """
    组合状态变更事件
    
    触发时机: Combination 的状态发生变化（如从 ACTIVE 变为 PARTIALLY_CLOSED）。
    """
    combination_id: str = ""
    old_status: str = ""
    new_status: str = ""
    combination_type: str = ""


    # ========== 组合策略事件 ==========
    @dataclass
    class CombinationStatusChangedEvent(DomainEvent):
        """
        组合状态变更事件

        触发时机: Combination 的状态发生变化（如从 ACTIVE 变为 PARTIALLY_CLOSED）。
        """
        combination_id: str = ""
        old_status: str = ""
        new_status: str = ""
        combination_type: str = ""


