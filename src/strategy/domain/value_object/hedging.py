"""
对冲相关值对象

定义 Delta 对冲和 Gamma Scalping 的配置与结果数据类。
"""
from dataclasses import dataclass
from typing import Optional

from .order_instruction import OrderInstruction, Direction


@dataclass(frozen=True)
class HedgingConfig:
    """Delta 对冲配置"""
    target_delta: float = 0.0
    hedging_band: float = 0.5
    hedge_instrument_vt_symbol: str = ""
    hedge_instrument_delta: float = 1.0
    hedge_instrument_multiplier: float = 10.0


@dataclass(frozen=True)
class HedgeResult:
    """Delta 对冲计算结果"""
    should_hedge: bool
    hedge_volume: int = 0
    hedge_direction: Optional[Direction] = None
    instruction: Optional[OrderInstruction] = None
    reason: str = ""


@dataclass(frozen=True)
class GammaScalpConfig:
    """Gamma Scalping 配置"""
    rebalance_threshold: float = 0.3
    hedge_instrument_vt_symbol: str = ""
    hedge_instrument_delta: float = 1.0
    hedge_instrument_multiplier: float = 10.0


@dataclass(frozen=True)
class ScalpResult:
    """Gamma Scalping 结果"""
    should_rebalance: bool
    rebalance_volume: int = 0
    rebalance_direction: Optional[Direction] = None
    instruction: Optional[OrderInstruction] = None
    rejected: bool = False
    reject_reason: str = ""


@dataclass(frozen=True)
class VegaHedgingConfig:
    """Vega 对冲配置"""
    target_vega: float = 0.0                    # 目标 Vega
    hedging_band: float = 50.0                  # Vega 容忍带
    hedge_instrument_vt_symbol: str = ""        # 对冲工具合约代码
    hedge_instrument_vega: float = 0.1          # 对冲工具每手 Vega
    hedge_instrument_delta: float = 0.5         # 对冲工具每手 Delta
    hedge_instrument_gamma: float = 0.01        # 对冲工具每手 Gamma
    hedge_instrument_theta: float = -0.05       # 对冲工具每手 Theta
    hedge_instrument_multiplier: float = 10.0   # 合约乘数


@dataclass(frozen=True)
class VegaHedgeResult:
    """Vega 对冲计算结果"""
    should_hedge: bool
    hedge_volume: int = 0
    hedge_direction: Optional[Direction] = None
    instruction: Optional[OrderInstruction] = None
    delta_impact: float = 0.0       # 对冲引入的 Delta 变化
    gamma_impact: float = 0.0       # 对冲引入的 Gamma 变化
    theta_impact: float = 0.0       # 对冲引入的 Theta 变化
    rejected: bool = False
    reject_reason: str = ""
    reason: str = ""
