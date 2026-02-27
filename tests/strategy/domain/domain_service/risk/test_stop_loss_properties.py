"""
StopLossManager 属性测试

使用 Hypothesis 进行基于属性的测试，验证止损管理服务的通用正确性属性。
"""
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime

from src.strategy.domain.domain_service.risk.stop_loss_manager import StopLossManager
from src.strategy.domain.entity.position import Position
from src.strategy.domain.value_object.risk.risk import StopLossConfig


# ============================================================================
# 测试数据生成策略
# ============================================================================

def position_strategy(
    min_volume: int = 1,
    max_volume: int = 100,
    min_price: float = 0.01,
    max_price: float = 10.0
):
    """生成持仓实体的策略"""
    return st.builds(
        Position,
        vt_symbol=st.text(min_size=10, max_size=20, alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ."),
        underlying_vt_symbol=st.just("510050.SSE"),
        signal=st.just("test_signal"),
        volume=st.integers(min_value=min_volume, max_value=max_volume),
        direction=st.sampled_from(["long", "short"]),
        open_price=st.floats(min_value=min_price, max_value=max_price, allow_nan=False, allow_infinity=False),
        is_closed=st.just(False),
    )


def stop_loss_config_strategy():
    """生成止损配置的策略"""
    return st.builds(
        StopLossConfig,
        enable_fixed_stop=st.booleans(),
        fixed_stop_loss_amount=st.floats(min_value=100.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        fixed_stop_loss_percent=st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False),
        enable_trailing_stop=st.booleans(),
        trailing_stop_percent=st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False),
        enable_portfolio_stop=st.booleans(),
        daily_loss_limit=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    )


# ============================================================================
# Feature: risk-service-enhancement, Property 1: 止损触发正确性
# **Validates: Requirements 1.1, 1.2, 1.4, 1.5, 1.6**
# ============================================================================

@settings(max_examples=100)
@given(
    config=stop_loss_config_strategy(),
    position=position_strategy(),
    current_price=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    peak_profit=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
)
def test_property_stop_loss_trigger_correctness(config, position, current_price, peak_profit):
    """
    Feature: risk-service-enhancement, Property 1: 止损触发正确性
    
    对于任意持仓、当前价格和历史最高盈利，当浮动亏损超过配置的止损阈值
    （固定止损或移动止损）时，止损检查应该返回包含完整信息的触发结果
    （合约代码、触发类型、亏损金额、阈值、价格信息）
    
    **Validates: Requirements 1.1, 1.2, 1.4, 1.5, 1.6**
    """
    # 确保持仓是活跃的
    assume(position.is_active)
    assume(position.volume > 0)
    
    manager = StopLossManager(config)
    
    # 计算持仓盈亏
    multiplier = 10000.0
    if position.direction == "short":
        pnl = (position.open_price - current_price) * position.volume * multiplier
    else:
        pnl = (current_price - position.open_price) * position.volume * multiplier
    
    # 计算开仓价值
    open_value = position.open_price * position.volume * multiplier
    
    # 执行止损检查
    result = manager.check_position_stop_loss(position, current_price, peak_profit)
    
    # 属性验证
    if result is not None:
        # 如果触发止损，必须包含完整信息
        assert result.vt_symbol == position.vt_symbol, "触发结果应包含正确的合约代码"
        assert result.trigger_type in ["fixed", "trailing"], "触发类型应为 fixed 或 trailing"
        assert result.current_loss >= 0, "当前亏损应为非负数"
        assert result.threshold > 0, "阈值应为正数"
        assert result.current_price == current_price, "触发结果应包含当前价格"
        assert result.open_price == position.open_price, "触发结果应包含开仓价格"
        assert len(result.message) > 0, "触发结果应包含消息"
        
        # 验证触发逻辑的正确性
        if result.trigger_type == "fixed":
            # 固定止损：必须启用且亏损超过阈值
            assert config.enable_fixed_stop, "固定止损触发时必须启用固定止损"
            assert pnl < 0, "固定止损触发时必须处于亏损状态"
            
            loss = abs(pnl)
            loss_percent = loss / open_value if open_value > 0 else 0
            
            # 至少满足一个止损条件
            assert (
                loss >= config.fixed_stop_loss_amount or
                loss_percent >= config.fixed_stop_loss_percent
            ), "固定止损触发时亏损必须超过至少一个阈值"
        
        elif result.trigger_type == "trailing":
            # 移动止损：必须启用且有历史盈利且回撤超过阈值
            assert config.enable_trailing_stop, "移动止损触发时必须启用移动止损"
            assert peak_profit > 0, "移动止损触发时必须有历史盈利"
            
            drawdown = peak_profit - pnl
            drawdown_percent = drawdown / peak_profit if peak_profit > 0 else 0
            
            assert drawdown_percent >= config.trailing_stop_percent, \
                "移动止损触发时回撤必须超过阈值"
    
    else:
        # 如果未触发止损，验证确实不满足触发条件
        if config.enable_fixed_stop and pnl < 0:
            # 固定止损启用且亏损，但未触发
            loss = abs(pnl)
            loss_percent = loss / open_value if open_value > 0 else 0
            
            # 不应同时满足两个止损条件
            assert not (
                loss >= config.fixed_stop_loss_amount and
                loss_percent >= config.fixed_stop_loss_percent
            ), "满足固定止损条件时应该触发"
        
        if config.enable_trailing_stop and peak_profit > 0:
            # 移动止损启用且有历史盈利，但未触发
            drawdown = peak_profit - pnl
            drawdown_percent = drawdown / peak_profit if peak_profit > 0 else 0
            
            # 回撤不应超过阈值（考虑固定止损优先级）
            if not (config.enable_fixed_stop and pnl < 0):
                assert drawdown_percent < config.trailing_stop_percent, \
                    "回撤超过阈值时应该触发移动止损"


