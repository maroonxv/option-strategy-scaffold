"""
Value Object Module

领域层值对象定义。

值对象列表:
- OrderInstruction: 交易指令
- AccountSnapshot: 账户快照
- PositionSnapshot: 持仓快照
- ContractParams: 合约交易参数
- QuoteRequest: 报价请求
- OptionContract: 期权合约信息
- GreeksInput / GreeksResult / IVResult: Greeks 计算相关
- RiskThresholds / RiskCheckResult / PortfolioGreeks / PositionGreeksEntry: 风控相关
- OrderExecutionConfig / ManagedOrder: 订单执行相关
- AdvancedOrderType / AdvancedOrderStatus / AdvancedOrderRequest / AdvancedOrder / ChildOrder / SliceEntry: 高级订单相关
- HedgingConfig / HedgeResult / GammaScalpConfig / ScalpResult: 对冲相关
- VolQuote / VolQueryResult / VolSmile / TermStructure / VolSurfaceSnapshot: 波动率曲面相关
"""

from .order_instruction import OrderInstruction, Direction, Offset, OrderType
from .account_snapshot import AccountSnapshot
from .position_snapshot import PositionSnapshot, PositionDirection
from .contract_params import ContractParams
from .quote_request import QuoteRequest
from .option_contract import OptionContract
from .greeks import GreeksInput, GreeksResult, IVResult
from .risk import RiskThresholds, RiskCheckResult, PortfolioGreeks, PositionGreeksEntry
from .order_execution import OrderExecutionConfig, ManagedOrder
from .advanced_order import (
    AdvancedOrderType, AdvancedOrderStatus,
    AdvancedOrderRequest, AdvancedOrder, ChildOrder, SliceEntry,
)
from .hedging import HedgingConfig, HedgeResult, GammaScalpConfig, ScalpResult
from .vol_surface import VolQuote, VolQueryResult, VolSmile, TermStructure, VolSurfaceSnapshot

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
]
