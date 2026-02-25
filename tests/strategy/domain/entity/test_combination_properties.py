"""
Combination 实体属性测试

Feature: combination-strategy-management
"""
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)

# ---------------------------------------------------------------------------
# 策略：基础构建块
# ---------------------------------------------------------------------------

_option_type = st.sampled_from(["call", "put"])
_direction = st.sampled_from(["long", "short"])
_strike_price = st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
_expiry_date = st.sampled_from(["20250901", "20251001", "20251101", "20251201"])
_volume = st.integers(min_value=1, max_value=100)
_open_price = st.floats(min_value=0.01, max_value=5000.0, allow_nan=False, allow_infinity=False)
_combination_type = st.sampled_from(list(CombinationType))


def _leg_strategy(
    vt_symbol=None,
    option_type=None,
    strike_price=None,
    expiry_date=None,
    direction=None,
    volume=None,
    open_price=None,
):
    """构建 Leg 策略，允许固定某些字段。"""
    return st.builds(
        Leg,
        vt_symbol=vt_symbol or st.from_regex(r"[a-z]{1,4}[0-9]{4}-[CP]-[0-9]{4}\.[A-Z]{3}", fullmatch=True),
        option_type=option_type or _option_type,
        strike_price=strike_price or _strike_price,
        expiry_date=expiry_date or _expiry_date,
        direction=direction or _direction,
        volume=volume or _volume,
        open_price=open_price or _open_price,
    )


# ---------------------------------------------------------------------------
# 策略：生成满足各类型约束的有效 Combination
# ---------------------------------------------------------------------------

def _valid_straddle_legs():
    """生成有效的 STRADDLE 腿：2 腿，同到期日、同行权价、一 Call 一 Put"""
    return st.tuples(_strike_price, _expiry_date, _direction, _direction, _volume, _volume, _open_price, _open_price).map(
        lambda t: [
            Leg(vt_symbol=f"opt-C-{int(t[0])}.EX", option_type="call", strike_price=t[0],
                expiry_date=t[1], direction=t[2], volume=t[4], open_price=t[6]),
            Leg(vt_symbol=f"opt-P-{int(t[0])}.EX", option_type="put", strike_price=t[0],
                expiry_date=t[1], direction=t[3], volume=t[5], open_price=t[7]),
        ]
    )


def _valid_strangle_legs():
    """生成有效的 STRANGLE 腿：2 腿，同到期日、不同行权价、一 Call 一 Put"""
    return st.tuples(
        _strike_price, _strike_price, _expiry_date,
        _direction, _direction, _volume, _volume, _open_price, _open_price,
    ).filter(lambda t: t[0] != t[1]).map(
        lambda t: [
            Leg(vt_symbol=f"opt-C-{int(t[0])}.EX", option_type="call", strike_price=t[0],
                expiry_date=t[2], direction=t[3], volume=t[5], open_price=t[7]),
            Leg(vt_symbol=f"opt-P-{int(t[1])}.EX", option_type="put", strike_price=t[1],
                expiry_date=t[2], direction=t[4], volume=t[6], open_price=t[8]),
        ]
    )


def _valid_vertical_spread_legs():
    """生成有效的 VERTICAL_SPREAD 腿：2 腿，同到期日、同类型、不同行权价"""
    return st.tuples(
        _option_type, _strike_price, _strike_price, _expiry_date,
        _direction, _direction, _volume, _volume, _open_price, _open_price,
    ).filter(lambda t: t[1] != t[2]).map(
        lambda t: [
            Leg(vt_symbol=f"opt-{t[0][0].upper()}-{int(t[1])}.EX", option_type=t[0], strike_price=t[1],
                expiry_date=t[3], direction=t[4], volume=t[6], open_price=t[8]),
            Leg(vt_symbol=f"opt-{t[0][0].upper()}-{int(t[2])}.EX", option_type=t[0], strike_price=t[2],
                expiry_date=t[3], direction=t[5], volume=t[7], open_price=t[9]),
        ]
    )


