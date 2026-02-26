"""
GreeksCalculator 领域服务

基于 Black-Scholes 模型计算期权 Greeks (Delta, Gamma, Theta, Vega)
以及隐含波动率反推。纯计算服务，无副作用。

IV 求解已委托给 IVSolver，保持原有接口不变。
"""
import math
from typing import Optional

from ....value_object.greeks import GreeksInput, GreeksResult, IVResult
from .iv_solver import IVSolver


def _norm_cdf(x: float) -> float:
    """标准正态分布累积分布函数"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """标准正态分布概率密度函数"""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


class GreeksCalculator:
    """
    Black-Scholes Greeks 计算器

    职责: 计算单个期权的 Greeks 和隐含波动率。
    IV 求解委托给 IVSolver。
    """

    def __init__(self, iv_solver: IVSolver | None = None):
        self._iv_solver = iv_solver or IVSolver()

    def calculate_greeks(self, params: GreeksInput) -> GreeksResult:
        """
        计算 Greeks (Black-Scholes)

        Args:
            params: Greeks 计算输入参数

        Returns:
            GreeksResult 包含 delta, gamma, theta, vega
        """
        S = params.spot_price
        K = params.strike_price
        T = params.time_to_expiry
        r = params.risk_free_rate
        sigma = params.volatility
        opt = params.option_type

        # 参数校验
        if S <= 0 or K <= 0:
            return GreeksResult(
                success=False,
                error_message="spot_price 和 strike_price 必须大于 0"
            )
        if T < 0:
            return GreeksResult(
                success=False,
                error_message="time_to_expiry 不能为负数"
            )
        if sigma <= 0:
            return GreeksResult(
                success=False,
                error_message="volatility 必须大于 0"
            )

        # 到期时边界处理
        if T == 0:
            if opt == "call":
                delta = 1.0 if S > K else 0.0
            else:
                delta = -1.0 if S < K else 0.0
            return GreeksResult(delta=delta, gamma=0.0, theta=0.0, vega=0.0)

        try:
            sqrt_T = math.sqrt(T)
            d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
            d2 = d1 - sigma * sqrt_T

            pdf_d1 = _norm_pdf(d1)
            cdf_d1 = _norm_cdf(d1)
            cdf_d2 = _norm_cdf(d2)

            # Gamma 和 Vega 对 call/put 相同
            gamma = pdf_d1 / (S * sigma * sqrt_T)
            vega = S * pdf_d1 * sqrt_T / 100.0  # 除以100使单位为1%波动率

            if opt == "call":
                delta = cdf_d1
                theta = (
                    -S * pdf_d1 * sigma / (2.0 * sqrt_T)
                    - r * K * math.exp(-r * T) * cdf_d2
                ) / 365.0
            else:
                delta = cdf_d1 - 1.0
                theta = (
                    -S * pdf_d1 * sigma / (2.0 * sqrt_T)
                    + r * K * math.exp(-r * T) * _norm_cdf(-d2)
                ) / 365.0

            return GreeksResult(delta=delta, gamma=gamma, theta=theta, vega=vega)

        except (OverflowError, ValueError) as e:
            return GreeksResult(
                success=False,
                error_message=f"计算溢出: {e}"
            )

    def bs_price(self, params: GreeksInput) -> float:
        """
        Black-Scholes 理论价格

        Args:
            params: Greeks 计算输入参数

        Returns:
            期权理论价格
        """
        S = params.spot_price
        K = params.strike_price
        T = params.time_to_expiry
        r = params.risk_free_rate
        sigma = params.volatility
        opt = params.option_type

        if T == 0:
            if opt == "call":
                return max(S - K, 0.0)
            else:
                return max(K - S, 0.0)

        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        if opt == "call":
            return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        else:
            return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)

    def calculate_implied_volatility(
        self,
        market_price: float,
        spot_price: float,
        strike_price: float,
        time_to_expiry: float,
        risk_free_rate: float,
        option_type: str,
        max_iterations: int = 100,
        tolerance: float = 0.01,
    ) -> IVResult:
        """
        求解隐含波动率，委托给 IVSolver。

        签名和返回类型与重构前完全一致。

        Args:
            market_price: 期权市场价格
            spot_price: 标的价格
            strike_price: 行权价
            time_to_expiry: 剩余到期时间 (年化)
            risk_free_rate: 无风险利率
            option_type: "call" | "put"
            max_iterations: 最大迭代次数
            tolerance: 收敛容差

        Returns:
            IVResult 包含隐含波动率和迭代信息
        """
        return self._iv_solver.solve(
            market_price=market_price,
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            option_type=option_type,
            max_iterations=max_iterations,
            tolerance=tolerance,
        )
