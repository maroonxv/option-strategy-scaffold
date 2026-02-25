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
