"""
示例信号生成服务 (Demo ISignalService)

本文件展示如何实现 ISignalService 接口，用于生成开平仓信号。

设计理念:
- 从 instrument.indicators 字典读取指标数据
- 根据策略逻辑判断开平仓时机
- 返回描述性的信号字符串
- 信号字符串采用 ACTION_REASON_DETAIL 命名规范

注意: 本示例使用 MACD 指标作为演示，实际使用时请替换为你的策略所需逻辑。
"""

from typing import Optional, TYPE_CHECKING

from src.strategy.domain.interface.signal_service import ISignalService

if TYPE_CHECKING:
    from src.strategy.domain.entity.target_instrument import TargetInstrument
    from src.strategy.domain.entity.position import Position


class DemoSignalService(ISignalService):
    """
    示例信号生成服务
    
    本类展示如何实现 ISignalService 接口，提供基于 MACD 指标的开平仓信号生成逻辑。
    
    信号定义:
        - "long_macd_golden_cross": MACD 金叉做多信号
        - "close_long_macd_death_cross": MACD 死叉平多信号
        - "short_macd_death_cross": MACD 死叉做空信号
        - "close_short_macd_golden_cross": MACD 金叉平空信号
    
    使用方法:
        >>> signal_service = DemoSignalService()
        >>> open_signal = signal_service.check_open_signal(instrument)
        >>> if open_signal:
        ...     print(f"触发开仓信号: {open_signal}")
    """
    
    def __init__(self):
        """
        初始化信号服务
        
        可以在这里添加策略参数，例如:
        - 信号过滤阈值
        - 信号确认周期
        - 风控参数
        """
        # 示例: MACD 柱状图阈值，用于过滤弱信号
        self.macd_bar_threshold = 0.0
        
        # 示例: 是否启用做空信号
        self.enable_short_signal = True
    
    def check_open_signal(self, instrument: "TargetInstrument") -> Optional[str]:
        """
        检查开仓信号
        
        策略逻辑:
        1. 检查 indicators 字典中是否存在 'macd' 指标
        2. 读取当前和前一根 K 线的 MACD 数据
        3. 判断是否发生金叉或死叉
        4. 返回相应的信号字符串
        
        Args:
            instrument: 标的实体，包含 indicators 字典
        
        Returns:
            str: 触发开仓时返回信号字符串
            None: 无开仓信号时返回 None
        """
        # 步骤 1: 检查指标数据是否存在
        if 'macd' not in instrument.indicators:
            # 指标数据不存在，返回 None（不抛出异常）
            return None
        
        macd_data = instrument.indicators['macd']
        
        # 步骤 2: 检查 MACD 数据结构是否完整
        # 期望的数据结构: {'dif': float, 'dea': float, 'macd_bar': float}
        required_keys = ['dif', 'dea', 'macd_bar']
        if not all(key in macd_data for key in required_keys):
            # 数据结构不完整，返回 None
            return None
        
        # 步骤 3: 读取当前 MACD 值
        current_dif = macd_data['dif']
        current_dea = macd_data['dea']
        current_macd_bar = macd_data['macd_bar']
        
        # 步骤 4: 检查是否有历史数据用于判断交叉
        # 注意: 这里假设 IIndicatorService 会在 indicators 中存储历史值
        # 如果没有历史值，可以从 instrument.bars 中重新计算
        if 'prev_dif' not in macd_data or 'prev_dea' not in macd_data:
            # 首次计算，无法判断交叉，返回 None
            return None
        
        prev_dif = macd_data['prev_dif']
        prev_dea = macd_data['prev_dea']
        
        # 步骤 5: 判断 MACD 金叉（做多信号）
        # 金叉条件: 前一根 K 线 DIF <= DEA，当前 K 线 DIF > DEA
        if prev_dif <= prev_dea and current_dif > current_dea:
            # 可选: 添加额外的过滤条件
            if current_macd_bar > self.macd_bar_threshold:
                return "long_macd_golden_cross"
        
        # 步骤 6: 判断 MACD 死叉（做空信号）
        # 死叉条件: 前一根 K 线 DIF >= DEA，当前 K 线 DIF < DEA
        if self.enable_short_signal:
            if prev_dif >= prev_dea and current_dif < current_dea:
                # 可选: 添加额外的过滤条件
                if current_macd_bar < -self.macd_bar_threshold:
                    return "short_macd_death_cross"
        
        # 步骤 7: 无信号触发
        return None
    
    def check_close_signal(
        self,
        instrument: "TargetInstrument",
        position: "Position"
    ) -> Optional[str]:
        """
        检查平仓信号
        
        策略逻辑:
        1. 检查 indicators 字典中是否存在 'macd' 指标
        2. 根据持仓方向判断平仓条件
        3. 多头持仓: MACD 死叉时平仓
        4. 空头持仓: MACD 金叉时平仓
        
        Args:
            instrument: 标的实体，包含 indicators 字典
            position: 当前持仓，包含方向、手数等信息
        
        Returns:
            str: 触发平仓时返回信号字符串
            None: 无平仓信号时返回 None
        """
        # 步骤 1: 检查指标数据是否存在
        if 'macd' not in instrument.indicators:
            return None
        
        macd_data = instrument.indicators['macd']
        
        # 步骤 2: 检查 MACD 数据结构是否完整
        required_keys = ['dif', 'dea', 'prev_dif', 'prev_dea']
        if not all(key in macd_data for key in required_keys):
            return None
        
        # 步骤 3: 读取当前和历史 MACD 值
        current_dif = macd_data['dif']
        current_dea = macd_data['dea']
        prev_dif = macd_data['prev_dif']
        prev_dea = macd_data['prev_dea']
        
        # 步骤 4: 根据持仓方向判断平仓信号
        
        # 多头持仓: 检查 MACD 死叉
        if position.direction == "long":
            # 死叉条件: 前一根 K 线 DIF >= DEA，当前 K 线 DIF < DEA
            if prev_dif >= prev_dea and current_dif < current_dea:
                return "close_long_macd_death_cross"
        
        # 空头持仓: 检查 MACD 金叉
        elif position.direction == "short":
            # 金叉条件: 前一根 K 线 DIF <= DEA，当前 K 线 DIF > DEA
            if prev_dif <= prev_dea and current_dif > current_dea:
                return "close_short_macd_golden_cross"
        
        # 步骤 5: 无平仓信号
        return None


