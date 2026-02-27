"""
PositionSnapshot 值对象 - 持仓快照

封装 vnpy PositionData 的关键字段，提供持仓信息的不可变快照。
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PositionDirection(Enum):
    """持仓方向"""
    LONG = "long"      # 多头
    SHORT = "short"    # 空头
    NET = "net"        # 净持仓


@dataclass(frozen=True)
class PositionSnapshot:
    """
    持仓快照值对象
    
    封装 vnpy PositionData 的关键字段，用于策略层查询持仓信息。
    
    Attributes:
        vt_symbol: 合约代码 (VnPy 格式，如 "rb2501.SHFE")
        direction: 持仓方向 (LONG/SHORT/NET)
        volume: 持仓量
        frozen: 冻结量 (挂单占用)
        price: 持仓均价
        pnl: 持仓盈亏
        yd_volume: 昨仓量 (上期所/能源中心需要区分今昨仓)
    """
    vt_symbol: str
    direction: PositionDirection
    volume: float
    frozen: float = 0.0
    price: float = 0.0
    pnl: float = 0.0
    yd_volume: float = 0.0
    
    @property
    def available(self) -> float:
        """可用持仓量 (总持仓 - 冻结)"""
        return max(0.0, self.volume - self.frozen)
    
    @property
    def today_volume(self) -> float:
        """今仓量 (总持仓 - 昨仓)"""
        return max(0.0, self.volume - self.yd_volume)
    
    @property
    def is_long(self) -> bool:
        """是否为多头持仓"""
        return self.direction == PositionDirection.LONG
    
    @property
    def is_short(self) -> bool:
        """是否为空头持仓"""
        return self.direction == PositionDirection.SHORT
    
    def __repr__(self) -> str:
        direction_str = "Long" if self.is_long else "Short"
        return (
            f"PositionSnapshot({self.vt_symbol} {direction_str} "
            f"vol={self.volume} frozen={self.frozen} "
            f"price={self.price:.2f} pnl={self.pnl:.2f})"
        )
