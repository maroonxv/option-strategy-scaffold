"""
AdvancedOrderScheduler - 高级订单调度器

统一管理冰山单、TWAP、VWAP 的拆单逻辑和子单生命周期。
"""
import math
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from src.strategy.domain.value_object.order_instruction import OrderInstruction
from src.strategy.domain.value_object.advanced_order import (
    AdvancedOrder, AdvancedOrderRequest, AdvancedOrderStatus,
    AdvancedOrderType, ChildOrder, SliceEntry,
)
from src.strategy.domain.event.event_types import (
    DomainEvent, IcebergCompleteEvent, IcebergCancelledEvent,
    TWAPCompleteEvent, VWAPCompleteEvent, TimedSplitCompleteEvent,
    ClassicIcebergCompleteEvent, ClassicIcebergCancelledEvent,
    EnhancedTWAPCompleteEvent,
)


class AdvancedOrderScheduler:
    """高级订单调度器"""

    def __init__(self):
        self._orders: Dict[str, AdvancedOrder] = {}

    def submit_iceberg(self, instruction: OrderInstruction, batch_size: int) -> AdvancedOrder:
        """提交冰山单，拆分为子单"""
        total_volume = instruction.volume
        if total_volume <= 0:
            raise ValueError("总量必须大于 0")
        if batch_size <= 0:
            raise ValueError("每批数量必须大于 0")

        order_id = str(uuid.uuid4())
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType.ICEBERG,
            instruction=instruction,
            batch_size=batch_size,
        )

        # 拆分子单
        child_orders: List[ChildOrder] = []
        remaining = total_volume
        idx = 0
        while remaining > 0:
            vol = min(batch_size, remaining)
            child = ChildOrder(
                child_id=f"{order_id}_child_{idx}",
                parent_id=order_id,
                volume=vol,
            )
            child_orders.append(child)
            remaining -= vol
            idx += 1

        order = AdvancedOrder(
            order_id=order_id,
            request=request,
            status=AdvancedOrderStatus.EXECUTING,
            child_orders=child_orders,
        )
        self._orders[order_id] = order
        return order
    def submit_timed_split(
        self,
        instruction: OrderInstruction,
        interval_seconds: int,
        per_order_volume: int,
        start_time: datetime,
    ) -> AdvancedOrder:
        """提交定时拆单"""
        total_volume = instruction.volume
        if total_volume <= 0:
            raise ValueError("总量必须大于 0")
        if interval_seconds <= 0:
            raise ValueError("时间间隔必须大于 0")
        if per_order_volume <= 0:
            raise ValueError("每笔数量必须大于 0")

        order_id = str(uuid.uuid4())
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType.TIMED_SPLIT,
            instruction=instruction,
            interval_seconds=interval_seconds,
            per_order_volume=per_order_volume,
        )

        # 拆分子单
        child_orders: List[ChildOrder] = []
        slice_schedule: List[SliceEntry] = []
        remaining = total_volume
        idx = 0
        while remaining > 0:
            vol = min(per_order_volume, remaining)
            scheduled = start_time + timedelta(seconds=interval_seconds * idx)
            child = ChildOrder(
                child_id=f"{order_id}_child_{idx}",
                parent_id=order_id,
                volume=vol,
                scheduled_time=scheduled,
            )
            child_orders.append(child)
            slice_schedule.append(SliceEntry(scheduled_time=scheduled, volume=vol))
            remaining -= vol
            idx += 1

        order = AdvancedOrder(
            order_id=order_id,
            request=request,
            status=AdvancedOrderStatus.EXECUTING,
            child_orders=child_orders,
            slice_schedule=slice_schedule,
        )
        self._orders[order_id] = order
        return order

    def submit_timed_split(
        self,
        instruction: OrderInstruction,
        interval_seconds: int,
        per_order_volume: int,
        start_time: datetime,
    ) -> AdvancedOrder:
        """提交定时拆单"""
        total_volume = instruction.volume
        if total_volume <= 0:
            raise ValueError("总量必须大于 0")
        if interval_seconds <= 0:
            raise ValueError("时间间隔必须大于 0")
        if per_order_volume <= 0:
            raise ValueError("每笔数量必须大于 0")

        order_id = str(uuid.uuid4())
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType.TIMED_SPLIT,
            instruction=instruction,
            interval_seconds=interval_seconds,
            per_order_volume=per_order_volume,
        )

        # 拆分子单
        child_orders: List[ChildOrder] = []
        slice_schedule: List[SliceEntry] = []
        remaining = total_volume
        idx = 0
        while remaining > 0:
            vol = min(per_order_volume, remaining)
            scheduled = start_time + timedelta(seconds=interval_seconds * idx)
            child = ChildOrder(
                child_id=f"{order_id}_child_{idx}",
                parent_id=order_id,
                volume=vol,
                scheduled_time=scheduled,
            )
            child_orders.append(child)
            slice_schedule.append(SliceEntry(scheduled_time=scheduled, volume=vol))
            remaining -= vol
            idx += 1

        order = AdvancedOrder(
            order_id=order_id,
            request=request,
            status=AdvancedOrderStatus.EXECUTING,
            child_orders=child_orders,
            slice_schedule=slice_schedule,
        )
        self._orders[order_id] = order
        return order

    def submit_classic_iceberg(
        self,
        instruction: OrderInstruction,
        per_order_volume: int,
        volume_randomize_ratio: float = 0.0,
        price_offset_ticks: int = 0,
        price_tick: float = 0.0,
    ) -> AdvancedOrder:
        """提交经典冰山单"""
        total_volume = instruction.volume
        if total_volume <= 0:
            raise ValueError("总量必须大于 0")
        if per_order_volume <= 0:
            raise ValueError("每笔数量必须大于 0")
        if volume_randomize_ratio < 0 or volume_randomize_ratio >= 1:
            raise ValueError("随机比例必须在 [0, 1) 范围内")
        if price_offset_ticks > 0 and price_tick <= 0:
            raise ValueError("使用价格偏移时 price_tick 必须大于 0")

        order_id = str(uuid.uuid4())
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType.CLASSIC_ICEBERG,
            instruction=instruction,
            per_order_volume=per_order_volume,
            volume_randomize_ratio=volume_randomize_ratio,
            price_offset_ticks=price_offset_ticks,
            price_tick=price_tick,
        )

        # 拆分子单
        child_orders: List[ChildOrder] = []
        remaining = total_volume
        idx = 0
        while remaining > 0:
            if volume_randomize_ratio > 0 and remaining > 1:
                low = per_order_volume * (1 - volume_randomize_ratio)
                high = per_order_volume * (1 + volume_randomize_ratio)
                randomized = random.uniform(low, high)
                vol = max(1, min(round(randomized), remaining))
            else:
                vol = min(per_order_volume, remaining)

            # 价格偏移
            if price_offset_ticks > 0 and price_tick > 0:
                offset = random.uniform(-price_offset_ticks, price_offset_ticks) * price_tick
            else:
                offset = 0.0

            child = ChildOrder(
                child_id=f"{order_id}_child_{idx}",
                parent_id=order_id,
                volume=vol,
                price_offset=offset,
            )
            child_orders.append(child)
            remaining -= vol
            idx += 1

        order = AdvancedOrder(
            order_id=order_id,
            request=request,
            status=AdvancedOrderStatus.EXECUTING,
            child_orders=child_orders,
        )
        self._orders[order_id] = order
        return order

    def submit_enhanced_twap(
        self,
        instruction: OrderInstruction,
        time_window_seconds: int,
        num_slices: int,
        start_time: datetime,
    ) -> AdvancedOrder:
        """提交增强型 TWAP"""
        total_volume = instruction.volume
        if total_volume <= 0:
            raise ValueError("总量必须大于 0")
        if time_window_seconds <= 0:
            raise ValueError("时间窗口必须大于 0")
        if num_slices <= 0:
            raise ValueError("分片数必须大于 0")

        order_id = str(uuid.uuid4())
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType.ENHANCED_TWAP,
            instruction=instruction,
            time_window_seconds=time_window_seconds,
            num_slices=num_slices,
        )

        # 均匀分配: 基础量 + 余数分配给前几片
        base_vol = total_volume // num_slices
        remainder = total_volume % num_slices
        interval = time_window_seconds / num_slices

        child_orders: List[ChildOrder] = []
        slice_schedule: List[SliceEntry] = []
        for i in range(num_slices):
            vol = base_vol + (1 if i < remainder else 0)
            scheduled = start_time + timedelta(seconds=round(interval * i))
            child = ChildOrder(
                child_id=f"{order_id}_child_{i}",
                parent_id=order_id,
                volume=vol,
                scheduled_time=scheduled,
            )
            child_orders.append(child)
            slice_schedule.append(SliceEntry(scheduled_time=scheduled, volume=vol))

        order = AdvancedOrder(
            order_id=order_id,
            request=request,
            status=AdvancedOrderStatus.EXECUTING,
            child_orders=child_orders,
            slice_schedule=slice_schedule,
        )
        self._orders[order_id] = order
        return order


    def submit_twap(self, instruction: OrderInstruction, time_window_seconds: int,
                    num_slices: int, start_time: datetime) -> AdvancedOrder:
        """提交 TWAP 单，均匀分配到时间片"""
        total_volume = instruction.volume
        if total_volume <= 0:
            raise ValueError("总量必须大于 0")
        if time_window_seconds <= 0:
            raise ValueError("时间窗口必须大于 0")
        if num_slices <= 0:
            raise ValueError("分片数必须大于 0")

        order_id = str(uuid.uuid4())
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType.TWAP,
            instruction=instruction,
            time_window_seconds=time_window_seconds,
            num_slices=num_slices,
        )

        # 均匀分配: 基础量 + 余数分配给前几片
        base_vol = total_volume // num_slices
        remainder = total_volume % num_slices
        interval = time_window_seconds / num_slices

        child_orders: List[ChildOrder] = []
        slice_schedule: List[SliceEntry] = []
        for i in range(num_slices):
            vol = base_vol + (1 if i < remainder else 0)
            scheduled = start_time + timedelta(seconds=round(interval * i))
            child = ChildOrder(
                child_id=f"{order_id}_child_{i}",
                parent_id=order_id,
                volume=vol,
                scheduled_time=scheduled,
            )
            child_orders.append(child)
            slice_schedule.append(SliceEntry(scheduled_time=scheduled, volume=vol))

        order = AdvancedOrder(
            order_id=order_id,
            request=request,
            status=AdvancedOrderStatus.EXECUTING,
            child_orders=child_orders,
            slice_schedule=slice_schedule,
        )
        self._orders[order_id] = order
        return order

    def submit_vwap(self, instruction: OrderInstruction, time_window_seconds: int,
                    volume_profile: List[float], start_time: datetime) -> AdvancedOrder:
        """提交 VWAP 单，按成交量分布比例分配"""
        total_volume = instruction.volume
        if total_volume <= 0:
            raise ValueError("总量必须大于 0")
        if time_window_seconds <= 0:
            raise ValueError("时间窗口必须大于 0")
        if not volume_profile or len(volume_profile) == 0:
            raise ValueError("成交量分布不能为空")
        if any(w <= 0 for w in volume_profile):
            raise ValueError("成交量分布权重必须为正数")

        order_id = str(uuid.uuid4())
        num_slices = len(volume_profile)
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType.VWAP,
            instruction=instruction,
            time_window_seconds=time_window_seconds,
            volume_profile=list(volume_profile),
        )

        # 按权重比例分配，使用最大余数法确保总量精确
        total_weight = sum(volume_profile)
        raw_volumes = [(total_volume * w / total_weight) for w in volume_profile]
        floor_volumes = [int(v) for v in raw_volumes]
        remainder = total_volume - sum(floor_volumes)
        # 按小数部分降序分配余数
        fractional_parts = [(raw_volumes[i] - floor_volumes[i], i) for i in range(num_slices)]
        fractional_parts.sort(key=lambda x: x[0], reverse=True)
        for j in range(remainder):
            floor_volumes[fractional_parts[j][1]] += 1

        interval = time_window_seconds / num_slices
        child_orders: List[ChildOrder] = []
        slice_schedule: List[SliceEntry] = []
        for i in range(num_slices):
            scheduled = start_time + timedelta(seconds=round(interval * i))
            child = ChildOrder(
                child_id=f"{order_id}_child_{i}",
                parent_id=order_id,
                volume=floor_volumes[i],
                scheduled_time=scheduled,
            )
            child_orders.append(child)
            slice_schedule.append(SliceEntry(scheduled_time=scheduled, volume=floor_volumes[i]))

        order = AdvancedOrder(
            order_id=order_id,
            request=request,
            status=AdvancedOrderStatus.EXECUTING,
            child_orders=child_orders,
            slice_schedule=slice_schedule,
        )
        self._orders[order_id] = order
        return order

    def on_child_filled(self, child_id: str) -> List[DomainEvent]:
        """子单成交回报处理，更新 filled_volume 并检查是否全部成交"""
        events: List[DomainEvent] = []
        for order in self._orders.values():
            for child in order.child_orders:
                if child.child_id == child_id and not child.is_filled:
                    child.is_filled = True
                    order.filled_volume += child.volume

                    # 检查是否全部成交
                    if all(c.is_filled for c in order.child_orders):
                        order.status = AdvancedOrderStatus.COMPLETED
                        vt_symbol = order.request.instruction.vt_symbol
                        total_vol = order.request.instruction.volume
                        if order.request.order_type == AdvancedOrderType.ICEBERG:
                            events.append(IcebergCompleteEvent(
                                order_id=order.order_id,
                                vt_symbol=vt_symbol,
                                total_volume=total_vol,
                                filled_volume=order.filled_volume,
                            ))
                        elif order.request.order_type == AdvancedOrderType.TWAP:
                            events.append(TWAPCompleteEvent(
                                order_id=order.order_id,
                                vt_symbol=vt_symbol,
                                total_volume=total_vol,
                            ))
                        elif order.request.order_type == AdvancedOrderType.VWAP:
                            events.append(VWAPCompleteEvent(
                                order_id=order.order_id,
                                vt_symbol=vt_symbol,
                                total_volume=total_vol,
                            ))
                        elif order.request.order_type == AdvancedOrderType.TIMED_SPLIT:
                            events.append(TimedSplitCompleteEvent(
                                order_id=order.order_id,
                                vt_symbol=vt_symbol,
                                total_volume=total_vol,
                                filled_volume=order.filled_volume,
                            ))
                        elif order.request.order_type == AdvancedOrderType.CLASSIC_ICEBERG:
                            events.append(ClassicIcebergCompleteEvent(
                                order_id=order.order_id,
                                vt_symbol=vt_symbol,
                                total_volume=total_vol,
                                filled_volume=order.filled_volume,
                            ))
                        elif order.request.order_type == AdvancedOrderType.ENHANCED_TWAP:
                            events.append(EnhancedTWAPCompleteEvent(
                                order_id=order.order_id,
                                vt_symbol=vt_symbol,
                                total_volume=total_vol,
                            ))
                    return events
        return events

    def get_pending_children(self, current_time: datetime) -> List[ChildOrder]:
        """获取当前时刻应提交的子单"""
        pending: List[ChildOrder] = []
        for order in self._orders.values():
            if order.status != AdvancedOrderStatus.EXECUTING:
                continue

            if order.request.order_type in (AdvancedOrderType.ICEBERG, AdvancedOrderType.CLASSIC_ICEBERG):
                # 冰山单/经典冰山单: 前一批已成交才提交下一批
                for child in order.child_orders:
                    if not child.is_submitted and not child.is_filled:
                        # 检查前面所有子单是否已成交
                        idx = order.child_orders.index(child)
                        all_prev_filled = all(
                            c.is_filled for c in order.child_orders[:idx]
                        )
                        if all_prev_filled:
                            pending.append(child)
                        break  # 冰山单一次只提交一个
            elif order.request.order_type in (
                AdvancedOrderType.TWAP,
                AdvancedOrderType.VWAP,
                AdvancedOrderType.TIMED_SPLIT,
                AdvancedOrderType.ENHANCED_TWAP,
            ):
                # TWAP/VWAP/TIMED_SPLIT/ENHANCED_TWAP: 到达调度时间的子单
                for child in order.child_orders:
                    if (not child.is_submitted and not child.is_filled
                            and child.scheduled_time is not None
                            and current_time >= child.scheduled_time):
                        pending.append(child)
        return pending

    def cancel_order(self, order_id: str) -> Tuple[List[str], List[DomainEvent]]:
        """取消高级订单，返回需撤销的子单 ID 列表和取消事件"""
        if order_id not in self._orders:
            return [], []

        order = self._orders[order_id]
        if order.status in (AdvancedOrderStatus.COMPLETED, AdvancedOrderStatus.CANCELLED):
            return [], []

        order.status = AdvancedOrderStatus.CANCELLED
        # 收集未成交的已提交子单 ID (需要撤销)
        cancel_ids = [
            c.child_id for c in order.child_orders
            if c.is_submitted and not c.is_filled
        ]

        remaining = sum(c.volume for c in order.child_orders if not c.is_filled)
        events: List[DomainEvent] = []
        vt_symbol = order.request.instruction.vt_symbol

        if order.request.order_type == AdvancedOrderType.ICEBERG:
            events.append(IcebergCancelledEvent(
                order_id=order.order_id,
                vt_symbol=vt_symbol,
                filled_volume=order.filled_volume,
                remaining_volume=remaining,
            ))
        elif order.request.order_type == AdvancedOrderType.CLASSIC_ICEBERG:
            events.append(ClassicIcebergCancelledEvent(
                order_id=order.order_id,
                vt_symbol=vt_symbol,
                filled_volume=order.filled_volume,
                remaining_volume=remaining,
            ))

        return cancel_ids, events

    def get_order(self, order_id: str) -> Optional[AdvancedOrder]:
        """获取高级订单"""
        return self._orders.get(order_id)
