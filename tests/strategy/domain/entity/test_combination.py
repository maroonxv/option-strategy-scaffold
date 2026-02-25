"""Combination 实体单元测试"""
from datetime import datetime

import pytest

from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)


# ========== 辅助工厂 ==========

def _make_leg(
    vt_symbol: str = "m2509-C-2800.DCE",
    option_type: str = "call",
    strike_price: float = 2800.0,
    expiry_date: str = "20250901",
    direction: str = "short",
    volume: int = 1,
    open_price: float = 120.0,
) -> Leg:
    return Leg(
        vt_symbol=vt_symbol,
        option_type=option_type,
        strike_price=strike_price,
        expiry_date=expiry_date,
        direction=direction,
        volume=volume,
        open_price=open_price,
    )


def _make_combination(
    combination_type: CombinationType = CombinationType.STRADDLE,
    legs: list | None = None,
    status: CombinationStatus = CombinationStatus.ACTIVE,
) -> Combination:
    if legs is None:
        legs = [
            _make_leg(vt_symbol="m2509-C-2800.DCE", option_type="call"),
            _make_leg(vt_symbol="m2509-P-2800.DCE", option_type="put"),
        ]
    return Combination(
        combination_id="test-uuid",
        combination_type=combination_type,
        underlying_vt_symbol="m2509.DCE",
        legs=legs,
        status=status,
        create_time=datetime(2025, 1, 15, 10, 30, 0),
    )


# ========== validate() 测试 ==========


class TestValidateStraddle:
    def test_valid_straddle(self):
        combo = _make_combination(CombinationType.STRADDLE)
        combo.validate()  # 不抛异常

    def test_straddle_wrong_leg_count(self):
        combo = _make_combination(
            CombinationType.STRADDLE,
            legs=[_make_leg()],
        )
        with pytest.raises(ValueError, match="2 腿"):
            combo.validate()

    def test_straddle_different_expiry(self):
        combo = _make_combination(
            CombinationType.STRADDLE,
            legs=[
                _make_leg(option_type="call", expiry_date="20250901"),
                _make_leg(option_type="put", expiry_date="20251001"),
            ],
        )
        with pytest.raises(ValueError, match="到期日"):
            combo.validate()

    def test_straddle_different_strike(self):
        combo = _make_combination(
            CombinationType.STRADDLE,
            legs=[
                _make_leg(option_type="call", strike_price=2800.0),
                _make_leg(option_type="put", strike_price=2900.0),
            ],
        )
        with pytest.raises(ValueError, match="行权价"):
            combo.validate()

    def test_straddle_same_option_type(self):
        combo = _make_combination(
            CombinationType.STRADDLE,
            legs=[
                _make_leg(option_type="call"),
                _make_leg(option_type="call", vt_symbol="m2509-C-2800b.DCE"),
            ],
        )
        with pytest.raises(ValueError, match="Call.*Put"):
            combo.validate()


class TestValidateStrangle:
    def test_valid_strangle(self):
        combo = _make_combination(
            CombinationType.STRANGLE,
            legs=[
                _make_leg(option_type="call", strike_price=2900.0),
                _make_leg(option_type="put", strike_price=2700.0),
            ],
        )
        combo.validate()

    def test_strangle_same_strike(self):
        combo = _make_combination(
            CombinationType.STRANGLE,
            legs=[
                _make_leg(option_type="call", strike_price=2800.0),
                _make_leg(option_type="put", strike_price=2800.0),
            ],
        )
        with pytest.raises(ValueError, match="行权价不同"):
            combo.validate()


