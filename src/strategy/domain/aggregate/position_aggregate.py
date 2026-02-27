"""
PositionAggregate - 持仓聚合根

管理期权持仓的生命周期，检测手动平仓，产生领域事件。
读写聚合根。
"""
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Set

from ..entity.position import Position
from ..entity.order import Order, OrderStatus
from ..value_object.trading.order_instruction import Offset
from ..event.event_types import (
    DomainEvent,
    ManualCloseDetectedEvent,
    ManualOpenDetectedEvent,
    RiskLimitExceededEvent,
)


class PositionAggregate:
    """
    持仓聚合根 (读写)
    
    职责:
    1. 管理 positions 字典 (策略发起的持仓)
    2. 追踪 pending_orders (进行中的订单)
    3. 检测手动平仓 (产生 ManualCloseDetectedEvent)
    4. 管理领域事件队列
    
    设计原则:
    - 持仓状态管理
    - 订单生命周期跟踪
    - 手动操作检测
    - 领域事件发布
    """
    
    def __init__(self) -> None:
        """初始化聚合根"""
        # 策略持仓 (按期权合约代码索引)
        self._positions: Dict[str, Position] = {}
        
        # 进行中的订单 (按订单 ID 索引)
        self._pending_orders: Dict[str, Order] = {}
        
        # 策略管理的合约集合 (用于检测手动操作)
        self._managed_symbols: Set[str] = set()
        
        # 领域事件队列
        self._domain_events: List[DomainEvent] = []
        
        # 风控状态 (每日开仓限额)
        self._daily_open_count_map: Dict[str, int] = {}  # 合约级“已成交开仓量”计数 (按日)
        self._global_daily_open_count: int = 0           # 全局“已成交开仓量”计数 (按日)
        self._last_trading_date: Optional[date] = None   # 日期追踪

    # ========== 持久化接口 ==========

    def to_snapshot(self) -> Dict[str, Any]:
        """生成状态快照"""
        return {
            "positions": self._positions,
            "pending_orders": self._pending_orders,
            "managed_symbols": self._managed_symbols,
            "daily_open_count_map": self._daily_open_count_map,
            "global_daily_open_count": self._global_daily_open_count,
            "last_trading_date": self._last_trading_date
        }

    @classmethod
    def from_snapshot(cls, snapshot: Dict[str, Any]) -> "PositionAggregate":
        """从快照恢复状态"""
        obj = cls()
        obj._positions = snapshot.get("positions", {})
        obj._pending_orders = snapshot.get("pending_orders", {})
        obj._managed_symbols = snapshot.get("managed_symbols", set())
        obj._daily_open_count_map = snapshot.get("daily_open_count_map", {})
        obj._global_daily_open_count = snapshot.get("global_daily_open_count", 0)
        obj._last_trading_date = snapshot.get("last_trading_date", None)
        return obj
    
    # ========== 持仓管理接口 ==========
    
    def create_position(
        self,
        option_vt_symbol: str,
        underlying_vt_symbol: str,
        signal: str,
        target_volume: int
    ) -> Position:
        """
        创建新持仓
        
        Args:
            option_vt_symbol: 期权合约代码
            underlying_vt_symbol: 标的期货合约代码
            signal: 开仓信号类型
            target_volume: 目标持仓数量
            
        Returns:
            新创建的 Position 实体
        """
        position = Position(
            vt_symbol=option_vt_symbol,
            underlying_vt_symbol=underlying_vt_symbol,
            signal=signal,
            target_volume=target_volume
        )
        
        self._positions[option_vt_symbol] = position
        self._managed_symbols.add(option_vt_symbol)
        
        return position
    
    def get_position(self, vt_symbol: str) -> Optional[Position]:
        """获取指定合约的持仓"""
        return self._positions.get(vt_symbol)
    
    def get_positions_by_underlying(
        self,
        underlying_vt_symbol: str
    ) -> List[Position]:
        """
        获取某期货标的下的所有活跃持仓
        
        Args:
            underlying_vt_symbol: 期货标的代码
            
        Returns:
            活跃持仓列表
        """
        return [
            p for p in self._positions.values()
            if p.underlying_vt_symbol == underlying_vt_symbol
            and not p.is_closed
            and p.volume > 0
        ]
    
    def get_active_positions(self) -> List[Position]:
        """获取所有活跃持仓"""
        return [p for p in self._positions.values() if p.is_active]
    
    def get_all_positions(self) -> List[Position]:
        """获取所有持仓 (包括已平仓)"""
        return list(self._positions.values())
    
    # ========== 订单管理接口 ==========
    
    def add_pending_order(self, order: Order) -> None:
        """添加待处理订单"""
        self._pending_orders[order.vt_orderid] = order
    
    def get_pending_order(self, vt_orderid: str) -> Optional[Order]:
        """获取待处理订单"""
        return self._pending_orders.get(vt_orderid)
    
    def get_all_pending_orders(self) -> List[Order]:
        """获取所有待处理订单"""
        return list(self._pending_orders.values())
    
    def has_pending_close(self, position: Position) -> bool:
        """
        检查是否有进行中的平仓订单
        
        Args:
            position: 持仓实体
            
        Returns:
            True 如果有进行中的平仓订单
        """
        for order in self._pending_orders.values():
            if order.vt_symbol == position.vt_symbol and not order.is_open_order:
                if order.is_active:
                    return True
        return False
    
    # ========== 风控状态接口 ==========
    
    def on_new_trading_day(self, current_date: date) -> None:
        """
        处理新交易日 (重置计数器)
        """
        if self._last_trading_date != current_date:
            self._daily_open_count_map.clear()
            self._global_daily_open_count = 0
            self._last_trading_date = current_date
            # 日志记录通常由 Application Service 处理，这里只负责状态变更
            
    def record_open_usage(
        self, 
        vt_symbol: str, 
        volume: int,
        global_limit: int = 50,
        contract_limit: int = 2
    ) -> None:
        """
        记录开仓额度使用 (通常在成交回报时调用)
        并检查是否触发风控告警
        """
        self._global_daily_open_count += volume
        self._daily_open_count_map[vt_symbol] = self._daily_open_count_map.get(vt_symbol, 0) + volume
        
        # 检查全局限额
        if self._global_daily_open_count >= global_limit:
             self._domain_events.append(RiskLimitExceededEvent(
                 vt_symbol="GLOBAL",
                 limit_type="global",
                 current_volume=self._global_daily_open_count,
                 limit_volume=global_limit
             ))
             
        # 检查单合约限额
        if self._daily_open_count_map[vt_symbol] >= contract_limit:
             self._domain_events.append(RiskLimitExceededEvent(
                 vt_symbol=vt_symbol,
                 limit_type="contract",
                 current_volume=self._daily_open_count_map[vt_symbol],
                 limit_volume=contract_limit
             ))

    def get_daily_open_volume(self, vt_symbol: str) -> int:
        """获取指定合约今日已开仓数量 (已成交)"""
        return self._daily_open_count_map.get(vt_symbol, 0)
    
    def get_global_daily_open_volume(self) -> int:
        """获取今日全局已开仓数量 (已成交)"""
        return self._global_daily_open_count

    def get_reserved_open_volume(self, vt_symbol: Optional[str] = None) -> int:
        """
        计算挂单占用的开仓额度
        
        Args:
            vt_symbol: 如果指定，只计算该合约；否则计算全局。
        """
        total = 0
        for order in self._pending_orders.values():
            # 必须是开仓订单且处于活动状态
            if not order.is_open_order:
                continue
            if not order.is_active:
                continue
            
            # 如果指定了合约，则需匹配
            if vt_symbol and order.vt_symbol != vt_symbol:
                continue
                
            # 累加剩余未成交量
            remaining = getattr(order, "remaining_volume", 0) or 0
            total += int(remaining)
            
        return total

    # ========== 状态更新接口 ==========
    
    def update_from_order(self, order_data: dict) -> None:
        """
        根据订单更新持仓状态
        
        注意: 不使用 on_ 前缀 (遵循设计原则)
        
        Args:
            order_data: 订单数据字典 (应包含 vt_orderid, vt_symbol, status, traded 等)
        """
        vt_orderid = order_data.get("vt_orderid", "")
        vt_symbol = order_data.get("vt_symbol", "")
        status = order_data.get("status", "")
        traded = order_data.get("traded", 0)
        
        # 更新订单状态
        order = self._pending_orders.get(vt_orderid)
        if order:
            # 映射状态字符串到枚举
            status_mapping = {
                "submitting": OrderStatus.SUBMITTING,
                "nottraded": OrderStatus.NOTTRADED,
                "parttraded": OrderStatus.PARTTRADED,
                "alltraded": OrderStatus.ALLTRADED,
                "cancelled": OrderStatus.CANCELLED,
                "rejected": OrderStatus.REJECTED,
            }
            new_status = status_mapping.get(status.lower())
            if new_status:
                order.update_status(new_status, traded)
            
            # 订单完结，从待处理中移除
            if order.is_finished:
                del self._pending_orders[vt_orderid]
    
    def update_from_trade(self, trade_data: dict) -> None:
        """
        根据成交更新持仓
        
        Args:
            trade_data: 成交数据字典 (应包含 vt_symbol, volume, offset, price, datetime 等)
        """
        vt_symbol = trade_data.get("vt_symbol", "")
        volume = trade_data.get("volume", 0)
        offset = trade_data.get("offset", "")
        price = trade_data.get("price", 0.0)
        trade_time = trade_data.get("datetime", datetime.now())
        
        if vt_symbol not in self._managed_symbols:
            return
        
        position = self._positions.get(vt_symbol)
        if not position:
            return
        
        # 开仓成交
        if offset.lower() == "open":
            position.add_fill(volume, price, trade_time)
            # 记录风控额度使用
            self.record_open_usage(vt_symbol, volume)
        
        # 平仓成交
        else:
            position.reduce_volume(volume, trade_time)
    
    def update_from_position(self, position_data: dict) -> None:
        """
        根据持仓数据检测手动平仓
        
        将实际持仓与策略记录的持仓进行比对，
        如果发现差异则视为手动操作。
        
        Args:
            position_data: 持仓数据字典 (应包含 vt_symbol, volume 等)
        """
        vt_symbol = position_data.get("vt_symbol", "")
        actual_volume = position_data.get("volume", 0)
        
        if vt_symbol not in self._managed_symbols:
            return
        
        position = self._positions.get(vt_symbol)
        if not position:
            return
        
        # 检测手动平仓 (实际持仓 < 策略记录的持仓)
        if actual_volume < position.volume:
            manual_volume = position.volume - actual_volume
            position.mark_as_manually_closed(manual_volume)
            
            # 发出领域事件
            self._domain_events.append(ManualCloseDetectedEvent(
                vt_symbol=vt_symbol,
                volume=manual_volume,
                timestamp=datetime.now()
            ))
        
        # 检测手动开仓 (实际持仓 > 策略记录的持仓)
        elif actual_volume > position.volume:
            manual_volume = actual_volume - position.volume
            
            # 发出领域事件 (但不修改策略持仓)
            self._domain_events.append(ManualOpenDetectedEvent(
                vt_symbol=vt_symbol,
                volume=manual_volume,
                timestamp=datetime.now()
            ))
    
    # ========== 领域事件接口 ==========
    
    def pop_domain_events(self) -> List[DomainEvent]:
        """
        获取并清空领域事件队列
        
        Returns:
            领域事件列表
        """
        events = self._domain_events.copy()
        self._domain_events.clear()
        return events
    
    def has_pending_events(self) -> bool:
        """检查是否有待处理的领域事件"""
        return len(self._domain_events) > 0
    
    # ========== 辅助方法 ==========
    
    def is_managed(self, vt_symbol: str) -> bool:
        """检查合约是否由策略管理"""
        return vt_symbol in self._managed_symbols
    
    def clear(self) -> None:
        """清空所有状态"""
        self._positions.clear()
        self._pending_orders.clear()
        self._managed_symbols.clear()
        self._domain_events.clear()
    
    def __repr__(self) -> str:
        active_count = len(self.get_active_positions())
        pending_count = len(self._pending_orders)
        return f"PositionAggregate(active={active_count}, pending={pending_count})"
