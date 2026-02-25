"""
CombinationAggregate 聚合根属性测试

Feature: combination-strategy-management
"""
from datetime import datetime
from typing import List, Set

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.aggregate.combination_aggregate import CombinationAggregate
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
_combination_status = st.sampled_from([CombinationStatus.PENDING, CombinationStatus.ACTIVE])
_create_time = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
)


# ---------------------------------------------------------------------------
# 策略：生成唯一标识符
# ---------------------------------------------------------------------------

def _unique_combination_ids(n: int):
    """生成 n 个唯一的 combination_id 策略。"""
    return st.lists(
        st.from_regex(r"combo-[a-f0-9]{8}", fullmatch=True),
        min_size=n,
        max_size=n,
        unique=True,
    )


def _unique_vt_symbols(n: int):
    """生成 n 个唯一的 vt_symbol 策略。"""
    return st.lists(
        st.from_regex(r"[a-z]{2}[0-9]{4}-[CP]-[0-9]{4}\.[A-Z]{3}", fullmatch=True),
        min_size=n,
        max_size=n,
        unique=True,
    )


def _unique_underlyings(n: int):
    """生成 n 个唯一的 underlying_vt_symbol 策略。"""
    return st.lists(
        st.from_regex(r"[a-z]{2}[0-9]{4}\.[A-Z]{3}", fullmatch=True),
        min_size=n,
        max_size=n,
        unique=True,
    )


# ---------------------------------------------------------------------------
# 策略：生成具有唯一 vt_symbol 的有效 CUSTOM Combination
# ---------------------------------------------------------------------------

def _combination_with_unique_legs(
    combination_id: str,
    underlying: str,
    vt_symbols: List[str],
):
    """
    根据给定的 combination_id、underlying 和 vt_symbols 列表生成 CUSTOM Combination。
    """
    n = len(vt_symbols)
    return st.tuples(
        st.lists(_option_type, min_size=n, max_size=n),
        st.lists(_strike_price, min_size=n, max_size=n),
        st.lists(_expiry_date, min_size=n, max_size=n),
        st.lists(_direction, min_size=n, max_size=n),
        st.lists(_volume, min_size=n, max_size=n),
        st.lists(_open_price, min_size=n, max_size=n),
        _combination_status,
        _create_time,
    ).map(
        lambda t: Combination(
            combination_id=combination_id,
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol=underlying,
            legs=[
                Leg(
                    vt_symbol=vt_symbols[i],
                    option_type=t[0][i],
                    strike_price=t[1][i],
                    expiry_date=t[2][i],
                    direction=t[3][i],
                    volume=t[4][i],
                    open_price=t[5][i],
                )
                for i in range(n)
            ],
            status=t[6],
            create_time=t[7],
        )
    )


def _single_combination_strategy():
    """
    生成单个具有唯一 vt_symbol 的有效 CUSTOM Combination。
    腿数量 2~4。
    """
    return st.integers(min_value=2, max_value=4).flatmap(
        lambda n: st.tuples(
            st.from_regex(r"combo-[a-f0-9]{8}", fullmatch=True),
            st.from_regex(r"[a-z]{2}[0-9]{4}\.[A-Z]{3}", fullmatch=True),
            _unique_vt_symbols(n),
        ).flatmap(
            lambda t: _combination_with_unique_legs(t[0], t[1], t[2])
        )
    )


# ---------------------------------------------------------------------------
# 策略：生成多个 Combination 的集合（用于聚合根测试）
# ---------------------------------------------------------------------------

def _multiple_combinations_strategy(min_combos: int = 1, max_combos: int = 5):
    """
    生成多个具有唯一 combination_id 和唯一 vt_symbol 的 Combination 集合。
    每个 Combination 有 2~3 个 Leg。
    """
    return st.integers(min_value=min_combos, max_value=max_combos).flatmap(
        lambda num_combos: st.tuples(
            _unique_combination_ids(num_combos),
            _unique_underlyings(num_combos),
            # 每个 combo 2~3 个 leg，总共需要 num_combos * 3 个唯一 vt_symbol（最大）
            st.integers(min_value=2, max_value=3).flatmap(
                lambda legs_per_combo: st.tuples(
                    st.just(legs_per_combo),
                    _unique_vt_symbols(num_combos * legs_per_combo),
                )
            ),
        ).flatmap(
            lambda t: _build_combinations(t[0], t[1], t[2][0], t[2][1])
        )
    )


