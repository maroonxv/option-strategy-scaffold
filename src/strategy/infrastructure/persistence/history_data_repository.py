from typing import List, Callable, Dict, Any, Optional
from datetime import datetime, timedelta
from logging import Logger

class HistoryDataRepository:
    """
    历史数据仓库
    
    负责从数据库加载历史数据并回放
    """
    def __init__(self, logger: Logger):
        self.logger = logger

    def replay_bars_from_database(
        self, 
        vt_symbols: List[str], 
        days: int, 
        on_bars_callback: Callable[[Dict[str, Any]], None]
    ) -> bool:
        """
        从数据库回放 Bar 数据
        
        Args:
            vt_symbols: 需要回放的合约代码列表
            days: 回放天数
            on_bars_callback: Bar 数据回调函数 (接收 dict{vt_symbol: BarData})
            
        Returns:
            bool: 是否成功
        """
        from vnpy.trader.database import get_database
        from vnpy.trader.constant import Interval, Exchange

        # 过滤无效 symbol
        vt_symbols = [s for s in vt_symbols if isinstance(s, str) and s]
        if not vt_symbols:
            self.logger.error("MySQL warmup 回放失败: 没有可用的 vt_symbol 列表")
            return False

        try:
            db = get_database()
        except Exception:
            self.logger.error("MySQL warmup 回放失败: 初始化 vn.py DatabaseManager 失败", exc_info=True)
            return False

        end = datetime.now()
        start = end - timedelta(days=int(days))

        self.logger.info(f"MySQL warmup 开始: days={days}, symbols={len(vt_symbols)}, range={start} ~ {end}")

        ok = False
        total_bars = 0
        for vt_symbol in vt_symbols:
            if "." not in vt_symbol:
                self.logger.warning(f"MySQL warmup 跳过无效 vt_symbol: {vt_symbol}")
                continue

            symbol_part, exchange_str = vt_symbol.split(".", 1)
            try:
                exchange = Exchange(exchange_str)
            except Exception:
                self.logger.warning(f"MySQL warmup 跳过无法解析交易所: {vt_symbol}")
                continue

            try:
                bars = db.load_bar_data(
                    symbol=symbol_part,
                    exchange=exchange,
                    interval=Interval.MINUTE,
                    start=start,
                    end=end,
                )
            except Exception:
                self.logger.error(f"MySQL warmup 读取 bar 失败: {vt_symbol}", exc_info=True)
                continue

            if not bars:
                self.logger.warning(f"MySQL warmup 无数据: {vt_symbol}")
                continue

            ok = True
            total_bars += len(bars)
            self.logger.info(f"MySQL warmup 加载成功: {vt_symbol}, bars={len(bars)}")
            for bar in bars:
                try:
                    on_bars_callback({vt_symbol: bar})
                except Exception:
                    self.logger.error(f"MySQL warmup 推送 bar 失败: {vt_symbol}", exc_info=True)
                    continue

        self.logger.info(f"MySQL warmup 完成: ok={ok}, total_bars={total_bars}")
        return ok
