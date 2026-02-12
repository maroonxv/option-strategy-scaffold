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
