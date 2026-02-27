"""
StopLossManager 单元测试

测试止损管理服务的固定止损、移动止损和组合止损功能。
"""
import pytest
from datetime import datetime

from src.strategy.domain.domain_service.risk.stop_loss_manager import StopLossManager
from src.strategy.domain.entity.position import Position
from src.strategy.domain.value_object.risk.risk import (
    StopLossConfig,
    StopLossTrigger,
    PortfolioStopLossTrigger,
)


class TestStopLossManagerFixedStop:
    """测试固定止损功能"""
    
    def test_fixed_stop_by_amount_triggered(self):
        """测试按金额固定止损触发"""
        # 配置: 固定止损金额 1000
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=1000.0,
            fixed_stop_loss_percent=0.5,
            enable_trailing_stop=False,
        )
        manager = StopLossManager(config)
        
        # 创建持仓: 卖权，开仓价 0.5，持仓 2 手
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 当前价格 0.56，亏损 = (0.56 - 0.5) * 2 * 10000 = 1200 > 1000
        current_price = 0.56
        
        result = manager.check_position_stop_loss(position, current_price)
        
        assert result is not None
        assert result.trigger_type == "fixed"
        assert result.vt_symbol == "10005000C2412.SSE"
        assert abs(result.current_loss - 1200.0) < 1e-6
        assert result.threshold == 1000.0
        assert result.current_price == 0.56
        assert result.open_price == 0.5
        assert "固定止损触发(金额)" in result.message
    
    def test_fixed_stop_by_percent_triggered(self):
        """测试按百分比固定止损触发"""
        # 配置: 固定止损百分比 50%
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=10000.0,  # 设置很高，不会触发
            fixed_stop_loss_percent=0.5,
            enable_trailing_stop=False,
        )
        manager = StopLossManager(config)
        
        # 创建持仓: 卖权，开仓价 0.5，持仓 2 手
        # 开仓价值 = 0.5 * 2 * 10000 = 10000
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 当前价格 0.76，亏损 = (0.76 - 0.5) * 2 * 10000 = 5200
        # 亏损比例 = 5200 / 10000 = 52% > 50%
        current_price = 0.76
        
        result = manager.check_position_stop_loss(position, current_price)
        
        assert result is not None
        assert result.trigger_type == "fixed"
        assert result.current_loss == 5200.0
        assert abs(result.threshold - 5000.0) < 1e-6  # 50% * 10000
        assert "固定止损触发(百分比)" in result.message
    
    def test_fixed_stop_not_triggered_profit(self):
        """测试盈利状态不触发固定止损"""
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=1000.0,
            fixed_stop_loss_percent=0.5,
        )
        manager = StopLossManager(config)
        
        # 创建持仓: 卖权，开仓价 0.5，持仓 2 手
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 当前价格 0.4，盈利 = (0.5 - 0.4) * 2 * 10000 = 2000 (盈利)
        current_price = 0.4
        
        result = manager.check_position_stop_loss(position, current_price)
        
        assert result is None
    
    def test_fixed_stop_not_triggered_loss_below_threshold(self):
        """测试亏损未达阈值不触发固定止损"""
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=2000.0,
            fixed_stop_loss_percent=0.5,
        )
        manager = StopLossManager(config)
        
        # 创建持仓: 卖权，开仓价 0.5，持仓 2 手
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 当前价格 0.54，亏损 = (0.54 - 0.5) * 2 * 10000 = 800 < 2000
        # 亏损比例 = 800 / 10000 = 8% < 50%
        current_price = 0.54
        
        result = manager.check_position_stop_loss(position, current_price)
        
        assert result is None
    
    def test_fixed_stop_disabled(self):
        """测试禁用固定止损"""
        config = StopLossConfig(
            enable_fixed_stop=False,
            fixed_stop_loss_amount=1000.0,
        )
        manager = StopLossManager(config)
        
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 即使亏损很大也不触发
        current_price = 1.0
        
        result = manager.check_position_stop_loss(position, current_price)
        
        assert result is None


