"""
Combination 实体属性测试

Feature: combination-strategy-management
"""
from datetime import datetime

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination.combination import (
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


# ---------------------------------------------------------------------------
# 策略：生成具有唯一 vt_symbol 的有效 Combination（用于状态测试）
# ---------------------------------------------------------------------------

def _unique_vt_symbols(n: int):
    """生成 n 个唯一的 vt_symbol 策略。"""
    return st.lists(
        st.from_regex(r"[a-z]{2}[0-9]{4}-[CP]-[0-9]{4}\.[A-Z]{3}", fullmatch=True),
        min_size=n,
        max_size=n,
        unique=True,
    )


def _combination_with_unique_legs():
    """
    生成具有唯一 vt_symbol 的有效 CUSTOM Combination。
    使用 CUSTOM 类型以避免结构约束，专注于状态转换逻辑。
    腿数量 2~6，每个 Leg 的 vt_symbol 唯一。
    """
    return st.integers(min_value=2, max_value=6).flatmap(
        lambda n: st.tuples(
            _unique_vt_symbols(n),
            st.lists(_option_type, min_size=n, max_size=n),
            st.lists(_strike_price, min_size=n, max_size=n),
            st.lists(_expiry_date, min_size=n, max_size=n),
            st.lists(_direction, min_size=n, max_size=n),
            st.lists(_volume, min_size=n, max_size=n),
            st.lists(_open_price, min_size=n, max_size=n),
            st.sampled_from([CombinationStatus.PENDING, CombinationStatus.ACTIVE]),
        ).map(
            lambda t: Combination(
                combination_id="test-status-id",
                combination_type=CombinationType.CUSTOM,
                underlying_vt_symbol="underlying.EX",
                legs=[
                    Leg(
                        vt_symbol=t[0][i],
                        option_type=t[1][i],
                        strike_price=t[2][i],
                        expiry_date=t[3][i],
                        direction=t[4][i],
                        volume=t[5][i],
                        open_price=t[6][i],
                    )
                    for i in range(len(t[0]))
                ],
                status=t[7],
                create_time=__import__("datetime").datetime(2025, 1, 1),
            )
        )
    )


# ---------------------------------------------------------------------------
# Feature: combination-strategy-management, Property 7: 组合状态反映腿的平仓状态
# ---------------------------------------------------------------------------

class TestProperty7CombinationStatusReflectsLegClosure:
    """
    Property 7: 组合状态反映腿的平仓状态

    *For any* Combination 和一组 closed_vt_symbols：
    - 当至少一个但非全部 Leg 的 vt_symbol 在 closed_vt_symbols 中时，
      update_status 应返回 PARTIALLY_CLOSED
    - 当所有 Leg 的 vt_symbol 在 closed_vt_symbols 中时，应返回 CLOSED
    - 当没有 Leg 的 vt_symbol 在 closed_vt_symbols 中时，状态不变（return None）

    **Validates: Requirements 6.3, 6.4**
    """

    @given(combo=_combination_with_unique_legs())
    @settings(max_examples=100)
    def test_no_legs_closed_returns_none(self, combo):
        """Feature: combination-strategy-management, Property 7: 组合状态反映腿的平仓状态
        当没有 Leg 的 vt_symbol 在 closed_vt_symbols 中时，状态不变（return None）。
        **Validates: Requirements 6.3, 6.4**
        """
        leg_symbols = {leg.vt_symbol for leg in combo.legs}
        # 构造一个与所有 leg vt_symbol 完全不相交的 closed 集合
        disjoint_symbols = {f"UNRELATED-{i}.ZZZ" for i in range(3)}
        assert disjoint_symbols.isdisjoint(leg_symbols)

        old_status = combo.status
        result = combo.update_status(disjoint_symbols)

        assert result is None
        assert combo.status == old_status

    @given(combo=_combination_with_unique_legs())
    @settings(max_examples=100)
    def test_no_legs_closed_empty_set_returns_none(self, combo):
        """Feature: combination-strategy-management, Property 7: 组合状态反映腿的平仓状态
        当 closed_vt_symbols 为空集时，状态不变（return None）。
        **Validates: Requirements 6.3, 6.4**
        """
        old_status = combo.status
        result = combo.update_status(set())

        assert result is None
        assert combo.status == old_status

    @given(combo=_combination_with_unique_legs())
    @settings(max_examples=100)
    def test_all_legs_closed_returns_closed(self, combo):
        """Feature: combination-strategy-management, Property 7: 组合状态反映腿的平仓状态
        当所有 Leg 的 vt_symbol 在 closed_vt_symbols 中时，应返回 CLOSED。
        **Validates: Requirements 6.3, 6.4**
        """
        all_symbols = {leg.vt_symbol for leg in combo.legs}
        # 可以包含额外的无关 symbol
        closed = all_symbols | {"extra-symbol.ZZZ"}

        result = combo.update_status(closed)

        assert result == CombinationStatus.CLOSED
        assert combo.status == CombinationStatus.CLOSED
        assert combo.close_time is not None

    @given(data=st.data())
    @settings(max_examples=100)
    def test_partial_legs_closed_returns_partially_closed(self, data):
        """Feature: combination-strategy-management, Property 7: 组合状态反映腿的平仓状态
        当至少一个但非全部 Leg 的 vt_symbol 在 closed_vt_symbols 中时，
        update_status 应返回 PARTIALLY_CLOSED。
        **Validates: Requirements 6.3, 6.4**
        """
        combo = data.draw(_combination_with_unique_legs(), label="combination")
        leg_symbols = [leg.vt_symbol for leg in combo.legs]
        assume(len(leg_symbols) >= 2)

        # 随机选择 1 到 len-1 个 leg 作为已平仓
        k = data.draw(
            st.integers(min_value=1, max_value=len(leg_symbols) - 1),
            label="num_closed",
        )
        closed_indices = data.draw(
            st.lists(
                st.sampled_from(range(len(leg_symbols))),
                min_size=k,
                max_size=k,
                unique=True,
            ),
            label="closed_indices",
        )
        closed_symbols = {leg_symbols[i] for i in closed_indices}

        result = combo.update_status(closed_symbols)

        assert result == CombinationStatus.PARTIALLY_CLOSED
        assert combo.status == CombinationStatus.PARTIALLY_CLOSED

    @given(combo=_combination_with_unique_legs())
    @settings(max_examples=100)
    def test_already_closed_status_returns_none(self, combo):
        """Feature: combination-strategy-management, Property 7: 组合状态反映腿的平仓状态
        当 Combination 已经是 CLOSED 状态，再次调用 update_status 全部平仓时返回 None（状态未变）。
        **Validates: Requirements 6.3, 6.4**
        """
        all_symbols = {leg.vt_symbol for leg in combo.legs}

        # 先设为 CLOSED
        combo.status = CombinationStatus.CLOSED
        result = combo.update_status(all_symbols)

        # 状态已经是 CLOSED，不应再次返回 CLOSED
        assert result is None
        assert combo.status == CombinationStatus.CLOSED

    @given(data=st.data())
    @settings(max_examples=100)
    def test_already_partially_closed_returns_none(self, data):
        """Feature: combination-strategy-management, Property 7: 组合状态反映腿的平仓状态
        当 Combination 已经是 PARTIALLY_CLOSED 状态，再次用相同的部分平仓集合调用时返回 None。
        **Validates: Requirements 6.3, 6.4**
        """
        combo = data.draw(_combination_with_unique_legs(), label="combination")
        leg_symbols = [leg.vt_symbol for leg in combo.legs]
        assume(len(leg_symbols) >= 2)

        # 选择部分 leg 平仓
        k = data.draw(
            st.integers(min_value=1, max_value=len(leg_symbols) - 1),
            label="num_closed",
        )
        closed_indices = data.draw(
            st.lists(
                st.sampled_from(range(len(leg_symbols))),
                min_size=k,
                max_size=k,
                unique=True,
            ),
            label="closed_indices",
        )
        closed_symbols = {leg_symbols[i] for i in closed_indices}

        # 先设为 PARTIALLY_CLOSED
        combo.status = CombinationStatus.PARTIALLY_CLOSED
        result = combo.update_status(closed_symbols)

        # 状态已经是 PARTIALLY_CLOSED，不应再次返回
        assert result is None
        assert combo.status == CombinationStatus.PARTIALLY_CLOSED


# ---------------------------------------------------------------------------
# 策略：生成各种类型的有效 Combination（用于序列化测试）
# ---------------------------------------------------------------------------

_combination_status = st.sampled_from(list(CombinationStatus))
_create_time = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
)
_combination_id = st.from_regex(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}", fullmatch=True)
_underlying = st.from_regex(r"[a-z]{1,4}[0-9]{4}\.[A-Z]{3}", fullmatch=True)


def _any_valid_combination():
    """
    生成任意类型的有效 Combination 实例（含可选 close_time）。
    覆盖所有 CombinationType，用于序列化往返测试。
    """
    return _combination_type.flatmap(
        lambda ct: st.tuples(
            st.just(ct),
            _valid_legs_for_type(ct),
            _combination_id,
            _underlying,
            _combination_status,
            _create_time,
            st.one_of(st.none(), _create_time),
        )
    ).map(
        lambda t: Combination(
            combination_id=t[2],
            combination_type=t[0],
            underlying_vt_symbol=t[3],
            legs=t[1],
            status=t[4],
            create_time=t[5],
            close_time=t[6],
        )
    )


# ---------------------------------------------------------------------------
# Feature: combination-strategy-management, Property 11: 序列化往返一致性
# ---------------------------------------------------------------------------

class TestProperty11SerializationRoundTrip:
    """
    Property 11: 序列化往返一致性

    *For any* 有效的 Combination 实例，`Combination.from_dict(combination.to_dict())`
    应产生与原始实例等价的 Combination（所有字段值相同）。

    **Validates: Requirements 9.3**
    """

    @given(combo=_any_valid_combination())
    @settings(max_examples=200)
    def test_roundtrip_preserves_all_fields(self, combo):
        """Feature: combination-strategy-management, Property 11: 序列化往返一致性
        对于任意有效 Combination，from_dict(to_dict(c)) 应产生等价实例。
        **Validates: Requirements 9.3**
        """
        serialized = combo.to_dict()
        restored = Combination.from_dict(serialized)

        # 比较所有顶层字段
        assert restored.combination_id == combo.combination_id
        assert restored.combination_type == combo.combination_type
        assert restored.underlying_vt_symbol == combo.underlying_vt_symbol
        assert restored.status == combo.status
        assert restored.create_time == combo.create_time
        assert restored.close_time == combo.close_time

        # 比较 legs 列表（数量和每个 Leg 的所有字段）
        assert len(restored.legs) == len(combo.legs)
        for orig_leg, rest_leg in zip(combo.legs, restored.legs):
            assert rest_leg.vt_symbol == orig_leg.vt_symbol
            assert rest_leg.option_type == orig_leg.option_type
            assert rest_leg.strike_price == orig_leg.strike_price
            assert rest_leg.expiry_date == orig_leg.expiry_date
            assert rest_leg.direction == orig_leg.direction
            assert rest_leg.volume == orig_leg.volume
            assert rest_leg.open_price == orig_leg.open_price

    @given(combo=_any_valid_combination())
    @settings(max_examples=100)
    def test_double_roundtrip_is_stable(self, combo):
        """Feature: combination-strategy-management, Property 11: 序列化往返一致性
        双重往返（序列化→反序列化→序列化）应产生相同的字典。
        **Validates: Requirements 9.3**
        """
        dict1 = combo.to_dict()
        restored = Combination.from_dict(dict1)
        dict2 = restored.to_dict()

        assert dict1 == dict2
