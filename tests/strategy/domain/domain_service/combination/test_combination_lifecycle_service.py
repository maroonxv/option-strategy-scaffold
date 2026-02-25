"""
CombinationLifecycleService 单元测试
"""
from datetime import datetime

import pytest

from src.strategy.domain.domain_service.combination.combination_lifecycle_service import (
    CombinationLifecycleService,
)
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)
from src.strategy.domain.value_object.order_instruction import (
    Direction,
    Offset,
)


def _make_combination(legs: list, ctype=CombinationType.CUSTOM) -> Combination:
    return Combination(
        combination_id="test-combo-1",
        combination_type=ctype,
        underlying_vt_symbol="m2509.DCE",
        legs=legs,
        status=CombinationStatus.ACTIVE,
        create_time=datetime(2025, 1, 15, 10, 30),
    )


@pytest.fixture
def service():
    return CombinationLifecycleService()


# ========== generate_open_instructions ==========


class TestGenerateOpenInstructions:
    def test_generates_one_instruction_per_leg(self, service):
        legs = [
            Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 2, 120.0),
            Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 3, 95.0),
        ]
        combo = _make_combination(legs)
        price_map = {"m2509-C-2800.DCE": 125.0, "m2509-P-2800.DCE": 90.0}

        result = service.generate_open_instructions(combo, price_map)

        assert len(result) == 2

    def test_long_leg_maps_to_long_direction(self, service):
        legs = [Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 1, 120.0)]
        combo = _make_combination(legs)
        price_map = {"m2509-C-2800.DCE": 125.0}

        result = service.generate_open_instructions(combo, price_map)

        assert result[0].direction == Direction.LONG

    def test_short_leg_maps_to_short_direction(self, service):
        legs = [Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 1, 95.0)]
        combo = _make_combination(legs)
        price_map = {"m2509-P-2800.DCE": 90.0}

        result = service.generate_open_instructions(combo, price_map)

        assert result[0].direction == Direction.SHORT

    def test_all_instructions_have_open_offset(self, service):
        legs = [
            Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 1, 120.0),
            Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 1, 95.0),
        ]
        combo = _make_combination(legs)
        price_map = {"m2509-C-2800.DCE": 125.0, "m2509-P-2800.DCE": 90.0}

        result = service.generate_open_instructions(combo, price_map)

        for instr in result:
            assert instr.offset == Offset.OPEN

    def test_volume_and_price_correct(self, service):
        legs = [Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 5, 120.0)]
        combo = _make_combination(legs)
        price_map = {"m2509-C-2800.DCE": 130.0}

        result = service.generate_open_instructions(combo, price_map)

        assert result[0].volume == 5
        assert result[0].price == 130.0

    def test_missing_price_defaults_to_zero(self, service):
        legs = [Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 1, 120.0)]
        combo = _make_combination(legs)

        result = service.generate_open_instructions(combo, {})

        assert result[0].price == 0.0


# ========== generate_close_instructions ==========


class TestGenerateCloseInstructions:
    def test_generates_instructions_for_active_legs_only(self, service):
        legs = [
            Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 2, 120.0),
            Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 0, 95.0),  # closed
        ]
        combo = _make_combination(legs)
        price_map = {"m2509-C-2800.DCE": 125.0, "m2509-P-2800.DCE": 90.0}

        result = service.generate_close_instructions(combo, price_map)

        assert len(result) == 1
        assert result[0].vt_symbol == "m2509-C-2800.DCE"

    def test_long_leg_closes_with_short_direction(self, service):
        legs = [Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 1, 120.0)]
        combo = _make_combination(legs)
        price_map = {"m2509-C-2800.DCE": 125.0}

        result = service.generate_close_instructions(combo, price_map)

        assert result[0].direction == Direction.SHORT

    def test_short_leg_closes_with_long_direction(self, service):
        legs = [Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 1, 95.0)]
        combo = _make_combination(legs)
        price_map = {"m2509-P-2800.DCE": 90.0}

        result = service.generate_close_instructions(combo, price_map)

        assert result[0].direction == Direction.LONG

    def test_all_instructions_have_close_offset(self, service):
        legs = [
            Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 1, 120.0),
            Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 1, 95.0),
        ]
        combo = _make_combination(legs)
        price_map = {"m2509-C-2800.DCE": 125.0, "m2509-P-2800.DCE": 90.0}

        result = service.generate_close_instructions(combo, price_map)

        for instr in result:
            assert instr.offset == Offset.CLOSE

    def test_all_legs_closed_returns_empty(self, service):
        legs = [
            Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 0, 120.0),
            Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 0, 95.0),
        ]
        combo = _make_combination(legs)

        result = service.generate_close_instructions(combo, {})

        assert len(result) == 0


# ========== generate_adjust_instruction ==========


