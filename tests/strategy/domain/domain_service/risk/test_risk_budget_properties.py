"""
RiskBudgetAllocator 属性测试

使用 Hypothesis 进行基于属性的测试，验证风险预算分配服务的通用正确性属性。
"""
from hypothesis import given, strategies as st, settings, assume
from typing import Dict

from src.strategy.domain.domain_service.risk.risk_budget_allocator import RiskBudgetAllocator
from src.strategy.domain.entity.position import Position
from src.strategy.domain.value_object.pricing.greeks import GreeksResult
from src.strategy.domain.value_object.risk.risk import (
    RiskBudgetConfig,
    RiskThresholds,
    GreeksBudget,
    GreeksUsage,
)


# ============================================================================
# 测试数据生成策略
# ============================================================================

def position_strategy(
    min_volume: int = 1,
    max_volume: int = 50,
):
    """生成持仓实体的策略"""
    return st.builds(
        Position,
        vt_symbol=st.text(min_size=10, max_size=20, alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ."),
        underlying_vt_symbol=st.sampled_from(["510050.SSE", "510300.SSE", "510500.SSE"]),
        signal=st.sampled_from(["strategy_A", "strategy_B", "strategy_C"]),
        volume=st.integers(min_value=min_volume, max_value=max_volume),
        direction=st.sampled_from(["long", "short"]),
        open_price=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
        is_closed=st.just(False),
    )


def greeks_result_strategy():
    """生成 Greeks 结果的策略"""
    return st.builds(
        GreeksResult,
        delta=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        gamma=st.floats(min_value=0.0, max_value=0.1, allow_nan=False, allow_infinity=False),
        vega=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        theta=st.floats(min_value=-1.0, max_value=0.0, allow_nan=False, allow_infinity=False),
        success=st.just(True),
    )


def risk_thresholds_strategy():
    """生成风险阈值的策略"""
    return st.builds(
        RiskThresholds,
        portfolio_delta_limit=st.floats(min_value=1.0, max_value=50.0, allow_nan=False, allow_infinity=False),
        portfolio_gamma_limit=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
        portfolio_vega_limit=st.floats(min_value=100.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    )


def valid_allocation_ratios_strategy():
    """生成有效的分配比例策略（总和为 1.0）"""
    # 生成 2-4 个品种的分配比例
    num_underlyings = st.integers(min_value=2, max_value=4)
    
    @st.composite
    def ratios(draw):
        n = draw(num_underlyings)
        underlyings = ["510050.SSE", "510300.SSE", "510500.SSE", "159919.SZE"][:n]
        
        # 生成 n-1 个随机比例
        ratios_list = []
        remaining = 1.0
        for i in range(n - 1):
            # 确保每个比例至少 0.1，最多不超过剩余的 0.9
            max_ratio = min(0.9, remaining - 0.1 * (n - i - 1))
            ratio = draw(st.floats(min_value=0.1, max_value=max_ratio, allow_nan=False, allow_infinity=False))
            ratios_list.append(ratio)
            remaining -= ratio
        
        # 最后一个比例是剩余的
        ratios_list.append(remaining)
        
        return dict(zip(underlyings, ratios_list))
    
    return ratios()


# ============================================================================
# Feature: risk-service-enhancement, Property 4: 预算分配守恒
# **Validates: Requirements 2.7**
# ============================================================================

@settings(max_examples=100)
@given(
    total_limits=risk_thresholds_strategy(),
    allocation_ratios=valid_allocation_ratios_strategy(),
)
def test_property_budget_allocation_conservation(total_limits, allocation_ratios):
    """
    Feature: risk-service-enhancement, Property 4: 预算分配守恒
    
    对于任意总预算限额和分配比例，所有维度（品种或策略）的预算分配总和
    不应超过组合级 Greeks 限额
    
    **Validates: Requirements 2.7**
    """
    config = RiskBudgetConfig(
        allocation_dimension="underlying",
        allocation_ratios=allocation_ratios,
    )
    
    allocator = RiskBudgetAllocator(config)
    budget_map = allocator.allocate_budget_by_underlying(total_limits)
    
    # 计算所有维度的预算总和
    total_delta_budget = sum(budget.delta_budget for budget in budget_map.values())
    total_gamma_budget = sum(budget.gamma_budget for budget in budget_map.values())
    total_vega_budget = sum(budget.vega_budget for budget in budget_map.values())
    
    # 属性验证：预算总和不应超过组合级限额
    # 由于浮点数精度问题，允许小误差
    tolerance = 1e-6
    
    assert total_delta_budget <= total_limits.portfolio_delta_limit + tolerance, \
        f"Delta 预算总和 {total_delta_budget} 不应超过组合限额 {total_limits.portfolio_delta_limit}"
    
    assert total_gamma_budget <= total_limits.portfolio_gamma_limit + tolerance, \
        f"Gamma 预算总和 {total_gamma_budget} 不应超过组合限额 {total_limits.portfolio_gamma_limit}"
    
    assert total_vega_budget <= total_limits.portfolio_vega_limit + tolerance, \
        f"Vega 预算总和 {total_vega_budget} 不应超过组合限额 {total_limits.portfolio_vega_limit}"
    
    # 由于分配比例总和为 1.0，预算总和应该接近组合限额
    assert abs(total_delta_budget - total_limits.portfolio_delta_limit) < 0.01, \
        f"Delta 预算总和应接近组合限额"
    
    assert abs(total_gamma_budget - total_limits.portfolio_gamma_limit) < 0.01, \
        f"Gamma 预算总和应接近组合限额"
    
    assert abs(total_vega_budget - total_limits.portfolio_vega_limit) < 0.01, \
        f"Vega 预算总和应接近组合限额"


# ============================================================================
# Feature: risk-service-enhancement, Property 5: 使用量计算正确性
# **Validates: Requirements 2.4**
# ============================================================================

@settings(max_examples=100)
@given(
    positions=st.lists(position_strategy(), min_size=1, max_size=10),
    dimension=st.sampled_from(["underlying", "strategy"]),
)
def test_property_usage_calculation_correctness(positions, dimension):
    """
    Feature: risk-service-enhancement, Property 5: 使用量计算正确性
    
    对于任意持仓列表和 Greeks 映射，计算的 Greeks 使用量应该等于
    所有持仓的 Greeks 加权和（greek × volume × multiplier）
    
    **Validates: Requirements 2.4**
    """
    config = RiskBudgetConfig(allocation_dimension=dimension)
    allocator = RiskBudgetAllocator(config)
    
    # 为每个持仓生成 Greeks 数据
    greeks_map: Dict[str, GreeksResult] = {}
    for pos in positions:
        greeks_map[pos.vt_symbol] = GreeksResult(
            delta=0.5,
            gamma=0.01,
            vega=10.0,
            theta=-0.05,
            success=True,
        )
    
    # 计算使用量
    usage_map = allocator.calculate_usage(positions, greeks_map, dimension=dimension)
    
    # 手动计算预期的使用量
    multiplier = 10000.0
    expected_usage: Dict[str, GreeksUsage] = {}
    
    for pos in positions:
        if not pos.is_active or pos.volume <= 0:
            continue
        
        greeks = greeks_map.get(pos.vt_symbol)
        if not greeks or not greeks.success:
            continue
        
        # 确定维度键
        if dimension == "underlying":
            key = pos.underlying_vt_symbol
        elif dimension == "strategy":
            key = pos.signal
        else:
            continue
        
        if key not in expected_usage:
            expected_usage[key] = GreeksUsage()
        
        # 累加使用量
        expected_usage[key].delta_used += abs(greeks.delta * pos.volume * multiplier)
        expected_usage[key].gamma_used += abs(greeks.gamma * pos.volume * multiplier)
        expected_usage[key].vega_used += abs(greeks.vega * pos.volume * multiplier)
        expected_usage[key].position_count += 1
    
    # 属性验证：计算的使用量应与手动计算一致
    assert set(usage_map.keys()) == set(expected_usage.keys()), \
        f"使用量映射的键应一致。实际: {set(usage_map.keys())}, 期望: {set(expected_usage.keys())}"
    
    for key in expected_usage:
        actual = usage_map[key]
        expected = expected_usage[key]
        
        assert abs(actual.delta_used - expected.delta_used) < 1e-6, \
            f"{key} 的 Delta 使用量不一致。实际: {actual.delta_used}, 期望: {expected.delta_used}"
        
        assert abs(actual.gamma_used - expected.gamma_used) < 1e-6, \
            f"{key} 的 Gamma 使用量不一致。实际: {actual.gamma_used}, 期望: {expected.gamma_used}"
        
        assert abs(actual.vega_used - expected.vega_used) < 1e-6, \
            f"{key} 的 Vega 使用量不一致。实际: {actual.vega_used}, 期望: {expected.vega_used}"
        
        assert actual.position_count == expected.position_count, \
            f"{key} 的持仓数量不一致。实际: {actual.position_count}, 期望: {expected.position_count}"


# ============================================================================
# Feature: risk-service-enhancement, Property 6: 预算超限检测
# **Validates: Requirements 2.3**
# ============================================================================

@settings(max_examples=100)
@given(
    delta_used=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    gamma_used=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    vega_used=st.floats(min_value=0.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
    delta_budget=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    gamma_budget=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    vega_budget=st.floats(min_value=0.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
)
def test_property_budget_limit_detection(
    delta_used, gamma_used, vega_used,
    delta_budget, gamma_budget, vega_budget
):
    """
    Feature: risk-service-enhancement, Property 6: 预算超限检测
    
    对于任意使用量和预算，当任一 Greek 维度的使用量超过预算时，
    预算检查应该返回失败并标识所有超限的维度
    
    **Validates: Requirements 2.3**
    """
    config = RiskBudgetConfig()
    allocator = RiskBudgetAllocator(config)
    
    usage = GreeksUsage(
        delta_used=delta_used,
        gamma_used=gamma_used,
        vega_used=vega_used,
        position_count=1,
    )
    
    budget = GreeksBudget(
        delta_budget=delta_budget,
        gamma_budget=gamma_budget,
        vega_budget=vega_budget,
    )
    
    result = allocator.check_budget_limit(usage, budget)
    
    # 手动判断哪些维度超限
    expected_exceeded = []
    if delta_used > delta_budget:
        expected_exceeded.append("delta")
    if gamma_used > gamma_budget:
        expected_exceeded.append("gamma")
    if vega_used > vega_budget:
        expected_exceeded.append("vega")
    
    # 属性验证
    if len(expected_exceeded) > 0:
        # 应该检测到超限
        assert result.passed is False, "存在超限维度时检查应该失败"
        assert set(result.exceeded_dimensions) == set(expected_exceeded), \
            f"超限维度不一致。实际: {set(result.exceeded_dimensions)}, 期望: {set(expected_exceeded)}"
        assert "超限" in result.message, "失败消息应包含'超限'"
    else:
        # 不应该检测到超限
        assert result.passed is True, "不存在超限维度时检查应该通过"
        assert len(result.exceeded_dimensions) == 0, "通过时不应有超限维度"
        assert "通过" in result.message, "成功消息应包含'通过'"
    
    # 验证结果包含正确的使用量和预算
    assert result.usage == usage, "结果应包含正确的使用量"
    assert result.budget == budget, "结果应包含正确的预算"


# ============================================================================
# Feature: risk-service-enhancement, Property 7: 剩余预算一致性
# **Validates: Requirements 2.5**
# ============================================================================

@settings(max_examples=100)
@given(
    delta_used=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    gamma_used=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    vega_used=st.floats(min_value=0.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
    delta_budget=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    gamma_budget=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    vega_budget=st.floats(min_value=0.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
)
def test_property_remaining_budget_consistency(
    delta_used, gamma_used, vega_used,
    delta_budget, gamma_budget, vega_budget
):
    """
    Feature: risk-service-enhancement, Property 7: 剩余预算一致性
    
    对于任意预算和使用量，剩余预算应该等于分配预算减去当前使用量，
    且不应为负数
    
    **Validates: Requirements 2.5**
    """
    config = RiskBudgetConfig()
    allocator = RiskBudgetAllocator(config)
    
    usage = GreeksUsage(
        delta_used=delta_used,
        gamma_used=gamma_used,
        vega_used=vega_used,
        position_count=1,
    )
    
    budget = GreeksBudget(
        delta_budget=delta_budget,
        gamma_budget=gamma_budget,
        vega_budget=vega_budget,
    )
    
    # 调用内部方法计算剩余预算
    remaining = allocator._calculate_remaining_budget(usage, budget)
    
    # 属性验证：剩余预算 = 预算 - 使用量（不为负）
    expected_delta_remaining = max(0.0, delta_budget - delta_used)
    expected_gamma_remaining = max(0.0, gamma_budget - gamma_used)
    expected_vega_remaining = max(0.0, vega_budget - vega_used)
    
    tolerance = 1e-6
    
    assert abs(remaining.delta_budget - expected_delta_remaining) < tolerance, \
        f"Delta 剩余预算不一致。实际: {remaining.delta_budget}, 期望: {expected_delta_remaining}"
    
    assert abs(remaining.gamma_budget - expected_gamma_remaining) < tolerance, \
        f"Gamma 剩余预算不一致。实际: {remaining.gamma_budget}, 期望: {expected_gamma_remaining}"
    
    assert abs(remaining.vega_budget - expected_vega_remaining) < tolerance, \
        f"Vega 剩余预算不一致。实际: {remaining.vega_budget}, 期望: {expected_vega_remaining}"
    
    # 验证剩余预算不为负数
    assert remaining.delta_budget >= 0.0, "Delta 剩余预算不应为负数"
    assert remaining.gamma_budget >= 0.0, "Gamma 剩余预算不应为负数"
    assert remaining.vega_budget >= 0.0, "Vega 剩余预算不应为负数"


# ============================================================================
# Feature: risk-service-enhancement, Property 8: 多维度预算分配
# **Validates: Requirements 2.1, 2.2, 2.6**
# ============================================================================

@settings(max_examples=100)
@given(
    total_limits=risk_thresholds_strategy(),
    allocation_ratios=valid_allocation_ratios_strategy(),
)
def test_property_multi_dimension_budget_allocation(total_limits, allocation_ratios):
    """
    Feature: risk-service-enhancement, Property 8: 多维度预算分配
    
    对于任意分配维度（品种或策略）和分配比例，预算分配应该按照
    配置的比例正确分配到各个维度
    
    **Validates: Requirements 2.1, 2.2, 2.6**
    """
    config = RiskBudgetConfig(
        allocation_dimension="underlying",
        allocation_ratios=allocation_ratios,
    )
    
    allocator = RiskBudgetAllocator(config)
    budget_map = allocator.allocate_budget_by_underlying(total_limits)
    
    # 属性验证：每个维度的预算应该等于总预算 × 分配比例
    tolerance = 1e-6
    
    for underlying, ratio in allocation_ratios.items():
        assert underlying in budget_map, f"预算映射应包含 {underlying}"
        
        budget = budget_map[underlying]
        
        # 验证 Delta 预算
        expected_delta = total_limits.portfolio_delta_limit * ratio
        assert abs(budget.delta_budget - expected_delta) < tolerance, \
            f"{underlying} 的 Delta 预算不一致。实际: {budget.delta_budget}, 期望: {expected_delta}"
        
        # 验证 Gamma 预算
        expected_gamma = total_limits.portfolio_gamma_limit * ratio
        assert abs(budget.gamma_budget - expected_gamma) < tolerance, \
            f"{underlying} 的 Gamma 预算不一致。实际: {budget.gamma_budget}, 期望: {expected_gamma}"
        
        # 验证 Vega 预算
        expected_vega = total_limits.portfolio_vega_limit * ratio
        assert abs(budget.vega_budget - expected_vega) < tolerance, \
            f"{underlying} 的 Vega 预算不一致。实际: {budget.vega_budget}, 期望: {expected_vega}"
    
    # 验证预算映射的大小
    assert len(budget_map) == len(allocation_ratios), \
        f"预算映射的大小应与分配比例一致。实际: {len(budget_map)}, 期望: {len(allocation_ratios)}"
    
    # 验证所有配置的维度都有预算分配
    for underlying in allocation_ratios.keys():
        assert underlying in budget_map, f"所有配置的维度都应有预算分配: {underlying}"
