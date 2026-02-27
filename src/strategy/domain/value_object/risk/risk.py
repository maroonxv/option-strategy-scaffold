"""
风控相关值对象

定义风控阈值、风控检查结果、组合级 Greeks 快照和持仓级 Greeks 条目。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict

from src.strategy.domain.value_object.pricing.greeks import GreeksResult


@dataclass(frozen=True)
class RiskThresholds:
    """
    风控阈值配置

    Attributes:
        position_delta_limit: 单持仓 Delta 绝对值阈值
        position_gamma_limit: 单持仓 Gamma 绝对值阈值
        position_vega_limit: 单持仓 Vega 绝对值阈值
        portfolio_delta_limit: 组合 Delta 绝对值阈值
        portfolio_gamma_limit: 组合 Gamma 绝对值阈值
        portfolio_vega_limit: 组合 Vega 绝对值阈值
    """
    position_delta_limit: float = 0.8
    position_gamma_limit: float = 0.1
    position_vega_limit: float = 50.0
    portfolio_delta_limit: float = 5.0
    portfolio_gamma_limit: float = 1.0
    portfolio_vega_limit: float = 500.0


@dataclass(frozen=True)
class RiskCheckResult:
    """
    风控检查结果

    Attributes:
        passed: 是否通过风控检查
        reject_reason: 拒绝原因 (通过时为空)
    """
    passed: bool
    reject_reason: str = ""


@dataclass
class PortfolioGreeks:
    """
    组合级 Greeks 快照

    Attributes:
        total_delta: 组合 Delta
        total_gamma: 组合 Gamma
        total_theta: 组合 Theta
        total_vega: 组合 Vega
        position_count: 活跃持仓数
        timestamp: 快照时间
    """
    total_delta: float = 0.0
    total_gamma: float = 0.0
    total_theta: float = 0.0
    total_vega: float = 0.0
    position_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典 (JSON 兼容)"""
        return {
            "total_delta": self.total_delta,
            "total_gamma": self.total_gamma,
            "total_theta": self.total_theta,
            "total_vega": self.total_vega,
            "position_count": self.position_count,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PortfolioGreeks":
        """从字典反序列化"""
        return cls(
            total_delta=data["total_delta"],
            total_gamma=data["total_gamma"],
            total_theta=data["total_theta"],
            total_vega=data["total_vega"],
            position_count=data["position_count"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass(frozen=True)
class PositionGreeksEntry:
    """
    持仓级 Greeks 条目 (用于组合聚合)

    Attributes:
        vt_symbol: 合约代码
        greeks: 单手 Greeks
        volume: 持仓手数
        multiplier: 合约乘数
    """
    vt_symbol: str
    greeks: GreeksResult
    volume: int
    multiplier: float
