"""
CRRPricer 领域服务

基于 Cox-Ross-Rubinstein (1979) 二叉树方法的期权定价器。
支持美式和欧式期权。纯计算服务，无副作用。
"""
import math

from ....value_object.pricing import ExerciseStyle, PricingInput, PricingResult


class CRRPricer:
    """CRR 二叉树定价器"""

    def __init__(self, steps: int = 100):
        self._steps = steps

    def price(self, params: PricingInput) -> PricingResult:
        """
        计算期权 CRR 二叉树理论价格

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
                model_used="crr",
            )

        # 2. T=0 边界处理，返回内在价值
        if params.time_to_expiry == 0:
            intrinsic = self._intrinsic_value(
                params.spot_price, params.strike_price, params.option_type
            )
            return PricingResult(price=intrinsic, model_used="crr")

        # 3. 二叉树定价
        try:
            computed = self._crr_price(
                S=params.spot_price,
                K=params.strike_price,
                T=params.time_to_expiry,
                r=params.risk_free_rate,
                sigma=params.volatility,
                option_type=params.option_type,
                is_american=params.exercise_style == ExerciseStyle.AMERICAN,
            )
            return PricingResult(price=computed, model_used="crr")
        except Exception as e:
            return PricingResult(
                success=False,
                error_message=f"计算异常: {e}",
                model_used="crr",
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

    def _crr_price(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: str,
        is_american: bool,
    ) -> float:
        """
        CRR 二叉树定价核心算法

        算法步骤:
        1. 计算参数: dt, u, d, p
        2. 构建到期节点的期权价值
        3. 从叶子节点向根节点回溯
           - 欧式: 仅折现
           - 美式: max(折现值, 提前行权价值)
        4. 返回根节点价格
        """
        n = self._steps
        dt = T / n
        u = math.exp(sigma * math.sqrt(dt))
        d = 1.0 / u
        disc = math.exp(-r * dt)
        p = (math.exp(r * dt) - d) / (u - d)
        q = 1.0 - p

        # 概率 p 必须在 [0, 1] 范围内，否则二叉树参数无效
        if p < 0 or p > 1:
            raise ValueError(
                f"CRR 概率 p={p:.6f} 超出 [0,1] 范围，"
                f"参数组合无效 (r={r}, σ={sigma}, dt={dt:.6f})"
            )

        is_call = option_type == "call"

        # 构建到期节点的期权价值
        # 节点 j 处标的价格: S * u^j * d^(n-j)
        option_values = [0.0] * (n + 1)
        for j in range(n + 1):
            spot_at_node = S * (u ** j) * (d ** (n - j))
            if is_call:
                option_values[j] = max(spot_at_node - K, 0.0)
            else:
                option_values[j] = max(K - spot_at_node, 0.0)

        # 从叶子节点向根节点回溯
        for i in range(n - 1, -1, -1):
            for j in range(i + 1):
                # 折现: 期望值的折现
                option_values[j] = disc * (
                    p * option_values[j + 1] + q * option_values[j]
                )

                # 美式期权: 检查提前行权
                if is_american:
                    spot_at_node = S * (u ** j) * (d ** (i - j))
                    if is_call:
                        exercise = max(spot_at_node - K, 0.0)
                    else:
                        exercise = max(K - spot_at_node, 0.0)
                    option_values[j] = max(option_values[j], exercise)

        return option_values[0]
