"""
ExecutionCoordinator 执行协调器

协调 SmartOrderExecutor 与 AdvancedOrderScheduler 的联动。
不直接调用交易网关，仅返回领域事件列表和执行指令。
"""
from datetime import datetime
from typing import List, Optional, Tuple

from ...event.event_types import DomainEvent
from ...value_object.trading.order_instruction import OrderInstruction
from .smart_order_executor import SmartOrderExecutor
from .advanced_order_scheduler import AdvancedOrderScheduler


class ExecutionCoordinator:
    """
    执行协调器

    协调 SmartOrderExecutor 与 AdvancedOrderScheduler 的联动。
    不直接调用交易网关，返回领域事件列表。
    """

    def __init__(
        self,
        executor: SmartOrderExecutor,
        scheduler: AdvancedOrderScheduler,
    ) -> None:
        self.executor = executor
        self.scheduler = scheduler

    def process_pending_children(
        self,
        current_time: datetime,
        bid_price: float,
        ask_price: float,
        price_tick: float,
    ) -> Tuple[List[OrderInstruction], List[DomainEvent]]:
        """
        处理待提交子单：
        1. 从 scheduler 获取到期子单
        2. 用 executor 计算自适应价格
        3. 返回带自适应价格的指令列表
        """
        instructions: List[OrderInstruction] = []
        events: List[DomainEvent] = []

        pending_children = self.scheduler.get_pending_children(current_time)

        for child in pending_children:
            # 查找子单所属的高级订单，获取原始指令信息
            parent_order = self.scheduler.get_order(child.parent_id)
            if parent_order is None:
                continue

            original_instruction = parent_order.request.instruction

            # 创建子单指令（使用原始指令的方向、开平等信息，但用子单的 volume）
            child_instruction = OrderInstruction(
                vt_symbol=original_instruction.vt_symbol,
                direction=original_instruction.direction,
                offset=original_instruction.offset,
                volume=child.volume,
                price=original_instruction.price,
                signal=original_instruction.signal,
                order_type=original_instruction.order_type,
            )

            # 用 executor 计算自适应价格
            adaptive_price = self.executor.calculate_adaptive_price(
                child_instruction, bid_price, ask_price, price_tick
            )
            rounded_price = self.executor.round_price_to_tick(
                adaptive_price, price_tick
            )

            # 创建带自适应价格的最终指令
            final_instruction = OrderInstruction(
                vt_symbol=original_instruction.vt_symbol,
                direction=original_instruction.direction,
                offset=original_instruction.offset,
                volume=child.volume,
                price=rounded_price,
                signal=original_instruction.signal,
                order_type=original_instruction.order_type,
            )

            instructions.append(final_instruction)

        return instructions, events

    def on_child_order_submitted(
        self, child_id: str, vt_orderid: str, instruction: OrderInstruction
    ) -> None:
        """子单提交后，注册到 executor 的超时管理"""
        self.executor.register_order(vt_orderid, instruction)

    def check_timeouts_and_retry(
        self, current_time: datetime, price_tick: float
    ) -> Tuple[List[str], List[OrderInstruction], List[DomainEvent]]:
        """
        检查超时并准备重试：
        1. 检查超时订单
        2. 对超时订单准备重试指令
        3. 重试耗尽时产生 OrderRetryExhaustedEvent
        返回: (需撤销ID列表, 重试指令列表, 事件列表)
        """
        # 1. 检查超时订单
        cancel_ids, timeout_events = self.executor.check_timeouts(current_time)

        retry_instructions: List[OrderInstruction] = []
        all_events: List[DomainEvent] = list(timeout_events)

        # 2. 对每个超时订单准备重试
        for vt_orderid in cancel_ids:
            managed_order = self.executor._orders.get(vt_orderid)
            if managed_order is None:
                continue

            retry_instruction, retry_events = self.executor.prepare_retry(
                managed_order, price_tick
            )

            all_events.extend(retry_events)

            if retry_instruction is not None:
                retry_instructions.append(retry_instruction)

        return cancel_ids, retry_instructions, all_events

    def on_child_filled(self, child_id: str) -> List[DomainEvent]:
        """子单成交回报，委托给 scheduler"""
        return self.scheduler.on_child_filled(child_id)
