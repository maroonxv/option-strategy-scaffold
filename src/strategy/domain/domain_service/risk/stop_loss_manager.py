"""
StopLossManager - 止损管理服务

负责监控持仓盈亏并触发止损，支持固定止损、移动止损和组合级止损。
"""

from typing import Dict, List, Optional

from ...entity.position import Position
from ...value_object.risk.risk import (
    StopLossConfig,
    StopLossTrigger,
    PortfolioStopLossTrigger,
)


class StopLossManager:
    """
    止损管理服务
    
    职责:
    1. 监控单个持仓的浮动盈亏
    2. 检查是否触发固定止损或移动止损
    3. 监控组合总亏损是否超过每日止损限额
    4. 生成止损触发结果
    """
    
    def __init__(self, config: StopLossConfig) -> None:
        """
        初始化止损管理器
        
        Args:
            config: 止损配置对象
        """
        self._config = config
    
    def check_position_stop_loss(
        self,
        position: Position,
        current_price: float,
        peak_profit: float = 0.0
    ) -> Optional[StopLossTrigger]:
        """
        检查单个持仓是否触发止损
        
        Args:
            position: 持仓实体
            current_price: 当前市场价格
            peak_profit: 历史最高盈利（用于移动止损）
            
        Returns:
            StopLossTrigger 或 None
        """
        if not position.is_active or position.volume <= 0:
            return None
        
        # 计算持仓盈亏
        pnl = self._calculate_position_pnl(position, current_price)
        
        # 检查固定止损
        if self._config.enable_fixed_stop:
            fixed_trigger = self._check_fixed_stop(position, current_price, pnl)
            if fixed_trigger:
                return fixed_trigger
        
        # 检查移动止损（仅在盈利状态下）
        if self._config.enable_trailing_stop and peak_profit > 0:
            trailing_trigger = self._check_trailing_stop(
                position, current_price, pnl, peak_profit
            )
            if trailing_trigger:
                return trailing_trigger
        
        return None
    
    def check_portfolio_stop_loss(
        self,
        positions: List[Position],
        current_prices: Dict[str, float],
        daily_start_equity: float,
        current_equity: float
    ) -> Optional[PortfolioStopLossTrigger]:
        """
        检查组合级止损
        
        Args:
            positions: 所有活跃持仓
            current_prices: 当前价格字典
            daily_start_equity: 当日起始权益
            current_equity: 当前权益
            
        Returns:
            PortfolioStopLossTrigger 或 None
        """
        if not self._config.enable_portfolio_stop:
            return None
        
        # 计算组合总亏损
        total_loss = daily_start_equity - current_equity
        
        # 检查是否超过每日止损限额
        if total_loss > self._config.daily_loss_limit:
            # 收集所有活跃持仓的合约代码
            positions_to_close = [
                pos.vt_symbol for pos in positions if pos.is_active
            ]
            
            message = (
                f"组合止损触发: 当日亏损 {total_loss:.2f} 超过限额 "
                f"{self._config.daily_loss_limit:.2f}"
            )
            
            return PortfolioStopLossTrigger(
                total_loss=total_loss,
                daily_limit=self._config.daily_loss_limit,
                positions_to_close=positions_to_close,
                message=message
            )
        
        return None
    
    def _calculate_position_pnl(
        self,
        position: Position,
        current_price: float
    ) -> float:
        """
        计算持仓盈亏
        
        对于卖权策略（short）:
        - 盈利: 开仓价格 > 当前价格 (卖高买低)
        - 亏损: 开仓价格 < 当前价格 (卖低买高)
        - PnL = (开仓价格 - 当前价格) × 手数 × 合约乘数
        
        对于买权策略（long）:
        - 盈利: 当前价格 > 开仓价格
        - 亏损: 当前价格 < 开仓价格
        - PnL = (当前价格 - 开仓价格) × 手数 × 合约乘数
        
        Args:
            position: 持仓实体
            current_price: 当前价格
            
        Returns:
            盈亏金额（正数为盈利，负数为亏损）
        """
        # 从合约代码中提取合约乘数（简化处理，实际应从合约信息中获取）
        # 期权合约乘数通常为 10000
        multiplier = 10000.0
        
        if position.direction == "short":
            # 卖权: 开仓价格 - 当前价格
            pnl = (position.open_price - current_price) * position.volume * multiplier
        else:
            # 买权: 当前价格 - 开仓价格
            pnl = (current_price - position.open_price) * position.volume * multiplier
        
        return pnl
    
    def _check_fixed_stop(
        self,
        position: Position,
        current_price: float,
        pnl: float
    ) -> Optional[StopLossTrigger]:
        """
        检查固定止损
        
        Args:
            position: 持仓实体
            current_price: 当前价格
            pnl: 当前盈亏
            
        Returns:
            StopLossTrigger 或 None
        """
        # 只在亏损时检查
        if pnl >= 0:
            return None
        
        loss = abs(pnl)
        
        # 计算开仓价值
        multiplier = 10000.0
        open_value = position.open_price * position.volume * multiplier
        
        # 检查按金额止损
        if loss >= self._config.fixed_stop_loss_amount:
            message = (
                f"固定止损触发(金额): 亏损 {loss:.2f} 超过阈值 "
                f"{self._config.fixed_stop_loss_amount:.2f}"
            )
            return StopLossTrigger(
                vt_symbol=position.vt_symbol,
                trigger_type="fixed",
                current_loss=loss,
                threshold=self._config.fixed_stop_loss_amount,
                current_price=current_price,
                open_price=position.open_price,
                message=message
            )
        
        # 检查按百分比止损
        loss_percent = loss / open_value if open_value > 0 else 0
        if loss_percent >= self._config.fixed_stop_loss_percent:
            message = (
                f"固定止损触发(百分比): 亏损比例 {loss_percent:.2%} 超过阈值 "
                f"{self._config.fixed_stop_loss_percent:.2%}"
            )
            return StopLossTrigger(
                vt_symbol=position.vt_symbol,
                trigger_type="fixed",
                current_loss=loss,
                threshold=self._config.fixed_stop_loss_percent * open_value,
                current_price=current_price,
                open_price=position.open_price,
                message=message
            )
        
        return None
    
    def _check_trailing_stop(
        self,
        position: Position,
        current_price: float,
        pnl: float,
        peak_profit: float
    ) -> Optional[StopLossTrigger]:
        """
        检查移动止损
        
        移动止损逻辑:
        - 仅在持仓曾经盈利时生效
        - 当盈利从峰值回撤超过配置的百分比时触发
        
        Args:
            position: 持仓实体
            current_price: 当前价格
            pnl: 当前盈亏
            peak_profit: 历史最高盈利
            
        Returns:
            StopLossTrigger 或 None
        """
        # 计算从峰值的回撤
        drawdown = peak_profit - pnl
        
        # 检查回撤是否超过阈值
        drawdown_percent = drawdown / peak_profit if peak_profit > 0 else 0
        
        if drawdown_percent >= self._config.trailing_stop_percent:
            message = (
                f"移动止损触发: 从峰值盈利 {peak_profit:.2f} 回撤 "
                f"{drawdown_percent:.2%} 超过阈值 "
                f"{self._config.trailing_stop_percent:.2%}"
            )
            return StopLossTrigger(
                vt_symbol=position.vt_symbol,
                trigger_type="trailing",
                current_loss=drawdown,
                threshold=self._config.trailing_stop_percent * peak_profit,
                current_price=current_price,
                open_price=position.open_price,
                message=message
            )
        
        return None