class TestStopLossManagerTrailingStop:
    """测试移动止损功能"""
    
    def test_trailing_stop_triggered(self):
        """测试移动止损触发"""
        # 配置: 移动止损回撤 30%
        config = StopLossConfig(
            enable_fixed_stop=False,
            enable_trailing_stop=True,
            trailing_stop_percent=0.3,
        )
        manager = StopLossManager(config)
        
        # 创建持仓: 卖权，开仓价 0.5，持仓 2 手
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 历史最高盈利 3000
        peak_profit = 3000.0
        
        # 当前价格 0.4，当前盈利 = (0.5 - 0.4) * 2 * 10000 = 2000
        # 回撤 = 3000 - 2000 = 1000
        # 回撤比例 = 1000 / 3000 = 33.3% > 30%
        current_price = 0.4
        
        result = manager.check_position_stop_loss(position, current_price, peak_profit)
        
        assert result is not None
        assert result.trigger_type == "trailing"
        assert result.vt_symbol == "10005000C2412.SSE"
        assert abs(result.current_loss - 1000.0) < 1e-6
        assert abs(result.threshold - 900.0) < 1e-6  # 30% * 3000
        assert "移动止损触发" in result.message
    
    def test_trailing_stop_not_triggered_drawdown_below_threshold(self):
        """测试回撤未达阈值不触发移动止损"""
        config = StopLossConfig(
            enable_fixed_stop=False,
            enable_trailing_stop=True,
            trailing_stop_percent=0.3,
        )
        manager = StopLossManager(config)
        
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 历史最高盈利 3000
        peak_profit = 3000.0
        
        # 当前价格 0.425，当前盈利 = (0.5 - 0.425) * 2 * 10000 = 1500
        # 回撤 = 3000 - 1500 = 1500
        # 回撤比例 = 1500 / 3000 = 50% > 30% (会触发)
        # 修改为 0.4375，当前盈利 = (0.5 - 0.4375) * 2 * 10000 = 1250
        # 回撤 = 3000 - 1250 = 1750
        # 回撤比例 = 1750 / 3000 = 58.3% > 30% (会触发)
        # 修改为 0.44，当前盈利 = (0.5 - 0.44) * 2 * 10000 = 1200
        # 回撤 = 3000 - 1200 = 1800
        # 回撤比例 = 1800 / 3000 = 60% > 30% (会触发)
        # 修改为 0.4475，当前盈利 = (0.5 - 0.4475) * 2 * 10000 = 1050
        # 回撤 = 3000 - 1050 = 1950
        # 回撤比例 = 1950 / 3000 = 65% > 30% (会触发)
        # 修改为 0.35，当前盈利 = (0.5 - 0.35) * 2 * 10000 = 3000
        # 回撤 = 3000 - 3000 = 0
        # 回撤比例 = 0 / 3000 = 0% < 30% (不触发)
        # 修改为 0.36，当前盈利 = (0.5 - 0.36) * 2 * 10000 = 2800
        # 回撤 = 3000 - 2800 = 200
        # 回撤比例 = 200 / 3000 = 6.67% < 30% (不触发)
        current_price = 0.36
        
        result = manager.check_position_stop_loss(position, current_price, peak_profit)
        
        assert result is None
    
    def test_trailing_stop_not_triggered_no_peak_profit(self):
        """测试无历史盈利不触发移动止损"""
        config = StopLossConfig(
            enable_fixed_stop=False,
            enable_trailing_stop=True,
            trailing_stop_percent=0.3,
        )
        manager = StopLossManager(config)
        
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 无历史盈利
        peak_profit = 0.0
        current_price = 0.4
        
        result = manager.check_position_stop_loss(position, current_price, peak_profit)
        
        assert result is None
    
    def test_trailing_stop_disabled(self):
        """测试禁用移动止损"""
        config = StopLossConfig(
            enable_fixed_stop=False,
            enable_trailing_stop=False,
            trailing_stop_percent=0.3,
        )
        manager = StopLossManager(config)
        
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 即使回撤很大也不触发
        peak_profit = 5000.0
        current_price = 0.5  # 盈利为 0，回撤 100%
        
        result = manager.check_position_stop_loss(position, current_price, peak_profit)
        
        assert result is None


