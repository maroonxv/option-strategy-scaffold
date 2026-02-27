"""
Combination 组合策略值对象

定义组合策略相关的枚举、值对象：
- CombinationType: 组合策略类型枚举
- CombinationStatus: 组合生命周期状态枚举
- Leg: 组合中的单个期权持仓值对象
- CombinationGreeks: 组合级 Greeks 聚合结果
- LegPnL: 单腿盈亏值对象
- CombinationPnL: 组合级盈亏值对象
- CombinationRiskConfig: 组合级风控阈值配置
- CombinationEvaluation: 组合评估结果值对象
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List

from src.strategy.domain.value_object.market.option_contract import OptionType
from src.strategy.domain.value_object.risk.risk import RiskCheckResult


class CombinationType(Enum):
    """组合策略类型"""
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    VERTICAL_SPREAD = "vertical_spread"
    CALENDAR_SPREAD = "calendar_spread"
    IRON_CONDOR = "iron_condor"
    CUSTOM = "custom"


class CombinationStatus(Enum):
    """组合生命周期状态"""
    PENDING = "pending"
    ACTIVE = "active"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"



@dataclass(frozen=True)
class Leg:
    """组合中的单个期权持仓"""
    vt_symbol: str          # 期权合约代码（松耦合引用 Position）
    option_type: OptionType  # call 或 put
    strike_price: float     # 行权价
    expiry_date: str        # 到期日
    direction: str          # "long" 或 "short"
    volume: int             # 持仓量
    open_price: float       # 开仓价

    @property
    def direction_sign(self) -> float:
        """返回方向符号：long → 1.0, short → -1.0"""
        return 1.0 if self.direction == "long" else -1.0



@dataclass(frozen=True)
class CombinationGreeks:
    """组合级 Greeks 聚合结果"""
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    failed_legs: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class LegPnL:
    """单腿盈亏"""
    vt_symbol: str
    unrealized_pnl: float
    price_available: bool = True
    realized_pnl: float = 0.0


@dataclass(frozen=True)
class CombinationPnL:
    """组合级盈亏"""
    total_unrealized_pnl: float
    leg_details: List[LegPnL] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    total_realized_pnl: float = 0.0


@dataclass(frozen=True)
class CombinationRiskConfig:
    """组合级风控阈值配置"""
    delta_limit: float = 2.0
    gamma_limit: float = 0.5
    vega_limit: float = 200.0
    theta_limit: float = 100.0


@dataclass(frozen=True)
class CombinationEvaluation:
    """组合评估结果"""
    greeks: CombinationGreeks
    pnl: CombinationPnL
    risk_result: RiskCheckResult
