"""
高级订单相关值对象

定义冰山单、TWAP、VWAP 的订单类型枚举、状态枚举和数据类。
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.strategy.domain.value_object.trading.order_instruction import OrderInstruction, Direction, Offset, OrderType


class AdvancedOrderType(Enum):
    """高级订单类型"""
    ICEBERG = "iceberg"
    TWAP = "twap"
    VWAP = "vwap"
    TIMED_SPLIT = "timed_split"
    CLASSIC_ICEBERG = "classic_iceberg"
    ENHANCED_TWAP = "enhanced_twap"



class AdvancedOrderStatus(Enum):
    """高级订单状态"""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class SliceEntry:
    """时间片条目"""
    scheduled_time: datetime
    volume: int


@dataclass
class ChildOrder:
    """子单"""
    child_id: str
    parent_id: str
    volume: int
    scheduled_time: Optional[datetime] = None
    is_submitted: bool = False
    is_filled: bool = False
    price_offset: float = 0.0


@dataclass
class AdvancedOrderRequest:
    """高级订单请求"""
    order_type: AdvancedOrderType
    instruction: OrderInstruction
    batch_size: int = 0
    time_window_seconds: int = 0
    num_slices: int = 0
    volume_profile: List[float] = field(default_factory=list)
    interval_seconds: int = 0
    per_order_volume: int = 0
    volume_randomize_ratio: float = 0.0
    price_offset_ticks: int = 0
    price_tick: float = 0.0


@dataclass
class AdvancedOrder:
    """高级订单状态"""
    order_id: str
    request: AdvancedOrderRequest
    status: AdvancedOrderStatus = AdvancedOrderStatus.PENDING
    filled_volume: int = 0
    child_orders: List[ChildOrder] = field(default_factory=list)
    created_time: datetime = field(default_factory=datetime.now)
    slice_schedule: List[SliceEntry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典 (JSON 兼容)"""
        return {
            "order_id": self.order_id,
            "request": {
                "order_type": self.request.order_type.value,
                "instruction": {
                    "vt_symbol": self.request.instruction.vt_symbol,
                    "direction": self.request.instruction.direction.value,
                    "offset": self.request.instruction.offset.value,
                    "volume": self.request.instruction.volume,
                    "price": self.request.instruction.price,
                    "signal": self.request.instruction.signal,
                    "order_type": self.request.instruction.order_type.value,
                },
                "batch_size": self.request.batch_size,
                "time_window_seconds": self.request.time_window_seconds,
                "num_slices": self.request.num_slices,
                "volume_profile": self.request.volume_profile,
                "interval_seconds": self.request.interval_seconds,
                "per_order_volume": self.request.per_order_volume,
                "volume_randomize_ratio": self.request.volume_randomize_ratio,
                "price_offset_ticks": self.request.price_offset_ticks,
                "price_tick": self.request.price_tick,
            },
            "status": self.status.value,
            "filled_volume": self.filled_volume,
            "child_orders": [
                {
                    "child_id": c.child_id,
                    "parent_id": c.parent_id,
                    "volume": c.volume,
                    "scheduled_time": c.scheduled_time.isoformat() if c.scheduled_time else None,
                    "is_submitted": c.is_submitted,
                    "is_filled": c.is_filled,
                    "price_offset": c.price_offset,
                }
                for c in self.child_orders
            ],
            "created_time": self.created_time.isoformat(),
            "slice_schedule": [
                {
                    "scheduled_time": s.scheduled_time.isoformat(),
                    "volume": s.volume,
                }
                for s in self.slice_schedule
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdvancedOrder":
        """从字典反序列化"""
        req_data = data["request"]
        instr_data = req_data["instruction"]
        instruction = OrderInstruction(
            vt_symbol=instr_data["vt_symbol"],
            direction=Direction(instr_data["direction"]),
            offset=Offset(instr_data["offset"]),
            volume=instr_data["volume"],
            price=instr_data["price"],
            signal=instr_data.get("signal", ""),
            order_type=OrderType(instr_data.get("order_type", "limit")),
        )
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType(req_data["order_type"]),
            instruction=instruction,
            batch_size=req_data.get("batch_size", 0),
            time_window_seconds=req_data.get("time_window_seconds", 0),
            num_slices=req_data.get("num_slices", 0),
            volume_profile=req_data.get("volume_profile", []),
            interval_seconds=req_data.get("interval_seconds", 0),
            per_order_volume=req_data.get("per_order_volume", 0),
            volume_randomize_ratio=req_data.get("volume_randomize_ratio", 0.0),
            price_offset_ticks=req_data.get("price_offset_ticks", 0),
            price_tick=req_data.get("price_tick", 0.0),
        )
        child_orders = [
            ChildOrder(
                child_id=c["child_id"],
                parent_id=c["parent_id"],
                volume=c["volume"],
                scheduled_time=datetime.fromisoformat(c["scheduled_time"]) if c.get("scheduled_time") else None,
                is_submitted=c["is_submitted"],
                is_filled=c["is_filled"],
                price_offset=c.get("price_offset", 0.0),
            )
            for c in data.get("child_orders", [])
        ]
        slice_schedule = [
            SliceEntry(
                scheduled_time=datetime.fromisoformat(s["scheduled_time"]),
                volume=s["volume"],
            )
            for s in data.get("slice_schedule", [])
        ]
        return cls(
            order_id=data["order_id"],
            request=request,
            status=AdvancedOrderStatus(data["status"]),
            filled_volume=data.get("filled_volume", 0),
            child_orders=child_orders,
            created_time=datetime.fromisoformat(data["created_time"]),
            slice_schedule=slice_schedule,
        )
