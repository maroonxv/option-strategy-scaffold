"""

DeltaHedgingService - Delta 对冲服务


监控组合 Delta 敞口，当偏离目标超过 Hedging Band 时计算对冲手数并生成对冲指令。
"""

from typing import List, Tuple


from ...value_object.hedging import HedgingConfig, HedgeResult

from ...value_object.order_instruction import OrderInstruction, Direction, Offset

from ...value_object.risk import PortfolioGreeks

from ...event.event_types import DomainEvent, HedgeExecutedEvent



class DeltaHedgingService:

    """Delta 对冲服务"""


    def __init__(self, config: HedgingConfig) -> None:
        self.config = config


    @classmethod

    def from_yaml_config(cls, config_dict: dict) -> "DeltaHedgingEngine":

        """从 YAML 配置字典创建实例，缺失字段使用 HedgingConfig 默认值"""

        defaults = HedgingConfig()

        config = HedgingConfig(

            target_delta=config_dict.get("target_delta", defaults.target_delta),

            hedging_band=config_dict.get("hedging_band", defaults.hedging_band),

            hedge_instrument_vt_symbol=config_dict.get("hedge_instrument_vt_symbol", defaults.hedge_instrument_vt_symbol),

            hedge_instrument_delta=config_dict.get("hedge_instrument_delta", defaults.hedge_instrument_delta),

            hedge_instrument_multiplier=config_dict.get("hedge_instrument_multiplier", defaults.hedge_instrument_multiplier),

        )

        return cls(config)


    def check_and_hedge(

        self, portfolio_greeks: PortfolioGreeks, current_price: float

    ) -> Tuple[HedgeResult, List[DomainEvent]]:

        """检查是否需要对冲，返回对冲结果和事件"""
        cfg = self.config


        # 无效配置检查

        if cfg.hedge_instrument_multiplier <= 0:

            return HedgeResult(should_hedge=False, reason="无效配置: 合约乘数 <= 0"), []

        if cfg.hedge_instrument_delta == 0:

            return HedgeResult(should_hedge=False, reason="对冲工具 Delta 为零"), []

        if current_price <= 0:

            return HedgeResult(should_hedge=False, reason="当前价格 <= 0"), []


        delta_diff = portfolio_greeks.total_delta - cfg.target_delta


        if abs(delta_diff) <= cfg.hedging_band:

            return HedgeResult(should_hedge=False, reason="Delta 偏离在容忍带内"), []


        # 计算对冲手数

        raw_volume = (cfg.target_delta - portfolio_greeks.total_delta) / (

            cfg.hedge_instrument_delta * cfg.hedge_instrument_multiplier

        )

        hedge_volume = round(raw_volume)


        if hedge_volume == 0:

            return HedgeResult(should_hedge=False, reason="对冲手数为零 (舍入后)"), []


        # 确定方向

        if hedge_volume > 0:

            direction = Direction.LONG

        else:

            direction = Direction.SHORT

            hedge_volume = abs(hedge_volume)


        instruction = OrderInstruction(

            vt_symbol=cfg.hedge_instrument_vt_symbol,
            direction=direction,

            offset=Offset.OPEN,

            volume=hedge_volume,

            price=current_price,
            signal="delta_hedge",

        )


        result = HedgeResult(

            should_hedge=True,

            hedge_volume=hedge_volume,
            hedge_direction=direction,
            instruction=instruction,

            reason=f"Delta 偏离 {delta_diff:.4f} 超过容忍带 {cfg.hedging_band}",

        )


        expected_delta_after = portfolio_greeks.total_delta + (

            hedge_volume * cfg.hedge_instrument_delta * cfg.hedge_instrument_multiplier

            * (1 if direction == Direction.LONG else -1)

        )


        event = HedgeExecutedEvent(

            hedge_volume=hedge_volume,

            hedge_direction=direction.value,

            portfolio_delta_before=portfolio_greeks.total_delta,

            portfolio_delta_after=expected_delta_after,

            hedge_instrument=cfg.hedge_instrument_vt_symbol,

        )


        return result, [event]