class TestValidateVerticalSpread:
    def test_valid_vertical_spread(self):
        combo = _make_combination(
            CombinationType.VERTICAL_SPREAD,
            legs=[
                _make_leg(option_type="call", strike_price=2800.0),
                _make_leg(option_type="call", strike_price=2900.0, vt_symbol="m2509-C-2900.DCE"),
            ],
        )
        combo.validate()

    def test_vertical_spread_different_type(self):
        combo = _make_combination(
            CombinationType.VERTICAL_SPREAD,
            legs=[
                _make_leg(option_type="call", strike_price=2800.0),
                _make_leg(option_type="put", strike_price=2900.0),
            ],
        )
        with pytest.raises(ValueError, match="类型相同"):
            combo.validate()

    def test_vertical_spread_same_strike(self):
        combo = _make_combination(
            CombinationType.VERTICAL_SPREAD,
            legs=[
                _make_leg(option_type="call", strike_price=2800.0),
                _make_leg(option_type="call", strike_price=2800.0, vt_symbol="m2509-C-2800b.DCE"),
            ],
        )
        with pytest.raises(ValueError, match="行权价不同"):
            combo.validate()


class TestValidateCalendarSpread:
    def test_valid_calendar_spread(self):
        combo = _make_combination(
            CombinationType.CALENDAR_SPREAD,
            legs=[
                _make_leg(option_type="call", expiry_date="20250901"),
                _make_leg(option_type="call", expiry_date="20251001", vt_symbol="m2510-C-2800.DCE"),
            ],
        )
        combo.validate()

    def test_calendar_spread_same_expiry(self):
        combo = _make_combination(
            CombinationType.CALENDAR_SPREAD,
            legs=[
                _make_leg(option_type="call", expiry_date="20250901"),
                _make_leg(option_type="call", expiry_date="20250901", vt_symbol="m2509-C-2800b.DCE"),
            ],
        )
        with pytest.raises(ValueError, match="到期日不同"):
            combo.validate()


class TestValidateIronCondor:
    def test_valid_iron_condor(self):
        combo = _make_combination(
            CombinationType.IRON_CONDOR,
            legs=[
                _make_leg(option_type="put", strike_price=2600.0, vt_symbol="m2509-P-2600.DCE"),
                _make_leg(option_type="put", strike_price=2700.0, vt_symbol="m2509-P-2700.DCE"),
                _make_leg(option_type="call", strike_price=2900.0, vt_symbol="m2509-C-2900.DCE"),
                _make_leg(option_type="call", strike_price=3000.0, vt_symbol="m2509-C-3000.DCE"),
            ],
        )
        combo.validate()

    def test_iron_condor_wrong_leg_count(self):
        combo = _make_combination(
            CombinationType.IRON_CONDOR,
            legs=[_make_leg(), _make_leg(vt_symbol="x"), _make_leg(vt_symbol="y")],
        )
        with pytest.raises(ValueError, match="4 腿"):
            combo.validate()

    def test_iron_condor_not_2_puts_2_calls(self):
        combo = _make_combination(
            CombinationType.IRON_CONDOR,
            legs=[
                _make_leg(option_type="call", strike_price=2600.0, vt_symbol="a"),
                _make_leg(option_type="call", strike_price=2700.0, vt_symbol="b"),
                _make_leg(option_type="call", strike_price=2900.0, vt_symbol="c"),
                _make_leg(option_type="put", strike_price=3000.0, vt_symbol="d"),
            ],
        )
        with pytest.raises(ValueError, match="2 个 Put.*2 个 Call"):
            combo.validate()

    def test_iron_condor_puts_same_strike(self):
        combo = _make_combination(
            CombinationType.IRON_CONDOR,
            legs=[
                _make_leg(option_type="put", strike_price=2700.0, vt_symbol="a"),
                _make_leg(option_type="put", strike_price=2700.0, vt_symbol="b"),
                _make_leg(option_type="call", strike_price=2900.0, vt_symbol="c"),
                _make_leg(option_type="call", strike_price=3000.0, vt_symbol="d"),
            ],
        )
        with pytest.raises(ValueError, match="Put.*行权价不同"):
            combo.validate()

    def test_iron_condor_different_expiry(self):
        combo = _make_combination(
            CombinationType.IRON_CONDOR,
            legs=[
                _make_leg(option_type="put", strike_price=2600.0, expiry_date="20250901", vt_symbol="a"),
                _make_leg(option_type="put", strike_price=2700.0, expiry_date="20250901", vt_symbol="b"),
                _make_leg(option_type="call", strike_price=2900.0, expiry_date="20251001", vt_symbol="c"),
                _make_leg(option_type="call", strike_price=3000.0, expiry_date="20250901", vt_symbol="d"),
            ],
        )
        with pytest.raises(ValueError, match="到期日"):
            combo.validate()


