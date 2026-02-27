"""
RiskBudgetAllocator 单元测试

测试风险预算分配服务的预算分配、使用量计算和预算超限检测功能。
"""
import pytest

from src.strategy.domain.domain_service.risk.risk_budget_allocator import RiskBudgetAllocator
from src.strategy.domain.entity.position import Position
from src.strategy.domain.value_object.pricing.greeks import GreeksResult
from src.strategy.domain.value_object.risk.risk import (
    RiskBudgetConfig,
    RiskThresholds,
    GreeksBudget,
    GreeksUsage,
    BudgetCheckResult,
)


class TestRiskBudgetAllocatorByUnderlying:
    """测试按品种分配预算功能"""
    
    def test_allocate_budget_by_underlying_basic(self):
        """测试基本的按品种分配预算"""
        # 配置: 50ETF 40%, 300ETF 30%, 500ETF 30%
        config = RiskBudgetConfig(
            allocation_dimension="underlying",
            allocation_ratios={
                "510050.SSE": 0.4,
                "510300.SSE": 0.3,
                "510500.SSE": 0.3,
            }
        )
        allocator = RiskBudgetAllocator(config)
        
        # 组合级限额
        total_limits = RiskThresholds(
            portfolio_delta_limit=10.0,
            portfolio_gamma_limit=2.0,
            portfolio_vega_limit=1000.0,
        )
        
        budget_map = allocator.allocate_budget_by_underlying(total_limits)
        
        # 验证分配结果
        assert len(budget_map) == 3
        
        # 50ETF: 40%
        assert "510050.SSE" in budget_map
        assert budget_map["510050.SSE"].delta_budget == 4.0
        assert budget_map["510050.SSE"].gamma_budget == 0.8
        assert budget_map["510050.SSE"].vega_budget == 400.0
        
        # 300ETF: 30%
        assert "510300.SSE" in budget_map
        assert budget_map["510300.SSE"].delta_budget == 3.0
        assert budget_map["510300.SSE"].gamma_budget == 0.6
        assert budget_map["510300.SSE"].vega_budget == 300.0
        
        # 500ETF: 30%
        assert "510500.SSE" in budget_map
        assert budget_map["510500.SSE"].delta_budget == 3.0
        assert budget_map["510500.SSE"].gamma_budget == 0.6
        assert budget_map["510500.SSE"].vega_budget == 300.0
    
    def test_allocate_budget_single_underlying(self):
        """测试单一品种分配预算"""
        config = RiskBudgetConfig(
            allocation_dimension="underlying",
            allocation_ratios={"510050.SSE": 1.0}
        )
        allocator = RiskBudgetAllocator(config)
        
        total_limits = RiskThresholds(
            portfolio_delta_limit=5.0,
            portfolio_gamma_limit=1.0,
            portfolio_vega_limit=500.0,
        )
        
        budget_map = allocator.allocate_budget_by_underlying(total_limits)
        
        assert len(budget_map) == 1
        assert budget_map["510050.SSE"].delta_budget == 5.0
        assert budget_map["510050.SSE"].gamma_budget == 1.0
        assert budget_map["510050.SSE"].vega_budget == 500.0
    
    def test_allocate_budget_empty_ratios(self):
        """测试空分配比例"""
        config = RiskBudgetConfig(
            allocation_dimension="underlying",
            allocation_ratios={}
        )
        allocator = RiskBudgetAllocator(config)
        
        total_limits = RiskThresholds(
            portfolio_delta_limit=5.0,
            portfolio_gamma_limit=1.0,
            portfolio_vega_limit=500.0,
        )
        
        budget_map = allocator.allocate_budget_by_underlying(total_limits)
        
        assert len(budget_map) == 0


