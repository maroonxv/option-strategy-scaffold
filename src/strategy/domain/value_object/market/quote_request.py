"""
QuoteRequest 值对象 - 报价请求

用于做市策略发送双边报价的请求对象。
"""
from dataclasses import dataclass
from src.strategy.domain.value_object.trading.order_instruction import Offset


@dataclass(frozen=True)
class QuoteRequest:
    """
    报价请求值对象
    
    用于做市策略发送双边报价。报价同时包含买入和卖出两个方向的价格和数量。
    
    Attributes:
        vt_symbol: 合约代码 (VnPy 格式，如 "rb2501.SHFE")
        bid_price: 买入价格 (做市商愿意买入的价格)
        bid_volume: 买入数量
        ask_price: 卖出价格 (做市商愿意卖出的价格)
        ask_volume: 卖出数量
        bid_offset: 买入开平标志 (默认 NONE，由系统自动处理)
        ask_offset: 卖出开平标志 (默认 NONE，由系统自动处理)
        reference: 报价来源标识 (可选，用于追踪)
    """
    vt_symbol: str
    bid_price: float
    bid_volume: int
    ask_price: float
    ask_volume: int
    bid_offset: Offset = Offset.OPEN
    ask_offset: Offset = Offset.OPEN
    reference: str = ""
    
    @property
    def spread(self) -> float:
        """买卖价差"""
        return self.ask_price - self.bid_price
    
    @property
    def mid_price(self) -> float:
        """中间价"""
        return (self.bid_price + self.ask_price) / 2
    
    def __repr__(self) -> str:
        return (
            f"QuoteRequest({self.vt_symbol} "
            f"bid={self.bid_price:.2f}x{self.bid_volume} "
            f"ask={self.ask_price:.2f}x{self.ask_volume})"
        )
