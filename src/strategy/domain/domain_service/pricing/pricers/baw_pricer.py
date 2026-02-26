"""
BAWPricer 领域服务

基于 Barone-Adesi Whaley (1987) 近似解析方法的美式期权定价器。
美式期权价格 = 欧式 BS 价格 + 提前行权溢价。
纯计算服务，无副作用。
"""
import math

from ....value_object.pricing import PricingInput, PricingResult


def _norm_cdf(x: float) -> float:
    """标准正态分布累积分布函数"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


class BAWPricer:
    """Barone-Adesi Whaley 美式期权近似定价器"""

    def price(self, params: PricingInput) -> PricingResult:
        """
        计算美式期权 BAW 近似理论价格

        Args:
            params: 定价输入参数

        Returns:
            PricingResult 包含理论价格和模型信息
        """
        # 1. 输入校验
        validation_error = self._validate(params)
        if validation_error:
            return PricingResult(
                success=False,
                error_message=validation_error,
                model_used="baw",
            )

        # 2. T=0 边界处理，返回内在价值
        if params.time_to_expiry == 0:
            intrinsic = self._intrinsic_value(
                params.spot_price, params.strike_price, params.option_type
            )
            return PricingResult(price=intrinsic, model_used="baw")

        # 3. 计算美式期权价格
        try:
            price = self._baw_price(
                S=params.spot_price,
                K=params.strike_price,
                T=params.time_to_expiry,
                r=params.risk_free_rate,
                sigma=params.volatility,
                option_type=params.option_type,
            )
            return PricingResult(price=price, model_used="baw")
        except Exception as e:
            return PricingResult(
                success=False,
                error_message=f"计算异常: {e}",
                model_used="baw",
            )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(params: PricingInput) -> str:
        """校验输入参数，返回错误信息或空字符串"""
        if params.spot_price <= 0:
            return "spot_price 必须大于 0"
        if params.strike_price <= 0:
            return "strike_price 必须大于 0"
        if params.volatility <= 0:
            return "volatility 必须大于 0"
        if params.time_to_expiry < 0:
            return "time_to_expiry 不能为负数"
        return ""

    @staticmethod
    def _intrinsic_value(S: float, K: float, option_type: str) -> float:
        """计算期权内在价值"""
        if option_type == "call":
            return max(S - K, 0.0)
        else:
            return max(K - S, 0.0)

    @staticmethod
    def _bs_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
        """计算欧式 Black-Scholes 价格"""
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        if option_type == "call":
            return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        else:
            return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)

    def _baw_price(
        self, S: float, K: float, T: float, r: float, sigma: float, option_type: str
    ) -> float:
        """
        BAW 美式期权近似定价核心算法

        算法步骤:
        1. 计算欧式 BS 价格
        2. 计算 BAW 参数 (M, N, K_factor, q)
        3. 牛顿法求解临界价格 S*
        4. 根据 S 与 S* 的关系计算美式价格
        """
        sigma_sq = sigma ** 2
        # M = 2r / σ², N = 2(r-q) / σ² (q=0 dividend yield)
        M = 2.0 * r / sigma_sq
        N = 2.0 * r / sigma_sq  # q=0, so N = M
        K_factor = 1.0 - math.exp(-r * T)

        # 当 r 接近 0 时，K_factor 接近 0，需要特殊处理
        if K_factor < 1e-15:
            # 当利率为 0 时，美式期权 = 欧式期权（无提前行权价值）
            return self._bs_price(S, K, T, r, sigma, option_type)

        if option_type == "call":
            return self._baw_call(S, K, T, r, sigma, M, N, K_factor)
        else:
            return self._baw_put(S, K, T, r, sigma, M, N, K_factor)

    def _baw_call(
        self, S: float, K: float, T: float, r: float, sigma: float,
        M: float, N: float, K_factor: float,
    ) -> float:
        """BAW 美式看涨期权定价"""
        bs = self._bs_price(S, K, T, r, sigma, "call")

        # q₂ = (-(N-1) + √((N-1)² + 4M/K_factor)) / 2
        discriminant = (N - 1) ** 2 + 4.0 * M / K_factor
        q2 = (-(N - 1) + math.sqrt(discriminant)) / 2.0

        # 牛顿法求解临界价格 S*
        S_star = self._find_critical_price_call(K, T, r, sigma, q2)

        if S >= S_star:
            # S >= S*: 立即行权最优，价格 = max(内在价值, BS价格)
            # 美式期权价格不应低于欧式价格
            return max(S - K, bs)
        else:
            # S < S*: 美式价格 = BS价格 + 提前行权溢价
            A2 = (S_star / q2) * (1.0 - self._bs_d1_cdf(S_star, K, T, r, sigma))
            premium = A2 * (S / S_star) ** q2
            return max(bs + premium, bs)

    def _baw_put(
        self, S: float, K: float, T: float, r: float, sigma: float,
        M: float, N: float, K_factor: float,
    ) -> float:
        """BAW 美式看跌期权定价"""
        bs = self._bs_price(S, K, T, r, sigma, "put")

        # q₁ = (-(N-1) - √((N-1)² + 4M/K_factor)) / 2
        discriminant = (N - 1) ** 2 + 4.0 * M / K_factor
        q1 = (-(N - 1) - math.sqrt(discriminant)) / 2.0

        # 牛顿法求解临界价格 S*
        S_star = self._find_critical_price_put(K, T, r, sigma, q1)

        if S <= S_star:
            # S <= S*: 立即行权最优，价格 = max(内在价值, BS价格)
            # 美式期权价格不应低于欧式价格
            return max(K - S, bs)
        else:
            # S > S*: 美式价格 = BS价格 + 提前行权溢价
            A1 = -(S_star / q1) * (1.0 - self._bs_d1_cdf_neg(S_star, K, T, r, sigma))
            premium = A1 * (S / S_star) ** q1
            return max(bs + premium, bs)

    def _find_critical_price_call(
        self, K: float, T: float, r: float, sigma: float, q2: float,
        max_iter: int = 500, tol: float = 1e-8,
    ) -> float:
        """牛顿法求解看涨期权临界价格 S*"""
        # 初始猜测: S* = K
        S_star = K
        for _ in range(max_iter):
            bs = self._bs_price(S_star, K, T, r, sigma, "call")
            d1 = self._calc_d1(S_star, K, T, r, sigma)
            Nd1 = _norm_cdf(d1)

            lhs = bs + (S_star / q2) * (1.0 - Nd1) - (S_star - K)

            # 导数
            d_bs = Nd1  # ∂bs/∂S = N(d1)
            d_A = (1.0 / q2) * (1.0 - Nd1)  # 简化的导数
            d_lhs = d_bs + d_A - 1.0

            if abs(d_lhs) < 1e-15:
                break

            S_new = S_star - lhs / d_lhs
            # 确保 S* > 0
            if S_new <= 0:
                S_star = S_star / 2.0
                continue

            if abs(S_new - S_star) < tol:
                S_star = S_new
                break
            S_star = S_new

        return max(S_star, K)  # S* 至少为 K

    def _find_critical_price_put(
        self, K: float, T: float, r: float, sigma: float, q1: float,
        max_iter: int = 500, tol: float = 1e-8,
    ) -> float:
        """牛顿法求解看跌期权临界价格 S*"""
        # 初始猜测: S* = K
        S_star = K
        for _ in range(max_iter):
            bs = self._bs_price(S_star, K, T, r, sigma, "put")
            d1 = self._calc_d1(S_star, K, T, r, sigma)
            Nd1_neg = _norm_cdf(-d1)

            lhs = bs - (S_star / q1) * (1.0 - Nd1_neg) - (K - S_star)

            # 导数
            d_bs = _norm_cdf(d1) - 1.0  # ∂bs_put/∂S = N(d1) - 1
            d_A = -(1.0 / q1) * (1.0 - Nd1_neg)
            d_lhs = d_bs + d_A + 1.0

            if abs(d_lhs) < 1e-15:
                break

            S_new = S_star - lhs / d_lhs
            if S_new <= 0:
                S_star = S_star / 2.0
                continue

            if abs(S_new - S_star) < tol:
                S_star = S_new
                break
            S_star = S_new

        return max(S_star, 1e-10)  # S* > 0

    @staticmethod
    def _calc_d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """计算 d1"""
        sqrt_T = math.sqrt(T)
        return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)

    def _bs_d1_cdf(self, S: float, K: float, T: float, r: float, sigma: float) -> float:
        """计算 N(d1) 用于看涨"""
        d1 = self._calc_d1(S, K, T, r, sigma)
        return _norm_cdf(d1)

    def _bs_d1_cdf_neg(self, S: float, K: float, T: float, r: float, sigma: float) -> float:
        """计算 N(-d1) 用于看跌"""
        d1 = self._calc_d1(S, K, T, r, sigma)
        return _norm_cdf(-d1)
