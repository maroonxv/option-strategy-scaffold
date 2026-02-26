"""
Leg.direction_sign 属性测试

Feature: combination-service-optimization
Property 1: direction_sign 正确性

**Validates: Requirements 1.1**
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.value_object.combination import Leg


# ---------------------------------------------------------------------------
# 策略：基础构建块
# ---------------------------------------------------------------------------

_option_type = st.sampled_from(["call", "put"])
_direction = st.sampled_from(["long", "short"])
_strike_price = st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
_expiry_date = st.sampled_from(["20250901", "20251001", "20251101", "20251201"])
_volume = st.integers(min_value=1, max_value=100)
_open_price = st.floats(min_value=0.01, max_value=5000.0, allow_nan=False, allow_infinity=False)


def _leg_strategy(direction=None):
    """构建 Leg 策略，允许固定 direction 字段。"""
    return st.builds(
        Leg,
        vt_symbol=st.from_regex(r"[a-z]{1,4}[0-9]{4}-[CP]-[0-9]{4}\.[A-Z]{3}", fullmatch=True),
        option_type=_option_type,
        strike_price=_strike_price,
        expiry_date=_expiry_date,
        direction=direction if direction is not None else _direction,
        volume=_volume,
        open_price=_open_price,
    )


# ---------------------------------------------------------------------------
# Feature: combination-service-optimization, Property 1: direction_sign 正确性
# ---------------------------------------------------------------------------

class TestProperty1DirectionSignCorrectness:
    """
    Property 1: direction_sign 正确性

    *For any* Leg，当 direction 为 "long" 时 direction_sign 应为 1.0，
    当 direction 为 "short" 时 direction_sign 应为 -1.0。

    **Validates: Requirements 1.1**
    """

    @given(leg=_leg_strategy(direction=st.just("long")))
    @settings(max_examples=100)
    def test_long_direction_returns_positive_one(self, leg: Leg):
        """Feature: combination-service-optimization, Property 1: direction_sign 正确性
        当 direction 为 "long" 时，direction_sign 应为 1.0。
        **Validates: Requirements 1.1**
        """
        assert leg.direction == "long"
        assert leg.direction_sign == 1.0

    @given(leg=_leg_strategy(direction=st.just("short")))
    @settings(max_examples=100)
    def test_short_direction_returns_negative_one(self, leg: Leg):
        """Feature: combination-service-optimization, Property 1: direction_sign 正确性
        当 direction 为 "short" 时，direction_sign 应为 -1.0。
        **Validates: Requirements 1.1**
        """
        assert leg.direction == "short"
        assert leg.direction_sign == -1.0

    @given(leg=_leg_strategy())
    @settings(max_examples=100)
    def test_direction_sign_mapping_is_correct(self, leg: Leg):
        """Feature: combination-service-optimization, Property 1: direction_sign 正确性
        对于任意 Leg，direction_sign 应正确映射：long → 1.0, short → -1.0。
        **Validates: Requirements 1.1**
        """
        expected_sign = 1.0 if leg.direction == "long" else -1.0
        assert leg.direction_sign == expected_sign

    @given(leg=_leg_strategy())
    @settings(max_examples=100)
    def test_direction_sign_is_float(self, leg: Leg):
        """Feature: combination-service-optimization, Property 1: direction_sign 正确性
        direction_sign 应返回 float 类型。
        **Validates: Requirements 1.1**
        """
        assert isinstance(leg.direction_sign, float)

    @given(leg=_leg_strategy())
    @settings(max_examples=100)
    def test_direction_sign_absolute_value_is_one(self, leg: Leg):
        """Feature: combination-service-optimization, Property 1: direction_sign 正确性
        direction_sign 的绝对值应为 1.0。
        **Validates: Requirements 1.1**
        """
        assert abs(leg.direction_sign) == 1.0