class TestStopLossManagerCombinedStop:
    """测试固定止损和移动止损组合场景"""
    
    def test_fixed_stop_priority_over_trailing(self):
        """测试固定止损优先于移动止损"""
        # 同时启用固定止损和移动止损
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=1000.0,
            enable_trailing_stop=True,
            trailing_stop_percent=0.3,
        )
        manager = StopLossManager(config)
        
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 当前价格 0.56，亏损 1200，触发固定止损
        current_price = 0.56
        peak_profit = 3000.0
        
        result = manager.check_position_stop_loss(position, current_price, peak_profit)
        
        # 应该返回固定止损触发（优先级更高）
        assert result is not None
        assert result.trigger_type == "fixed"
    
    def test_trailing_stop_when_fixed_not_triggered(self):
        """测试固定止损未触发时检查移动止损"""
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=10000.0,  # 设置很高，不会触发
            enable_trailing_stop=True,
            trailing_stop_percent=0.3,
        )
        manager = StopLossManager(config)
        
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 历史最高盈利 3000，当前盈利 2000，回撤 33.3%
        peak_profit = 3000.0
        current_price = 0.4
        
        result = manager.check_position_stop_loss(position, current_price, peak_profit)
        
        # 应该返回移动止损触发
        assert result is not None
        assert result.trigger_type == "trailing"


class TestStopLossManagerPortfolioStop:
    """测试组合级止损功能"""
    
    def test_portfolio_stop_triggered(self):
        """测试组合止损触发"""
        # 配置: 每日止损限额 5000
        config = StopLossConfig(
            enable_portfolio_stop=True,
            daily_loss_limit=5000.0,
        )
        manager = StopLossManager(config)
        
        # 创建多个持仓
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
        
        current_prices = {
            "10005000C2412.SSE": 0.5,
            "10005100C2412.SSE": 0.6,
        }
        
        # 当日起始权益 100000，当前权益 94000，亏损 6000 > 5000
        daily_start_equity = 100000.0
        current_equity = 94000.0
        
        result = manager.check_portfolio_stop_loss(
            positions, current_prices, daily_start_equity, current_equity
        )
        
        assert result is not None
        assert result.total_loss == 6000.0
        assert result.daily_limit == 5000.0
        assert len(result.positions_to_close) == 2
        assert "10005000C2412.SSE" in result.positions_to_close
        assert "10005100C2412.SSE" in result.positions_to_close
        assert "组合止损触发" in result.message
    
    def test_portfolio_stop_not_triggered_loss_below_limit(self):
        """测试亏损未达限额不触发组合止损"""
        config = StopLossConfig(
            enable_portfolio_stop=True,
            daily_loss_limit=5000.0,
        )
        manager = StopLossManager(config)
        
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
        
        current_prices = {"10005000C2412.SSE": 0.5}
        
        # 当日起始权益 100000，当前权益 96000，亏损 4000 < 5000
        daily_start_equity = 100000.0
        current_equity = 96000.0
        
        result = manager.check_portfolio_stop_loss(
            positions, current_prices, daily_start_equity, current_equity
        )
        
        assert result is None
    
    def test_portfolio_stop_not_triggered_profit(self):
        """测试盈利状态不触发组合止损"""
        config = StopLossConfig(
            enable_portfolio_stop=True,
            daily_loss_limit=5000.0,
        )
        manager = StopLossManager(config)
        
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
        
        current_prices = {"10005000C2412.SSE": 0.5}
        
        # 当日起始权益 100000，当前权益 105000，盈利 5000
        daily_start_equity = 100000.0
        current_equity = 105000.0
        
        result = manager.check_portfolio_stop_loss(
            positions, current_prices, daily_start_equity, current_equity
        )
        
        assert result is None
    
    def test_portfolio_stop_disabled(self):
        """测试禁用组合止损"""
        config = StopLossConfig(
            enable_portfolio_stop=False,
            daily_loss_limit=5000.0,
        )
        manager = StopLossManager(config)
        
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
        
        current_prices = {"10005000C2412.SSE": 0.5}
        
        # 即使亏损很大也不触发
        daily_start_equity = 100000.0
        current_equity = 80000.0
        
        result = manager.check_portfolio_stop_loss(
            positions, current_prices, daily_start_equity, current_equity
        )
        
        assert result is None