# ============================================================================
# 高级示例: 多条件信号生成服务
# ============================================================================

class AdvancedSignalService(ISignalService):
    """
    高级信号生成服务示例
    
    本类展示如何实现更复杂的信号生成逻辑，结合多个指标和条件。
    
    特性:
    - 多指标组合判断
    - 信号确认机制: 需要多个条件同时满足
    - 风控过滤: 根据市场状态过滤信号
    
    信号定义:
        - "long_multi_confirm": 多指标确认做多信号
        - "short_multi_confirm": 多指标确认做空信号
        - "close_long_stop_loss": 多头止损
        - "close_short_stop_loss": 空头止损
    """
    
    def __init__(self, stop_loss_pct: float = 0.02):
        """
        初始化高级信号服务
        
        Args:
            stop_loss_pct: 止损百分比（默认 2%）
        """
        self.stop_loss_pct = stop_loss_pct
    
    def check_open_signal(self, instrument: "TargetInstrument") -> Optional[str]:
        """
        检查开仓信号（多指标组合）
        
        开仓条件示例:
        1. 指标 A 满足条件
        2. 指标 B 满足条件
        3. 两者同时满足时触发信号
        
        Args:
            instrument: 标的实体
        
        Returns:
            信号字符串或 None
        """
        # 检查所有必需的指标是否存在
        # TODO: 替换为你的策略所需指标
        required_indicators = ['indicator_a', 'indicator_b']
        if not all(ind in instrument.indicators for ind in required_indicators):
            return None
        
        ind_a = instrument.indicators['indicator_a']
        ind_b = instrument.indicators['indicator_b']
        
        # TODO: 实现你的多指标组合判断逻辑
        # 示例:
        # if ind_a.get('bullish') and ind_b.get('confirm'):
        #     return "long_multi_confirm"
        # if ind_a.get('bearish') and ind_b.get('confirm'):
        #     return "short_multi_confirm"
        
        return None
    
    def check_close_signal(
        self,
        instrument: "TargetInstrument",
        position: "Position"
    ) -> Optional[str]:
        """
        检查平仓信号（包含止损逻辑）
        
        Args:
            instrument: 标的实体
            position: 当前持仓
        
        Returns:
            信号字符串或 None
        """
        # 检查止损
        stop_loss_signal = self._check_stop_loss(instrument, position)
        if stop_loss_signal:
            return stop_loss_signal
        
        # TODO: 实现反向信号平仓逻辑
        
        return None
    
    def _check_stop_loss(
        self,
        instrument: "TargetInstrument",
        position: "Position"
    ) -> Optional[str]:
        """
        检查止损条件
        
        Args:
            instrument: 标的实体
            position: 当前持仓
        
        Returns:
            止损信号字符串或 None
        """
        # 获取当前价格
        current_price = instrument.latest_close
        if current_price <= 0:
            return None
        
        # 计算盈亏比例
        if position.direction == "long":
            stop_loss_price = position.open_price * (1 - self.stop_loss_pct)
            if current_price < stop_loss_price:
                return "close_long_stop_loss"
        
        elif position.direction == "short":
            stop_loss_price = position.open_price * (1 + self.stop_loss_pct)
            if current_price > stop_loss_price:
                return "close_short_stop_loss"
        
        return None


# ============================================================================
# 使用示例
# ============================================================================

def example_usage():
    """
    示例: 如何使用 DemoSignalService
    
    注意: 这只是演示代码，实际使用时需要在 GenericStrategyAdapter 中
    通过 setup_services 方法注入到 StrategyEngine。
    """
    from src.strategy.domain.entity.target_instrument import TargetInstrument
    from src.strategy.domain.entity.position import Position
    
    # 创建信号服务实例
    signal_service = DemoSignalService()
    
    # 创建标的实体（假设已经由 IIndicatorService 填充了指标数据）
    instrument = TargetInstrument(vt_symbol="rb2501.SHFE")
    
    # 模拟指标数据（由 IIndicatorService 填充）
    instrument.indicators['macd'] = {
        'dif': 10.5,
        'dea': 8.3,
        'macd_bar': 2.2,
        'prev_dif': 8.0,
        'prev_dea': 9.0
    }
    
    # 检查开仓信号
    open_signal = signal_service.check_open_signal(instrument)
    if open_signal:
        print(f"触发开仓信号: {open_signal}")
    
    # 创建持仓实体
    position = Position(
        vt_symbol="rb2501C4000.SHFE",
        underlying_vt_symbol="rb2501.SHFE",
        signal=open_signal or "example_signal",
        direction="long",
        volume=10,
        open_price=4000.0
    )
    
    # 检查平仓信号
    close_signal = signal_service.check_close_signal(instrument, position)
    if close_signal:
        print(f"触发平仓信号: {close_signal}")


if __name__ == "__main__":
    # 运行示例
    example_usage()
