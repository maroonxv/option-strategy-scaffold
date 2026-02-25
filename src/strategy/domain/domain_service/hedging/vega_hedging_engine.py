"""
VegaHedgingEngine - Vega 对冲引擎

监控组合 Vega 敞口，当偏离目标超过容忍带时计算对冲手数并生成对冲指令。
与 Delta 对冲不同，Vega 对冲使用期权作为对冲工具，因此需要计算附带的 Delta、Gamma、Theta 影响。
"""
import math
from typing import List, Tuple

from ...value_object.hedging import VegaHedgingConfig, VegaHedgeResult
from ...value_object.order_instruction import OrderInstruction, Direction, Offset
from ...value_object.risk import PortfolioGreeks
from ...event.event_types import DomainEvent, VegaHedgeExecutedEvent


class VegaHedgingEngine:
    """Vega 对冲引擎"""

    def __init__(self, config: VegaHedgingConfig) -> None:
        self.config = config

    @classmethod
    def from_yaml_config(cls, config_dict: dict) -> "VegaHedgingEngine":
        """从 YAML 配置字典创建实例，缺失字段使用 VegaHedgingConfig 默认值"""
        defaults = VegaHedgingConfig()
        config = VegaHedgingConfig(
            target_vega=config_dict.get("target_vega", defaults.target_vega),
            hedging_band=config_dict.get("hedging_band", defaults.hedging_band),
            hedge_instrument_vt_symbol=config_dict.get("hedge_instrument_vt_symbol", defaults.hedge_instrument_vt_symbol),
            hedge_instrument_vega=config_dict.get("hedge_instrument_vega", defaults.hedge_instrument_vega),
            hedge_instrument_delta=config_dict.get("hedge_instrument_delta", defaults.hedge_instrument_delta),
            hedge_instrument_gamma=config_dict.get("hedge_instrument_gamma", defaults.hedge_instrument_gamma),
            hedge_instrument_theta=config_dict.get("hedge_instrument_theta", defaults.hedge_instrument_theta),
            hedge_instrument_multiplier=config_dict.get("hedge_instrument_multiplier", defaults.hedge_instrument_multiplier),
        )
        return cls(config)

    def check_and_hedge(
        self, portfolio_greeks: PortfolioGreeks, current_price: float
    ) -> Tuple[VegaHedgeResult, List[DomainEvent]]:
        """检查是否需要 Vega 对冲，返回对冲结果和事件"""
        cfg = self.config

        # 无效配置检查
        if cfg.hedge_instrument_multiplier <= 0:
            return VegaHedgeResult(
                should_hedge=False, rejected=True,
                reject_reason="无效配置: 合约乘数 <= 0",
            ), []
        if cfg.hedge_instrument_vega == 0:
            return VegaHedgeResult(
                should_hedge=False, rejected=True,
                reject_reason="对冲工具 Vega 为零",
            ), []
        if current_price <= 0:
            return VegaHedgeResult(
                should_hedge=False, rejected=True,
                reject_reason="当前价格 <= 0",
            ), []

        vega_diff = portfolio_greeks.total_vega - cfg.target_vega

        if abs(vega_diff) <= cfg.hedging_band:
            return VegaHedgeResult(should_hedge=False, reason="Vega 偏离在容忍带内"), []

        # 计算对冲手数
        denominator = cfg.hedge_instrument_vega * cfg.hedge_instrument_multiplier
        if denominator == 0:
            return VegaHedgeResult(should_hedge=False, reason="对冲工具有效 Vega 为零 (下溢)"), []
        raw_volume = (cfg.target_vega - portfolio_greeks.total_vega) / denominator
        if not math.isfinite(raw_volume):
            return VegaHedgeResult(should_hedge=False, reason="对冲手数计算溢出"), []
        hedge_volume = round(raw_volume)

        if hedge_volume == 0:
            return VegaHedgeResult(should_hedge=False, reason="对冲手数为零 (舍入后)"), []

        # 确定方向
        if hedge_volume > 0:
            direction = Direction.LONG
            direction_sign = 1
        else:
            direction = Direction.SHORT
            direction_sign = -1
            hedge_volume = abs(hedge_volume)

        # 计算附带 Greeks 影响
        delta_impact = hedge_volume * cfg.hedge_instrument_delta * cfg.hedge_instrument_multiplier * direction_sign
        gamma_impact = hedge_volume * cfg.hedge_instrument_gamma * cfg.hedge_instrument_multiplier * direction_sign
        theta_impact = hedge_volume * cfg.hedge_instrument_theta * cfg.hedge_instrument_multiplier * direction_sign

        instruction = OrderInstruction(
            vt_symbol=cfg.hedge_instrument_vt_symbol,
            direction=direction,
            offset=Offset.OPEN,
            volume=hedge_volume,
            price=current_price,
            signal="vega_hedge",
        )

        result = VegaHedgeResult(
            should_hedge=True,
            hedge_volume=hedge_volume,
            hedge_direction=direction,
            instruction=instruction,
            delta_impact=delta_impact,
            gamma_impact=gamma_impact,
            theta_impact=theta_impact,
            reason=f"Vega 偏离 {vega_diff:.4f} 超过容忍带 {cfg.hedging_band}",
        )

        portfolio_vega_after = portfolio_greeks.total_vega + (
            hedge_volume * cfg.hedge_instrument_vega * cfg.hedge_instrument_multiplier * direction_sign
        )

        event = VegaHedgeExecutedEvent(
            hedge_volume=hedge_volume,
            hedge_direction=direction.value,
            portfolio_vega_before=portfolio_greeks.total_vega,
            portfolio_vega_after=portfolio_vega_after,
            hedge_instrument=cfg.hedge_instrument_vt_symbol,
            delta_impact=delta_impact,
            gamma_impact=gamma_impact,
            theta_impact=theta_impact,
        )

        return result, [event]
