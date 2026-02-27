"""
OrderInstruction 值对象 - 交易指令

由 PositionSizingService (Decider) 生成的交易指令，
由 StrategyEngine (Doer) 通过 Gateway 执行。

注意: 此模块不依赖 VnPy，使用自定义的 Direction 和 Offset 枚举。
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Direction(Enum):
    """交易方向"""
    LONG = "long"      # 买入/做多
    SHORT = "short"    # 卖出/做空

    @classmethod
    def from_leg_direction(cls, leg_direction: str) -> "Direction":
        """将 Leg 的 direction 字符串映射为 Direction 枚举"""
        return cls(leg_direction)

    def reverse(self) -> "Direction":
        """返回反向 Direction"""
        return Direction.SHORT if self == Direction.LONG else Direction.LONG

    @classmethod
    def from_leg_direction(cls, leg_direction: str) -> "Direction":
        """将 Leg 的 direction 字符串映射为 Direction 枚举"""
        return cls(leg_direction)

    def reverse(self) -> "Direction":
        """返回反向 Direction"""
        return Direction.SHORT if self == Direction.LONG else Direction.LONG


class Offset(Enum):
    """开平标志"""
    OPEN = "open"      # 开仓
    CLOSE = "close"    # 平仓
    CLOSETODAY = "closetoday"  # 平今
    CLOSEYESTERDAY = "closeyesterday"  # 平昨


class OrderType(Enum):
    """
    订单类型
    
    - LIMIT: 限价单，指定价格成交
    - MARKET: 市价单，以当前市场价格立即成交
    - FAK: Fill and Kill，立即成交剩余撤销
    - FOK: Fill or Kill，全部成交或全部撤销
    """
    LIMIT = "limit"        # 限价单
    MARKET = "market"      # 市价单
    FAK = "fak"            # 立即成交剩余撤销
    FOK = "fok"            # 全部成交或撤销


@dataclass(frozen=True)
class OrderInstruction:
    """
    交易指令值对象
    
    这是 Decider/Doer 模式中的"决策结果"。
    PositionSizingService 生成此对象，表达交易意图。
    StrategyEngine 接收此对象，调用 Gateway 执行实际交易。
    
    Attributes:
        vt_symbol: 合约代码 (VnPy 格式，如 "rb2501.SHFE")
        direction: 交易方向 (LONG/SHORT)
        offset: 开平标志 (OPEN/CLOSE)
        volume: 交易数量
        price: 交易价格 (0 表示市价)
        signal: 触发此指令的信号类型 (可选)
    """
    vt_symbol: str
    direction: Direction
    offset: Offset
    volume: int
    price: float = 0.0
    signal: str = ""
    order_type: OrderType = OrderType.LIMIT  # 订单类型，默认限价单
    
    @property
    def is_open(self) -> bool:
        """判断是否为开仓指令"""
        return self.offset == Offset.OPEN
    
    @property
    def is_close(self) -> bool:
        """判断是否为平仓指令"""
        return self.offset in (Offset.CLOSE, Offset.CLOSETODAY, Offset.CLOSEYESTERDAY)
    
    @property
    def is_buy(self) -> bool:
        """判断是否为买入方向"""
        return self.direction == Direction.LONG
    
    @property
    def is_sell(self) -> bool:
        """判断是否为卖出方向"""
        return self.direction == Direction.SHORT
    
    def __repr__(self) -> str:
        direction_str = "Buy" if self.is_buy else "Sell"
        offset_str = "Open" if self.is_open else "Close"
        type_str = self.order_type.value.upper()
        return (
            f"OrderInstruction({direction_str} {offset_str} "
            f"{self.vt_symbol} x{self.volume} @{self.price:.2f} [{type_str}])"
        )
