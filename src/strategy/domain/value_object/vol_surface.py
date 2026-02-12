"""
波动率曲面相关值对象

定义波动率报价、查询结果、微笑曲线、期限结构和曲面快照数据类。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass(frozen=True)
class VolQuote:
    """单个期权的波动率报价"""
    strike: float
    time_to_expiry: float
    implied_vol: float


@dataclass(frozen=True)
class VolQueryResult:
    """波动率查询结果"""
    implied_vol: float = 0.0
    success: bool = True
    error_message: str = ""


@dataclass
class VolSmile:
    """波动率微笑"""
    time_to_expiry: float
    strikes: List[float] = field(default_factory=list)
    vols: List[float] = field(default_factory=list)


@dataclass
class TermStructure:
    """期限结构"""
    strike: float
    expiries: List[float] = field(default_factory=list)
    vols: List[float] = field(default_factory=list)


@dataclass
class VolSurfaceSnapshot:
    """波动率曲面快照"""
    strikes: List[float] = field(default_factory=list)
    expiries: List[float] = field(default_factory=list)
    vol_matrix: List[List[float]] = field(default_factory=list)  # [expiry_idx][strike_idx]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典 (JSON 兼容)"""
        return {
            "strikes": self.strikes,
            "expiries": self.expiries,
            "vol_matrix": self.vol_matrix,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VolSurfaceSnapshot":
        """从字典反序列化"""
        return cls(
            strikes=data["strikes"],
            expiries=data["expiries"],
            vol_matrix=data["vol_matrix"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )
