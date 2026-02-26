"""
Combination.validate() 行为等价性属性测试

Feature: combination-service-optimization, Property 5: validate() 行为等价性

验证使用共享规则集的 Combination.validate() 对所有合法和非法输入产生正确的验证结果。

**Validates: Requirements 3.5**
"""
from datetime import datetime
from typing import List, Optional

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationStatus,
    CombinationType,
    Leg,
)
from src.strategy.domain.value_object.combination_rules import (
    LegStructure,
    VALIDATION_RULES,
    validate_straddle,
    validate_strangle,
    validate_vertical_spread,
    validate_calendar_spread,
    validate_iron_condor,
    validate_custom,
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
# 辅助函数：将 Leg 转换为 LegStructure
# ---------------------------------------------------------------------------

def _legs_to_structures(legs: List[Leg]) -> List[LegStructure]:
    """将 Leg 列表转换为 LegStructure 列表。"""
    return [
        LegStructure(
            option_type=leg.option_type,
            strike_price=leg.strike_price,
            expiry_date=leg.expiry_date,
        )
        for leg in legs
    ]


# ---------------------------------------------------------------------------
# 策略：生成满足各类型约束的有效 Leg 列表
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


def _strangle_invalid_structure():
    """生成 2 腿但结构不满足 STRANGLE 约束的 Leg 列表。"""
    return st.one_of(
        # 同到期日、不同行权价，但两个都是 call
        st.tuples(_strike_price, _strike_price, _expiry_date).filter(lambda t: t[0] != t[1]).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type="call", strike_price=t[0],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type="call", strike_price=t[1],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
            ]
        ),
        # 一 Call 一 Put，同到期日，但相同行权价（这是 STRADDLE 不是 STRANGLE）
        st.tuples(_strike_price, _expiry_date).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type="call", strike_price=t[0],
                    expiry_date=t[1], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type="put", strike_price=t[0],
                    expiry_date=t[1], direction="long", volume=1, open_price=1.0),
            ]
        ),
        # 一 Call 一 Put，不同行权价，但不同到期日
        st.tuples(_strike_price, _strike_price, _expiry_date, _expiry_date).filter(
            lambda t: t[0] != t[1] and t[2] != t[3]
        ).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type="call", strike_price=t[0],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type="put", strike_price=t[1],
                    expiry_date=t[3], direction="long", volume=1, open_price=1.0),
            ]
        ),
    )


def _vertical_spread_invalid_structure():
    """生成 2 腿但结构不满足 VERTICAL_SPREAD 约束的 Leg 列表。"""
    return st.one_of(
        # 同到期日、不同行权价，但不同类型（一 Call 一 Put）
        st.tuples(_strike_price, _strike_price, _expiry_date).filter(lambda t: t[0] != t[1]).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type="call", strike_price=t[0],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type="put", strike_price=t[1],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
            ]
        ),
        # 同到期日、同类型，但相同行权价
        st.tuples(_option_type, _strike_price, _expiry_date).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type=t[0], strike_price=t[1],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type=t[0], strike_price=t[1],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
            ]
        ),
        # 同类型、不同行权价，但不同到期日
        st.tuples(_option_type, _strike_price, _strike_price, _expiry_date, _expiry_date).filter(
            lambda t: t[1] != t[2] and t[3] != t[4]
        ).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type=t[0], strike_price=t[1],
                    expiry_date=t[3], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type=t[0], strike_price=t[2],
                    expiry_date=t[4], direction="long", volume=1, open_price=1.0),
            ]
        ),
    )


def _calendar_spread_invalid_structure():
    """生成 2 腿但结构不满足 CALENDAR_SPREAD 约束的 Leg 列表。"""
    return st.one_of(
        # 不同到期日、同行权价，但不同类型
        st.tuples(_strike_price, _expiry_date, _expiry_date).filter(lambda t: t[1] != t[2]).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type="call", strike_price=t[0],
                    expiry_date=t[1], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type="put", strike_price=t[0],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
            ]
        ),
        # 不同到期日、同类型，但不同行权价
        st.tuples(_option_type, _strike_price, _strike_price, _expiry_date, _expiry_date).filter(
            lambda t: t[1] != t[2] and t[3] != t[4]
        ).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type=t[0], strike_price=t[1],
                    expiry_date=t[3], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type=t[0], strike_price=t[2],
                    expiry_date=t[4], direction="long", volume=1, open_price=1.0),
            ]
        ),
        # 同类型、同行权价，但相同到期日
        st.tuples(_option_type, _strike_price, _expiry_date).map(
            lambda t: [
                Leg(vt_symbol="a.EX", option_type=t[0], strike_price=t[1],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="b.EX", option_type=t[0], strike_price=t[1],
                    expiry_date=t[2], direction="long", volume=1, open_price=1.0),
            ]
        ),
    )


