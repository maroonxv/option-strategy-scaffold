"""
BlackScholesPricer 领域服务

基于 Black-Scholes 模型的欧式期权定价器，委托给现有 GreeksCalculator.bs_price 实现。
纯计算服务，无副作用。
"""
from ...value_object.greeks import GreeksInput
from ...value_object.pricing import PricingInput, PricingResult
from .greeks_calculator import GreeksCalculator


class BlackScholesPricer:
    """Black-Scholes 定价器，委托给 GreeksCalculator"""

    def __init__(self, greeks_calculator: GreeksCalculator):
        self._calculator = greeks_calculator

    def price(self, params: PricingInput) -> PricingResult:
        """
        计算欧式期权 Black-Scholes 理论价格

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
                model_used="black_scholes",
            )

        # 2. 转换为 GreeksInput 并委托计算
        try:
            greeks_input = GreeksInput(
                spot_price=params.spot_price,
                strike_price=params.strike_price,
                time_to_expiry=params.time_to_expiry,
                risk_free_rate=params.risk_free_rate,
                volatility=params.volatility,
                option_type=params.option_type,
            )
            price = self._calculator.bs_price(greeks_input)
            return PricingResult(price=price, model_used="black_scholes")
        except Exception as e:
            return PricingResult(
                success=False,
                error_message=f"计算异常: {e}",
                model_used="black_scholes",
            )

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