def _valid_calendar_spread_legs():
    """生成有效的 CALENDAR_SPREAD 腿：2 腿，不同到期日、同行权价、同类型"""
    return st.tuples(
        _option_type, _strike_price, _expiry_date, _expiry_date,
        _direction, _direction, _volume, _volume, _open_price, _open_price,
    ).filter(lambda t: t[2] != t[3]).map(
        lambda t: [
            Leg(vt_symbol=f"opt-{t[0][0].upper()}-{int(t[1])}-A.EX", option_type=t[0], strike_price=t[1],
                expiry_date=t[2], direction=t[4], volume=t[6], open_price=t[8]),
            Leg(vt_symbol=f"opt-{t[0][0].upper()}-{int(t[1])}-B.EX", option_type=t[0], strike_price=t[1],
                expiry_date=t[3], direction=t[5], volume=t[7], open_price=t[9]),
        ]
    )


def _valid_iron_condor_legs():
    """生成有效的 IRON_CONDOR 腿：4 腿，同到期日，2 Put 不同行权价 + 2 Call 不同行权价"""
    return st.tuples(
        _expiry_date,
        _strike_price, _strike_price,  # put strikes
        _strike_price, _strike_price,  # call strikes
        st.lists(_direction, min_size=4, max_size=4),
        st.lists(_volume, min_size=4, max_size=4),
        st.lists(_open_price, min_size=4, max_size=4),
    ).filter(lambda t: t[1] != t[2] and t[3] != t[4]).map(
        lambda t: [
            Leg(vt_symbol=f"opt-P-{int(t[1])}.EX", option_type="put", strike_price=t[1],
                expiry_date=t[0], direction=t[5][0], volume=t[6][0], open_price=t[7][0]),
            Leg(vt_symbol=f"opt-P-{int(t[2])}.EX", option_type="put", strike_price=t[2],
                expiry_date=t[0], direction=t[5][1], volume=t[6][1], open_price=t[7][1]),
            Leg(vt_symbol=f"opt-C-{int(t[3])}.EX", option_type="call", strike_price=t[3],
                expiry_date=t[0], direction=t[5][2], volume=t[6][2], open_price=t[7][2]),
            Leg(vt_symbol=f"opt-C-{int(t[4])}.EX", option_type="call", strike_price=t[4],
                expiry_date=t[0], direction=t[5][3], volume=t[6][3], open_price=t[7][3]),
        ]
    )


def _valid_custom_legs():
    """生成有效的 CUSTOM 腿：至少 1 腿"""
    return st.lists(
        _leg_strategy(),
        min_size=1,
        max_size=6,
    )


def _valid_legs_for_type(combo_type: CombinationType):
    """根据 CombinationType 返回对应的有效 Leg 列表策略。"""
    mapping = {
        CombinationType.STRADDLE: _valid_straddle_legs(),
        CombinationType.STRANGLE: _valid_strangle_legs(),
        CombinationType.VERTICAL_SPREAD: _valid_vertical_spread_legs(),
        CombinationType.CALENDAR_SPREAD: _valid_calendar_spread_legs(),
        CombinationType.IRON_CONDOR: _valid_iron_condor_legs(),
        CombinationType.CUSTOM: _valid_custom_legs(),
    }
    return mapping[combo_type]


# ---------------------------------------------------------------------------
# 策略：生成不满足约束的无效 Leg 列表
# ---------------------------------------------------------------------------

def _invalid_leg_count(combo_type: CombinationType):
    """生成腿数量不满足约束的 Leg 列表。"""
    if combo_type == CombinationType.CUSTOM:
        # CUSTOM 只在 0 腿时无效
        return st.just([])

    expected = 4 if combo_type == CombinationType.IRON_CONDOR else 2
    # 生成错误数量的腿（0, 1, 3, 5 等，但不等于 expected）
    wrong_count = st.integers(min_value=0, max_value=6).filter(lambda n: n != expected)
    return wrong_count.flatmap(
        lambda n: st.lists(_leg_strategy(), min_size=n, max_size=n)
    )


