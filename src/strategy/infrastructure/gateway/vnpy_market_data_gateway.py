"""
VnpyMarketDataGateway - 行情/合约网关

封装 vnpy MainEngine 的行情订阅、合约查询和历史数据查询能力。
"""
from typing import List, Optional, Any
from datetime import datetime
from vnpy.trader.object import SubscribeRequest
from ...domain.value_object.contract_params import ContractParams
from .vnpy_gateway_adapter import VnpyGatewayAdapter


class VnpyMarketDataGateway(VnpyGatewayAdapter):
    """
    行情/合约网关
    
    封装行情和合约相关能力，包括：
    - 行情订阅/取消订阅
    - Tick 数据查询
    - 合约信息查询
    - 合约筛选（按产品类型、交易所）
    - 历史数据查询
    """

    def _try_add_bar_recording(self, vt_symbol: str) -> None:
        if not self.main_engine or not hasattr(self.main_engine, "get_engine"):
            return

        from vnpy_datarecorder import APP_NAME

        try:
            recorder_engine = self.main_engine.get_engine(APP_NAME)
            if recorder_engine and hasattr(recorder_engine, "add_bar_recording"):
                recorder_engine.add_bar_recording(vt_symbol)
        except Exception:
            return
    
    def subscribe(self, vt_symbol: str) -> bool:
        """订阅行情，返回是否成功"""
        # 回测模式兼容: 如果 main_engine 不存在，视为回测，跳过订阅
        if not self.main_engine:
            if hasattr(self.context, "backtesting") and self.context.backtesting:
                 # 回测模式下，只更新 context 的 vt_symbols 列表
                if hasattr(self.context, "vt_symbols") and isinstance(self.context.vt_symbols, list):
                    if vt_symbol not in self.context.vt_symbols:
                        self.context.vt_symbols.append(vt_symbol)
                return True

            self._log(f"订阅失败：主引擎不可用 ({vt_symbol})")
            return False

        contract = self.main_engine.get_contract(vt_symbol)
        if not contract:
            self._log(f"订阅失败：找不到合约 ({vt_symbol})")
            return False

        # 1. 向 MainEngine 发送订阅请求
        req = SubscribeRequest(
            symbol=contract.symbol,
            exchange=contract.exchange
        )
        self.main_engine.subscribe(req, contract.gateway_name)
        self._try_add_bar_recording(vt_symbol)
        
        # 2. 注册策略到 StrategyEngine 的映射中，以便接收推送

        if hasattr(self.context, "strategy_engine"):
            strategy_engine = self.context.strategy_engine
            
            # 更新 symbol_strategy_map (确保策略能收到 Tick 推送)
            if hasattr(strategy_engine, "symbol_strategy_map"):
                strategies = strategy_engine.symbol_strategy_map[vt_symbol]
                if self.context not in strategies:
                    strategies.append(self.context)
                    self._log(f"已注册策略接收 {vt_symbol} 的 Tick 推送")
            
            # 3. 更新策略内部的 vt_symbols 列表 (用于 load_bars 等)
            if hasattr(self.context, "vt_symbols") and isinstance(self.context.vt_symbols, list):
                if vt_symbol not in self.context.vt_symbols:
                    self.context.vt_symbols.append(vt_symbol)
        
        self._log(f"已成功订阅 {vt_symbol}")
        return True

    def get_tick(self, vt_symbol: str) -> Optional[Any]:
        if self.main_engine:
            return self.main_engine.get_tick(vt_symbol)
            
        # 回测模式兼容: 构造模拟 Tick
        if hasattr(self.context, "backtesting") and self.context.backtesting:
             # 尝试从策略的应用服务中获取最新 Bar 数据
            instrument = None
            # 优先直接从 context 获取 target_aggregate (pragmatic DDD)
            agg = getattr(self.context, "target_aggregate", None)
            if agg:
                instrument = agg.get_instrument(vt_symbol)
            elif hasattr(self.context, "app_engine") and self.context.app_engine:
                instrument = self.context.app_engine.instrument_manager.get_instrument(vt_symbol)
            elif hasattr(self.context, "app_service") and self.context.app_service:
                agg2 = getattr(self.context.app_service, "target_aggregate", None)
                if agg2:
                    instrument = agg2.get_instrument(vt_symbol)
            
            # 如果从 aggregate 中获取不到 (例如期权合约尚未加入 aggregate)，尝试从策略引擎缓存的 last_bars 获取
            last_bar = None
            if instrument and hasattr(instrument, "bars"):
                bars = getattr(instrument, "bars", None)
                if isinstance(bars, list) and bars:
                    row = bars[-1] if isinstance(bars[-1], dict) else {}
                    class MockBar:
                        close_price = float(row.get("close", 0.0) or 0.0)
                        volume = int(row.get("volume", 0) or 0)
                    last_bar = MockBar()
                else:
                    empty = getattr(bars, "empty", True)
                    if not empty:
                        row = bars.iloc[-1]
                        class MockBar:
                            close_price = float(row["close"])
                            volume = int(row["volume"])
                        last_bar = MockBar()
            elif hasattr(self.context, "last_bars") and vt_symbol in getattr(self.context, "last_bars", {}):
                # 使用策略缓存的最新 BarData (pragmatic DDD: context 直接持有 last_bars)
                bar = self.context.last_bars[vt_symbol]
                class MockBar:
                    close_price = bar.close_price
                    volume = bar.volume
                last_bar = MockBar()

            if last_bar:
                # 使用最新的 Bar 构造 Tick
                # 这里的关键是 bid_price 和 bid_volume，用于 OptionSelectorService 的流动性检查
                last_close = last_bar.close_price
                last_volume = last_bar.volume

                # 简单的 Tick 模拟
                from vnpy.trader.object import TickData
                from vnpy.trader.constant import Exchange
                from datetime import datetime

                try:
                    symbol_part, exchange_str = vt_symbol.split(".")
                    exchange = Exchange(exchange_str)
                except ValueError:
                    symbol_part = vt_symbol
                    exchange = None

                return TickData(
                    symbol=symbol_part,
                    exchange=exchange,
                    datetime=datetime.now(), # 回测中时间可能不准，但 check_liquidity 不看时间
                    name=vt_symbol,
                    volume=last_volume,
                    turnover=0,
                    open_interest=0,
                    last_price=last_close,
                    last_volume=last_volume,
                    limit_up=0,
                    limit_down=0,
                    open_price=0,
                    high_price=0,
                    low_price=0,
                    pre_close=0,
                    bid_price_1=last_close,
                    bid_volume_1=max(last_volume, 1000), # 确保有足够的流动性通过过滤
                    ask_price_1=last_close,
                    ask_volume_1=max(last_volume, 1000),
                    gateway_name="BACKTESTING"
                )
        return None

    def get_contract(self, vt_symbol: str) -> Optional[Any]:
        if self.main_engine:
            return self.main_engine.get_contract(vt_symbol)
            
        # 回测模式兼容: 尝试从 strategy_engine 获取 (通过 ContractRegistry.inject_into_engine 注入)
        if hasattr(self.context, "strategy_engine"):
            engine = self.context.strategy_engine
            if hasattr(engine, "get_contract"):
                return engine.get_contract(vt_symbol)
                
        return None

    def get_all_contracts(self) -> List[Any]:
        if self.main_engine:
            return self.main_engine.get_all_contracts()
            
        # 回测模式兼容
        if hasattr(self.context, "strategy_engine"):
            engine = self.context.strategy_engine
            if hasattr(engine, "get_all_contracts"):
                return engine.get_all_contracts()
                
        return []

    def unsubscribe(self, vt_symbol: str) -> bool:
        """
        取消行情订阅
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            是否成功取消订阅
        """
        # 回测模式兼容
        if not self.main_engine:
            if hasattr(self.context, "backtesting") and self.context.backtesting:
                # 回测模式下，只从 vt_symbols 列表移除
                if hasattr(self.context, "vt_symbols") and isinstance(self.context.vt_symbols, list):
                    if vt_symbol in self.context.vt_symbols:
                        self.context.vt_symbols.remove(vt_symbol)
                        return True
                return False
            
            self._log(f"取消订阅失败：主引擎不可用 ({vt_symbol})")
            return False
        
        # 1. 从 symbol_strategy_map 移除映射
        if hasattr(self.context, "strategy_engine"):
            strategy_engine = self.context.strategy_engine
            
            if hasattr(strategy_engine, "symbol_strategy_map"):
                strategies = strategy_engine.symbol_strategy_map.get(vt_symbol, [])
                if self.context in strategies:
                    strategies.remove(self.context)
                    self._log(f"已从 {vt_symbol} 的 Tick 推送中移除策略")
        
        # 2. 从策略的 vt_symbols 列表移除
        if hasattr(self.context, "vt_symbols") and isinstance(self.context.vt_symbols, list):
            if vt_symbol in self.context.vt_symbols:
                self.context.vt_symbols.remove(vt_symbol)
        
        self._log(f"已取消订阅 {vt_symbol}")
        return True
    
    def get_contracts_by_product(self, product: Any) -> List[Any]:
        """
        按产品类型筛选合约
        
        Args:
            product: 产品类型 (vnpy Product 枚举: FUTURES, OPTION, SPREAD 等)
            
        Returns:
            符合条件的合约列表
        """
        all_contracts = self.get_all_contracts()
        if not all_contracts:
            return []
        
        # 获取 product 的值用于比较
        product_value = getattr(product, "value", product) if product else None
        
        result = []
        for contract in all_contracts:
            contract_product = getattr(contract, "product", None)
            if contract_product:
                contract_product_value = getattr(contract_product, "value", contract_product)
                if contract_product_value == product_value or contract_product == product:
                    result.append(contract)
        
        return result
    
    def get_contracts_by_exchange(self, exchange: Any) -> List[Any]:
        """
        按交易所筛选合约
        
        Args:
            exchange: 交易所 (vnpy Exchange 枚举: SHFE, DCE, CZCE, CFFEX, INE, GFEX 等)
            
        Returns:
            符合条件的合约列表
        """
        all_contracts = self.get_all_contracts()
        if not all_contracts:
            return []
        
        # 获取 exchange 的值用于比较
        exchange_value = getattr(exchange, "value", exchange) if exchange else None
        
        result = []
        for contract in all_contracts:
            contract_exchange = getattr(contract, "exchange", None)
            if contract_exchange:
                contract_exchange_value = getattr(contract_exchange, "value", contract_exchange)
                if contract_exchange_value == exchange_value or contract_exchange == exchange:
                    result.append(contract)
        
        return result
    
    def get_contract_trading_params(self, vt_symbol: str) -> Optional[ContractParams]:
        """
        获取合约交易参数
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            ContractParams 对象，包含合约乘数、最小变动价位、下单量限制等
        """
        contract = self.get_contract(vt_symbol)
        if not contract:
            return None
        
        return ContractParams(
            vt_symbol=vt_symbol,
            size=float(getattr(contract, "size", 1.0) or 1.0),
            pricetick=float(getattr(contract, "pricetick", 0.01) or 0.01),
            min_volume=float(getattr(contract, "min_volume", 1.0) or 1.0),
            max_volume=getattr(contract, "max_volume", None),
            stop_supported=bool(getattr(contract, "stop_supported", False)),
            net_position=bool(getattr(contract, "net_position", False))
        )
    
    def query_history(
        self, 
        vt_symbol: str, 
        interval: Any, 
        start: datetime, 
        end: Optional[datetime] = None
    ) -> List[Any]:
        """
        查询历史K线数据
        
        Args:
            vt_symbol: 合约代码
            interval: K线周期 (vnpy Interval 枚举)
            start: 开始时间
            end: 结束时间 (可选，默认为当前时间)
            
        Returns:
            BarData 列表
        """
        if not self.main_engine:
            self._log(f"MainEngine 不可用，无法查询历史数据: {vt_symbol}")
            return []
        
        from vnpy.trader.object import HistoryRequest

        try:
            # 获取合约信息
            contract = self.get_contract(vt_symbol)
            if not contract:
                self._log(f"找不到合约: {vt_symbol}")
                return []
            
            # 检查合约是否支持历史数据查询
            if not getattr(contract, "history_data", False):
                self._log(f"合约 {vt_symbol} 不支持历史数据查询")
                return []
            
            # 创建历史数据请求
            req = HistoryRequest(
                symbol=contract.symbol,
                exchange=contract.exchange,
                start=start,
                end=end or datetime.now(),
                interval=interval
            )
            
            # 查询历史数据
            bars = self.main_engine.query_history(req, contract.gateway_name)
            return bars if bars else []
            
        except Exception as e:
            self._log(f"查询历史数据失败: {vt_symbol}, 错误: {e}")
            return []
    
    def get_all_ticks(self) -> List[Any]:
        """
        获取所有已订阅合约的最新 Tick
        
        Returns:
            所有 Tick 数据列表
        """
        if not self.main_engine:
            return []
        
        try:
            return self.main_engine.get_all_ticks()
        except Exception as e:
            self._log(f"获取所有 Tick 失败: {e}")
            return []
