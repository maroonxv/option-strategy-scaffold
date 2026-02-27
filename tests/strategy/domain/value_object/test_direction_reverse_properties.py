"""
Direction.reverse 对合性属性测试

Feature: combination-service-optimization
Property 7: Direction.reverse round-trip

**Validates: Requirements 4.2**
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.value_object.trading.order_instruction import Direction


# ---------------------------------------------------------------------------
# 策略：Direction 枚举值
# ---------------------------------------------------------------------------

_direction = st.sampled_from([Direction.LONG, Direction.SHORT])


# ---------------------------------------------------------------------------
# Feature: combination-service-optimization, Property 7: Direction.reverse round-trip
# ---------------------------------------------------------------------------

class TestProperty7DirectionReverseRoundTrip:
    """
    Property 7: Direction.reverse 对合性（round-trip）

    *For any* Direction 值 d，`d.reverse().reverse()` 应等于 d。
    且 `Direction.LONG.reverse()` 应为 `Direction.SHORT`，反之亦然。

    **Validates: Requirements 4.2**
    """

    @given(d=_direction)
    @settings(max_examples=100)
    def test_reverse_round_trip(self, d: Direction):
        """Feature: combination-service-optimization, Property 7: Direction.reverse round-trip
        对于任意 Direction 值 d，d.reverse().reverse() 应等于 d。
        **Validates: Requirements 4.2**
        """
        assert d.reverse().reverse() == d

    @given(d=_direction)
    @settings(max_examples=100)
    def test_reverse_is_involution(self, d: Direction):
        """Feature: combination-service-optimization, Property 7: Direction.reverse round-trip
        reverse 是对合映射（involution），即 reverse(reverse(x)) = x。
        **Validates: Requirements 4.2**
        """
        # 对合性：函数与自身复合等于恒等函数
        assert d.reverse().reverse() is d

    def test_long_reverse_is_short(self):
        """Feature: combination-service-optimization, Property 7: Direction.reverse round-trip
        Direction.LONG.reverse() 应为 Direction.SHORT。
        **Validates: Requirements 4.2**
        """
        assert Direction.LONG.reverse() == Direction.SHORT

    def test_short_reverse_is_long(self):
        """Feature: combination-service-optimization, Property 7: Direction.reverse round-trip
        Direction.SHORT.reverse() 应为 Direction.LONG。
        **Validates: Requirements 4.2**
        """
        assert Direction.SHORT.reverse() == Direction.LONG

    @given(d=_direction)
    @settings(max_examples=100)
    def test_reverse_returns_direction_type(self, d: Direction):
        """Feature: combination-service-optimization, Property 7: Direction.reverse round-trip
        reverse() 应返回 Direction 类型。
        **Validates: Requirements 4.2**
        """
        assert isinstance(d.reverse(), Direction)

    @given(d=_direction)
    @settings(max_examples=100)
    def test_reverse_returns_different_value(self, d: Direction):
        """Feature: combination-service-optimization, Property 7: Direction.reverse round-trip
        reverse() 应返回与原值不同的 Direction。
        **Validates: Requirements 4.2**
        """
        assert d.reverse() != d

    @given(d=_direction)
    @settings(max_examples=100)
    def test_reverse_is_bijective(self, d: Direction):
        """Feature: combination-service-optimization, Property 7: Direction.reverse round-trip
        reverse 是双射（bijection）：每个 Direction 值恰好映射到另一个不同的 Direction 值。
        **Validates: Requirements 4.2**
        """
        reversed_d = d.reverse()
        # 双射性：不同输入映射到不同输出
        assert reversed_d != d
        # 且反向映射回原值
        assert reversed_d.reverse() == d

