"""
PricingEngine 领域服务

统一定价引擎入口，根据期权行权方式和配置自动路由到合适的定价器。
- EUROPEAN → BlackScholesPricer
- AMERICAN → BAWPricer（默认）或 CRRPricer（可配置）
"""
from .pricers.bs_pricer import BlackScholesPricer
from .pricers.baw_pricer import BAWPricer
from .pricers.crr_pricer import CRRPricer
from .iv.greeks_calculator import GreeksCalculator
from ...value_object.pricing import ExerciseStyle, PricingInput, PricingResult, PricingModel


class PricingEngine:
    """统一定价引擎入口"""

    def __init__(
        self,
        american_model: PricingModel = PricingModel.BAW,
        crr_steps: int = 100,
    ):
        self._greeks_calc = GreeksCalculator()
        self._bs_pricer = BlackScholesPricer(self._greeks_calc)
        self._baw_pricer = BAWPricer()
        self._crr_pricer = CRRPricer(steps=crr_steps)
        self._american_model = american_model

    def price(self, params: PricingInput) -> PricingResult:
        """
        统一定价入口。
        根据 exercise_style 和配置路由到对应定价器。
        """
        error = self._validate(params)
        if error:
            return PricingResult(success=False, error_message=error, model_used="")

        if params.exercise_style == ExerciseStyle.EUROPEAN:
            return self._bs_pricer.price(params)
        else:  # AMERICAN
            if self._american_model == PricingModel.CRR:
                return self._crr_pricer.price(params)
            else:
                return self._baw_pricer.price(params)

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
