"""
OptionSelectorConfig - 期权选择服务配置值对象

将 OptionSelectorService 中散落的硬编码参数收拢为统一的不可变配置对象，
提升可配置性和可测试性。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class OptionSelectorConfig:
    """
    期权选择服务配置

    所有字段均有合理默认值，可按需覆盖。
    """

    # ── 基础筛选 ──
    strike_level: int = 3               # 目标虚值档位
    min_bid_price: float = 10.0         # 最小买一价
    min_bid_volume: int = 10            # 最小买一量
    min_trading_days: int = 1           # 最小剩余交易日
    max_trading_days: int = 50          # 最大剩余交易日

    # ── 开仓前流动性检查 (check_liquidity) ──
    liquidity_min_volume: int = 100     # 当日最小成交量
    liquidity_min_bid_volume: int = 1   # 最小买一量
    liquidity_max_spread_ticks: int = 3 # 最大买卖价差跳数

    # ── 评分权重 (score_candidates) ──
    score_liquidity_weight: float = 0.4
    score_otm_weight: float = 0.3
    score_expiry_weight: float = 0.3

    # ── 流动性评分内部权重 (_calc_liquidity_score) ──
    liq_spread_weight: float = 0.6
    liq_volume_weight: float = 0.4

    # ── Delta 选择 ──
    delta_tolerance: float = 0.05

    # ── 垂直价差 ──
    default_spread_width: int = 1