def _build_combinations(
    combo_ids: List[str],
    underlyings: List[str],
    legs_per_combo: int,
    all_vt_symbols: List[str],
):
    """
    根据给定的 combo_ids、underlyings 和 vt_symbols 构建 Combination 列表。
    """
    num_combos = len(combo_ids)
    # 将 vt_symbols 分配给每个 combo
    combos_strategies = []
    for i in range(num_combos):
        start_idx = i * legs_per_combo
        end_idx = start_idx + legs_per_combo
        vt_symbols = all_vt_symbols[start_idx:end_idx]
        combos_strategies.append(
            _combination_with_unique_legs(combo_ids[i], underlyings[i], vt_symbols)
        )
    return st.tuples(*combos_strategies).map(list)


def _combinations_with_shared_underlying_strategy():
    """
    生成多个 Combination，其中部分共享相同的 underlying_vt_symbol。
    用于测试 get_combinations_by_underlying 查询。
    """
    return st.tuples(
        st.integers(min_value=2, max_value=4),  # 共享该 underlying 的 combo 数量
        st.integers(min_value=1, max_value=2),  # 使用不同 underlying 的 combo 数量
    ).flatmap(
        lambda t: _build_combinations_with_shared_underlying(t[0], t[1])
    )


def _build_combinations_with_shared_underlying(
    num_shared: int,
    num_different: int,
):
    """构建部分共享 underlying 的 Combination 列表。"""
    total = num_shared + num_different
    legs_per_combo = 2
    total_legs = total * legs_per_combo

    # 生成 num_different + 1 个唯一的 underlying，第一个作为共享的
    return st.tuples(
        _unique_combination_ids(total),
        _unique_underlyings(num_different + 1),  # 第一个是共享的，其余是不同的
        _unique_vt_symbols(total_legs),
    ).flatmap(
        lambda t: _build_mixed_underlying_combinations(
            t[0], t[1][0], t[1][1:], num_shared, num_different, legs_per_combo, t[2]
        )
    )


def _build_mixed_underlying_combinations(
    combo_ids: List[str],
    shared_underlying: str,
    different_underlyings: List[str],
    num_shared: int,
    num_different: int,
    legs_per_combo: int,
    all_vt_symbols: List[str],
):
    """构建混合 underlying 的 Combination 列表。"""
    combos_strategies = []

    # 共享 underlying 的 combos
    for i in range(num_shared):
        start_idx = i * legs_per_combo
        end_idx = start_idx + legs_per_combo
        vt_symbols = all_vt_symbols[start_idx:end_idx]
        combos_strategies.append(
            _combination_with_unique_legs(combo_ids[i], shared_underlying, vt_symbols)
        )

    # 不同 underlying 的 combos
    for i in range(num_different):
        combo_idx = num_shared + i
        start_idx = combo_idx * legs_per_combo
        end_idx = start_idx + legs_per_combo
        vt_symbols = all_vt_symbols[start_idx:end_idx]
        combos_strategies.append(
            _combination_with_unique_legs(
                combo_ids[combo_idx],
                different_underlyings[i],
                vt_symbols,
            )
        )

    return st.tuples(*combos_strategies).map(
        lambda combos: (shared_underlying, num_shared, list(combos))
    )


def _combinations_with_shared_vt_symbol_strategy():
    """
    生成多个 Combination，其中部分共享相同的 vt_symbol（同一个 Leg 被多个 Combination 引用）。
    用于测试 get_combinations_by_symbol 反向索引查询。
    """
    return st.tuples(
        st.from_regex(r"[a-z]{2}[0-9]{4}-[CP]-[0-9]{4}\.[A-Z]{3}", fullmatch=True),  # 共享的 vt_symbol
        st.integers(min_value=2, max_value=4),  # 引用该 vt_symbol 的 combo 数量
    ).flatmap(
        lambda t: _build_combinations_with_shared_vt_symbol(t[0], t[1])
    )


def _build_combinations_with_shared_vt_symbol(
    shared_vt_symbol: str,
    num_combos: int,
):
    """构建共享 vt_symbol 的 Combination 列表。"""
    # 每个 combo 有 2 个 leg，其中一个是共享的 vt_symbol
    # 需要 num_combos 个唯一的 combo_id 和 num_combos 个唯一的非共享 vt_symbol
    return st.tuples(
        _unique_combination_ids(num_combos),
        _unique_underlyings(num_combos),
        _unique_vt_symbols(num_combos),  # 非共享的 vt_symbols
    ).flatmap(
        lambda t: _build_shared_symbol_combinations(
            t[0], t[1], shared_vt_symbol, t[2]
        )
    )