class TestValidateCustom:
    def test_valid_custom(self):
        combo = _make_combination(
            CombinationType.CUSTOM,
            legs=[_make_leg()],
        )
        combo.validate()

    def test_custom_empty_legs(self):
        combo = _make_combination(
            CombinationType.CUSTOM,
            legs=[],
        )
        with pytest.raises(ValueError, match="至少.*1 腿"):
            combo.validate()


# ========== update_status() 测试 ==========


class TestUpdateStatus:
    def test_all_closed(self):
        combo = _make_combination()
        result = combo.update_status({"m2509-C-2800.DCE", "m2509-P-2800.DCE"})
        assert result == CombinationStatus.CLOSED
        assert combo.status == CombinationStatus.CLOSED
        assert combo.close_time is not None

    def test_partially_closed(self):
        combo = _make_combination()
        result = combo.update_status({"m2509-C-2800.DCE"})
        assert result == CombinationStatus.PARTIALLY_CLOSED
        assert combo.status == CombinationStatus.PARTIALLY_CLOSED

    def test_none_closed(self):
        combo = _make_combination()
        result = combo.update_status({"other-symbol"})
        assert result is None
        assert combo.status == CombinationStatus.ACTIVE

    def test_already_partially_closed_no_change(self):
        combo = _make_combination(status=CombinationStatus.PARTIALLY_CLOSED)
        result = combo.update_status({"m2509-C-2800.DCE"})
        assert result is None  # 状态未变

    def test_partially_to_closed(self):
        combo = _make_combination(status=CombinationStatus.PARTIALLY_CLOSED)
        result = combo.update_status({"m2509-C-2800.DCE", "m2509-P-2800.DCE"})
        assert result == CombinationStatus.CLOSED


# ========== get_active_legs() 测试 ==========


class TestGetActiveLegs:
    def test_all_active(self):
        combo = _make_combination()
        active = combo.get_active_legs()
        assert len(active) == 2

    def test_with_zero_volume_leg(self):
        combo = _make_combination(
            legs=[
                _make_leg(volume=1),
                _make_leg(volume=0, vt_symbol="m2509-P-2800.DCE", option_type="put"),
            ],
        )
        active = combo.get_active_legs()
        assert len(active) == 1
        assert active[0].volume == 1


# ========== to_dict() / from_dict() 测试 ==========


class TestSerialization:
    def test_roundtrip(self):
        combo = _make_combination()
        data = combo.to_dict()
        restored = Combination.from_dict(data)

        assert restored.combination_id == combo.combination_id
        assert restored.combination_type == combo.combination_type
        assert restored.underlying_vt_symbol == combo.underlying_vt_symbol
        assert restored.status == combo.status
        assert restored.create_time == combo.create_time
        assert restored.close_time == combo.close_time
        assert len(restored.legs) == len(combo.legs)
        for orig, rest in zip(combo.legs, restored.legs):
            assert orig.vt_symbol == rest.vt_symbol
            assert orig.option_type == rest.option_type
            assert orig.strike_price == rest.strike_price
            assert orig.expiry_date == rest.expiry_date
            assert orig.direction == rest.direction
            assert orig.volume == rest.volume
            assert orig.open_price == rest.open_price

    def test_to_dict_format(self):
        combo = _make_combination()
        data = combo.to_dict()
        assert data["combination_type"] == "straddle"
        assert data["status"] == "active"
        assert data["close_time"] is None
        assert isinstance(data["legs"], list)
        assert data["legs"][0]["option_type"] == "call"

    def test_roundtrip_with_close_time(self):
        combo = _make_combination()
        combo.close_time = datetime(2025, 2, 1, 15, 0, 0)
        data = combo.to_dict()
        restored = Combination.from_dict(data)
        assert restored.close_time == combo.close_time
