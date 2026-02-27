"""
Order 实体 - 订单

追踪订单的生命周期状态。
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from ..value_object.trading.order_instruction import Direction, Offset


class OrderStatus(Enum):
    """订单状态枚举"""
    SUBMITTING = "submitting"       # 提交中
    NOTTRADED = "nottraded"         # 未成交
    PARTTRADED = "parttraded"       # 部分成交
    ALLTRADED = "alltraded"         # 全部成交
    CANCELLED = "cancelled"         # 已撤单
    REJECTED = "rejected"           # 拒单


@dataclass
class Order:
    """
    订单实体
    
    职责:
    1. 委托追踪: 记录订单的生命周期状态 (提交、成交、撤单)
    2. 关联: 关联到具体的策略操作和信号类型
    
    Attributes:
        vt_orderid: VnPy 订单 ID
        vt_symbol: 合约代码
        direction: 交易方向
        offset: 开平标志
        volume: 委托数量
        price: 委托价格
        status: 订单状态
        traded: 已成交数量
        signal: 关联的信号类型
        create_time: 订单创建时间
        update_time: 订单更新时间
    """
    vt_orderid: str
    vt_symbol: str
    direction: Direction
    offset: Offset
    volume: int
    price: float = 0.0
    status: OrderStatus = OrderStatus.SUBMITTING
    traded: int = 0
    signal: str = ""
    create_time: datetime = field(default_factory=datetime.now)
    update_time: Optional[datetime] = None
    
    def update_status(self, new_status: OrderStatus, traded: int = 0) -> None:
        """
        更新订单状态
        
        Args:
            new_status: 新状态
            traded: 已成交数量
        """
        self.status = new_status
        self.traded = traded
        self.update_time = datetime.now()
    
    def add_trade(self, trade_volume: int) -> None:
        """
        记录成交
        
        Args:
            trade_volume: 本次成交数量
        """
        self.traded += trade_volume
        self.update_time = datetime.now()
        
        if self.traded >= self.volume:
            self.status = OrderStatus.ALLTRADED
        elif self.traded > 0:
            self.status = OrderStatus.PARTTRADED
    
    @property
    def is_active(self) -> bool:
        """判断订单是否处于活跃状态 (可能继续成交)"""
        return self.status in (
            OrderStatus.SUBMITTING,
            OrderStatus.NOTTRADED,
            OrderStatus.PARTTRADED
        )
    
    @property
    def is_finished(self) -> bool:
        """判断订单是否已完结 (不会再有状态变化)"""
        return self.status in (
            OrderStatus.ALLTRADED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED
        )
    
    @property
    def is_open_order(self) -> bool:
        """判断是否为开仓订单"""
        return self.offset == Offset.OPEN
    
    @property
    def is_close_order(self) -> bool:
        """判断是否为平仓订单"""
        return self.offset in (Offset.CLOSE, Offset.CLOSETODAY, Offset.CLOSEYESTERDAY)
    
    @property
    def remaining_volume(self) -> int:
        """获取剩余未成交数量"""
        return max(0, self.volume - self.traded)
    
    def __repr__(self) -> str:
        direction_str = "Buy" if self.direction == Direction.LONG else "Sell"
        offset_str = "Open" if self.is_open_order else "Close"
        return (
            f"Order({self.vt_orderid}, {direction_str} {offset_str} "
            f"{self.vt_symbol} {self.traded}/{self.volume} @{self.price:.2f}, "
            f"{self.status.value})"
        )