def _straddle_invalid_structure():
    """生成 2 腿但结构不满足 STRADDLE 约束的 Leg 列表。"""
    return st.one_of(
        # 同到期日、同行权价，但两个都是 call
        st.tuples(_strike_price, _expiry_date).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type="call", strike_price=t[0],
                    expiry_date=t[1], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type="call", strike_price=t[0],
                    expiry_date=t[1], direction="long", volume=1, open_price=1.0),
            ]
        ),
        # 一 Call 一 Put，同行权价，但不同到期日
        st.tuples(_strike_price, _expiry_date, _expiry_date).filter(lambda t: t[1] != t[2]).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type="call", strike_price=t[0],
                    expiry_date=t[1], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type="put", strike_price=t[0],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
            ]
        ),
        # 一 Call 一 Put，同到期日，但不同行权价
        st.tuples(_strike_price, _strike_price, _expiry_date).filter(lambda t: t[0] != t[1]).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type="call", strike_price=t[0],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type="put", strike_price=t[1],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
            ]
        ),
    )


# ---------------------------------------------------------------------------
# Feature: combination-strategy-management, Property 1: 组合结构验证
# ---------------------------------------------------------------------------

class TestProperty1CombinationStructureValidation:
    """
    Property 1: 组合结构验证

    *For any* CombinationType 和一组 Leg，当 Leg 数量和结构满足该类型的约束时，
    Combination 验证应通过；当不满足时，验证应失败并返回错误信息。

    **Validates: Requirements 1.2, 1.3, 1.4**
    """

    # ---- 有效组合：验证应通过 ----

    @given(data=st.data())
    @settings(max_examples=100)
    def test_valid_combination_passes_validation(self, data):
        """Feature: combination-strategy-management, Property 1: 组合结构验证
        对于任意 CombinationType，满足约束的 Leg 列表应通过验证。
        **Validates: Requirements 1.2, 1.3, 1.4**
        """
        combo_type = data.draw(_combination_type, label="combination_type")
        legs = data.draw(_valid_legs_for_type(combo_type), label="legs")

        combo = Combination(
            combination_id="test-id",
            combination_type=combo_type,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=__import__("datetime").datetime(2025, 1, 1),
        )
        # 不应抛出异常
        combo.validate()

    # ---- 无效腿数量：验证应失败 ----

    @given(data=st.data())
    @settings(max_examples=100)
    def test_invalid_leg_count_raises_value_error(self, data):
        """Feature: combination-strategy-management, Property 1: 组合结构验证
        对于任意 CombinationType，腿数量不满足约束时应抛出 ValueError。
        **Validates: Requirements 1.2, 1.4**
        """
        combo_type = data.draw(_combination_type, label="combination_type")
        legs = data.draw(_invalid_leg_count(combo_type), label="invalid_legs")

        combo = Combination(
            combination_id="test-id",
            combination_type=combo_type,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=__import__("datetime").datetime(2025, 1, 1),
        )
        with pytest.raises(ValueError):
            combo.validate()

    # ---- STRADDLE 结构无效：验证应失败 ----

    @given(legs=_straddle_invalid_structure())
    @settings(max_examples=100)
    def test_straddle_invalid_structure_raises_value_error(self, legs):
        """Feature: combination-strategy-management, Property 1: 组合结构验证
        STRADDLE 有 2 腿但结构不满足约束（到期日不同/行权价不同/类型相同）时应抛出 ValueError。
        **Validates: Requirements 1.2, 1.3, 1.4**
        """
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.STRADDLE,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=__import__("datetime").datetime(2025, 1, 1),
        )
        with pytest.raises(ValueError):
            combo.validate()

    # ---- STRANGLE 行权价相同：验证应失败 ----

    @given(strike=_strike_price, expiry=_expiry_date)
    @settings(max_examples=100)
    def test_strangle_same_strike_raises_value_error(self, strike, expiry):
        """Feature: combination-strategy-management, Property 1: 组合结构验证
        STRANGLE 两腿行权价相同时应抛出 ValueError。
        **Validates: Requirements 1.2, 1.4**
        """
        legs = [
            Leg(vt_symbol="a.EX", option_type="call", strike_price=strike,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
            Leg(vt_symbol="b.EX", option_type="put", strike_price=strike,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
        ]
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.STRANGLE,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=__import__("datetime").datetime(2025, 1, 1),
        )
        with pytest.raises(ValueError):
            combo.validate()

    # ---- VERTICAL_SPREAD 不同类型：验证应失败 ----

    @given(
        strike1=_strike_price, strike2=_strike_price, expiry=_expiry_date,
    )
    @settings(max_examples=100)
    def test_vertical_spread_different_option_type_raises(self, strike1, strike2, expiry):
        """Feature: combination-strategy-management, Property 1: 组合结构验证
        VERTICAL_SPREAD 两腿期权类型不同时应抛出 ValueError。
        **Validates: Requirements 1.3, 1.4**
        """
        assume(strike1 != strike2)
        legs = [
            Leg(vt_symbol="a.EX", option_type="call", strike_price=strike1,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
            Leg(vt_symbol="b.EX", option_type="put", strike_price=strike2,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
        ]
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.VERTICAL_SPREAD,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=__import__("datetime").datetime(2025, 1, 1),
        )
        with pytest.raises(ValueError):
            combo.validate()

    # ---- VERTICAL_SPREAD 相同行权价：验证应失败 ----

    @given(strike=_strike_price, expiry=_expiry_date, opt_type=_option_type)
    @settings(max_examples=100)
    def test_vertical_spread_same_strike_raises(self, strike, expiry, opt_type):
        """Feature: combination-strategy-management, Property 1: 组合结构验证
        VERTICAL_SPREAD 两腿行权价相同时应抛出 ValueError。
        **Validates: Requirements 1.2, 1.4**
        """
        legs = [
            Leg(vt_symbol="a.EX", option_type=opt_type, strike_price=strike,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
            Leg(vt_symbol="b.EX", option_type=opt_type, strike_price=strike,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
        ]
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.VERTICAL_SPREAD,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=__import__("datetime").datetime(2025, 1, 1),
        )
        with pytest.raises(ValueError):
            combo.validate()

    # ---- CALENDAR_SPREAD 同到期日：验证应失败 ----

    @given(strike=_strike_price, expiry=_expiry_date, opt_type=_option_type)
    @settings(max_examples=100)
    def test_calendar_spread_same_expiry_raises(self, strike, expiry, opt_type):
        """Feature: combination-strategy-management, Property 1: 组合结构验证
        CALENDAR_SPREAD 两腿到期日相同时应抛出 ValueError。
        **Validates: Requirements 1.2, 1.4**
        """
        legs = [
            Leg(vt_symbol="a.EX", option_type=opt_type, strike_price=strike,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
            Leg(vt_symbol="b.EX", option_type=opt_type, strike_price=strike,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
        ]
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.CALENDAR_SPREAD,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=__import__("datetime").datetime(2025, 1, 1),
        )
        with pytest.raises(ValueError):
            combo.validate()

    # ---- IRON_CONDOR Put 行权价相同：验证应失败 ----

    @given(
        expiry=_expiry_date, put_strike=_strike_price,
        call_strike1=_strike_price, call_strike2=_strike_price,
    )
    @settings(max_examples=100)
    def test_iron_condor_same_put_strike_raises(self, expiry, put_strike, call_strike1, call_strike2):
        """Feature: combination-strategy-management, Property 1: 组合结构验证
        IRON_CONDOR 两个 Put 行权价相同时应抛出 ValueError。
        **Validates: Requirements 1.2, 1.4**
        """
        assume(call_strike1 != call_strike2)
        legs = [
            Leg(vt_symbol="p1.EX", option_type="put", strike_price=put_strike,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
            Leg(vt_symbol="p2.EX", option_type="put", strike_price=put_strike,
                expiry_date=expiry, direction="short", volume=1, open_price=1.0),
            Leg(vt_symbol="c1.EX", option_type="call", strike_price=call_strike1,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
            Leg(vt_symbol="c2.EX", option_type="call", strike_price=call_strike2,
                expiry_date=expiry, direction="short", volume=1, open_price=1.0),
        ]
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.IRON_CONDOR,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=__import__("datetime").datetime(2025, 1, 1),
        )
        with pytest.raises(ValueError):
            combo.validate()

    # ---- IRON_CONDOR Call 行权价相同：验证应失败 ----

    @given(
        expiry=_expiry_date, call_strike=_strike_price,
        put_strike1=_strike_price, put_strike2=_strike_price,
    )
    @settings(max_examples=100)
    def test_iron_condor_same_call_strike_raises(self, expiry, call_strike, put_strike1, put_strike2):
        """Feature: combination-strategy-management, Property 1: 组合结构验证
        IRON_CONDOR 两个 Call 行权价相同时应抛出 ValueError。
        **Validates: Requirements 1.2, 1.4**
        """
        assume(put_strike1 != put_strike2)
        legs = [
            Leg(vt_symbol="p1.EX", option_type="put", strike_price=put_strike1,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
            Leg(vt_symbol="p2.EX", option_type="put", strike_price=put_strike2,
                expiry_date=expiry, direction="short", volume=1, open_price=1.0),
            Leg(vt_symbol="c1.EX", option_type="call", strike_price=call_strike,
                expiry_date=expiry, direction="long", volume=1, open_price=1.0),
            Leg(vt_symbol="c2.EX", option_type="call", strike_price=call_strike,
                expiry_date=expiry, direction="short", volume=1, open_price=1.0),
        ]
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.IRON_CONDOR,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=__import__("datetime").datetime(2025, 1, 1),
        )
        with pytest.raises(ValueError):
            combo.validate()

    # ---- IRON_CONDOR 不同到期日：验证应失败 ----

    @given(
        expiry1=_expiry_date, expiry2=_expiry_date,
        ps1=_strike_price, ps2=_strike_price,
        cs1=_strike_price, cs2=_strike_price,
    )
    @settings(max_examples=100)
    def test_iron_condor_different_expiry_raises(self, expiry1, expiry2, ps1, ps2, cs1, cs2):
        """Feature: combination-strategy-management, Property 1: 组合结构验证
        IRON_CONDOR 腿到期日不全相同时应抛出 ValueError。
        **Validates: Requirements 1.2, 1.4**
        """
        assume(expiry1 != expiry2)
        assume(ps1 != ps2)
        assume(cs1 != cs2)
        legs = [
            Leg(vt_symbol="p1.EX", option_type="put", strike_price=ps1,
                expiry_date=expiry1, direction="long", volume=1, open_price=1.0),
            Leg(vt_symbol="p2.EX", option_type="put", strike_price=ps2,
                expiry_date=expiry1, direction="short", volume=1, open_price=1.0),
            Leg(vt_symbol="c1.EX", option_type="call", strike_price=cs1,
                expiry_date=expiry2, direction="long", volume=1, open_price=1.0),
            Leg(vt_symbol="c2.EX", option_type="call", strike_price=cs2,
                expiry_date=expiry1, direction="short", volume=1, open_price=1.0),
        ]
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.IRON_CONDOR,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=__import__("datetime").datetime(2025, 1, 1),
        )
        with pytest.raises(ValueError):
            combo.validate()
