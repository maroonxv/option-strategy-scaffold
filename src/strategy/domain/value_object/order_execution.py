"""
订单执行相关值对象

定义订单执行配置和受管理订单状态。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict

from .order_instruction import OrderInstruction, Direction, Offset, OrderType


@dataclass(frozen=True)
class OrderExecutionConfig:
    """
    订单执行配置

    Attributes:
        timeout_seconds: 超时秒数
        max_retries: 最大重试次数
        slippage_ticks: 滑点跳数
        price_tick: 最小变动价位
    """
    timeout_seconds: int = 30
    max_retries: int = 3
    slippage_ticks: int = 2
    price_tick: float = 0.2


@dataclass
class ManagedOrder:
    """
    受管理的订单状态

    Attributes:
        vt_orderid: 订单 ID
        instruction: 原始交易指令
        submit_time: 提交时间
        retry_count: 已重试次数
        is_active: 是否活跃
    """
    vt_orderid: str
    instruction: OrderInstruction
    submit_time: datetime
    retry_count: int = 0
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典 (JSON 兼容)"""
        return {
            "vt_orderid": self.vt_orderid,
            "instruction": {
                "vt_symbol": self.instruction.vt_symbol,
                "direction": self.instruction.direction.value,
                "offset": self.instruction.offset.value,
                "volume": self.instruction.volume,
                "price": self.instruction.price,
                "signal": self.instruction.signal,
                "order_type": self.instruction.order_type.value,
            },
            "submit_time": self.submit_time.isoformat(),
            "retry_count": self.retry_count,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManagedOrder":
        """从字典反序列化"""
        instr_data = data["instruction"]
        instruction = OrderInstruction(
            vt_symbol=instr_data["vt_symbol"],
            direction=Direction(instr_data["direction"]),
            offset=Offset(instr_data["offset"]),
            volume=instr_data["volume"],
            price=instr_data["price"],
            signal=instr_data.get("signal", ""),
            order_type=OrderType(instr_data.get("order_type", "limit")),
        )
        return cls(
            vt_orderid=data["vt_orderid"],
            instruction=instruction,
            submit_time=datetime.fromisoformat(data["submit_time"]),
            retry_count=data["retry_count"],
            is_active=data["is_active"],
        )
