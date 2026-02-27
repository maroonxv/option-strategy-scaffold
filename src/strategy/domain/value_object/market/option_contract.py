"""
OptionContract - 期权合约值对象

定义期权合约的基本属性和类型。
"""
from dataclasses import dataclass
from typing import Literal


OptionType = Literal["call", "put"]


@dataclass
class OptionContract:
    """期权合约信息"""
    vt_symbol: str              # 合约代码
    underlying_symbol: str      # 标的代码
    option_type: OptionType     # 期权类型 (call/put)
    strike_price: float         # 行权价
    expiry_date: str            # 到期日
    diff1: float                # 虚值程度 (行权价与标的价格的偏离度)
    bid_price: float            # 买一价
    bid_volume: int             # 买一量
    ask_price: float            # 卖一价
    ask_volume: int             # 卖一量
    days_to_expiry: int         # 剩余交易日
