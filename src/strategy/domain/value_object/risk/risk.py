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


# ============================================================================
# 止损相关值对象
# ============================================================================

@dataclass(frozen=True)
class StopLossConfig:
    """
    止损配置
    
    Attributes:
        enable_fixed_stop: 是否启用固定止损
        fixed_stop_loss_amount: 单笔止损金额
        fixed_stop_loss_percent: 单笔止损百分比（相对开仓价值）
        enable_trailing_stop: 是否启用移动止损
        trailing_stop_percent: 回撤百分比触发移动止损
        enable_portfolio_stop: 是否启用组合级止损
        daily_loss_limit: 每日最大亏损限额
    """
    enable_fixed_stop: bool = True
    fixed_stop_loss_amount: float = 1000.0
    fixed_stop_loss_percent: float = 0.5
    enable_trailing_stop: bool = False
    trailing_stop_percent: float = 0.3
    enable_portfolio_stop: bool = True
    daily_loss_limit: float = 5000.0


@dataclass(frozen=True)
class StopLossTrigger:
    """
    止损触发结果
    
    Attributes:
        vt_symbol: 合约代码
        trigger_type: 触发类型 ("fixed" | "trailing")
        current_loss: 当前亏损金额
        threshold: 止损阈值
        current_price: 当前价格
        open_price: 开仓价格
        message: 触发消息
    """
    vt_symbol: str
    trigger_type: str
    current_loss: float
    threshold: float
    current_price: float
    open_price: float
    message: str


@dataclass(frozen=True)
class PortfolioStopLossTrigger:
    """
    组合级止损触发结果
    
    Attributes:
        total_loss: 组合总亏损
        daily_limit: 每日止损限额
        positions_to_close: 需要平仓的合约代码列表
        message: 触发消息
    """
    total_loss: float
    daily_limit: float
    positions_to_close: list[str]
    message: str
