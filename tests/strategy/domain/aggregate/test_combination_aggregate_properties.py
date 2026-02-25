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



# ---------------------------------------------------------------------------
# 策略：生成用于状态同步测试的 Combination
# ---------------------------------------------------------------------------

def _active_combination_strategy():
    """
    生成状态为 ACTIVE 的 Combination，用于状态同步测试。
    """
    return st.integers(min_value=2, max_value=4).flatmap(
        lambda n: st.tuples(
            st.from_regex(r"combo-[a-f0-9]{8}", fullmatch=True),
            st.from_regex(r"[a-z]{2}[0-9]{4}\.[A-Z]{3}", fullmatch=True),
            _unique_vt_symbols(n),
        ).flatmap(
            lambda t: _build_active_combination(t[0], t[1], t[2])
        )
    )


def _build_active_combination(
    combination_id: str,
    underlying: str,
    vt_symbols: List[str],
):
    """
    构建状态为 ACTIVE 的 CUSTOM Combination。
    """
    n = len(vt_symbols)
    return st.tuples(
        st.lists(_option_type, min_size=n, max_size=n),
        st.lists(_strike_price, min_size=n, max_size=n),
        st.lists(_expiry_date, min_size=n, max_size=n),
        st.lists(_direction, min_size=n, max_size=n),
        st.lists(_volume, min_size=n, max_size=n),
        st.lists(_open_price, min_size=n, max_size=n),
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
            status=CombinationStatus.ACTIVE,  # 固定为 ACTIVE
            create_time=t[6],
        )
    )


def _multiple_active_combinations_strategy(min_combos: int = 1, max_combos: int = 5):
    """
    生成多个状态为 ACTIVE 的 Combination 集合。
    """
    return st.integers(min_value=min_combos, max_value=max_combos).flatmap(
        lambda num_combos: st.tuples(
            _unique_combination_ids(num_combos),
            _unique_underlyings(num_combos),
            st.integers(min_value=2, max_value=3).flatmap(
                lambda legs_per_combo: st.tuples(
                    st.just(legs_per_combo),
                    _unique_vt_symbols(num_combos * legs_per_combo),
                )
            ),
        ).flatmap(
            lambda t: _build_active_combinations(t[0], t[1], t[2][0], t[2][1])
        )
    )


def _build_active_combinations(
    combo_ids: List[str],
    underlyings: List[str],
    legs_per_combo: int,
    all_vt_symbols: List[str],
):
    """
    构建多个状态为 ACTIVE 的 Combination 列表。
    """
    num_combos = len(combo_ids)
    combos_strategies = []
    for i in range(num_combos):
        start_idx = i * legs_per_combo
        end_idx = start_idx + legs_per_combo
        vt_symbols = all_vt_symbols[start_idx:end_idx]
        combos_strategies.append(
            _build_active_combination(combo_ids[i], underlyings[i], vt_symbols)
        )
    return st.tuples(*combos_strategies).map(list)


# ---------------------------------------------------------------------------
# Feature: combination-strategy-management, Property 10: 跨聚合根状态同步
# ---------------------------------------------------------------------------

