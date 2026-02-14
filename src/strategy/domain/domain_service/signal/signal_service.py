"""
SignalService - 信号判断领域服务（模板）

本文件是框架模板，提供信号判断服务的骨架结构。
使用本模板时，请根据你的策略需求实现具体的开平仓信号逻辑。

═══════════════════════════════════════════════════════════════════
  开发指南
═══════════════════════════════════════════════════════════════════

1. 本类实现 ISignalService 接口，负责根据指标状态判断开平仓信号。

2. 信号以字符串形式返回，建议命名规范: ACTION_REASON_DETAIL
   - 开仓信号示例: "long_golden_cross", "short_death_cross", "buy_call_breakout"
   - 平仓信号示例: "close_long_stop_loss", "close_short_take_profit"

3. 信号判断流程:
   a. 从 instrument.indicators 字典读取指标数据（由 IndicatorService 填充）
   b. 根据策略逻辑判断是否触发信号
   c. 返回信号字符串或 None

4. check_close_signal() 接收 position 参数，可根据持仓方向、开仓信号等
   决定平仓逻辑。position.signal 存储了开仓时的信号字符串。

5. 直接在本文件中实现你的信号逻辑即可
"""
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...entity.target_instrument import TargetInstrument
    from ...entity.position import Position


class ISignalService(ABC):
    """信号生成服务接口"""

    @abstractmethod
    def check_open_signal(self, instrument: "TargetInstrument") -> Optional[str]:
        """检查开仓信号"""
        pass

    @abstractmethod
    def check_close_signal(self, instrument: "TargetInstrument", position: "Position") -> Optional[str]:
        """检查平仓信号"""
        pass


class SignalService(ISignalService):
    """
    信号判断服务（模板）

    使用时请根据策略需求:
    1. 在 check_open_signal() 中实现开仓信号逻辑
    2. 在 check_close_signal() 中实现平仓信号逻辑
    3. 从 instrument.indicators 读取指标数据进行判断
    """

    def check_open_signal(
        self,
        instrument: "TargetInstrument",
    ) -> Optional[str]:
        """
        检查开仓信号

        TODO: 实现你的开仓信号逻辑，例如:
            if 'ema' not in instrument.indicators:
                return None

            ema = instrument.indicators['ema']
            if ema['fast'] > ema['slow']:
                return "long_ema_crossover"

            return None

        Args:
            instrument: 标的实体（包含 indicators 字典）

        Returns:
            触发的信号字符串，无信号返回 None
        """
        return None

    def check_close_signal(
        self,
        instrument: "TargetInstrument",
        position: "Position",
    ) -> Optional[str]:
        """
        检查平仓信号

        TODO: 实现你的平仓信号逻辑，例如:
            if 'ema' not in instrument.indicators:
                return None

            ema = instrument.indicators['ema']
            open_signal = position.signal

            # 多头持仓: EMA 死叉时平仓
            if position.direction == "long" and ema['fast'] < ema['slow']:
                return "close_long_ema_crossover"

            return None

        Args:
            instrument: 标的实体（包含 indicators 字典）
            position: 持仓实体（包含 direction, signal 等信息）

        Returns:
            匹配的平仓信号字符串，或 None
        """
        return None