def _iron_condor_invalid_structure():
    """生成 4 腿但结构不满足 IRON_CONDOR 约束的 Leg 列表。"""
    return st.one_of(
        # 4 腿同到期日，但 Put 行权价相同
        st.tuples(
            _expiry_date, _strike_price,  # put_strike (same)
            _strike_price, _strike_price,  # call strikes (different)
        ).filter(lambda t: t[2] != t[3]).map(
            lambda t: [
                Leg(vt_symbol="p1.EX", option_type="put", strike_price=t[1],
                    expiry_date=t[0], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="p2.EX", option_type="put", strike_price=t[1],
                    expiry_date=t[0], direction="short", volume=1, open_price=1.0),
                Leg(vt_symbol="c1.EX", option_type="call", strike_price=t[2],
                    expiry_date=t[0], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="c2.EX", option_type="call", strike_price=t[3],
                    expiry_date=t[0], direction="short", volume=1, open_price=1.0),
            ]
        ),
        # 4 腿同到期日，但 Call 行权价相同
        st.tuples(
            _expiry_date,
            _strike_price, _strike_price,  # put strikes (different)
            _strike_price,  # call_strike (same)
        ).filter(lambda t: t[1] != t[2]).map(
            lambda t: [
                Leg(vt_symbol="p1.EX", option_type="put", strike_price=t[1],
                    expiry_date=t[0], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="p2.EX", option_type="put", strike_price=t[2],
                    expiry_date=t[0], direction="short", volume=1, open_price=1.0),
                Leg(vt_symbol="c1.EX", option_type="call", strike_price=t[3],
                    expiry_date=t[0], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="c2.EX", option_type="call", strike_price=t[3],
                    expiry_date=t[0], direction="short", volume=1, open_price=1.0),
            ]
        ),
        # 4 腿，Put/Call 行权价都不同，但到期日不全相同
        st.tuples(
            _expiry_date, _expiry_date,
            _strike_price, _strike_price,  # put strikes
            _strike_price, _strike_price,  # call strikes
        ).filter(lambda t: t[0] != t[1] and t[2] != t[3] and t[4] != t[5]).map(
            lambda t: [
                Leg(vt_symbol="p1.EX", option_type="put", strike_price=t[2],
                    expiry_date=t[0], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="p2.EX", option_type="put", strike_price=t[3],
                    expiry_date=t[0], direction="short", volume=1, open_price=1.0),
                Leg(vt_symbol="c1.EX", option_type="call", strike_price=t[4],
                    expiry_date=t[1], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="c2.EX", option_type="call", strike_price=t[5],
                    expiry_date=t[0], direction="short", volume=1, open_price=1.0),
            ]
        ),
        # 4 腿同到期日，但 Put/Call 数量不对（3 Put + 1 Call）
        st.tuples(
            _expiry_date,
            _strike_price, _strike_price, _strike_price,  # 3 put strikes
            _strike_price,  # 1 call strike
        ).filter(lambda t: len({t[1], t[2], t[3]}) == 3).map(
            lambda t: [
                Leg(vt_symbol="p1.EX", option_type="put", strike_price=t[1],
                    expiry_date=t[0], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="p2.EX", option_type="put", strike_price=t[2],
                    expiry_date=t[0], direction="short", volume=1, open_price=1.0),
                Leg(vt_symbol="p3.EX", option_type="put", strike_price=t[3],
                    expiry_date=t[0], direction="long", volume=1, open_price=1.0),
                Leg(vt_symbol="c1.EX", option_type="call", strike_price=t[4],
                    expiry_date=t[0], direction="short", volume=1, open_price=1.0),
            ]
        ),
    )


# ---------------------------------------------------------------------------
# Feature: combination-service-optimization, Property 5: validate() 行为等价性
# ---------------------------------------------------------------------------

