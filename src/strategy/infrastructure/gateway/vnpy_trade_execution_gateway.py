"""
VnpyTradeExecutionGateway - 交易执行网关

封装 vnpy 的交易执行能力，包括下单、撤单、开平转换等。
"""
from typing import Any, List, Optional
from ...domain.value_object.order_instruction import OrderInstruction, Direction, Offset, OrderType
from .vnpy_gateway_adapter import VnpyGatewayAdapter


class VnpyTradeExecutionGateway(VnpyGatewayAdapter):
    """
    交易执行网关
    
    封装交易执行能力，包括：
    - 发送订单（支持多种订单类型）
    - 撤销订单
    - 开平转换（自动处理上期所/能源中心的平今平昨）
    """
    
    def __init__(self, strategy_context: Any):
        """
        初始化交易执行网关
        
        Args:
            strategy_context: VnPy 策略实例
        """
        super().__init__(strategy_context)
    
    def send_order(self, instruction: OrderInstruction) -> List[str]:
        """
        发送订单
        
        VnPy 策略模板提供了 buy/sell/short/cover 方法。
        支持 LIMIT、MARKET、FAK、FOK 订单类型。
        
        Args:
            instruction: 交易指令
            
        Returns:
            订单ID列表
        """
        if hasattr(self.context, "paper_trading") and self.context.paper_trading:
            self._log(f"[PAPER] 模拟下单: {instruction}")
            return ["PAPER_ORDER"]

        vt_orderids = []
        
        # 提取参数
        vt_symbol = instruction.vt_symbol
        try:
            price = float(instruction.price)
        except Exception:
            price = instruction.price
        try:
            volume = int(instruction.volume)
        except Exception:
            volume = instruction.volume
        direction = instruction.direction
        offset = instruction.offset
        order_type = getattr(instruction, 'order_type', OrderType.LIMIT)
        
        # 根据指令调用对应方法
        # 注意: self.context 是策略实例
        method_name = None
        if direction == Direction.LONG:
            if offset == Offset.OPEN:
                method_name = "buy"
            elif offset in (Offset.CLOSE, Offset.CLOSETODAY, Offset.CLOSEYESTERDAY):
                method_name = "cover"
        elif direction == Direction.SHORT:
            if offset == Offset.OPEN:
                method_name = "short"
            elif offset in (Offset.CLOSE, Offset.CLOSETODAY, Offset.CLOSEYESTERDAY):
                method_name = "sell"

        if not method_name:
            self._log(f"下单失败：无法映射指令到下单方法: {instruction}")
            return []

        if not hasattr(self.context, method_name):
            self._log(f"下单失败：策略缺少方法 {method_name}()，指令: {instruction}")
            return []

        try:
            # 检查是否支持订单类型参数
            # vnpy 策略模板的 buy/sell/short/cover 方法签名:
            # def buy(self, vt_symbol, price, volume, lock=False, net=False)
            # 不直接支持 order_type，需要通过 send_order 方法
            if order_type != OrderType.LIMIT and self.main_engine:
                # 使用 MainEngine 直接下单以支持不同订单类型
                vt_orderids = self._send_order_via_engine(instruction)
            else:
                # 使用策略模板方法下单（默认限价单）
                vt_orderids = getattr(self.context, method_name)(vt_symbol, price, volume)
        except Exception as e:
            self._log(f"下单异常：{method_name}({vt_symbol}, {price}, {volume}) 失败，指令: {instruction}, 错误: {e}")
            return []
        
        # VnPy 的下单函数返回的是 list[vt_orderid] 或 str(vt_orderid)
        # 这里统一处理为 list
        if isinstance(vt_orderids, str):
            return [vt_orderids]
        vt_orderids = vt_orderids or []
        if not vt_orderids:
            self._log(f"下单返回空订单号：{method_name}() 未产生委托，指令: {instruction}")
        return vt_orderids
    
    def _send_order_via_engine(self, instruction: OrderInstruction) -> List[str]:
        """
        通过 MainEngine 直接发送订单，支持不同订单类型
        
        Args:
            instruction: 交易指令
            
        Returns:
            订单ID列表
        """
        if not self.main_engine:
            self._log("MainEngine 不可用，无法发送订单")
            return []
        
        try:
            from vnpy.trader.object import OrderRequest
            from vnpy.trader.constant import Direction as VnDirection, Offset as VnOffset, OrderType as VnOrderType
            
            # 获取合约信息
            contract = self.main_engine.get_contract(instruction.vt_symbol)
            if not contract:
                self._log(f"找不到合约: {instruction.vt_symbol}")
                return []
            
            # 转换方向
            vn_direction = VnDirection.LONG if instruction.direction == Direction.LONG else VnDirection.SHORT
            
            # 转换开平
            offset_map = {
                Offset.OPEN: VnOffset.OPEN,
                Offset.CLOSE: VnOffset.CLOSE,
                Offset.CLOSETODAY: VnOffset.CLOSETODAY,
                Offset.CLOSEYESTERDAY: VnOffset.CLOSEYESTERDAY,
            }
            vn_offset = offset_map.get(instruction.offset, VnOffset.NONE)
            
            # 转换订单类型
            order_type = getattr(instruction, 'order_type', OrderType.LIMIT)
            order_type_map = {
                OrderType.LIMIT: VnOrderType.LIMIT,
                OrderType.MARKET: VnOrderType.MARKET,
                OrderType.FAK: VnOrderType.FAK,
                OrderType.FOK: VnOrderType.FOK,
            }
            vn_order_type = order_type_map.get(order_type, VnOrderType.LIMIT)
            
            # 创建订单请求
            req = OrderRequest(
                symbol=contract.symbol,
                exchange=contract.exchange,
                direction=vn_direction,
                type=vn_order_type,
                volume=float(instruction.volume),
                price=float(instruction.price),
                offset=vn_offset,
                reference=instruction.signal or ""
            )
            
            # 发送订单
            vt_orderid = self.main_engine.send_order(req, contract.gateway_name)
            return [vt_orderid] if vt_orderid else []
            
        except Exception as e:
            self._log(f"通过 MainEngine 下单失败: {e}")
            return []

    def cancel_order(self, vt_orderid: str) -> None:
        """
        撤销订单
        
        Args:
            vt_orderid: 订单唯一标识
        """
        if hasattr(self.context, "cancel_order"):
            self.context.cancel_order(vt_orderid)

    def cancel_all_orders(self) -> None:
        """撤销所有订单"""
        if hasattr(self.context, "cancel_all"):
            self.context.cancel_all()
    
    def convert_order_request(
        self, 
        order_request: Any, 
        lock: bool = False, 
        net: bool = False
    ) -> List[Any]:
        """
        转换订单请求（开平转换）
        
        对于上期所和能源中心的合约，平仓时需要区分平今和平昨。
        此方法会根据当前持仓自动拆分订单。
        
        Args:
            order_request: vnpy OrderRequest 对象
            lock: 是否使用锁仓模式
            net: 是否使用净仓模式
            
        Returns:
            转换后的订单请求列表
        """
        if not self.main_engine:
            self._log("MainEngine 不可用，返回原始订单请求")
            return [order_request]
        
        try:
            # 获取 gateway_name
            gateway_name = self._get_gateway_name()
            if not gateway_name:
                self._log("无法获取 gateway_name，返回原始订单请求")
                return [order_request]
            
            # 调用 MainEngine 的 convert_order_request 方法
            converted = self.main_engine.convert_order_request(
                order_request, 
                gateway_name, 
                lock, 
                net
            )
            return converted if converted else [order_request]
            
        except Exception as e:
            self._log(f"开平转换失败: {e}，返回原始订单请求")
            return [order_request]
    
    def get_offset_converter(self) -> Optional[Any]:
        """
        获取开平转换器
        
        Returns:
            OffsetConverter 对象，如果不可用则返回 None
        """
        if not self.main_engine:
            return None
        
        try:
            gateway_name = self._get_gateway_name()
            if gateway_name:
                return self.main_engine.get_converter(gateway_name)
        except Exception as e:
            self._log(f"获取开平转换器失败: {e}")
        
        return None
    
    def _get_gateway_name(self) -> Optional[str]:
        """获取当前使用的 gateway 名称"""
        # 尝试从 main_engine 获取
        if self.main_engine:
            gateway_names = self.main_engine.get_all_gateway_names()
            if gateway_names:
                return gateway_names[0]
        
        # 尝试从 context 获取
        if hasattr(self.context, "gateway_name"):
            return self.context.gateway_name
        
        return None
