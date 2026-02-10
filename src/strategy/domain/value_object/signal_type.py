"""
SignalType 值对象 - 信号类型枚举（模板）

本文件是框架模板，提供信号类型定义的骨架结构。
使用本模板时，请根据你的策略需求定义具体的信号类型。

═══════════════════════════════════════════════════════════════════
  开发指南
═══════════════════════════════════════════════════════════════════

1. 本枚举用于定义策略中所有的开仓和平仓信号类型。
   如果你的策略使用纯字符串信号（推荐），可以不使用本枚举。

2. 信号命名建议:
   - 开仓信号: LONG_<原因>, SHORT_<原因>, BUY_CALL_<原因>, SELL_PUT_<原因>
   - 平仓信号: CLOSE_LONG_<原因>, CLOSE_SHORT_<原因>
   - 示例: LONG_GOLDEN_CROSS, CLOSE_LONG_STOP_LOSS

3. get_valid_close_signals() 定义开仓信号与平仓信号的映射关系，
   用于限制某种开仓信号只能被特定的平仓信号平掉。

4. 如果不需要枚举约束，可以直接在 SignalService 中使用字符串常量。
   参考: src/strategy/domain/domain_service/signal_service.py
"""
from enum import Enum
from typing import Set


class SignalType(Enum):
    """
    信号类型枚举（模板）

    TODO: 根据策略需求定义信号类型，例如:

    # ========== 开仓信号 ==========
    LONG_GOLDEN_CROSS = "long_golden_cross"
    SHORT_DEATH_CROSS = "short_death_cross"

    # ========== 平仓信号 ==========
    CLOSE_LONG_STOP_LOSS = "close_long_stop_loss"
    CLOSE_LONG_TAKE_PROFIT = "close_long_take_profit"
    CLOSE_SHORT_STOP_LOSS = "close_short_stop_loss"
    CLOSE_SHORT_TAKE_PROFIT = "close_short_take_profit"
    """

    # 示例信号（请替换为你的策略信号）
    EXAMPLE_OPEN = "example_open"
    EXAMPLE_CLOSE = "example_close"

    @staticmethod
    def get_valid_close_signals(open_signal: "SignalType") -> Set["SignalType"]:
        """
        获取某开仓信号对应的有效平仓信号集合

        TODO: 定义开仓信号与平仓信号的映射关系，例如:
            mapping = {
                SignalType.LONG_GOLDEN_CROSS: {
                    SignalType.CLOSE_LONG_STOP_LOSS,
                    SignalType.CLOSE_LONG_TAKE_PROFIT,
                },
            }
            return mapping.get(open_signal, set())

        Args:
            open_signal: 开仓信号类型

        Returns:
            该开仓信号可用的平仓信号集合
        """
        mapping: dict[SignalType, Set[SignalType]] = {}
        return mapping.get(open_signal, set())

    def is_open_signal(self) -> bool:
        """判断是否为开仓信号"""
        return not self.value.startswith("close_")

    def is_close_signal(self) -> bool:
        """判断是否为平仓信号"""
        return self.value.startswith("close_")
