"""
示例指标计算服务实现 (DemoIndicatorService)

本模块提供了 IIndicatorService 接口的示例实现，展示如何计算技术指标并更新 TargetInstrument 的 indicators 字典。

使用场景:
- 作为学习示例，了解如何实现 IIndicatorService 接口
- 作为模板，快速开发自定义指标服务

注意: 本示例使用 MACD/EMA 作为演示指标，实际使用时请替换为你的策略所需指标。
"""

from typing import TYPE_CHECKING
import pandas as pd
import numpy as np

from src.strategy.domain.interface.indicator_service import IIndicatorService

if TYPE_CHECKING:
    from src.strategy.domain.entity.target_instrument import TargetInstrument


class DemoIndicatorService(IIndicatorService):
    """
    示例指标计算服务
    
    本类展示如何实现 IIndicatorService 接口，计算 MACD 和 EMA 指标。
    
    指标说明:
    - MACD: 由快线(DIF)、慢线(DEA)和柱状图(MACD Bar)组成
      - DIF = EMA(12) - EMA(26)
      - DEA = EMA(DIF, 9)
      - MACD Bar = (DIF - DEA) * 2
    
    - EMA: 指数移动平均线，对近期价格赋予更高权重
    
    Attributes:
        fast_period (int): 快速 EMA 周期，默认 12
        slow_period (int): 慢速 EMA 周期，默认 26
        signal_period (int): 信号线 EMA 周期，默认 9
        min_bars (int): 计算指标所需的最小 K 线数量
    """
    
    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ):
        """
        初始化指标服务
        
        Args:
            fast_period: 快速 EMA 周期
            slow_period: 慢速 EMA 周期
            signal_period: 信号线 EMA 周期
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        # 计算指标所需的最小 K 线数量 = 慢速周期 + 信号周期
        self.min_bars = slow_period + signal_period
    
    def calculate_bar(self, instrument: "TargetInstrument", bar: dict) -> None:
        """
        计算并更新指标
        
        此方法在每根新 K 线到达时被调用，计算 MACD 和 EMA 指标并更新到 instrument.indicators 字典。
        
        Args:
            instrument: 标的实体，包含历史 K 线数据
            bar: 新 K 线数据（已由框架添加到 instrument.bars 中）
        
        更新的指标结构:
            instrument.indicators['macd'] = {
                'dif': float,      # 快慢线差值
                'dea': float,      # 信号线
                'macd_bar': float  # 柱状图值
            }
            
            instrument.indicators['ema'] = {
                'fast': float,     # 快速 EMA
                'slow': float      # 慢速 EMA
            }
        """
        # 1. 检查数据是否充足
        if len(instrument.bars) < self.min_bars:
            # 数据不足，跳过计算（不抛出异常，保持策略继续运行）
            return
        
        # 2. 获取收盘价序列
        close_prices = instrument.bars['close'].values
        
        # 3. 计算 EMA 指标
        fast_ema = self._calculate_ema(close_prices, self.fast_period)
        slow_ema = self._calculate_ema(close_prices, self.slow_period)
        
        # 4. 计算 MACD 指标
        dif = fast_ema - slow_ema  # DIF = 快线 - 慢线
        
        # 计算 DEA (DIF 的 EMA)
        # 注意: 需要使用历史 DIF 值来计算 DEA
        dif_series = self._calculate_dif_series(close_prices)
        dea = self._calculate_ema(dif_series, self.signal_period)
        
        # 计算 MACD 柱状图
        macd_bar = (dif - dea) * 2
        
        # 5. 更新 instrument.indicators 字典
        instrument.indicators['macd'] = {
            'dif': float(dif),
            'dea': float(dea),
            'macd_bar': float(macd_bar)
        }
        
        instrument.indicators['ema'] = {
            'fast': float(fast_ema),
            'slow': float(slow_ema)
        }
    
    def _calculate_ema(self, data: np.ndarray, period: int) -> float:
        """
        计算指数移动平均线 (EMA)
        
        EMA 公式:
        - EMA(today) = α * Price(today) + (1 - α) * EMA(yesterday)
        - α = 2 / (period + 1)
        
        Args:
            data: 价格数据数组
            period: EMA 周期
        
        Returns:
            最新的 EMA 值
        """
        # 使用 pandas 的 ewm 方法计算 EMA
        # adjust=False 表示使用递归公式
        ema_series = pd.Series(data).ewm(span=period, adjust=False).mean()
        return float(ema_series.iloc[-1])
    
    def _calculate_dif_series(self, close_prices: np.ndarray) -> np.ndarray:
        """
        计算 DIF 序列（用于计算 DEA）
        
        Args:
            close_prices: 收盘价数组
        
        Returns:
            DIF 值序列
        """
        # 计算快慢 EMA 序列
        fast_ema_series = pd.Series(close_prices).ewm(
            span=self.fast_period, adjust=False
        ).mean()
        slow_ema_series = pd.Series(close_prices).ewm(
            span=self.slow_period, adjust=False
        ).mean()
        
        # DIF = 快线 - 慢线
        dif_series = (fast_ema_series - slow_ema_series).values
        return dif_series
    
    def __repr__(self) -> str:
        return (
            f"DemoIndicatorService("
            f"fast={self.fast_period}, "
            f"slow={self.slow_period}, "
            f"signal={self.signal_period})"
        )


# ============================================================================
# 使用示例
# ============================================================================

def example_usage():
    """
    示例: 如何使用 DemoIndicatorService
    
    此函数展示了如何在策略中使用指标服务:
    1. 创建指标服务实例
    2. 在 K 线更新时调用 calculate_bar
    3. 从 instrument.indicators 读取指标值
    """
    from src.strategy.domain.entity.target_instrument import TargetInstrument
    from datetime import datetime
    
    # 1. 创建指标服务（使用默认参数）
    indicator_service = DemoIndicatorService()
    
    # 2. 创建标的实体
    instrument = TargetInstrument(vt_symbol="rb2501.SHFE")
    
    # 3. 模拟添加 K 线数据
    for i in range(50):
        bar_data = {
            'datetime': datetime.now(),
            'open': 3500 + i,
            'high': 3510 + i,
            'low': 3490 + i,
            'close': 3500 + i,
            'volume': 1000
        }
        instrument.append_bar(bar_data)
        
        # 4. 计算指标
        indicator_service.calculate_bar(instrument, bar_data)
    
    # 5. 读取指标值
    if 'macd' in instrument.indicators:
        macd = instrument.indicators['macd']
        print(f"MACD DIF: {macd['dif']:.2f}")
        print(f"MACD DEA: {macd['dea']:.2f}")
        print(f"MACD Bar: {macd['macd_bar']:.2f}")
    
    if 'ema' in instrument.indicators:
        ema = instrument.indicators['ema']
        print(f"Fast EMA: {ema['fast']:.2f}")
        print(f"Slow EMA: {ema['slow']:.2f}")


if __name__ == "__main__":
    # 运行示例
    example_usage()