class TestProperty5ValidateBehaviorEquivalence:
    """
    Property 5: validate() 行为等价性

    *For any* CombinationType 和 Leg 列表，使用共享规则集的 Combination.validate()
    应产生与重构前完全相同的验证结果（通过或抛出相同错误信息）。

    测试策略：
    - 生成各类型的有效 Leg 列表，验证验证通过
    - 生成各类型的无效 Leg 列表，验证验证失败并返回正确的错误信息
    - 验证 Combination.validate() 与 VALIDATION_RULES 的行为一致

    **Validates: Requirements 3.5**
    """

    # ---- 有效组合：验证应通过 ----

    @given(data=st.data())
    @settings(max_examples=100)
    def test_valid_combination_passes_validation(self, data):
        """Feature: combination-service-optimization, Property 5: validate() 行为等价性
        对于任意 CombinationType，满足约束的 Leg 列表应通过验证。
        **Validates: Requirements 3.5**
        """
        combo_type = data.draw(_combination_type, label="combination_type")
        legs = data.draw(_valid_legs_for_type(combo_type), label="legs")

        combo = Combination(
            combination_id="test-id",
            combination_type=combo_type,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        # 验证 Combination.validate() 不抛出异常
        combo.validate()

        # 验证与 VALIDATION_RULES 行为一致
        leg_structures = _legs_to_structures(legs)
        error_message = VALIDATION_RULES[combo_type](leg_structures)
        assert error_message is None

    @given(data=st.data())
    @settings(max_examples=100)
    def test_validate_and_rules_produce_same_result_for_valid_input(self, data):
        """Feature: combination-service-optimization, Property 5: validate() 行为等价性
        对于有效输入，Combination.validate() 和 VALIDATION_RULES 应产生相同结果（都通过）。
        **Validates: Requirements 3.5**
        """
        combo_type = data.draw(_combination_type, label="combination_type")
        legs = data.draw(_valid_legs_for_type(combo_type), label="legs")

        # 使用 VALIDATION_RULES 直接验证
        leg_structures = _legs_to_structures(legs)
        rules_result = VALIDATION_RULES[combo_type](leg_structures)

        # 使用 Combination.validate() 验证
        combo = Combination(
            combination_id="test-id",
            combination_type=combo_type,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        # 两者应该都通过（rules_result 为 None，validate() 不抛异常）
        assert rules_result is None
        combo.validate()  # 不应抛出异常

    # ---- 无效腿数量：验证应失败 ----

    @given(data=st.data())
    @settings(max_examples=100)
    def test_invalid_leg_count_raises_value_error(self, data):
        """Feature: combination-service-optimization, Property 5: validate() 行为等价性
        对于任意 CombinationType，腿数量不满足约束时应抛出 ValueError。
        **Validates: Requirements 3.5**
        """
        combo_type = data.draw(_combination_type, label="combination_type")
        legs = data.draw(_invalid_leg_count(combo_type), label="invalid_legs")

        combo = Combination(
            combination_id="test-id",
            combination_type=combo_type,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        # 验证 VALIDATION_RULES 返回错误信息
        leg_structures = _legs_to_structures(legs)
        rules_error = VALIDATION_RULES[combo_type](leg_structures)
        assert rules_error is not None

        # 验证 Combination.validate() 抛出相同错误信息
        with pytest.raises(ValueError) as exc_info:
            combo.validate()
        assert str(exc_info.value) == rules_error


    # ---- STRADDLE 结构无效：验证应失败并返回正确错误信息 ----

    @given(legs=_straddle_invalid_structure())
    @settings(max_examples=100)
    def test_straddle_invalid_structure_error_message_matches(self, legs):
        """Feature: combination-service-optimization, Property 5: validate() 行为等价性
        STRADDLE 结构无效时，validate() 抛出的错误信息应与 VALIDATION_RULES 一致。
        **Validates: Requirements 3.5**
        """
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.STRADDLE,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        # 获取 VALIDATION_RULES 的错误信息
        leg_structures = _legs_to_structures(legs)
        rules_error = validate_straddle(leg_structures)
        assert rules_error is not None

        # 验证 Combination.validate() 抛出相同错误信息
        with pytest.raises(ValueError) as exc_info:
            combo.validate()
        assert str(exc_info.value) == rules_error

    # ---- STRANGLE 结构无效：验证应失败并返回正确错误信息 ----

    @given(legs=_strangle_invalid_structure())
    @settings(max_examples=100)
    def test_strangle_invalid_structure_error_message_matches(self, legs):
        """Feature: combination-service-optimization, Property 5: validate() 行为等价性
        STRANGLE 结构无效时，validate() 抛出的错误信息应与 VALIDATION_RULES 一致。
        **Validates: Requirements 3.5**
        """
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.STRANGLE,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        # 获取 VALIDATION_RULES 的错误信息
        leg_structures = _legs_to_structures(legs)
        rules_error = validate_strangle(leg_structures)
        assert rules_error is not None

        # 验证 Combination.validate() 抛出相同错误信息
        with pytest.raises(ValueError) as exc_info:
            combo.validate()
        assert str(exc_info.value) == rules_error

    # ---- VERTICAL_SPREAD 结构无效：验证应失败并返回正确错误信息 ----

    @given(legs=_vertical_spread_invalid_structure())
    @settings(max_examples=100)
    def test_vertical_spread_invalid_structure_error_message_matches(self, legs):
        """Feature: combination-service-optimization, Property 5: validate() 行为等价性
        VERTICAL_SPREAD 结构无效时，validate() 抛出的错误信息应与 VALIDATION_RULES 一致。
        **Validates: Requirements 3.5**
        """
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.VERTICAL_SPREAD,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        # 获取 VALIDATION_RULES 的错误信息
        leg_structures = _legs_to_structures(legs)
        rules_error = validate_vertical_spread(leg_structures)
        assert rules_error is not None

        # 验证 Combination.validate() 抛出相同错误信息
        with pytest.raises(ValueError) as exc_info:
            combo.validate()
        assert str(exc_info.value) == rules_error

    # ---- CALENDAR_SPREAD 结构无效：验证应失败并返回正确错误信息 ----

    @given(legs=_calendar_spread_invalid_structure())
    @settings(max_examples=100)
    def test_calendar_spread_invalid_structure_error_message_matches(self, legs):
        """Feature: combination-service-optimization, Property 5: validate() 行为等价性
        CALENDAR_SPREAD 结构无效时，validate() 抛出的错误信息应与 VALIDATION_RULES 一致。
        **Validates: Requirements 3.5**
        """
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.CALENDAR_SPREAD,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        # 获取 VALIDATION_RULES 的错误信息
        leg_structures = _legs_to_structures(legs)
        rules_error = validate_calendar_spread(leg_structures)
        assert rules_error is not None

        # 验证 Combination.validate() 抛出相同错误信息
        with pytest.raises(ValueError) as exc_info:
            combo.validate()
        assert str(exc_info.value) == rules_error


    # ---- IRON_CONDOR 结构无效：验证应失败并返回正确错误信息 ----

    @given(legs=_iron_condor_invalid_structure())
    @settings(max_examples=100)
    def test_iron_condor_invalid_structure_error_message_matches(self, legs):
        """Feature: combination-service-optimization, Property 5: validate() 行为等价性
        IRON_CONDOR 结构无效时，validate() 抛出的错误信息应与 VALIDATION_RULES 一致。
        **Validates: Requirements 3.5**
        """
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.IRON_CONDOR,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        # 获取 VALIDATION_RULES 的错误信息
        leg_structures = _legs_to_structures(legs)
        rules_error = validate_iron_condor(leg_structures)
        assert rules_error is not None

        # 验证 Combination.validate() 抛出相同错误信息
        with pytest.raises(ValueError) as exc_info:
            combo.validate()
        assert str(exc_info.value) == rules_error

    # ---- CUSTOM 空腿列表：验证应失败 ----

    @given(data=st.data())
    @settings(max_examples=100)
    def test_custom_empty_legs_raises_value_error(self, data):
        """Feature: combination-service-optimization, Property 5: validate() 行为等价性
        CUSTOM 组合空腿列表时应抛出 ValueError。
        **Validates: Requirements 3.5**
        """
        combo = Combination(
            combination_id="test-id",
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol="underlying.EX",
            legs=[],
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        # 获取 VALIDATION_RULES 的错误信息
        rules_error = validate_custom([])
        assert rules_error is not None

        # 验证 Combination.validate() 抛出相同错误信息
        with pytest.raises(ValueError) as exc_info:
            combo.validate()
        assert str(exc_info.value) == rules_error

    # ---- 验证 VALIDATION_RULES 与 Combination.validate() 行为完全一致 ----

    @given(data=st.data())
    @settings(max_examples=100)
    def test_validate_behavior_equivalence_for_any_input(self, data):
        """Feature: combination-service-optimization, Property 5: validate() 行为等价性
        对于任意 CombinationType 和 Leg 列表，Combination.validate() 的行为
        应与直接调用 VALIDATION_RULES 完全一致。
        **Validates: Requirements 3.5**
        """
        combo_type = data.draw(_combination_type, label="combination_type")
        # 生成随机 Leg 列表（可能有效也可能无效）
        legs = data.draw(
            st.lists(_leg_strategy(), min_size=0, max_size=6),
            label="legs",
        )

        combo = Combination(
            combination_id="test-id",
            combination_type=combo_type,
            underlying_vt_symbol="underlying.EX",
            legs=legs,
            status=CombinationStatus.ACTIVE,
            create_time=datetime(2025, 1, 1),
        )

        # 使用 VALIDATION_RULES 直接验证
        leg_structures = _legs_to_structures(legs)
        rules_result = VALIDATION_RULES[combo_type](leg_structures)

        if rules_result is None:
            # 规则验证通过，Combination.validate() 也应通过
            combo.validate()
        else:
            # 规则验证失败，Combination.validate() 应抛出相同错误
            with pytest.raises(ValueError) as exc_info:
                combo.validate()
            assert str(exc_info.value) == rules_result
