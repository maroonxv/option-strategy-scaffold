"""
FutureSelectorConfig - 期货选择器配置值对象

将 BaseFutureSelector 方法签名中的硬编码参数提取为统一的不可变配置对象，
提升可配置性和可测试性。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FutureSelectorConfig:
    """
    期货选择器配置

    所有字段均有合理默认值，与 BaseFutureSelector 原默认参数一致。
    """

    # ── 主力合约选择参数 ──
    volume_weight: float = 0.6    # 成交量权重
    oi_weight: float = 0.4        # 持仓量权重

    # ── 移仓换月参数 ──
    rollover_days: int = 5        # 移仓阈值天数
