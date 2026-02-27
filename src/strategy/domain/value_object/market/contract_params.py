"""
ContractParams 值对象 - 合约交易参数

封装 vnpy ContractData 中与交易相关的参数，用于下单前的校验。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ContractParams:
    """
    合约交易参数值对象
    
    封装 vnpy ContractData 中与交易相关的参数，
    用于策略层进行下单前的参数校验和价格计算。
    
    Attributes:
        vt_symbol: 合约代码 (VnPy 格式，如 "rb2501.SHFE")
        size: 合约乘数 (每手对应的标的数量)
        pricetick: 最小价格变动单位
        min_volume: 最小下单量 (通常为 1)
        max_volume: 最大下单量 (None 表示无限制)
        stop_supported: 是否支持止损单
        net_position: 是否使用净持仓模式
    """
    vt_symbol: str
    size: float
    pricetick: float
    min_volume: float = 1.0
    max_volume: Optional[float] = None
    stop_supported: bool = False
    net_position: bool = False
    
    def round_price(self, price: float) -> float:
        """
        将价格调整为符合最小变动单位的值
        
        Args:
            price: 原始价格
            
        Returns:
            调整后的价格
        """
        if self.pricetick <= 0:
            return price
        return round(price / self.pricetick) * self.pricetick
    
    def is_valid_volume(self, volume: float) -> bool:
        """
        检查下单量是否有效
        
        Args:
            volume: 下单量
            
        Returns:
            是否有效
        """
        if volume < self.min_volume:
            return False
        if self.max_volume is not None and volume > self.max_volume:
            return False
        return True
    
    def __repr__(self) -> str:
        max_vol_str = str(self.max_volume) if self.max_volume else "∞"
        return (
            f"ContractParams({self.vt_symbol} "
            f"size={self.size} tick={self.pricetick} "
            f"vol=[{self.min_volume}, {max_vol_str}])"
        )