class TestRiskBudgetAllocatorUsageCalculation:
    """测试使用量计算功能"""
    
    def test_calculate_usage_by_underlying_basic(self):
        """测试基本的按品种计算使用量"""
        config = RiskBudgetConfig(allocation_dimension="underlying")
        allocator = RiskBudgetAllocator(config)
        
        # 创建持仓
        positions = [
            Position(
                vt_symbol="10005000C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=2,
                direction="short",
                open_price=0.5,
            ),
            Position(
                vt_symbol="10005100C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=3,
                direction="short",
                open_price=0.6,
            ),
        ]
        
        # Greeks 数据
        greeks_map = {
            "10005000C2412.SSE": GreeksResult(
                delta=0.5,
                gamma=0.01,
                vega=10.0,
                success=True,
            ),
            "10005100C2412.SSE": GreeksResult(
                delta=0.3,
                gamma=0.02,
                vega=15.0,
                success=True,
            ),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        # 验证使用量
        assert len(usage_map) == 1
        assert "510050.SSE" in usage_map
        
        usage = usage_map["510050.SSE"]
        # Delta: |0.5 * 2 * 10000| + |0.3 * 3 * 10000| = 10000 + 9000 = 19000
        assert usage.delta_used == 19000.0
        # Gamma: |0.01 * 2 * 10000| + |0.02 * 3 * 10000| = 200 + 600 = 800
        assert usage.gamma_used == 800.0
        # Vega: |10.0 * 2 * 10000| + |15.0 * 3 * 10000| = 200000 + 450000 = 650000
        assert usage.vega_used == 650000.0
        assert usage.position_count == 2
    
    def test_calculate_usage_by_strategy(self):
        """测试按策略计算使用量"""
        config = RiskBudgetConfig(allocation_dimension="strategy")
        allocator = RiskBudgetAllocator(config)
        
        # 创建不同策略的持仓
        positions = [
            Position(
                vt_symbol="10005000C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="strategy_A",
                volume=2,
                direction="short",
                open_price=0.5,
            ),
            Position(
                vt_symbol="10005100C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="strategy_B",
                volume=3,
                direction="short",
                open_price=0.6,
            ),
        ]
        
        greeks_map = {
            "10005000C2412.SSE": GreeksResult(
                delta=0.5,
                gamma=0.01,
                vega=10.0,
                success=True,
            ),
            "10005100C2412.SSE": GreeksResult(
                delta=0.3,
                gamma=0.02,
                vega=15.0,
                success=True,
            ),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="strategy")
        
        # 验证按策略分组
        assert len(usage_map) == 2
        assert "strategy_A" in usage_map
        assert "strategy_B" in usage_map
        
        # Strategy A
        usage_a = usage_map["strategy_A"]
        assert usage_a.delta_used == 10000.0
        assert usage_a.gamma_used == 200.0
        assert usage_a.vega_used == 200000.0
        assert usage_a.position_count == 1
        
        # Strategy B
        usage_b = usage_map["strategy_B"]
        assert usage_b.delta_used == 9000.0
        assert usage_b.gamma_used == 600.0
        assert usage_b.vega_used == 450000.0
        assert usage_b.position_count == 1
    
    def test_calculate_usage_multiple_underlyings(self):
        """测试多个品种的使用量计算"""
        config = RiskBudgetConfig(allocation_dimension="underlying")
        allocator = RiskBudgetAllocator(config)
        
        positions = [
            Position(
                vt_symbol="10005000C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=2,
                direction="short",
                open_price=0.5,
            ),
            Position(
                vt_symbol="10003000C2412.SSE",
                underlying_vt_symbol="510300.SSE",
                signal="open_signal",
                volume=1,
                direction="short",
                open_price=0.4,
            ),
        ]
        
        greeks_map = {
            "10005000C2412.SSE": GreeksResult(
                delta=0.5,
                gamma=0.01,
                vega=10.0,
                success=True,
            ),
            "10003000C2412.SSE": GreeksResult(
                delta=0.4,
                gamma=0.015,
                vega=12.0,
                success=True,
            ),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        assert len(usage_map) == 2
        
        # 50ETF
        assert "510050.SSE" in usage_map
        assert usage_map["510050.SSE"].delta_used == 10000.0
        assert usage_map["510050.SSE"].position_count == 1
        
        # 300ETF
        assert "510300.SSE" in usage_map
        assert usage_map["510300.SSE"].delta_used == 4000.0
        assert usage_map["510300.SSE"].gamma_used == 150.0
        assert usage_map["510300.SSE"].vega_used == 120000.0
        assert usage_map["510300.SSE"].position_count == 1
    
    def test_calculate_usage_skip_inactive_positions(self):
        """测试跳过非活跃持仓"""
        config = RiskBudgetConfig(allocation_dimension="underlying")
        allocator = RiskBudgetAllocator(config)
        
        positions = [
            Position(
                vt_symbol="10005000C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=2,
                direction="short",
                open_price=0.5,
            ),
            Position(
                vt_symbol="10005100C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=0,  # 非活跃
                direction="short",
                open_price=0.6,
                is_closed=True,
            ),
        ]
        
        greeks_map = {
            "10005000C2412.SSE": GreeksResult(
                delta=0.5,
                gamma=0.01,
                vega=10.0,
                success=True,
            ),
            "10005100C2412.SSE": GreeksResult(
                delta=0.3,
                gamma=0.02,
                vega=15.0,
                success=True,
            ),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        # 只计算活跃持仓
        assert usage_map["510050.SSE"].delta_used == 10000.0
        assert usage_map["510050.SSE"].position_count == 1
    
    def test_calculate_usage_skip_missing_greeks(self):
        """测试跳过缺失 Greeks 数据的持仓"""
        config = RiskBudgetConfig(allocation_dimension="underlying")
        allocator = RiskBudgetAllocator(config)
        
        positions = [
            Position(
                vt_symbol="10005000C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=2,
                direction="short",
                open_price=0.5,
            ),
            Position(
                vt_symbol="10005100C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=3,
                direction="short",
                open_price=0.6,
            ),
        ]
        
        # 只提供一个合约的 Greeks
        greeks_map = {
            "10005000C2412.SSE": GreeksResult(
                delta=0.5,
                gamma=0.01,
                vega=10.0,
                success=True,
            ),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        # 只计算有 Greeks 数据的持仓
        assert usage_map["510050.SSE"].delta_used == 10000.0
        assert usage_map["510050.SSE"].position_count == 1
    
    def test_calculate_usage_skip_failed_greeks(self):
        """测试跳过 Greeks 计算失败的持仓"""
        config = RiskBudgetConfig(allocation_dimension="underlying")
        allocator = RiskBudgetAllocator(config)
        
        positions = [
            Position(
                vt_symbol="10005000C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=2,
                direction="short",
                open_price=0.5,
            ),
        ]
        
        # Greeks 计算失败
        greeks_map = {
            "10005000C2412.SSE": GreeksResult(
                delta=0.0,
                gamma=0.0,
                vega=0.0,
                success=False,
                error_message="计算失败",
            ),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        # 不应包含失败的持仓
        assert len(usage_map) == 0
    
    def test_calculate_usage_empty_positions(self):
        """测试空持仓列表"""
        config = RiskBudgetConfig(allocation_dimension="underlying")
        allocator = RiskBudgetAllocator(config)
        
        positions = []
        greeks_map = {}
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        assert len(usage_map) == 0


class TestRiskBudgetAllocatorBudgetCheck:
    """测试预算超限检测功能"""
    
    def test_check_budget_limit_passed(self):
        """测试预算检查通过"""
        config = RiskBudgetConfig()
        allocator = RiskBudgetAllocator(config)
        
        usage = GreeksUsage(
            delta_used=3000.0,
            gamma_used=400.0,
            vega_used=250000.0,
            position_count=2,
        )
        
        budget = GreeksBudget(
            delta_budget=5000.0,
            gamma_budget=500.0,
            vega_budget=300000.0,
        )
        
        result = allocator.check_budget_limit(usage, budget)
        
        assert result.passed is True
        assert len(result.exceeded_dimensions) == 0
        assert result.usage == usage
        assert result.budget == budget
        assert "通过" in result.message
    
    def test_check_budget_limit_delta_exceeded(self):
        """测试 Delta 预算超限"""
        config = RiskBudgetConfig()
        allocator = RiskBudgetAllocator(config)
        
        usage = GreeksUsage(
            delta_used=6000.0,  # 超限
            gamma_used=400.0,
            vega_used=250000.0,
            position_count=2,
        )
        
        budget = GreeksBudget(
            delta_budget=5000.0,
            gamma_budget=500.0,
            vega_budget=300000.0,
        )
        
        result = allocator.check_budget_limit(usage, budget)
        
        assert result.passed is False
        assert "delta" in result.exceeded_dimensions
        assert len(result.exceeded_dimensions) == 1
        assert "超限" in result.message
        assert "delta" in result.message
    
    def test_check_budget_limit_gamma_exceeded(self):
        """测试 Gamma 预算超限"""
        config = RiskBudgetConfig()
        allocator = RiskBudgetAllocator(config)
        
        usage = GreeksUsage(
            delta_used=3000.0,
            gamma_used=600.0,  # 超限
            vega_used=250000.0,
            position_count=2,
        )
        
        budget = GreeksBudget(
            delta_budget=5000.0,
            gamma_budget=500.0,
            vega_budget=300000.0,
        )
        
        result = allocator.check_budget_limit(usage, budget)
        
        assert result.passed is False
        assert "gamma" in result.exceeded_dimensions
        assert len(result.exceeded_dimensions) == 1
    
    def test_check_budget_limit_vega_exceeded(self):
        """测试 Vega 预算超限"""
        config = RiskBudgetConfig()
        allocator = RiskBudgetAllocator(config)
        
        usage = GreeksUsage(
            delta_used=3000.0,
            gamma_used=400.0,
            vega_used=350000.0,  # 超限
            position_count=2,
        )
        
        budget = GreeksBudget(
            delta_budget=5000.0,
            gamma_budget=500.0,
            vega_budget=300000.0,
        )
        
        result = allocator.check_budget_limit(usage, budget)
        
        assert result.passed is False
        assert "vega" in result.exceeded_dimensions
        assert len(result.exceeded_dimensions) == 1
    
    def test_check_budget_limit_multiple_exceeded(self):
        """测试多个维度预算超限"""
        config = RiskBudgetConfig()
        allocator = RiskBudgetAllocator(config)
        
        usage = GreeksUsage(
            delta_used=6000.0,  # 超限
            gamma_used=600.0,   # 超限
            vega_used=350000.0, # 超限
            position_count=2,
        )
        
        budget = GreeksBudget(
            delta_budget=5000.0,
            gamma_budget=500.0,
            vega_budget=300000.0,
        )
        
        result = allocator.check_budget_limit(usage, budget)
        
        assert result.passed is False
        assert len(result.exceeded_dimensions) == 3
        assert "delta" in result.exceeded_dimensions
        assert "gamma" in result.exceeded_dimensions
        assert "vega" in result.exceeded_dimensions
    
    def test_check_budget_limit_exact_boundary(self):
        """测试恰好达到预算边界"""
        config = RiskBudgetConfig()
        allocator = RiskBudgetAllocator(config)
        
        usage = GreeksUsage(
            delta_used=5000.0,  # 恰好等于预算
            gamma_used=500.0,   # 恰好等于预算
            vega_used=300000.0, # 恰好等于预算
            position_count=2,
        )
        
        budget = GreeksBudget(
            delta_budget=5000.0,
            gamma_budget=500.0,
            vega_budget=300000.0,
        )
        
        result = allocator.check_budget_limit(usage, budget)
        
        # 恰好等于预算应该通过
        assert result.passed is True
        assert len(result.exceeded_dimensions) == 0
    
    def test_check_budget_limit_zero_usage(self):
        """测试零使用量"""
        config = RiskBudgetConfig()
        allocator = RiskBudgetAllocator(config)
        
        usage = GreeksUsage(
            delta_used=0.0,
            gamma_used=0.0,
            vega_used=0.0,
            position_count=0,
        )
        
        budget = GreeksBudget(
            delta_budget=5000.0,
            gamma_budget=500.0,
            vega_budget=300000.0,
        )
        
        result = allocator.check_budget_limit(usage, budget)
        
        assert result.passed is True
        assert len(result.exceeded_dimensions) == 0


class TestRiskBudgetAllocatorValidation:
    """测试配置验证功能"""
    
    def test_validate_allocation_ratios_valid(self):
        """测试有效的分配比例"""
        # 总和为 1.0
        config = RiskBudgetConfig(
            allocation_ratios={
                "510050.SSE": 0.4,
                "510300.SSE": 0.3,
                "510500.SSE": 0.3,
            }
        )
        
        # 不应抛出异常
        allocator = RiskBudgetAllocator(config)
        assert allocator is not None
    
    def test_validate_allocation_ratios_sum_not_one(self):
        """测试分配比例总和不为 1"""
        # 总和为 0.8
        config = RiskBudgetConfig(
            allocation_ratios={
                "510050.SSE": 0.4,
                "510300.SSE": 0.2,
                "510500.SSE": 0.2,
            }
        )
        
        with pytest.raises(ValueError) as exc_info:
            RiskBudgetAllocator(config)
        
        assert "总和应为 1.0" in str(exc_info.value)
    
    def test_validate_allocation_ratios_negative(self):
        """测试负数分配比例"""
        config = RiskBudgetConfig(
            allocation_ratios={
                "510050.SSE": 0.6,
                "510300.SSE": -0.2,  # 负数
                "510500.SSE": 0.6,
            }
        )
        
        with pytest.raises(ValueError) as exc_info:
            RiskBudgetAllocator(config)
        
        assert "不能为负数" in str(exc_info.value)
    
    def test_validate_allocation_ratios_empty(self):
        """测试空分配比例"""
        config = RiskBudgetConfig(allocation_ratios={})
        
        # 空比例应该不抛出异常
        allocator = RiskBudgetAllocator(config)
        assert allocator is not None
    
    def test_validate_allocation_ratios_small_error_tolerance(self):
        """测试小误差容忍"""
        # 总和为 1.005（在容忍范围内）
        config = RiskBudgetConfig(
            allocation_ratios={
                "510050.SSE": 0.335,
                "510300.SSE": 0.335,
                "510500.SSE": 0.335,
            }
        )
        
        # 应该通过验证
        allocator = RiskBudgetAllocator(config)
        assert allocator is not None


class TestRiskBudgetAllocatorBoundaryConditions:
    """测试边界情况"""
    
    def test_single_underlying_full_allocation(self):
        """测试单一品种完全分配"""
        config = RiskBudgetConfig(
            allocation_ratios={"510050.SSE": 1.0}
        )
        allocator = RiskBudgetAllocator(config)
        
        positions = [
            Position(
                vt_symbol="10005000C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=5,
                direction="short",
                open_price=0.5,
            ),
        ]
        
        greeks_map = {
            "10005000C2412.SSE": GreeksResult(
                delta=0.5,
                gamma=0.01,
                vega=10.0,
                success=True,
            ),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        assert len(usage_map) == 1
        assert usage_map["510050.SSE"].delta_used == 25000.0
        assert usage_map["510050.SSE"].position_count == 1
    
    def test_allocation_ratios_sum_slightly_over_one(self):
        """测试分配比例总和略大于 1（超出容忍范围）"""
        config = RiskBudgetConfig(
            allocation_ratios={
                "510050.SSE": 0.4,
                "510300.SSE": 0.35,
                "510500.SSE": 0.3,
            }
        )
        
        # 总和为 1.05，超出容忍范围
        with pytest.raises(ValueError):
            RiskBudgetAllocator(config)
    
    def test_zero_volume_position_not_counted(self):
        """测试零持仓量不计入使用量"""
        config = RiskBudgetConfig(allocation_dimension="underlying")
        allocator = RiskBudgetAllocator(config)
        
        positions = [
            Position(
                vt_symbol="10005000C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=0,  # 零持仓
                direction="short",
                open_price=0.5,
            ),
        ]
        
        greeks_map = {
            "10005000C2412.SSE": GreeksResult(
                delta=0.5,
                gamma=0.01,
                vega=10.0,
                success=True,
            ),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        # 零持仓不应计入
        assert len(usage_map) == 0
    
    def test_negative_greeks_absolute_value(self):
        """测试负 Greeks 值取绝对值"""
        config = RiskBudgetConfig(allocation_dimension="underlying")
        allocator = RiskBudgetAllocator(config)
        
        positions = [
            Position(
                vt_symbol="10005000C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=2,
                direction="short",
                open_price=0.5,
            ),
        ]
        
        # 负 Delta 和 Theta
        greeks_map = {
            "10005000C2412.SSE": GreeksResult(
                delta=-0.5,  # 负值
                gamma=0.01,
                theta=-0.05,  # 负值
                vega=10.0,
                success=True,
            ),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        # 应该取绝对值
        assert usage_map["510050.SSE"].delta_used == 10000.0  # |-0.5 * 2 * 10000|
    
    def test_very_small_greeks_values(self):
        """测试非常小的 Greeks 值"""
        config = RiskBudgetConfig(allocation_dimension="underlying")
        allocator = RiskBudgetAllocator(config)
        
        positions = [
            Position(
                vt_symbol="10005000C2412.SSE",
                underlying_vt_symbol="510050.SSE",
                signal="open_signal",
                volume=1,
                direction="short",
                open_price=0.5,
            ),
        ]
        
        greeks_map = {
            "10005000C2412.SSE": GreeksResult(
                delta=0.0001,
                gamma=0.00001,
                vega=0.001,
                success=True,
            ),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        # 应该正确计算小值
        assert usage_map["510050.SSE"].delta_used == 1.0
        assert usage_map["510050.SSE"].gamma_used == 0.1
        assert usage_map["510050.SSE"].vega_used == 10.0
