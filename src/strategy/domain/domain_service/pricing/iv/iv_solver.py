"""
IVSolver 隐含波动率求解器

从市场价格反推隐含波动率的独立服务，支持多算法（牛顿法、二分法、Brent 法）和批量求解。
从 GreeksCalculator.calculate_implied_volatility 中提取并增强。
"""
import math
from enum import Enum
from typing import List

from ....value_object.pricing.greeks import GreeksInput, IVQuote, IVResult


def _norm_cdf(x: float) -> float:
    """标准正态分布累积分布函数"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """标准正态分布概率密度函数"""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


class SolveMethod(str, Enum):
    """IV 求解算法枚举"""
    NEWTON = "newton"
    BISECTION = "bisection"
    BRENT = "brent"


class IVSolver:
    """隐含波动率求解器"""

    _SIGMA_LOW = 0.001
    _SIGMA_HIGH = 10.0
    _INITIAL_GUESS = 0.5

    # ------------------------------------------------------------------
    # 内部 BS 定价与 Vega 计算（与 GreeksCalculator 一致）
    # ------------------------------------------------------------------

    @staticmethod
    def _bs_price(S: float, K: float, T: float, r: float, sigma: float, opt: str) -> float:
        """Black-Scholes 理论价格"""
        if T == 0:
            return max(S - K, 0.0) if opt == "call" else max(K - S, 0.0)
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        if opt == "call":
            return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        else:
            return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)

    @staticmethod
    def _bs_vega_raw(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """BS Vega（未除以 100 的原始值），即 dPrice/dSigma"""
        if T <= 0:
            return 0.0
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
        return S * _norm_pdf(d1) * sqrt_T

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def solve(
        self,
        market_price: float,
        spot_price: float,
        strike_price: float,
        time_to_expiry: float,
        risk_free_rate: float,
        option_type: str,
        method: SolveMethod = SolveMethod.NEWTON,
        max_iterations: int = 100,
        tolerance: float = 0.01,
    ) -> IVResult:
        """
        求解单个期权的隐含波动率。

        默认使用牛顿法，牛顿法未收敛时自动回退到二分法。
        调用方可通过 method 参数指定算法（指定时不自动回退）。
        """
        # ---- 输入校验 ----
        if market_price <= 0:
            return IVResult(success=False, error_message="市场价格必须大于 0")

        if option_type == "call":
            intrinsic = max(spot_price - strike_price * math.exp(-risk_free_rate * time_to_expiry), 0.0)
        else:
            intrinsic = max(strike_price * math.exp(-risk_free_rate * time_to_expiry) - spot_price, 0.0)

        if market_price < intrinsic - tolerance:
            return IVResult(success=False, error_message="市场价格低于期权内在价值")

        # ---- 分派求解 ----
        try:
            if method == SolveMethod.NEWTON:
                result = self._solve_newton(
                    market_price, spot_price, strike_price,
                    time_to_expiry, risk_free_rate, option_type,
                    max_iterations, tolerance,
                )
                # 牛顿法未收敛 → 自动回退二分法
                if not result.success:
                    result = self._solve_bisection(
                        market_price, spot_price, strike_price,
                        time_to_expiry, risk_free_rate, option_type,
                        max_iterations, tolerance,
                    )
                return result
            elif method == SolveMethod.BISECTION:
                return self._solve_bisection(
                    market_price, spot_price, strike_price,
                    time_to_expiry, risk_free_rate, option_type,
                    max_iterations, tolerance,
                )
            else:  # BRENT
                return self._solve_brent(
                    market_price, spot_price, strike_price,
                    time_to_expiry, risk_free_rate, option_type,
                    max_iterations, tolerance,
                )
        except (OverflowError, ValueError, ZeroDivisionError) as e:
            return IVResult(success=False, error_message=f"计算异常: {e}")

    def solve_batch(
        self,
        quotes: List[IVQuote],
        method: SolveMethod = SolveMethod.NEWTON,
        max_iterations: int = 100,
        tolerance: float = 0.01,
    ) -> List[IVResult]:
        """
        批量求解隐含波动率。

        每个报价独立求解，单个失败不影响其他。
        返回列表与输入列表保持相同顺序和长度。
        """
        results: List[IVResult] = []
        for quote in quotes:
            try:
                result = self.solve(
                    market_price=quote.market_price,
                    spot_price=quote.spot_price,
                    strike_price=quote.strike_price,
                    time_to_expiry=quote.time_to_expiry,
                    risk_free_rate=quote.risk_free_rate,
                    option_type=quote.option_type,
                    method=method,
                    max_iterations=max_iterations,
                    tolerance=tolerance,
                )
            except Exception as e:
                result = IVResult(success=False, error_message=f"求解异常: {e}")
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # 内部求解算法
    # ------------------------------------------------------------------

    def _solve_newton(
        self,
        market_price: float,
        spot_price: float,
        strike_price: float,
        time_to_expiry: float,
        risk_free_rate: float,
        option_type: str,
        max_iterations: int,
        tolerance: float,
    ) -> IVResult:
        """
        牛顿法求解隐含波动率。

        与原 GreeksCalculator.calculate_implied_volatility 逻辑一致：
        初始猜测 σ=0.5，维护二分法边界 [0.001, 10.0]，
        当牛顿步超出边界时回退到二分法步。
        """
        sigma = self._INITIAL_GUESS
        sigma_low = self._SIGMA_LOW
        sigma_high = self._SIGMA_HIGH

        for i in range(max_iterations):
            price = self._bs_price(
                spot_price, strike_price, time_to_expiry,
                risk_free_rate, sigma, option_type,
            )
            diff = price - market_price

            if abs(diff) < tolerance:
                return IVResult(implied_volatility=sigma, iterations=i + 1)

            # 更新二分法边界
            if diff > 0:
                sigma_high = sigma
            else:
                sigma_low = sigma

            # 尝试牛顿法步进
            vega_raw = self._bs_vega_raw(
                spot_price, strike_price, time_to_expiry,
                risk_free_rate, sigma,
            )
            if abs(vega_raw) > 1e-10:
                new_sigma = sigma - diff / vega_raw
                if sigma_low < new_sigma < sigma_high:
                    sigma = new_sigma
                else:
                    sigma = (sigma_low + sigma_high) / 2.0
            else:
                sigma = (sigma_low + sigma_high) / 2.0

        return IVResult(
            success=False,
            error_message=f"在 {max_iterations} 次迭代内未收敛",
            iterations=max_iterations,
        )

    def _solve_bisection(
        self,
        market_price: float,
        spot_price: float,
        strike_price: float,
        time_to_expiry: float,
        risk_free_rate: float,
        option_type: str,
        max_iterations: int,
        tolerance: float,
    ) -> IVResult:
        """纯二分法，在 [0.001, 10.0] 区间内搜索。"""
        sigma_low = self._SIGMA_LOW
        sigma_high = self._SIGMA_HIGH

        for i in range(max_iterations):
            sigma_mid = (sigma_low + sigma_high) / 2.0
            price = self._bs_price(
                spot_price, strike_price, time_to_expiry,
                risk_free_rate, sigma_mid, option_type,
            )
            diff = price - market_price

            if abs(diff) < tolerance:
                return IVResult(implied_volatility=sigma_mid, iterations=i + 1)

            if diff > 0:
                sigma_high = sigma_mid
            else:
                sigma_low = sigma_mid

        return IVResult(
            success=False,
            error_message=f"在 {max_iterations} 次迭代内未收敛",
            iterations=max_iterations,
        )

    def _solve_brent(
        self,
        market_price: float,
        spot_price: float,
        strike_price: float,
        time_to_expiry: float,
        risk_free_rate: float,
        option_type: str,
        max_iterations: int,
        tolerance: float,
    ) -> IVResult:
        """
        Brent 求根法（手动实现）。

        结合二分法、割线法和逆二次插值，收敛速度优于纯二分法。
        """
        a = self._SIGMA_LOW
        b = self._SIGMA_HIGH

        def f(sigma: float) -> float:
            return self._bs_price(
                spot_price, strike_price, time_to_expiry,
                risk_free_rate, sigma, option_type,
            ) - market_price

        fa = f(a)
        fb = f(b)

        # 确保 f(a) 和 f(b) 异号（正常情况下应满足）
        if fa * fb > 0:
            # 区间端点同号，回退到二分法逻辑
            return self._solve_bisection(
                market_price, spot_price, strike_price,
                time_to_expiry, risk_free_rate, option_type,
                max_iterations, tolerance,
            )

        # 确保 |f(a)| >= |f(b)|
        if abs(fa) < abs(fb):
            a, b = b, a
            fa, fb = fb, fa

        c = a
        fc = fa
        mflag = True
        d = 0.0  # 上一步的步长

        for i in range(max_iterations):
            if abs(fb) < tolerance:
                return IVResult(implied_volatility=b, iterations=i + 1)

            if abs(b - a) < 1e-15:
                return IVResult(implied_volatility=b, iterations=i + 1)

            # 尝试逆二次插值或割线法
            if abs(fa - fc) > 1e-15 and abs(fb - fc) > 1e-15:
                # 逆二次插值
                s = (
                    a * fb * fc / ((fa - fb) * (fa - fc))
                    + b * fa * fc / ((fb - fa) * (fb - fc))
                    + c * fa * fb / ((fc - fa) * (fc - fb))
                )
            else:
                # 割线法
                if abs(fa - fb) < 1e-15:
                    s = b
                else:
                    s = b - fb * (b - a) / (fb - fa)

            # 判断是否需要回退到二分法
            bisect = False
            mid = (a + b) / 2.0

            # 条件 1: s 不在 (min(3a+b)/4, b) 之间
            bound_lo = min((3 * a + b) / 4.0, b)
            bound_hi = max((3 * a + b) / 4.0, b)
            if not (bound_lo <= s <= bound_hi):
                bisect = True
            # 条件 2: mflag 且 |s-b| >= |b-c|/2
            elif mflag and abs(s - b) >= abs(b - c) / 2.0:
                bisect = True
            # 条件 3: !mflag 且 |s-b| >= |c-d|/2
            elif not mflag and abs(s - b) >= abs(c - d) / 2.0:
                bisect = True
            # 条件 4: mflag 且 |b-c| < 1e-15
            elif mflag and abs(b - c) < 1e-15:
                bisect = True
            # 条件 5: !mflag 且 |c-d| < 1e-15
            elif not mflag and abs(c - d) < 1e-15:
                bisect = True

            if bisect:
                s = mid
                mflag = True
            else:
                mflag = False

            fs = f(s)
            d = c
            c = b
            fc = fb

            if fa * fs < 0:
                b = s
                fb = fs
            else:
                a = s
                fa = fs

            # 确保 |f(a)| >= |f(b)|
            if abs(fa) < abs(fb):
                a, b = b, a
                fa, fb = fb, fa

        return IVResult(
            success=False,
            error_message=f"在 {max_iterations} 次迭代内未收敛",
            iterations=max_iterations,
        )
