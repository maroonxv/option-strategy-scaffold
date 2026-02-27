"""
PositionSizingConfig - 仓位管理服务配置值对象

将 PositionSizingService 中散落的硬编码参数收拢为统一的不可变配置对象，
提升可配置性和可测试性。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PositionSizingConfig:
    """
    仓位管理服务配置

    所有字段均有合理默认值，可按需覆盖。
    """

    # ── 持仓限制 ──
    max_positions: int = 5              # 最大持仓数量
    global_daily_limit: int = 50        # 全局日开仓限制
    contract_daily_limit: int = 2       # 单合约日开仓限制

    # ── 保证金参数 ──
    margin_ratio: float = 0.12          # 保证金比例
    min_margin_ratio: float = 0.07      # 最低保证金比例
    margin_usage_limit: float = 0.6     # 保证金使用率上限

    # ── 订单限制 ──
    max_volume_per_order: int = 10      # 单笔最大手数
