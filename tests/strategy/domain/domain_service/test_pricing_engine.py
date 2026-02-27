"""
PricingEngine 单元测试

验证 PricingEngine 的路由逻辑（欧式→BS、美式→BAW/CRR）和输入校验。
"""
import pytest

from src.strategy.domain.domain_service.pricing import PricingEngine
from src.strategy.domain.value_object.config.pricing_engine_config import PricingEngineConfig
from src.strategy.domain.value_object.pricing.pricing import (
    ExerciseStyle,
    PricingInput,
    PricingModel,
    PricingResult,
)


def _make_input(
    spot_price=100.0,
    strike_price=100.0,
    time_to_expiry=0.5,
    risk_free_rate=0.05,
    volatility=0.2,
    option_type="call",
    exercise_style=ExerciseStyle.EUROPEAN,
) -> PricingInput:
    return PricingInput(
        spot_price=spot_price,
        strike_price=strike_price,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=volatility,
        option_type=option_type,
        exercise_style=exercise_style,
    )


@pytest.fixture
def engine():
    """默认 PricingEngine（美式默认 BAW）"""
    return PricingEngine()


@pytest.fixture
def crr_engine():
    """配置美式使用 CRR 的 PricingEngine"""
    return PricingEngine(config=PricingEngineConfig(american_model=PricingModel.CRR, crr_steps=100))


# ── 路由逻辑测试 ──────────────────────────────────────────────────────────


class TestPricingEngineRouting:
    """测试 PricingEngine 根据 exercise_style 和配置正确路由"""

    def test_european_call_routes_to_bs(self, engine):
        """欧式看涨 → BlackScholes"""
        result = engine.price(_make_input(option_type="call", exercise_style=ExerciseStyle.EUROPEAN))
        assert result.success
        assert result.price > 0
        assert result.model_used == "black_scholes"

    def test_european_put_routes_to_bs(self, engine):
        """欧式看跌 → BlackScholes"""
        result = engine.price(_make_input(option_type="put", exercise_style=ExerciseStyle.EUROPEAN))
        assert result.success
        assert result.price > 0
        assert result.model_used == "black_scholes"

    def test_american_call_default_routes_to_baw(self, engine):
        """美式看涨（默认）→ BAW"""
        result = engine.price(_make_input(option_type="call", exercise_style=ExerciseStyle.AMERICAN))
        assert result.success
        assert result.price > 0
        assert result.model_used == "baw"

    def test_american_put_default_routes_to_baw(self, engine):
        """美式看跌（默认）→ BAW"""
        result = engine.price(_make_input(option_type="put", exercise_style=ExerciseStyle.AMERICAN))
        assert result.success
        assert result.price > 0
        assert result.model_used == "baw"

    def test_american_call_configured_crr(self, crr_engine):
        """美式看涨（配置 CRR）→ CRR"""
        result = crr_engine.price(_make_input(option_type="call", exercise_style=ExerciseStyle.AMERICAN))
        assert result.success
        assert result.price > 0
        assert result.model_used == "crr"

    def test_american_put_configured_crr(self, crr_engine):
        """美式看跌（配置 CRR）→ CRR"""
        result = crr_engine.price(_make_input(option_type="put", exercise_style=ExerciseStyle.AMERICAN))
        assert result.success
        assert result.price > 0
        assert result.model_used == "crr"

    def test_model_used_field_european(self, engine):
        """欧式期权 model_used 字段正确"""
        result = engine.price(_make_input(exercise_style=ExerciseStyle.EUROPEAN))
        assert result.model_used == "black_scholes"

    def test_model_used_field_american_baw(self, engine):
        """美式期权（BAW）model_used 字段正确"""
        result = engine.price(_make_input(exercise_style=ExerciseStyle.AMERICAN))
        assert result.model_used == "baw"

    def test_model_used_field_american_crr(self, crr_engine):
        """美式期权（CRR）model_used 字段正确"""
        result = crr_engine.price(_make_input(exercise_style=ExerciseStyle.AMERICAN))
        assert result.model_used == "crr"


# ── 输入校验测试 ──────────────────────────────────────────────────────────


class TestPricingEngineValidation:
    """测试 PricingEngine 对无效输入返回 success=False"""

    def test_spot_price_zero(self, engine):
        result = engine.price(_make_input(spot_price=0))
        assert not result.success
        assert "spot_price" in result.error_message

    def test_spot_price_negative(self, engine):
        result = engine.price(_make_input(spot_price=-10.0))
        assert not result.success
        assert "spot_price" in result.error_message

    def test_strike_price_zero(self, engine):
        result = engine.price(_make_input(strike_price=0))
        assert not result.success
        assert "strike_price" in result.error_message

    def test_strike_price_negative(self, engine):
        result = engine.price(_make_input(strike_price=-5.0))
        assert not result.success
        assert "strike_price" in result.error_message

    def test_volatility_zero(self, engine):
        result = engine.price(_make_input(volatility=0))
        assert not result.success
        assert "volatility" in result.error_message

    def test_volatility_negative(self, engine):
        result = engine.price(_make_input(volatility=-0.2))
        assert not result.success
        assert "volatility" in result.error_message

    def test_time_to_expiry_negative(self, engine):
        result = engine.price(_make_input(time_to_expiry=-0.01))
        assert not result.success
        assert "time_to_expiry" in result.error_message

    def test_invalid_input_model_used_empty(self, engine):
        """无效输入时 model_used 应为空字符串"""
        result = engine.price(_make_input(spot_price=-1))
        assert not result.success
        assert result.model_used == ""