class TestStopLossManagerBoundaryConditions:
    """测试边界情况"""
    
    def test_empty_position_list(self):
        """测试空持仓列表"""
        config = StopLossConfig(
            enable_portfolio_stop=True,
            daily_loss_limit=5000.0,
        )
        manager = StopLossManager(config)
        
        positions = []
        current_prices = {}
        daily_start_equity = 100000.0
        current_equity = 94000.0
        
        result = manager.check_portfolio_stop_loss(
            positions, current_prices, daily_start_equity, current_equity
        )
        
        # 即使亏损超限，但没有持仓可平
        assert result is not None
        assert len(result.positions_to_close) == 0
    
    def test_inactive_position(self):
        """测试非活跃持仓"""
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=1000.0,
        )
        manager = StopLossManager(config)
        
        # 创建已平仓的持仓
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=0,  # 无持仓
            direction="short",
            open_price=0.5,
            is_closed=True,
        )
        
        current_price = 0.6
        
        result = manager.check_position_stop_loss(position, current_price)
        
        assert result is None
    
    def test_zero_volume_position(self):
        """测试零持仓量"""
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=1000.0,
        )
        manager = StopLossManager(config)
        
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=0,
            direction="short",
            open_price=0.5,
        )
        
        current_price = 0.6
        
        result = manager.check_position_stop_loss(position, current_price)
        
        assert result is None
    
    def test_long_position_pnl_calculation(self):
        """测试买权持仓盈亏计算"""
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=1000.0,
        )
        manager = StopLossManager(config)
        
        # 创建买权持仓
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="long",  # 买权
            open_price=0.5,
        )
        
        # 当前价格 0.44，亏损 = (0.44 - 0.5) * 2 * 10000 = -1200 (亏损)
        current_price = 0.44
        
        result = manager.check_position_stop_loss(position, current_price)
        
        assert result is not None
        assert result.trigger_type == "fixed"
        assert result.current_loss == 1200.0
    
    def test_all_positions_profitable(self):
        """测试所有持仓盈利"""
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=1000.0,
        )
        manager = StopLossManager(config)
        
        # 创建盈利持仓
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 当前价格 0.3，盈利 = (0.5 - 0.3) * 2 * 10000 = 4000 (盈利)
        current_price = 0.3
        
        result = manager.check_position_stop_loss(position, current_price)
        
        assert result is None
    
    def test_exact_threshold_boundary(self):
        """测试恰好达到阈值边界"""
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=1200.0,
        )
        manager = StopLossManager(config)
        
        position = Position(
            vt_symbol="10005000C2412.SSE",
            underlying_vt_symbol="510050.SSE",
            signal="open_signal",
            volume=2,
            direction="short",
            open_price=0.5,
        )
        
        # 当前价格 0.56，亏损 = (0.56 - 0.5) * 2 * 10000 = 1200 (恰好等于阈值)
        current_price = 0.56
        
        result = manager.check_position_stop_loss(position, current_price)
        
        # 应该触发（>= 阈值）
        assert result is not None
        assert abs(result.current_loss - 1200.0) < 1e-6
        assert result.threshold == 1200.0