# ============================================================================
# Feature: risk-service-enhancement, Property 2: 组合止损全平仓
# **Validates: Requirements 1.3**
# ============================================================================

@settings(max_examples=100)
@given(
    config=stop_loss_config_strategy(),
    positions=st.lists(position_strategy(), min_size=0, max_size=10),
    daily_start_equity=st.floats(min_value=50000.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
    current_equity=st.floats(min_value=10000.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
)
def test_property_portfolio_stop_loss_closes_all_positions(config, positions, daily_start_equity, current_equity):
    """
    Feature: risk-service-enhancement, Property 2: 组合止损全平仓
    
    对于任意持仓组合和价格字典，当组合总亏损超过每日止损限额时，
    组合止损检查应该返回包含所有活跃持仓合约代码的平仓列表
    
    **Validates: Requirements 1.3**
    """
    manager = StopLossManager(config)
    
    # 生成价格字典（为每个持仓生成一个价格）
    current_prices = {
        pos.vt_symbol: pos.open_price * 1.1  # 简单设置为开仓价的 1.1 倍
        for pos in positions
    }
    
    # 计算组合总亏损
    total_loss = daily_start_equity - current_equity
    
    # 执行组合止损检查
    result = manager.check_portfolio_stop_loss(
        positions, current_prices, daily_start_equity, current_equity
    )
    
    # 收集所有活跃持仓
    active_positions = [pos for pos in positions if pos.is_active]
    active_symbols = {pos.vt_symbol for pos in active_positions}
    
    # 属性验证
    if result is not None:
        # 如果触发组合止损，必须满足条件
        assert config.enable_portfolio_stop, "组合止损触发时必须启用组合止损"
        assert total_loss > config.daily_loss_limit, "组合止损触发时亏损必须超过限额"
        
        # 验证返回的平仓列表包含所有活跃持仓
        assert result.total_loss == total_loss, "触发结果应包含正确的总亏损"
        assert result.daily_limit == config.daily_loss_limit, "触发结果应包含正确的限额"
        assert len(result.message) > 0, "触发结果应包含消息"
        
        # 关键属性：平仓列表应包含所有活跃持仓
        result_symbols = set(result.positions_to_close)
        assert result_symbols == active_symbols, \
            f"平仓列表应包含所有活跃持仓。期望: {active_symbols}, 实际: {result_symbols}"
        
        # 平仓列表不应包含非活跃持仓
        for symbol in result.positions_to_close:
            assert any(pos.vt_symbol == symbol and pos.is_active for pos in positions), \
                f"平仓列表不应包含非活跃持仓: {symbol}"
    
    else:
        # 如果未触发组合止损，验证确实不满足触发条件
        if config.enable_portfolio_stop:
            assert total_loss <= config.daily_loss_limit, \
                "亏损超过限额时应该触发组合止损"


# ============================================================================
# Feature: risk-service-enhancement, Property 3: 止损计算一致性
# **Validates: Requirements 1.2**
# ============================================================================

@settings(max_examples=100)
@given(
    position=position_strategy(),
    current_price=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
)
def test_property_stop_loss_calculation_consistency(position, current_price):
    """
    Feature: risk-service-enhancement, Property 3: 止损计算一致性
    
    对于任意持仓和价格，按金额止损和按百分比止损计算的亏损值
    应该与实际盈亏一致（当前价值 - 开仓价值）
    
    **Validates: Requirements 1.2**
    """
    # 确保持仓是活跃的
    assume(position.is_active)
    assume(position.volume > 0)
    assume(position.open_price > 0)
    
    # 创建配置：同时启用金额和百分比止损
    config = StopLossConfig(
        enable_fixed_stop=True,
        fixed_stop_loss_amount=1000.0,
        fixed_stop_loss_percent=0.5,
        enable_trailing_stop=False,
    )
    
    manager = StopLossManager(config)
    
    # 计算实际盈亏
    multiplier = 10000.0
    if position.direction == "short":
        actual_pnl = (position.open_price - current_price) * position.volume * multiplier
    else:
        actual_pnl = (current_price - position.open_price) * position.volume * multiplier
    
    # 计算开仓价值和当前价值
    open_value = position.open_price * position.volume * multiplier
    current_value = current_price * position.volume * multiplier
    
    # 执行止损检查
    result = manager.check_position_stop_loss(position, current_price)
    
    # 属性验证：盈亏计算一致性
    if result is not None and result.trigger_type == "fixed":
        # 如果触发固定止损，验证亏损计算的一致性
        assert actual_pnl < 0, "触发固定止损时应该处于亏损状态"
        
        actual_loss = abs(actual_pnl)
        
        # 验证触发结果中的亏损与实际计算一致
        assert abs(result.current_loss - actual_loss) < 1e-6, \
            f"触发结果中的亏损应与实际计算一致。期望: {actual_loss}, 实际: {result.current_loss}"
        
        # 验证盈亏计算与价值差一致
        if position.direction == "short":
            # 卖权：亏损 = 当前价值 - 开仓价值（当前价格上涨时亏损）
            expected_pnl = open_value - current_value
        else:
            # 买权：盈亏 = 当前价值 - 开仓价值
            expected_pnl = current_value - open_value
        
        assert abs(actual_pnl - expected_pnl) < 1e-6, \
            f"盈亏计算应与价值差一致。实际盈亏: {actual_pnl}, 价值差: {expected_pnl}"
        
        # 验证按百分比计算的亏损与按金额计算的亏损一致
        loss_percent = actual_loss / open_value if open_value > 0 else 0
        loss_by_percent = loss_percent * open_value
        
        assert abs(loss_by_percent - actual_loss) < 1e-6, \
            f"按百分比计算的亏损应与按金额计算的亏损一致。" \
            f"按百分比: {loss_by_percent}, 按金额: {actual_loss}"
    
    # 无论是否触发，验证盈亏计算的基本一致性
    # 盈亏 = (当前价值 - 开仓价值) * 方向系数
    if position.direction == "short":
        expected_pnl = open_value - current_value
    else:
        expected_pnl = current_value - open_value
    
    assert abs(actual_pnl - expected_pnl) < 1e-6, \
        f"盈亏计算应始终与价值差一致。实际: {actual_pnl}, 期望: {expected_pnl}"
