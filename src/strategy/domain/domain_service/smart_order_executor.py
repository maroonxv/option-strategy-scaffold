"""
SmartOrderExecutor 领域服务

自适应价格计算、超时管理、重试逻辑。
不直接调用网关，返回执行指令。
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..value_object.order_instruction import OrderInstruction, Direction, Offset
from ..value_object.order_execution import OrderExecutionConfig, ManagedOrder
from ..event.event_types import DomainEvent, OrderTimeoutEvent, OrderRetryExhaustedEvent


class SmartOrderExecutor:
    """
    智能订单执行器

    职责:
    1. 自适应委托价格计算
    2. 价格对齐到最小变动价位
    3. 订单超时管理
    4. 订单重试逻辑
    """

    def __init__(self, config: OrderExecutionConfig) -> None:
        self.config = config
        self._orders: Dict[str, ManagedOrder] = {}

    def calculate_adaptive_price(
        self,
        instruction: OrderInstruction,
        bid_price: float,
        ask_price: float,
        price_tick: float,
    ) -> float:
        """
        根据盘口计算自适应委托价格

        卖出 (SHORT): bid_price - slippage_ticks * price_tick
        买入 (LONG): ask_price + slippage_ticks * price_tick
        盘口不可用时返回原始指令价格。
        """
        if instruction.direction == Direction.SHORT:
            if bid_price <= 0:
                return instruction.price
            return bid_price - self.config.slippage_ticks * price_tick
        else:
            if ask_price <= 0:
                return instruction.price
            return ask_price + self.config.slippage_ticks * price_tick

    def round_price_to_tick(self, price: float, price_tick: float) -> float:
        """将价格对齐到最小变动价位"""
        if price_tick <= 0:
            return price
        return round(price / price_tick) * price_tick

    def register_order(
        self, vt_orderid: str, instruction: OrderInstruction
    ) -> ManagedOrder:
        """注册新订单到超时管理"""
        order = ManagedOrder(
            vt_orderid=vt_orderid,
            instruction=instruction,
            submit_time=datetime.now(),
        )
        self._orders[vt_orderid] = order
        return order

    def check_timeouts(
        self, current_time: datetime
    ) -> Tuple[List[str], List[DomainEvent]]:
        """
        检查超时订单

        Returns:
            (需撤销的订单ID列表, 事件列表)
        """
        cancel_ids: List[str] = []
        events: List[DomainEvent] = []

        for vt_orderid, order in self._orders.items():
            if not order.is_active:
                continue
            elapsed = (current_time - order.submit_time).total_seconds()
            if elapsed >= self.config.timeout_seconds:
                cancel_ids.append(vt_orderid)
                events.append(OrderTimeoutEvent(
                    vt_orderid=vt_orderid,
                    vt_symbol=order.instruction.vt_symbol,
                    elapsed_seconds=elapsed,
                ))

        return cancel_ids, events

    def mark_order_filled(self, vt_orderid: str) -> None:
        """标记订单已成交"""
        if vt_orderid in self._orders:
            self._orders[vt_orderid].is_active = False

    def mark_order_cancelled(self, vt_orderid: str) -> None:
        """标记订单已撤销"""
        if vt_orderid in self._orders:
            self._orders[vt_orderid].is_active = False

    def prepare_retry(
        self, managed_order: ManagedOrder, price_tick: float
    ) -> Optional[OrderInstruction]:
        """
        准备重试指令

        Returns:
            新的 OrderInstruction，或 None 表示重试耗尽
        """
        if managed_order.retry_count >= self.config.max_retries:
            return None

        old_instr = managed_order.instruction
        # 更激进的价格: 卖出方向降价，买入方向加价
        if old_instr.direction == Direction.SHORT:
            new_price = old_instr.price - price_tick
        else:
            new_price = old_instr.price + price_tick

        new_price = self.round_price_to_tick(new_price, price_tick)

        managed_order.retry_count += 1

        return OrderInstruction(
            vt_symbol=old_instr.vt_symbol,
            direction=old_instr.direction,
            offset=old_instr.offset,
            volume=old_instr.volume,
            price=new_price,
            signal=old_instr.signal,
            order_type=old_instr.order_type,
        )