class TestGenerateAdjustInstruction:
    def test_increase_volume_generates_open_instruction(self, service):
        legs = [Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 2, 120.0)]
        combo = _make_combination(legs)

        result = service.generate_adjust_instruction(
            combo, "m2509-C-2800.DCE", 5, 130.0
        )

        assert result.offset == Offset.OPEN
        assert result.direction == Direction.LONG
        assert result.volume == 3  # 5 - 2

    def test_decrease_volume_generates_close_instruction(self, service):
        legs = [Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 5, 120.0)]
        combo = _make_combination(legs)

        result = service.generate_adjust_instruction(
            combo, "m2509-C-2800.DCE", 2, 130.0
        )

        assert result.offset == Offset.CLOSE
        assert result.direction == Direction.SHORT  # opposite of long
        assert result.volume == 3  # 5 - 2

    def test_increase_short_leg_generates_short_open(self, service):
        legs = [Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 1, 95.0)]
        combo = _make_combination(legs)

        result = service.generate_adjust_instruction(
            combo, "m2509-P-2800.DCE", 3, 100.0
        )

        assert result.offset == Offset.OPEN
        assert result.direction == Direction.SHORT
        assert result.volume == 2

    def test_decrease_short_leg_generates_long_close(self, service):
        legs = [Leg("m2509-P-2800.DCE", "put", 2800.0, "20250901", "short", 4, 95.0)]
        combo = _make_combination(legs)

        result = service.generate_adjust_instruction(
            combo, "m2509-P-2800.DCE", 1, 100.0
        )

        assert result.offset == Offset.CLOSE
        assert result.direction == Direction.LONG  # opposite of short
        assert result.volume == 3

    def test_leg_not_found_raises_value_error(self, service):
        legs = [Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 1, 120.0)]
        combo = _make_combination(legs)

        with pytest.raises(ValueError, match="不存在"):
            service.generate_adjust_instruction(
                combo, "nonexistent.DCE", 5, 130.0
            )

    def test_same_volume_raises_value_error(self, service):
        legs = [Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 3, 120.0)]
        combo = _make_combination(legs)

        with pytest.raises(ValueError, match="无需调整"):
            service.generate_adjust_instruction(
                combo, "m2509-C-2800.DCE", 3, 130.0
            )

    def test_adjust_uses_current_price(self, service):
        legs = [Leg("m2509-C-2800.DCE", "call", 2800.0, "20250901", "long", 2, 120.0)]
        combo = _make_combination(legs)

        result = service.generate_adjust_instruction(
            combo, "m2509-C-2800.DCE", 4, 135.5
        )

        assert result.price == 135.5


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------
from hypothesis import given, settings
from hypothesis import strategies as st

# Hypothesis strategies for generating random CUSTOM Combinations
_direction_st = st.sampled_from(["long", "short"])
_option_type_st = st.sampled_from(["call", "put"])
_volume_st = st.integers(min_value=0, max_value=100)
_price_st = st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)
_strike_st = st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False)


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
def random_price_map(draw, combination):
    """为 Combination 的所有 Leg 生成随机价格映射。"""
    price_map = {}
    for leg in combination.legs:
        price_map[leg.vt_symbol] = draw(_price_st)
    return price_map


# ---------------------------------------------------------------------------
# Feature: combination-strategy-management, Property 6: 生命周期指令生成
# ---------------------------------------------------------------------------

class TestProperty6LifecycleInstructionGeneration:
    """
    Property 6: 生命周期指令生成

    *For any* Combination，generate_open_instructions 应为每个 Leg 生成恰好一个
    OrderInstruction（方向和偏移正确），generate_close_instructions 应为每个活跃 Leg
    生成恰好一个平仓 OrderInstruction（已平仓 Leg 被跳过）。

    **Validates: Requirements 6.1, 6.2, 6.6**
    """

    @given(data=st.data())
    @settings(max_examples=100)
    def test_open_instructions_count_equals_leg_count(self, data):
        """Feature: combination-strategy-management, Property 6: 生命周期指令生成
        open_instructions 数量等于 Leg 数量。
        **Validates: Requirements 6.1**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_open_instructions(combo, price_map)

        assert len(instructions) == len(combo.legs)

    @given(data=st.data())
    @settings(max_examples=100)
    def test_open_instructions_direction_and_offset_correct(self, data):
        """Feature: combination-strategy-management, Property 6: 生命周期指令生成
        每个 open instruction 的方向与 Leg 方向一致，偏移为 OPEN。
        **Validates: Requirements 6.1**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_open_instructions(combo, price_map)

        for leg, instr in zip(combo.legs, instructions):
            expected_dir = Direction.LONG if leg.direction == "long" else Direction.SHORT
            assert instr.vt_symbol == leg.vt_symbol
            assert instr.direction == expected_dir
            assert instr.offset == Offset.OPEN
            assert instr.volume == leg.volume

    @given(data=st.data())
    @settings(max_examples=100)
    def test_close_instructions_count_equals_active_leg_count(self, data):
        """Feature: combination-strategy-management, Property 6: 生命周期指令生成
        close_instructions 数量等于活跃 Leg（volume > 0）数量。
        **Validates: Requirements 6.2, 6.6**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_close_instructions(combo, price_map)
        active_legs = [leg for leg in combo.legs if leg.volume > 0]

        assert len(instructions) == len(active_legs)

    @given(data=st.data())
    @settings(max_examples=100)
    def test_close_instructions_direction_reversed_and_offset_close(self, data):
        """Feature: combination-strategy-management, Property 6: 生命周期指令生成
        每个 close instruction 的方向与 Leg 方向相反，偏移为 CLOSE。
        **Validates: Requirements 6.2, 6.6**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_close_instructions(combo, price_map)
        active_legs = combo.get_active_legs()

        for leg, instr in zip(active_legs, instructions):
            expected_dir = Direction.SHORT if leg.direction == "long" else Direction.LONG
            assert instr.vt_symbol == leg.vt_symbol
            assert instr.direction == expected_dir
            assert instr.offset == Offset.CLOSE
            assert instr.volume == leg.volume

    @given(data=st.data())
    @settings(max_examples=100)
    def test_closed_legs_skipped_in_close_instructions(self, data):
        """Feature: combination-strategy-management, Property 6: 生命周期指令生成
        volume == 0 的 Leg 不出现在 close_instructions 中。
        **Validates: Requirements 6.6**
        """
        combo = data.draw(random_custom_combination())
        price_map = data.draw(random_price_map(combo))
        svc = CombinationLifecycleService()

        instructions = svc.generate_close_instructions(combo, price_map)
        closed_symbols = {leg.vt_symbol for leg in combo.legs if leg.volume == 0}

        for instr in instructions:
            assert instr.vt_symbol not in closed_symbols
