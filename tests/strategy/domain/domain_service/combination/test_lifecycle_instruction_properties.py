"""
Lifecycle 指令生成等价性属性测试

Feature: combination-service-optimization
Property 8: Lifecycle 指令生成等价性

*For any* Combination 和 price_map，重构后的 CombinationLifecycleService 生成的
开仓、平仓、调整指令应与重构前完全相同。

**Validates: Requirements 4.5**
"""
from datetime import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from src.strategy.domain.domain_service.combination.combination_lifecycle_service import (
    CombinationLifecycleService,
)
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)
from src.strategy.domain.value_object.trading.order_instruction import (
    Direction,
    Offset,
)


# ---------------------------------------------------------------------------
# 策略：生成随机 Leg 和 Combination
# ---------------------------------------------------------------------------

_direction_st = st.sampled_from(["long", "short"])
_option_type_st = st.sampled_from(["call", "put"])
_volume_st = st.integers(min_value=0, max_value=100)
_active_volume_st = st.integers(min_value=1, max_value=100)
_price_st = st.floats(
    min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False
)
_strike_st = st.floats(
    min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False
)


@st.composite
def random_leg(draw, idx=0):
    """生成随机 Leg，使用唯一的 vt_symbol。"""
    option_type = draw(_option_type_st)
    strike = draw(_strike_st)
    direction = draw(_direction_st)
    volume = draw(_volume_st)
    open_price = draw(_price_st)
    vt_symbol = f"m2509-{option_type[0].upper()}-{int(strike)}-{idx}.DCE"
    return Leg(
        vt_symbol=vt_symbol,
        option_type=option_type,
        strike_price=strike,
        expiry_date="20250901",
        direction=direction,
        volume=volume,
        open_price=open_price,
    )


@st.composite
def random_active_leg(draw, idx=0):
    """生成 volume > 0 的随机 Leg（活跃腿）。"""
    option_type = draw(_option_type_st)
    strike = draw(_strike_st)
    direction = draw(_direction_st)
    volume = draw(_active_volume_st)
    open_price = draw(_price_st)
    vt_symbol = f"m2509-{option_type[0].upper()}-{int(strike)}-{idx}.DCE"
    return Leg(
        vt_symbol=vt_symbol,
        option_type=option_type,
        strike_price=strike,
        expiry_date="20250901",
        direction=direction,
        volume=volume,
        open_price=open_price,
    )


@st.composite
def random_custom_combination(draw):
    """生成随机 CUSTOM Combination，包含 1~6 个 Leg，volume 可为 0 或 > 0。"""
    num_legs = draw(st.integers(min_value=1, max_value=6))
    legs = [draw(random_leg(idx=i)) for i in range(num_legs)]
    return Combination(
        combination_id=f"combo-{draw(st.uuids())}",
        combination_type=CombinationType.CUSTOM,
        underlying_vt_symbol="m2509.DCE",
        legs=legs,
        status=CombinationStatus.ACTIVE,
        create_time=datetime(2025, 1, 15, 10, 30),
    )


@st.composite
def random_active_combination(draw):
    """生成包含 1~6 个活跃 Leg（volume > 0）的随机 CUSTOM Combination。"""
    num_legs = draw(st.integers(min_value=1, max_value=6))
    legs = [draw(random_active_leg(idx=i)) for i in range(num_legs)]
    return Combination(
        combination_id=f"combo-{draw(st.uuids())}",
        combination_type=CombinationType.CUSTOM,
        underlying_vt_symbol="m2509.DCE",
        legs=legs,
        status=CombinationStatus.ACTIVE,
        create_time=datetime(2025, 1, 15, 10, 30),
    )


@st.composite
def random_price_map(draw, combination):
    """为 Combination 的所有 Leg 生成随机价格映射。"""
    price_map = {}
    for leg in combination.legs:
        price_map[leg.vt_symbol] = draw(_price_st)
    return price_map


# ---------------------------------------------------------------------------
# 参考实现：重构前的方向映射逻辑（用于等价性验证）
# ---------------------------------------------------------------------------


def _legacy_direction_for_open(leg_direction: str) -> Direction:
    """重构前的开仓方向映射：直接 if-else。"""
    if leg_direction == "long":
        return Direction.LONG
    else:
        return Direction.SHORT


