"""
Greeks 相关值对象

定义 Greeks 计算的输入参数、计算结果和隐含波动率求解结果。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GreeksInput:
    """
    Greeks 计算输入参数

    Attributes:
        spot_price: 标的价格
        strike_price: 行权价
        time_to_expiry: 剩余到期时间 (年化)
        risk_free_rate: 无风险利率
        volatility: 波动率 (隐含或历史)
        option_type: 期权类型 ("call" | "put")
    """
    spot_price: float
    strike_price: float
    time_to_expiry: float
    risk_free_rate: float
    volatility: float
    option_type: str


@dataclass(frozen=True)
class GreeksResult:
    """
    Greeks 计算结果

    Attributes:
        delta: Delta
        gamma: Gamma
        theta: Theta
        vega: Vega
        success: 计算是否成功
        error_message: 失败时的错误描述
    """
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    success: bool = True
    error_message: str = ""


@dataclass(frozen=True)
class IVResult:
    """
    隐含波动率求解结果

    Attributes:
        implied_volatility: 隐含波动率
        iterations: 迭代次数
        success: 是否收敛
        error_message: 失败时的错误描述
    """
    implied_volatility: float = 0.0
    iterations: int = 0
    success: bool = True
    error_message: str = ""


@dataclass(frozen=True)
class IVQuote:
    """
    批量 IV 求解的单个报价输入

    Attributes:
        market_price: 期权市场价格
        spot_price: 标的价格
        strike_price: 行权价
        time_to_expiry: 剩余到期时间（年化）
        risk_free_rate: 无风险利率
        option_type: 期权类型 ("call" | "put")
    """
    market_price: float
    spot_price: float
    strike_price: float
    time_to_expiry: float
    risk_free_rate: float
    option_type: str