def _build_shared_symbol_combinations(
    combo_ids: List[str],
    underlyings: List[str],
    shared_vt_symbol: str,
    other_vt_symbols: List[str],
):
    """构建每个 Combination 都包含共享 vt_symbol 的列表。"""
    combos_strategies = []

    for i in range(len(combo_ids)):
        # 每个 combo 有 2 个 leg：一个共享，一个唯一
        vt_symbols = [shared_vt_symbol, other_vt_symbols[i]]
        combos_strategies.append(
            _combination_with_unique_legs(combo_ids[i], underlyings[i], vt_symbols)
        )

    return st.tuples(*combos_strategies).map(
        lambda combos: (shared_vt_symbol, list(combos))
    )


# ---------------------------------------------------------------------------
# Feature: combination-strategy-management, Property 9: 聚合根注册与查询一致性
# ---------------------------------------------------------------------------

class TestProperty9AggregateRegistrationAndQueryConsistency:
    """
    Property 9: 聚合根注册与查询一致性

    *For any* 一组 Combination 注册到 CombinationAggregate 后：
    - 按 combination_id 查询应返回对应的 Combination
    - 按标的合约查询应返回所有匹配该标的的 Combination，且不遗漏、不多余
    - 按 vt_symbol 查询（反向索引）应返回所有引用该 vt_symbol 的 Combination

    **Validates: Requirements 7.2, 7.5**
    """

    @given(combinations=_multiple_combinations_strategy(min_combos=1, max_combos=5))
    @settings(max_examples=100)
    def test_get_combination_by_id_returns_correct_combination(self, combinations: List[Combination]):
        """Feature: combination-strategy-management, Property 9: 聚合根注册与查询一致性
        注册后按 combination_id 查询应返回对应的 Combination。
        **Validates: Requirements 7.2, 7.5**
        """
        aggregate = CombinationAggregate()

        # 注册所有 Combination
        for combo in combinations:
            aggregate.register_combination(combo)

        # 验证按 id 查询
        for combo in combinations:
            result = aggregate.get_combination(combo.combination_id)
            assert result is not None
            assert result.combination_id == combo.combination_id
            assert result.combination_type == combo.combination_type
            assert result.underlying_vt_symbol == combo.underlying_vt_symbol
            assert len(result.legs) == len(combo.legs)

    @given(combinations=_multiple_combinations_strategy(min_combos=1, max_combos=5))
    @settings(max_examples=100)
    def test_get_combination_by_nonexistent_id_returns_none(self, combinations: List[Combination]):
        """Feature: combination-strategy-management, Property 9: 聚合根注册与查询一致性
        查询不存在的 combination_id 应返回 None。
        **Validates: Requirements 7.2, 7.5**
        """
        aggregate = CombinationAggregate()

        for combo in combinations:
            aggregate.register_combination(combo)

        # 查询不存在的 id
        result = aggregate.get_combination("nonexistent-id-12345678")
        assert result is None

    @given(data=st.data())
    @settings(max_examples=100)
    def test_get_combinations_by_underlying_returns_all_matching(self, data):
        """Feature: combination-strategy-management, Property 9: 聚合根注册与查询一致性
        按标的合约查询应返回所有匹配该标的的 Combination，且不遗漏、不多余。
        **Validates: Requirements 7.2, 7.5**
        """
        shared_underlying, expected_count, combinations = data.draw(
            _combinations_with_shared_underlying_strategy(),
            label="combinations_with_shared_underlying",
        )

        aggregate = CombinationAggregate()
        for combo in combinations:
            aggregate.register_combination(combo)

        # 按 underlying 查询
        results = aggregate.get_combinations_by_underlying(shared_underlying)

        # 验证数量正确
        assert len(results) == expected_count

        # 验证所有返回的 Combination 都匹配该 underlying
        for result in results:
            assert result.underlying_vt_symbol == shared_underlying

        # 验证不遗漏：所有匹配的 Combination 都在结果中
        expected_ids = {
            combo.combination_id
            for combo in combinations
            if combo.underlying_vt_symbol == shared_underlying
        }
        result_ids = {result.combination_id for result in results}
        assert result_ids == expected_ids

    @given(data=st.data())
    @settings(max_examples=100)
    def test_get_combinations_by_symbol_returns_all_referencing(self, data):
        """Feature: combination-strategy-management, Property 9: 聚合根注册与查询一致性
        按 vt_symbol 查询（反向索引）应返回所有引用该 vt_symbol 的 Combination。
        **Validates: Requirements 7.2, 7.5**
        """
        shared_vt_symbol, combinations = data.draw(
            _combinations_with_shared_vt_symbol_strategy(),
            label="combinations_with_shared_vt_symbol",
        )

        aggregate = CombinationAggregate()
        for combo in combinations:
            aggregate.register_combination(combo)

        # 按 vt_symbol 查询
        results = aggregate.get_combinations_by_symbol(shared_vt_symbol)

        # 验证数量正确（所有 combo 都引用了 shared_vt_symbol）
        assert len(results) == len(combinations)

        # 验证所有返回的 Combination 都引用了该 vt_symbol
        for result in results:
            leg_symbols = {leg.vt_symbol for leg in result.legs}
            assert shared_vt_symbol in leg_symbols

        # 验证不遗漏
        expected_ids = {combo.combination_id for combo in combinations}
        result_ids = {result.combination_id for result in results}
        assert result_ids == expected_ids

    @given(combinations=_multiple_combinations_strategy(min_combos=1, max_combos=5))
    @settings(max_examples=100)
    def test_get_combinations_by_symbol_for_each_leg(self, combinations: List[Combination]):
        """Feature: combination-strategy-management, Property 9: 聚合根注册与查询一致性
        对于每个注册的 Combination 的每个 Leg，按该 Leg 的 vt_symbol 查询应包含该 Combination。
        **Validates: Requirements 7.2, 7.5**
        """
        aggregate = CombinationAggregate()
        for combo in combinations:
            aggregate.register_combination(combo)

        # 对每个 Combination 的每个 Leg 验证反向索引
        for combo in combinations:
            for leg in combo.legs:
                results = aggregate.get_combinations_by_symbol(leg.vt_symbol)
                result_ids = {r.combination_id for r in results}
                assert combo.combination_id in result_ids

    @given(combinations=_multiple_combinations_strategy(min_combos=1, max_combos=5))
    @settings(max_examples=100)
    def test_get_combinations_by_nonexistent_symbol_returns_empty(self, combinations: List[Combination]):
        """Feature: combination-strategy-management, Property 9: 聚合根注册与查询一致性
        查询不存在的 vt_symbol 应返回空列表。
        **Validates: Requirements 7.2, 7.5**
        """
        aggregate = CombinationAggregate()
        for combo in combinations:
            aggregate.register_combination(combo)

        # 查询不存在的 vt_symbol
        results = aggregate.get_combinations_by_symbol("nonexistent-symbol.ZZZ")
        assert results == []

    @given(combinations=_multiple_combinations_strategy(min_combos=1, max_combos=5))
    @settings(max_examples=100)
    def test_get_active_combinations_excludes_closed(self, combinations: List[Combination]):
        """Feature: combination-strategy-management, Property 9: 聚合根注册与查询一致性
        get_active_combinations 应排除 CLOSED 状态的 Combination。
        **Validates: Requirements 7.2, 7.5**
        """
        aggregate = CombinationAggregate()
        for combo in combinations:
            aggregate.register_combination(combo)

        # 将部分 Combination 设为 CLOSED
        closed_ids = set()
        for i, combo in enumerate(combinations):
            if i % 2 == 0:  # 偶数索引的设为 CLOSED
                combo.status = CombinationStatus.CLOSED
                closed_ids.add(combo.combination_id)

        # 获取活跃 Combination
        active_results = aggregate.get_active_combinations()

        # 验证不包含 CLOSED 的 Combination
        for result in active_results:
            assert result.status != CombinationStatus.CLOSED
            assert result.combination_id not in closed_ids

        # 验证包含所有非 CLOSED 的 Combination
        expected_active_ids = {
            combo.combination_id
            for combo in combinations
            if combo.status != CombinationStatus.CLOSED
        }
        result_ids = {r.combination_id for r in active_results}
        assert result_ids == expected_active_ids

    @given(combo=_single_combination_strategy())
    @settings(max_examples=100)
    def test_register_same_id_overwrites(self, combo: Combination):
        """Feature: combination-strategy-management, Property 9: 聚合根注册与查询一致性
        注册相同 combination_id 的 Combination 应覆盖原有记录。
        **Validates: Requirements 7.2, 7.5**
        """
        aggregate = CombinationAggregate()

        # 注册第一个
        aggregate.register_combination(combo)

        # 创建一个具有相同 id 但不同 underlying 的 Combination
        new_underlying = "new-underlying.EX"
        new_combo = Combination(
            combination_id=combo.combination_id,
            combination_type=CombinationType.CUSTOM,
            underlying_vt_symbol=new_underlying,
            legs=combo.legs,
            status=combo.status,
            create_time=combo.create_time,
        )

        # 注册第二个（覆盖）
        aggregate.register_combination(new_combo)

        # 验证查询返回新的 Combination
        result = aggregate.get_combination(combo.combination_id)
        assert result is not None
        assert result.underlying_vt_symbol == new_underlying

