"""
Value Object Module

领域层值对象定义。

子模块分类:
- market/: 市场数据相关 (账户快照、持仓快照、合约参数、期权合约、报价请求)
- trading/: 交易相关 (交易指令、订单执行、高级订单)
- pricing/: 定价相关 (Greeks 计算、期权定价、波动率曲面)
- risk/: 风控相关 (风控阈值、对冲、仓位计算)
- combination/: 组合策略相关 (组合类型、验证规则)
- selection/: 选择服务相关 (行情数据、移仓建议、评分)
- signal/: 信号相关 (信号类型枚举)
- config/: 配置相关 (期货选择配置、仓位配置、定价引擎配置)
"""

from .trading.order_instruction import OrderInstruction, Direction, Offset, OrderType
from .market.account_snapshot import AccountSnapshot
from .market.position_snapshot import PositionSnapshot, PositionDirection
from .market.contract_params import ContractParams
from .market.quote_request import QuoteRequest
from .market.option_contract import OptionContract
from .pricing.greeks import GreeksInput, GreeksResult, IVResult
from .risk.risk import RiskThresholds, RiskCheckResult, PortfolioGreeks, PositionGreeksEntry
from .trading.order_execution import OrderExecutionConfig, ManagedOrder
from .trading.advanced_order import (
    AdvancedOrderType, AdvancedOrderStatus,
    AdvancedOrderRequest, AdvancedOrder, ChildOrder, SliceEntry,
)
from .risk.hedging import HedgingConfig, HedgeResult, GammaScalpConfig, ScalpResult
from .pricing.vol_surface import VolQuote, VolQueryResult, VolSmile, TermStructure, VolSurfaceSnapshot
from .pricing.pricing import ExerciseStyle, PricingModel, PricingInput, PricingResult
from .risk.sizing import SizingResult
from .selection.selection import MarketData, RolloverRecommendation, CombinationSelectionResult, SelectionScore

__all__ = [
    # 交易指令相关
    "OrderInstruction",
    "Direction",
    "Offset",
    "OrderType",
    # 账户/持仓快照
    "AccountSnapshot",
    "PositionSnapshot",
    "PositionDirection",
    # 合约相关
    "ContractParams",
    "OptionContract",
    # 报价相关
    "QuoteRequest",
    # Greeks 相关
    "GreeksInput",
    "GreeksResult",
    "IVResult",
    # 风控相关
    "RiskThresholds",
    "RiskCheckResult",
    "PortfolioGreeks",
    "PositionGreeksEntry",
    # 订单执行相关
    "OrderExecutionConfig",
    "ManagedOrder",
    # 高级订单相关
    "AdvancedOrderType",
    "AdvancedOrderStatus",
    "AdvancedOrderRequest",
    "AdvancedOrder",
    "ChildOrder",
    "SliceEntry",
    # 对冲相关
    "HedgingConfig",
    "HedgeResult",
    "GammaScalpConfig",
    "ScalpResult",
    # 波动率曲面相关
    "VolQuote",
    "VolQueryResult",
    "VolSmile",
    "TermStructure",
    "VolSurfaceSnapshot",
    # 期权定价相关
    "ExerciseStyle",
    "PricingModel",
    "PricingInput",
    "PricingResult",
    # 仓位计算相关
    "SizingResult",
    # 选择服务相关
    "MarketData",
    "RolloverRecommendation",
    "CombinationSelectionResult",
    "SelectionScore",
]