class TestProperty10CrossAggregateStatusSync:
    """
    Property 10: 跨聚合根状态同步

    *For any* 属于某 Combination 的 Position，当该 Position 的 vt_symbol 加入
    closed_vt_symbols 集合后，调用 CombinationAggregate.sync_combination_status
    应正确更新关联的 Combination 状态，并产生 CombinationStatusChangedEvent 领域事件。

    **Validates: Requirements 7.3, 7.4**
    """

    @given(combo=_active_combination_strategy())
    @settings(max_examples=100)
    def test_sync_all_legs_closed_produces_closed_status_and_event(self, combo: Combination):
        """Feature: combination-strategy-management, Property 10: 跨聚合根状态同步
        当所有 Leg 的 vt_symbol 都在 closed_vt_symbols 中时，状态应变为 CLOSED 并产生事件。
        **Validates: Requirements 7.3, 7.4**
        """
        aggregate = CombinationAggregate()
        aggregate.register_combination(combo)

        # 所有 Leg 的 vt_symbol 都平仓
        all_leg_symbols = {leg.vt_symbol for leg in combo.legs}
        closed_vt_symbols = all_leg_symbols.copy()

        # 选择任意一个 vt_symbol 触发同步
        trigger_symbol = list(all_leg_symbols)[0]

        # 同步状态
        aggregate.sync_combination_status(trigger_symbol, closed_vt_symbols)

        # 验证状态变为 CLOSED
        updated_combo = aggregate.get_combination(combo.combination_id)
        assert updated_combo is not None
        assert updated_combo.status == CombinationStatus.CLOSED

        # 验证产生了 CombinationStatusChangedEvent
        events = aggregate.pop_domain_events()
        assert len(events) == 1
        event = events[0]
        assert event.combination_id == combo.combination_id
        assert event.old_status == CombinationStatus.ACTIVE.value
        assert event.new_status == CombinationStatus.CLOSED.value
        assert event.combination_type == combo.combination_type.value

    @given(combo=_active_combination_strategy())
    @settings(max_examples=100)
    def test_sync_partial_legs_closed_produces_partially_closed_status_and_event(self, combo: Combination):
        """Feature: combination-strategy-management, Property 10: 跨聚合根状态同步
        当部分（非全部）Leg 的 vt_symbol 在 closed_vt_symbols 中时，状态应变为 PARTIALLY_CLOSED 并产生事件。
        **Validates: Requirements 7.3, 7.4**
        """
        # 确保至少有 2 个 Leg 才能测试部分平仓
        assume(len(combo.legs) >= 2)

        aggregate = CombinationAggregate()
        aggregate.register_combination(combo)

        # 只平仓第一个 Leg
        all_leg_symbols = [leg.vt_symbol for leg in combo.legs]
        closed_vt_symbols = {all_leg_symbols[0]}

        # 同步状态
        aggregate.sync_combination_status(all_leg_symbols[0], closed_vt_symbols)

        # 验证状态变为 PARTIALLY_CLOSED
        updated_combo = aggregate.get_combination(combo.combination_id)
        assert updated_combo is not None
        assert updated_combo.status == CombinationStatus.PARTIALLY_CLOSED

        # 验证产生了 CombinationStatusChangedEvent
        events = aggregate.pop_domain_events()
        assert len(events) == 1
        event = events[0]
        assert event.combination_id == combo.combination_id
        assert event.old_status == CombinationStatus.ACTIVE.value
        assert event.new_status == CombinationStatus.PARTIALLY_CLOSED.value

    @given(combo=_active_combination_strategy())
    @settings(max_examples=100)
    def test_sync_no_legs_closed_produces_no_status_change_and_no_event(self, combo: Combination):
        """Feature: combination-strategy-management, Property 10: 跨聚合根状态同步
        当没有 Leg 的 vt_symbol 在 closed_vt_symbols 中时，状态不变且不产生事件。
        **Validates: Requirements 7.3, 7.4**
        """
        aggregate = CombinationAggregate()
        aggregate.register_combination(combo)

        # 空的 closed_vt_symbols
        closed_vt_symbols: Set[str] = set()

        # 选择任意一个 vt_symbol 触发同步
        trigger_symbol = combo.legs[0].vt_symbol

        # 同步状态
        aggregate.sync_combination_status(trigger_symbol, closed_vt_symbols)

        # 验证状态不变
        updated_combo = aggregate.get_combination(combo.combination_id)
        assert updated_combo is not None
        assert updated_combo.status == CombinationStatus.ACTIVE

        # 验证没有产生事件
        events = aggregate.pop_domain_events()
        assert len(events) == 0

    @given(combo=_active_combination_strategy())
    @settings(max_examples=100)
    def test_sync_with_unrelated_symbol_produces_no_change(self, combo: Combination):
        """Feature: combination-strategy-management, Property 10: 跨聚合根状态同步
        当触发同步的 vt_symbol 不属于任何 Combination 时，不产生任何变化。
        **Validates: Requirements 7.3, 7.4**
        """
        aggregate = CombinationAggregate()
        aggregate.register_combination(combo)

        # 使用不存在的 vt_symbol 触发同步
        unrelated_symbol = "unrelated-symbol-9999.ZZZ"
        closed_vt_symbols = {unrelated_symbol}

        # 同步状态
        aggregate.sync_combination_status(unrelated_symbol, closed_vt_symbols)

        # 验证状态不变
        updated_combo = aggregate.get_combination(combo.combination_id)
        assert updated_combo is not None
        assert updated_combo.status == CombinationStatus.ACTIVE

        # 验证没有产生事件
        events = aggregate.pop_domain_events()
        assert len(events) == 0

    @given(combinations=_multiple_active_combinations_strategy(min_combos=2, max_combos=4))
    @settings(max_examples=100)
    def test_sync_affects_only_related_combinations(self, combinations: List[Combination]):
        """Feature: combination-strategy-management, Property 10: 跨聚合根状态同步
        同步操作只影响引用了指定 vt_symbol 的 Combination，其他 Combination 不受影响。
        **Validates: Requirements 7.3, 7.4**
        """
        aggregate = CombinationAggregate()
        for combo in combinations:
            aggregate.register_combination(combo)

        # 选择第一个 Combination 的第一个 Leg 进行平仓
        target_combo = combinations[0]
        target_symbol = target_combo.legs[0].vt_symbol
        closed_vt_symbols = {target_symbol}

        # 同步状态
        aggregate.sync_combination_status(target_symbol, closed_vt_symbols)

        # 验证目标 Combination 状态变化
        updated_target = aggregate.get_combination(target_combo.combination_id)
        assert updated_target is not None
        # 如果只有一个 Leg 被平仓，应该是 PARTIALLY_CLOSED（假设有多个 Leg）
        if len(target_combo.legs) > 1:
            assert updated_target.status == CombinationStatus.PARTIALLY_CLOSED
        else:
            assert updated_target.status == CombinationStatus.CLOSED

        # 验证其他 Combination 状态不变
        for combo in combinations[1:]:
            updated_combo = aggregate.get_combination(combo.combination_id)
            assert updated_combo is not None
            assert updated_combo.status == CombinationStatus.ACTIVE

    @given(combo=_active_combination_strategy())
    @settings(max_examples=100)
    def test_sync_sequential_closures_produces_correct_state_transitions(self, combo: Combination):
        """Feature: combination-strategy-management, Property 10: 跨聚合根状态同步
        顺序平仓多个 Leg 时，状态应正确从 ACTIVE → PARTIALLY_CLOSED → CLOSED 转换。
        **Validates: Requirements 7.3, 7.4**
        """
        # 确保至少有 2 个 Leg
        assume(len(combo.legs) >= 2)

        aggregate = CombinationAggregate()
        aggregate.register_combination(combo)

        all_leg_symbols = [leg.vt_symbol for leg in combo.legs]
        closed_vt_symbols: Set[str] = set()

        # 第一次平仓：平仓第一个 Leg
        closed_vt_symbols.add(all_leg_symbols[0])
        aggregate.sync_combination_status(all_leg_symbols[0], closed_vt_symbols)

        updated_combo = aggregate.get_combination(combo.combination_id)
        assert updated_combo is not None
        assert updated_combo.status == CombinationStatus.PARTIALLY_CLOSED

        events = aggregate.pop_domain_events()
        assert len(events) == 1
        assert events[0].new_status == CombinationStatus.PARTIALLY_CLOSED.value

        # 继续平仓剩余的 Leg
        for symbol in all_leg_symbols[1:]:
            closed_vt_symbols.add(symbol)
            aggregate.sync_combination_status(symbol, closed_vt_symbols)

        # 最终状态应为 CLOSED
        final_combo = aggregate.get_combination(combo.combination_id)
        assert final_combo is not None
        assert final_combo.status == CombinationStatus.CLOSED

        # 验证最后一次同步产生了 CLOSED 事件
        final_events = aggregate.pop_domain_events()
        # 可能有多个事件（每次同步一个），最后一个应该是 CLOSED
        if final_events:
            last_event = final_events[-1]
            assert last_event.new_status == CombinationStatus.CLOSED.value

    @given(combo=_active_combination_strategy())
    @settings(max_examples=100)
    def test_sync_idempotent_no_duplicate_events(self, combo: Combination):
        """Feature: combination-strategy-management, Property 10: 跨聚合根状态同步
        重复调用 sync_combination_status 不应产生重复的状态变更事件。
        **Validates: Requirements 7.3, 7.4**
        """
        aggregate = CombinationAggregate()
        aggregate.register_combination(combo)

        # 平仓所有 Leg
        all_leg_symbols = {leg.vt_symbol for leg in combo.legs}
        closed_vt_symbols = all_leg_symbols.copy()
        trigger_symbol = list(all_leg_symbols)[0]

        # 第一次同步
        aggregate.sync_combination_status(trigger_symbol, closed_vt_symbols)
        events1 = aggregate.pop_domain_events()
        assert len(events1) == 1

        # 第二次同步（相同参数）
        aggregate.sync_combination_status(trigger_symbol, closed_vt_symbols)
        events2 = aggregate.pop_domain_events()

        # 不应产生新事件（状态已经是 CLOSED，没有变化）
        assert len(events2) == 0

    @given(data=st.data())
    @settings(max_examples=100)
    def test_sync_shared_symbol_affects_multiple_combinations(self, data):
        """Feature: combination-strategy-management, Property 10: 跨聚合根状态同步
        当多个 Combination 共享同一个 vt_symbol 时，同步操作应影响所有相关的 Combination。
        **Validates: Requirements 7.3, 7.4**
        """
        shared_vt_symbol, combinations = data.draw(
            _combinations_with_shared_vt_symbol_strategy(),
            label="combinations_with_shared_vt_symbol",
        )

        # 将所有 Combination 设为 ACTIVE 状态
        for combo in combinations:
            combo.status = CombinationStatus.ACTIVE

        aggregate = CombinationAggregate()
        for combo in combinations:
            aggregate.register_combination(combo)

        # 平仓共享的 vt_symbol
        closed_vt_symbols = {shared_vt_symbol}

        # 同步状态
        aggregate.sync_combination_status(shared_vt_symbol, closed_vt_symbols)

        # 验证所有相关的 Combination 状态都发生了变化
        for combo in combinations:
            updated_combo = aggregate.get_combination(combo.combination_id)
            assert updated_combo is not None
            # 根据 Leg 的 vt_symbol 分布判断预期状态
            leg_symbols = {leg.vt_symbol for leg in combo.legs}
            closed_in_combo = leg_symbols & closed_vt_symbols
            if closed_in_combo == leg_symbols:
                # 所有 Leg 都被平仓（可能所有 Leg 共享同一个 vt_symbol）
                assert updated_combo.status == CombinationStatus.CLOSED
            else:
                # 部分 Leg 被平仓
                assert updated_combo.status == CombinationStatus.PARTIALLY_CLOSED

        # 验证产生了正确数量的事件
        events = aggregate.pop_domain_events()
        assert len(events) == len(combinations)

        # 验证每个事件对应一个 Combination
        event_combo_ids = {e.combination_id for e in events}
        expected_combo_ids = {c.combination_id for c in combinations}
        assert event_combo_ids == expected_combo_ids

    @given(combo=_active_combination_strategy())
    @settings(max_examples=100)
    def test_event_contains_correct_combination_type(self, combo: Combination):
        """Feature: combination-strategy-management, Property 10: 跨聚合根状态同步
        产生的 CombinationStatusChangedEvent 应包含正确的 combination_type。
        **Validates: Requirements 7.3, 7.4**
        """
        aggregate = CombinationAggregate()
        aggregate.register_combination(combo)

        # 平仓所有 Leg
        all_leg_symbols = {leg.vt_symbol for leg in combo.legs}
        closed_vt_symbols = all_leg_symbols.copy()
        trigger_symbol = list(all_leg_symbols)[0]

        # 同步状态
        aggregate.sync_combination_status(trigger_symbol, closed_vt_symbols)

        # 验证事件中的 combination_type
        events = aggregate.pop_domain_events()
        assert len(events) == 1
        assert events[0].combination_type == combo.combination_type.value