def _legacy_direction_for_close(leg_direction: str) -> Direction:
    """重构前的平仓方向映射：取反。"""
    if leg_direction == "long":
        return Direction.SHORT
    else:
        return Direction.LONG


def _legacy_direction_for_adjust_increase(leg_direction: str) -> Direction:
    """重构前的增仓方向映射：与 Leg 方向一致。"""
    if leg_direction == "long":
        return Direction.LONG
    else:
        return Direction.SHORT


def _legacy_direction_for_adjust_decrease(leg_direction: str) -> Direction:
    """重构前的减仓方向映射：与 Leg 方向相反。"""
    if leg_direction == "long":
        return Direction.SHORT
    else:
        return Direction.LONG


# ---------------------------------------------------------------------------
# Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
# ---------------------------------------------------------------------------


class TestProperty8LifecycleInstructionEquivalence:
    """
    Property 8: Lifecycle 指令生成等价性

    *For any* Combination 和 price_map，重构后的 CombinationLifecycleService 生成的
    开仓、平仓、调整指令应与重构前完全相同。

    测试策略：
    - Generate random Combination + price_map
    - Verify instruction generation produces correct directions and offsets
    - For open: direction matches leg.direction
    - For close: direction is reversed from leg.direction
    - For adjust: increase uses same direction, decrease uses reversed direction

    **Validates: Requirements 4.5**
    """

    # ========== 开仓指令等价性 ==========

    @given(data=st.data())
    @settings(max_examples=100)
    def test_open_instruction_direction_equals_legacy(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        开仓指令的方向应与重构前的 if-else 逻辑产生相同结果。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_open_instructions(combo, price_map)

        for leg, instr in zip(combo.legs, instructions):
            expected_dir = _legacy_direction_for_open(leg.direction)
            assert instr.direction == expected_dir, (
                f"开仓方向不一致: leg.direction={leg.direction}, "
                f"expected={expected_dir}, actual={instr.direction}"
            )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_open_instruction_offset_is_open(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        所有开仓指令的偏移应为 Offset.OPEN。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_open_instructions(combo, price_map)

        for instr in instructions:
            assert instr.offset == Offset.OPEN

    @given(data=st.data())
    @settings(max_examples=100)
    def test_open_instruction_uses_direction_from_leg_direction(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        开仓指令应使用 Direction.from_leg_direction() 获取方向。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_open_instructions(combo, price_map)

        for leg, instr in zip(combo.legs, instructions):
            expected_dir = Direction.from_leg_direction(leg.direction)
            assert instr.direction == expected_dir

    # ========== 平仓指令等价性 ==========

    @given(data=st.data())
    @settings(max_examples=100)
    def test_close_instruction_direction_equals_legacy(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        平仓指令的方向应与重构前的 if-else 取反逻辑产生相同结果。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_close_instructions(combo, price_map)
        active_legs = combo.get_active_legs()

        for leg, instr in zip(active_legs, instructions):
            expected_dir = _legacy_direction_for_close(leg.direction)
            assert instr.direction == expected_dir, (
                f"平仓方向不一致: leg.direction={leg.direction}, "
                f"expected={expected_dir}, actual={instr.direction}"
            )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_close_instruction_offset_is_close(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        所有平仓指令的偏移应为 Offset.CLOSE。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_close_instructions(combo, price_map)

        for instr in instructions:
            assert instr.offset == Offset.CLOSE

    @given(data=st.data())
    @settings(max_examples=100)
    def test_close_instruction_uses_direction_reverse(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        平仓指令应使用 Direction.from_leg_direction().reverse() 获取方向。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_close_instructions(combo, price_map)
        active_legs = combo.get_active_legs()

        for leg, instr in zip(active_legs, instructions):
            expected_dir = Direction.from_leg_direction(leg.direction).reverse()
            assert instr.direction == expected_dir

    # ========== 调整指令等价性 - 增仓 ==========

    @given(data=st.data())
    @settings(max_examples=100)
    def test_adjust_increase_direction_equals_legacy(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        增仓调整指令的方向应与重构前的 if-else 逻辑产生相同结果（与 Leg 方向一致）。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_active_combination())
        leg_idx = data.draw(st.integers(min_value=0, max_value=len(combo.legs) - 1))
        target_leg = combo.legs[leg_idx]
        new_volume = data.draw(
            st.integers(
                min_value=target_leg.volume + 1, max_value=target_leg.volume + 100
            )
        )
        current_price = data.draw(_price_st)
        svc = CombinationLifecycleService()

        instr = svc.generate_adjust_instruction(
            combo, target_leg.vt_symbol, new_volume, current_price
        )

        expected_dir = _legacy_direction_for_adjust_increase(target_leg.direction)
        assert instr.direction == expected_dir, (
            f"增仓方向不一致: leg.direction={target_leg.direction}, "
            f"expected={expected_dir}, actual={instr.direction}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_adjust_increase_offset_is_open(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        增仓调整指令的偏移应为 Offset.OPEN。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_active_combination())
        leg_idx = data.draw(st.integers(min_value=0, max_value=len(combo.legs) - 1))
        target_leg = combo.legs[leg_idx]
        new_volume = data.draw(
            st.integers(
                min_value=target_leg.volume + 1, max_value=target_leg.volume + 100
            )
        )
        current_price = data.draw(_price_st)
        svc = CombinationLifecycleService()

        instr = svc.generate_adjust_instruction(
            combo, target_leg.vt_symbol, new_volume, current_price
        )

        assert instr.offset == Offset.OPEN

    @given(data=st.data())
    @settings(max_examples=100)
    def test_adjust_increase_uses_direction_from_leg_direction(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        增仓调整指令应使用 Direction.from_leg_direction() 获取方向。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_active_combination())
        leg_idx = data.draw(st.integers(min_value=0, max_value=len(combo.legs) - 1))
        target_leg = combo.legs[leg_idx]
        new_volume = data.draw(
            st.integers(
                min_value=target_leg.volume + 1, max_value=target_leg.volume + 100
            )
        )
        current_price = data.draw(_price_st)
        svc = CombinationLifecycleService()

        instr = svc.generate_adjust_instruction(
            combo, target_leg.vt_symbol, new_volume, current_price
        )

        expected_dir = Direction.from_leg_direction(target_leg.direction)
        assert instr.direction == expected_dir

    # ========== 调整指令等价性 - 减仓 ==========

    @given(data=st.data())
    @settings(max_examples=100)
    def test_adjust_decrease_direction_equals_legacy(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        减仓调整指令的方向应与重构前的 if-else 取反逻辑产生相同结果。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_active_combination())
        leg_idx = data.draw(st.integers(min_value=0, max_value=len(combo.legs) - 1))
        target_leg = combo.legs[leg_idx]
        new_volume = data.draw(
            st.integers(min_value=0, max_value=target_leg.volume - 1)
        )
        current_price = data.draw(_price_st)
        svc = CombinationLifecycleService()

        instr = svc.generate_adjust_instruction(
            combo, target_leg.vt_symbol, new_volume, current_price
        )

        expected_dir = _legacy_direction_for_adjust_decrease(target_leg.direction)
        assert instr.direction == expected_dir, (
            f"减仓方向不一致: leg.direction={target_leg.direction}, "
            f"expected={expected_dir}, actual={instr.direction}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_adjust_decrease_offset_is_close(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        减仓调整指令的偏移应为 Offset.CLOSE。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_active_combination())
        leg_idx = data.draw(st.integers(min_value=0, max_value=len(combo.legs) - 1))
        target_leg = combo.legs[leg_idx]
        new_volume = data.draw(
            st.integers(min_value=0, max_value=target_leg.volume - 1)
        )
        current_price = data.draw(_price_st)
        svc = CombinationLifecycleService()

        instr = svc.generate_adjust_instruction(
            combo, target_leg.vt_symbol, new_volume, current_price
        )

        assert instr.offset == Offset.CLOSE

    @given(data=st.data())
    @settings(max_examples=100)
    def test_adjust_decrease_uses_direction_reverse(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        减仓调整指令应使用 Direction.from_leg_direction().reverse() 获取方向。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_active_combination())
        leg_idx = data.draw(st.integers(min_value=0, max_value=len(combo.legs) - 1))
        target_leg = combo.legs[leg_idx]
        new_volume = data.draw(
            st.integers(min_value=0, max_value=target_leg.volume - 1)
        )
        current_price = data.draw(_price_st)
        svc = CombinationLifecycleService()

        instr = svc.generate_adjust_instruction(
            combo, target_leg.vt_symbol, new_volume, current_price
        )

        expected_dir = Direction.from_leg_direction(target_leg.direction).reverse()
        assert instr.direction == expected_dir

    # ========== 调整指令 volume 正确性 ==========

    @given(data=st.data())
    @settings(max_examples=100)
    def test_adjust_volume_is_absolute_diff(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        调整指令的 volume 应为 |new_volume - current_volume|。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_active_combination())
        leg_idx = data.draw(st.integers(min_value=0, max_value=len(combo.legs) - 1))
        target_leg = combo.legs[leg_idx]
        # new_volume != current volume
        new_volume = data.draw(
            st.integers(min_value=0, max_value=target_leg.volume + 100).filter(
                lambda v: v != target_leg.volume
            )
        )
        current_price = data.draw(_price_st)
        svc = CombinationLifecycleService()

        instr = svc.generate_adjust_instruction(
            combo, target_leg.vt_symbol, new_volume, current_price
        )

        expected_volume = abs(new_volume - target_leg.volume)
        assert instr.volume == expected_volume

    # ========== 综合等价性验证 ==========

    @given(data=st.data())
    @settings(max_examples=100)
    def test_open_close_adjust_all_use_refactored_direction_methods(self, data):
        """Feature: combination-service-optimization, Property 8: Lifecycle 指令生成等价性
        所有指令生成方法应使用重构后的 Direction.from_leg_direction() 和 .reverse()，
        且结果与重构前的 if-else 逻辑完全一致。
        **Validates: Requirements 4.5**
        """
        combo = data.draw(random_active_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        # 验证开仓指令
        open_instructions = svc.generate_open_instructions(combo, price_map)
        for leg, instr in zip(combo.legs, open_instructions):
            # 重构后方法
            refactored_dir = Direction.from_leg_direction(leg.direction)
            # 重构前逻辑
            legacy_dir = _legacy_direction_for_open(leg.direction)
            # 两者应相等
            assert refactored_dir == legacy_dir
            # 指令方向应与两者一致
            assert instr.direction == refactored_dir == legacy_dir

        # 验证平仓指令
        close_instructions = svc.generate_close_instructions(combo, price_map)
        active_legs = combo.get_active_legs()
        for leg, instr in zip(active_legs, close_instructions):
            # 重构后方法
            refactored_dir = Direction.from_leg_direction(leg.direction).reverse()
            # 重构前逻辑
            legacy_dir = _legacy_direction_for_close(leg.direction)
            # 两者应相等
            assert refactored_dir == legacy_dir
            # 指令方向应与两者一致
            assert instr.direction == refactored_dir == legacy_dir

        # 验证调整指令（增仓）
        if len(combo.legs) > 0:
            target_leg = combo.legs[0]
            new_volume = target_leg.volume + 10
            current_price = data.draw(_price_st)
            instr = svc.generate_adjust_instruction(
                combo, target_leg.vt_symbol, new_volume, current_price
            )
            # 重构后方法
            refactored_dir = Direction.from_leg_direction(target_leg.direction)
            # 重构前逻辑
            legacy_dir = _legacy_direction_for_adjust_increase(target_leg.direction)
            # 两者应相等
            assert refactored_dir == legacy_dir
            # 指令方向应与两者一致
            assert instr.direction == refactored_dir == legacy_dir

            # 验证调整指令（减仓）
            if target_leg.volume > 1:
                new_volume = target_leg.volume - 1
                instr = svc.generate_adjust_instruction(
                    combo, target_leg.vt_symbol, new_volume, current_price
                )
                # 重构后方法
                refactored_dir = Direction.from_leg_direction(
                    target_leg.direction
                ).reverse()
                # 重构前逻辑
                legacy_dir = _legacy_direction_for_adjust_decrease(target_leg.direction)
                # 两者应相等
                assert refactored_dir == legacy_dir
                # 指令方向应与两者一致
                assert instr.direction == refactored_dir == legacy_dir
