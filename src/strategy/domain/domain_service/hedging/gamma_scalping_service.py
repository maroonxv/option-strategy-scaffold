"""

GammaScalpingService - Gamma Scalping 服务


在持有正 Gamma 敞口时，当 Delta 偏离零超过阈值时生成再平衡指令。
"""

from typing import List, Tuple


from ...value_object.hedging import GammaScalpConfig, ScalpResult

from ...value_object.order_instruction import OrderInstruction, Direction, Offset

from ...value_object.risk import PortfolioGreeks

from ...event.event_types import DomainEvent, GammaScalpEvent



class GammaScalpingService:

    """Gamma Scalping 服务"""


    def __init__(self, config: GammaScalpConfig) -> None:
        self.config = config


    @classmethod

    def from_yaml_config(cls, config_dict: dict) -> "GammaScalpingEngine":

        """从 YAML 配置字典创建实例，缺失字段使用 GammaScalpConfig 默认值"""

        defaults = GammaScalpConfig()

        config = GammaScalpConfig(

            rebalance_threshold=config_dict.get("rebalance_threshold", defaults.rebalance_threshold),

            hedge_instrument_vt_symbol=config_dict.get("hedge_instrument_vt_symbol", defaults.hedge_instrument_vt_symbol),

            hedge_instrument_delta=config_dict.get("hedge_instrument_delta", defaults.hedge_instrument_delta),

            hedge_instrument_multiplier=config_dict.get("hedge_instrument_multiplier", defaults.hedge_instrument_multiplier),

        )

        return cls(config)


    def check_and_rebalance(

        self, portfolio_greeks: PortfolioGreeks, current_price: float

    ) -> Tuple[ScalpResult, List[DomainEvent]]:

        """检查是否需要 Gamma Scalping 再平衡"""
        cfg = self.config


        # Gamma <= 0 时拒绝

        if portfolio_greeks.total_gamma <= 0:

            return ScalpResult(

                should_rebalance=False, rejected=True,

                reject_reason="组合 Gamma 非正",

            ), []


        # 无效配置检查

        if cfg.hedge_instrument_multiplier <= 0:

            return ScalpResult(

                should_rebalance=False, rejected=True,

                reject_reason="无效配置: 合约乘数 <= 0",

            ), []

        if cfg.hedge_instrument_delta == 0:

            return ScalpResult(

                should_rebalance=False, rejected=True,

                reject_reason="对冲工具 Delta 为零",

            ), []

        if current_price <= 0:

            return ScalpResult(

                should_rebalance=False, rejected=True,

                reject_reason="当前价格 <= 0",

            ), []


        portfolio_delta = portfolio_greeks.total_delta


        if abs(portfolio_delta) <= cfg.rebalance_threshold:

            return ScalpResult(should_rebalance=False), []


        # 计算再平衡手数使 delta 归零

        raw_volume = -portfolio_delta / (cfg.hedge_instrument_delta * cfg.hedge_instrument_multiplier)

        rebalance_volume = round(raw_volume)


        if rebalance_volume == 0:

            return ScalpResult(should_rebalance=False), []


        if rebalance_volume > 0:

            direction = Direction.LONG

        else:

            direction = Direction.SHORT

            rebalance_volume = abs(rebalance_volume)


        instruction = OrderInstruction(

            vt_symbol=cfg.hedge_instrument_vt_symbol,
            direction=direction,

            offset=Offset.OPEN,

            volume=rebalance_volume,
            price=current_price,
            signal="gamma_scalp",

        )


        result = ScalpResult(

            should_rebalance=True,

            rebalance_volume=rebalance_volume,

            rebalance_direction=direction,
            instruction=instruction,

        )


        event = GammaScalpEvent(

            rebalance_volume=rebalance_volume,

            rebalance_direction=direction.value,

            portfolio_delta_before=portfolio_delta,

            portfolio_gamma=portfolio_greeks.total_gamma,

            hedge_instrument=cfg.hedge_instrument_vt_symbol,

        )


        return result, [event]

