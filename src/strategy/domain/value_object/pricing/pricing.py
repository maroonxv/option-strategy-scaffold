"""
期权定价相关值对象

定义期权定价的行权方式、定价模型枚举，以及定价输入参数和定价结果。
"""
from dataclasses import dataclass
from enum import Enum


class ExerciseStyle(str, Enum):
    """期权行权方式"""
    AMERICAN = "american"
    EUROPEAN = "european"


class PricingModel(str, Enum):
    """定价模型枚举"""
    BAW = "baw"
    CRR = "crr"
    BLACK_SCHOLES = "black_scholes"


@dataclass(frozen=True)
class PricingInput:
    """
    定价输入参数

    Attributes:
        spot_price: 标的价格
        strike_price: 行权价
        time_to_expiry: 剩余到期时间（年化）
        risk_free_rate: 无风险利率
        volatility: 波动率
        option_type: 期权类型 ("call" | "put")
        exercise_style: 行权方式
    """
    spot_price: float
    strike_price: float
    time_to_expiry: float
    risk_free_rate: float
    volatility: float
    option_type: str
    exercise_style: ExerciseStyle


@dataclass(frozen=True)
class PricingResult:
    """
    定价结果

    Attributes:
        price: 理论价格
        model_used: 实际使用的定价模型名称
        success: 是否成功
        error_message: 错误描述
    """
    price: float = 0.0
    model_used: str = ""
    success: bool = True
    error_message: str = ""
