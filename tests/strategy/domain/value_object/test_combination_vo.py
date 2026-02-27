"""
值对象单元测试：CombinationType、CombinationStatus、Leg、CombinationGreeks、
LegPnL、CombinationPnL、CombinationRiskConfig

Requirements: 1.5, 5.1, 8.2
"""
import dataclasses
from datetime import datetime

import pytest

from src.strategy.domain.value_object.combination.combination import (
    CombinationGreeks,
    CombinationPnL,
    CombinationRiskConfig,
    CombinationStatus,
    CombinationType,
    Leg,
    LegPnL,
)


# ── CombinationType 枚举 ──────────────────────────────────────────

class TestCombinationType:
    """Validates: Requirement 1.5"""

    def test_has_all_six_values(self):
        expected = {"STRADDLE", "STRANGLE", "VERTICAL_SPREAD",
                    "CALENDAR_SPREAD", "IRON_CONDOR", "CUSTOM"}
        actual = {member.name for member in CombinationType}
        assert actual == expected

    def test_enum_string_values(self):
        assert CombinationType.STRADDLE.value == "straddle"
        assert CombinationType.STRANGLE.value == "strangle"
        assert CombinationType.VERTICAL_SPREAD.value == "vertical_spread"
        assert CombinationType.CALENDAR_SPREAD.value == "calendar_spread"
        assert CombinationType.IRON_CONDOR.value == "iron_condor"
        assert CombinationType.CUSTOM.value == "custom"

    def test_member_count(self):
        assert len(CombinationType) == 6


# ── CombinationStatus 枚举 ─────────────────────────────────────────

class TestCombinationStatus:
    """Validates: Requirement 1.5"""

    def test_has_all_four_values(self):
        expected = {"PENDING", "ACTIVE", "PARTIALLY_CLOSED", "CLOSED"}
        actual = {member.name for member in CombinationStatus}
        assert actual == expected

    def test_enum_string_values(self):
        assert CombinationStatus.PENDING.value == "pending"
        assert CombinationStatus.ACTIVE.value == "active"
        assert CombinationStatus.PARTIALLY_CLOSED.value == "partially_closed"
        assert CombinationStatus.CLOSED.value == "closed"

    def test_member_count(self):
        assert len(CombinationStatus) == 4


# ── Leg frozen 不可变性 ────────────────────────────────────────────

class TestLeg:
    """Validates: Requirement 1.5 — Leg 是 frozen dataclass"""

    @pytest.fixture()
    def sample_leg(self):
        return Leg(
            vt_symbol="m2509-C-2800.DCE",
            option_type="call",
            strike_price=2800.0,
            expiry_date="20250901",
            direction="long",
            volume=1,
            open_price=120.0,
        )

    def test_creation(self, sample_leg):
        assert sample_leg.vt_symbol == "m2509-C-2800.DCE"
        assert sample_leg.option_type == "call"
        assert sample_leg.strike_price == 2800.0
        assert sample_leg.direction == "long"
        assert sample_leg.volume == 1

    def test_frozen_cannot_set_attribute(self, sample_leg):
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample_leg.volume = 10

    def test_frozen_cannot_set_vt_symbol(self, sample_leg):
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample_leg.vt_symbol = "other.DCE"

    def test_frozen_cannot_delete_attribute(self, sample_leg):
        with pytest.raises(dataclasses.FrozenInstanceError):
            del sample_leg.volume

    def test_equality(self):
        leg1 = Leg("sym", "call", 100.0, "20250901", "long", 1, 10.0)
        leg2 = Leg("sym", "call", 100.0, "20250901", "long", 1, 10.0)
        assert leg1 == leg2

    def test_inequality(self):
        leg1 = Leg("sym", "call", 100.0, "20250901", "long", 1, 10.0)
        leg2 = Leg("sym", "put", 100.0, "20250901", "long", 1, 10.0)
        assert leg1 != leg2


# ── CombinationRiskConfig 默认值 ───────────────────────────────────

class TestCombinationRiskConfig:
    """Validates: Requirements 5.1, 8.2"""

    def test_default_values(self):
        config = CombinationRiskConfig()
        assert config.delta_limit == 2.0
        assert config.gamma_limit == 0.5
        assert config.vega_limit == 200.0

    def test_custom_values(self):
        config = CombinationRiskConfig(delta_limit=5.0, gamma_limit=1.0, vega_limit=500.0)
        assert config.delta_limit == 5.0
        assert config.gamma_limit == 1.0
        assert config.vega_limit == 500.0

    def test_frozen(self):
        config = CombinationRiskConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.delta_limit = 99.0


# ── CombinationGreeks 默认值与 failed_legs ─────────────────────────

class TestCombinationGreeks:
    """Validates: Requirement 3.2"""

    def test_default_values(self):
        greeks = CombinationGreeks()
        assert greeks.delta == 0.0
        assert greeks.gamma == 0.0
        assert greeks.theta == 0.0
        assert greeks.vega == 0.0
        assert greeks.failed_legs == []

    def test_with_values(self):
        greeks = CombinationGreeks(delta=1.5, gamma=0.3, theta=-0.1, vega=50.0,
                                   failed_legs=["sym1"])
        assert greeks.delta == 1.5
        assert greeks.failed_legs == ["sym1"]

    def test_frozen(self):
        greeks = CombinationGreeks()
        with pytest.raises(dataclasses.FrozenInstanceError):
            greeks.delta = 99.0


# ── LegPnL 与 CombinationPnL ──────────────────────────────────────

class TestLegPnL:
    def test_creation(self):
        pnl = LegPnL(vt_symbol="sym1", unrealized_pnl=100.0)
        assert pnl.vt_symbol == "sym1"
        assert pnl.unrealized_pnl == 100.0
        assert pnl.price_available is True

    def test_price_unavailable(self):
        pnl = LegPnL(vt_symbol="sym1", unrealized_pnl=0.0, price_available=False)
        assert pnl.price_available is False

    def test_frozen(self):
        pnl = LegPnL(vt_symbol="sym1", unrealized_pnl=100.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            pnl.unrealized_pnl = 999.0


class TestCombinationPnL:
    def test_creation(self):
        leg_pnl = LegPnL(vt_symbol="sym1", unrealized_pnl=50.0)
        now = datetime.now()
        pnl = CombinationPnL(total_unrealized_pnl=50.0, leg_details=[leg_pnl],
                              timestamp=now)
        assert pnl.total_unrealized_pnl == 50.0
        assert len(pnl.leg_details) == 1
        assert pnl.timestamp == now

    def test_default_leg_details_and_timestamp(self):
        pnl = CombinationPnL(total_unrealized_pnl=0.0)
        assert pnl.leg_details == []
        assert isinstance(pnl.timestamp, datetime)

    def test_frozen(self):
        pnl = CombinationPnL(total_unrealized_pnl=0.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            pnl.total_unrealized_pnl = 999.0
