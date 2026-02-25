"""
VnpyQuoteGateway - 报价/做市网关

封装 vnpy MainEngine 的双边报价能力，用于做市策略。
"""
from typing import List, Optional, Any
from ...domain.value_object.quote_request import QuoteRequest
from ...domain.value_object.order_instruction import Offset
from .vnpy_gateway_adapter import VnpyGatewayAdapter
from vnpy.trader.object import QuoteRequest as VnQuoteRequest, CancelRequest
from vnpy.trader.constant import Offset as VnOffset


class VnpyQuoteGateway(VnpyGatewayAdapter):
    """
    报价/做市网关
    
    封装双边报价能力，包括：
    - 发送报价
    - 撤销报价
    - 报价查询
    """
    
    def send_quote(self, quote_request: QuoteRequest) -> str:
        """
        发送双边报价
        
        Args:
            quote_request: 报价请求对象
            
        Returns:
            vt_quoteid，如果失败则返回空字符串
        """
        if not self.main_engine:
            self._log("MainEngine 不可用，无法发送报价")
            return ""
        
        try:
            # 获取合约信息
            contract = self.main_engine.get_contract(quote_request.vt_symbol)
            if not contract:
                self._log(f"找不到合约: {quote_request.vt_symbol}")
                return ""
            
            # 转换开平标志
            offset_map = {
                Offset.OPEN: VnOffset.OPEN,
                Offset.CLOSE: VnOffset.CLOSE,
                Offset.CLOSETODAY: VnOffset.CLOSETODAY,
                Offset.CLOSEYESTERDAY: VnOffset.CLOSEYESTERDAY,
            }
            bid_offset = offset_map.get(quote_request.bid_offset, VnOffset.NONE)
            ask_offset = offset_map.get(quote_request.ask_offset, VnOffset.NONE)
            
            # 创建 vnpy 报价请求
            vn_req = VnQuoteRequest(
                symbol=contract.symbol,
                exchange=contract.exchange,
                bid_price=float(quote_request.bid_price),
                bid_volume=int(quote_request.bid_volume),
                ask_price=float(quote_request.ask_price),
                ask_volume=int(quote_request.ask_volume),
                bid_offset=bid_offset,
                ask_offset=ask_offset,
                reference=quote_request.reference
            )
            
            # 发送报价
            vt_quoteid = self.main_engine.send_quote(vn_req, contract.gateway_name)
            return vt_quoteid if vt_quoteid else ""
            
        except Exception as e:
            self._log(f"发送报价失败: {e}")
            return ""
    
    def cancel_quote(self, vt_quoteid: str) -> None:
        """
        撤销报价
        
        Args:
            vt_quoteid: 报价唯一标识
        """
        if not self.main_engine:
            self._log(f"MainEngine 不可用，无法撤销报价: {vt_quoteid}")
            return
        
        try:
            # 获取报价信息
            quote = self.main_engine.get_quote(vt_quoteid)
            if not quote:
                self._log(f"找不到报价: {vt_quoteid}")
                return
            
            # 创建撤销请求
            req = CancelRequest(
                orderid=quote.quoteid,
                symbol=quote.symbol,
                exchange=quote.exchange
            )
            
            # 撤销报价
            self.main_engine.cancel_quote(req, quote.gateway_name)
            
        except Exception as e:
            self._log(f"撤销报价失败: {vt_quoteid}, 错误: {e}")
    
    def get_quote(self, vt_quoteid: str) -> Optional[Any]:
        """
        获取指定报价
        
        Args:
            vt_quoteid: 报价唯一标识
            
        Returns:
            QuoteData 对象，如果不存在则返回 None
        """
        if not self.main_engine:
            self._log(f"MainEngine 不可用，无法查询报价: {vt_quoteid}")
            return None
        
        try:
            return self.main_engine.get_quote(vt_quoteid)
        except Exception as e:
            self._log(f"查询报价失败: {vt_quoteid}, 错误: {e}")
            return None
    
    def get_all_quotes(self) -> List[Any]:
        """
        获取所有报价
        
        Returns:
            所有报价的列表
        """
        if not self.main_engine:
            self._log("MainEngine 不可用，无法查询所有报价")
            return []
        
        try:
            return self.main_engine.get_all_quotes()
        except Exception as e:
            self._log(f"查询所有报价失败: {e}")
            return []
    
    def get_all_active_quotes(self) -> List[Any]:
        """
        获取所有活动报价
        
        活动报价指状态为 SUBMITTING、NOTTRADED 或 PARTTRADED 的报价。
        
        Returns:
            所有活动报价的列表
        """
        if not self.main_engine:
            self._log("MainEngine 不可用，无法查询活动报价")
            return []
        
        try:
            return self.main_engine.get_all_active_quotes()
        except Exception as e:
            self._log(f"查询活动报价失败: {e}")
            return []
    
    def get_quotes_by_symbol(self, vt_symbol: str) -> List[Any]:
        """
        获取指定合约的所有报价
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            该合约的所有报价列表
        """
        all_quotes = self.get_all_quotes()
        return [quote for quote in all_quotes if quote.vt_symbol == vt_symbol]
    
    def get_active_quotes_by_symbol(self, vt_symbol: str) -> List[Any]:
        """
        获取指定合约的活动报价
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            该合约的活动报价列表
        """
        active_quotes = self.get_all_active_quotes()
        return [quote for quote in active_quotes if quote.vt_symbol == vt_symbol]
