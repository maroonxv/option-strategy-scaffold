import os
import sys
import glob
import pickle
import json
import re
import pandas as pd
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# 将项目根目录添加到 sys.path 以允许反序列化策略对象
current_dir = os.path.dirname(os.path.abspath(__file__))
# src/interface/web -> src/interface -> src -> 根目录
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

class SnapshotReader:
    def __init__(self, monitor_dir="data/monitor"):
        # 将项目根目录添加到 sys.path 以允许反序列化策略对象
        # src/interface/web -> src/interface -> src -> 项目根目录
        self.monitor_dir = os.path.join(project_root, monitor_dir)

    @staticmethod
    def extract_delivery_month(vt_symbol):
        """
        从合约代码中提取到期月份
        支持格式: 
        - pp2601.DCE -> 2601
        - SH601.CZCE -> 601 -> 2601 (补全)
        """
        try:
            # 提取 symbol 部分 (去掉 .交易所)
            symbol = vt_symbol.split('.')[0]
            
            # 1. 尝试匹配 4 位数字 (如 2601) - 放在前面优先匹配
            # 这里的正则意味着：字母开头 + 2 + 3位数字
            match_4 = re.search(r'[a-zA-Z]+(2\d{3})', symbol)
            if match_4:
                return match_4.group(1) 
                
            # 2. 尝试匹配 3 位数字 (如 601) - 放在后面
            # 这里的正则意味着：字母开头 + 6/7/8/9 + 2位数字
            match_3 = re.search(r'[a-zA-Z]+([6-9]\d{2})', symbol)
            if match_3:
                # 补全为 4 位，例如 601 -> 2601
                short_month = match_3.group(1)
                return "2" + short_month 
        except Exception:
            pass
            
        return "Other"

    def list_available_strategies(self):
        """扫描目录下所有的 snapshot_*.pkl"""
        pattern = os.path.join(self.monitor_dir, "snapshot_*.pkl")
        files = glob.glob(pattern)
        strategies = []
        for f in files:
            try:
                # snapshot_15m.pkl -> 15m
                basename = os.path.basename(f)
                variant = basename.replace("snapshot_", "").replace(".pkl", "")
                
                # 获取最后修改时间
                mtime = os.path.getmtime(f)
                dt = datetime.fromtimestamp(mtime)
                
                strategies.append({
                    "variant": variant,
                    "last_update": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "file_size": os.path.getsize(f)
                })
            except Exception:
                continue
        return strategies

    def get_strategy_data(self, variant_name):
        """读取指定变体的快照并转换为 JSON"""
        file_path = os.path.join(self.monitor_dir, f"snapshot_{variant_name}.pkl")
        
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "rb") as f:
                raw_data = pickle.load(f)
        except Exception as e:
            print(f"Error loading pickle: {e}")
            return None

        if isinstance(raw_data, dict) and "timestamp" in raw_data and "instruments" in raw_data:
            return raw_data

        # 数据清洗
        return {
            "timestamp": raw_data["update_time"].strftime("%Y-%m-%d %H:%M:%S"),
            "variant": raw_data["variant"],
            "instruments": self._parse_instruments(
                raw_data["instruments"], 
                raw_data.get("macd_history", {}), 
                raw_data.get("dullness", {}), 
                raw_data.get("divergence", {})
            ),
            "positions": self._parse_positions(raw_data["positions"]),
            "orders": self._parse_orders(raw_data["positions"])
        }

    def _parse_instruments(self, aggregate, macd_history, dullness_states, divergence_states):
        """解析标的数据（兼容旧 pickle 格式参数，但不再使用 MACD/TD 专属逻辑）"""
        result = {}
        # aggregate 是 InstrumentManager 对象
        
        for symbol in aggregate.get_all_symbols():
            instrument = aggregate.get_instrument(symbol)
            if not instrument:
                continue
                
            # 获取 K 线数据
            # TargetInstrument 使用 DataFrame `bars`
            # 但 pickle 转换脚本或旧 pickle 可能不同
            # 让我们检查属性
            if hasattr(instrument, "bars") and isinstance(instrument.bars, pd.DataFrame):
                # DataFrame 格式
                bars_df = instrument.bars
                if bars_df.empty:
                    continue
                
                # 转换为字典列表以便迭代
                # 我们需要 时间、开盘价、最高价、最低价、收盘价、成交量
                ohlc = []
                dates = []
                volumes = []
                
                # 遍历行
                for idx, row in bars_df.iterrows():
                    dt = row.get("datetime")
                    if isinstance(dt, str):
                        dt_str = dt
                    else:
                        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""
                        
                    dates.append(dt_str)
                    high = row.get("high")
                    low = row.get("low")
                    ohlc.append([
                        row.get("open"),
                        row.get("close"),
                        low,
                        high
                    ])
                    volumes.append(row.get("volume", 0))
            
            elif hasattr(instrument, "bar_history"):
                # 旧格式或 deque？
                bars = list(instrument.bar_history)
                if not bars:
                    continue
                    
                # 构建类 DataFrame 结构
                ohlc = []
                dates = []
                volumes = []
                
                for bar in bars:
                    # BarData 通常包含 datetime, open_price, high_price, low_price, close_price, volume
                    dt_str = bar.datetime.strftime("%Y-%m-%d %H:%M:%S")
                    dates.append(dt_str)
                    # ECharts K线格式: [open, close, low, high]
                    ohlc.append([bar.open_price, bar.close_price, bar.low_price, bar.high_price])
                    volumes.append(bar.volume)
            else:
                continue
            
            # 指标数据和状态由具体策略实现决定
            indicator_data = getattr(instrument, "indicators", {})
            
            result[symbol] = {
                "dates": dates,
                "ohlc": ohlc,
                "volumes": volumes,
                "indicators": indicator_data,
                "status": {},
                "last_price": instrument.latest_close,
                "delivery_month": self.extract_delivery_month(symbol)
            }
        return result

    def _parse_positions(self, position_aggregate):
        # PositionAggregate 包含 positions 字典
        result = []
        for pos in position_aggregate.get_all_positions():
            result.append({
                "vt_symbol": pos.vt_symbol,
                "direction": str(pos.direction),
                "volume": pos.volume,
                "price": pos.open_price,
                "pnl": 0.0
            })
        return result

    def _parse_orders(self, position_aggregate):
        # PositionAggregate 包含 pending_orders 字典
        result = []
        # 使用新的 getter 或回退到受保护成员（如果是旧 pickle）
        if hasattr(position_aggregate, "get_all_pending_orders"):
            orders = position_aggregate.get_all_pending_orders()
        else:
            orders = position_aggregate._pending_orders.values()

        for order in orders:
            result.append({
                "vt_orderid": order.vt_orderid,
                "vt_symbol": order.vt_symbol,
                "direction": str(order.direction),
                "offset": str(order.offset),
                "volume": order.volume,
                "price": order.price,
                "status": str(order.status) if hasattr(order, "status") else "Unknown"
            })
        return result


class MySQLSnapshotReader:
    def __init__(self):
        self.instance_id = os.getenv("MONITOR_INSTANCE_ID", "default") or "default"
        self._db_config = {
            "host": os.getenv("VNPY_DATABASE_HOST", "") or "",
            "port": int(os.getenv("VNPY_DATABASE_PORT", "3306") or 3306),
            "user": os.getenv("VNPY_DATABASE_USER", "") or "",
            "password": os.getenv("VNPY_DATABASE_PASSWORD", "") or "",
            "database": os.getenv("VNPY_DATABASE_DATABASE", "") or "",
        }
        self._tables_ensured = False

    def _db_available(self) -> bool:
        cfg = self._db_config or {}
        return bool(cfg.get("host") and cfg.get("user") and cfg.get("database"))

    def _connect(self):
        if not self._db_available():
            return None
        try:
            import pymysql
        except Exception:
            return None
        try:
            return pymysql.connect(
                host=self._db_config["host"],
                port=int(self._db_config["port"]),
                user=self._db_config["user"],
                password=self._db_config["password"],
                database=self._db_config["database"],
                charset="utf8mb4",
                autocommit=True,
                cursorclass=pymysql.cursors.DictCursor,
            )
        except Exception:
            return None

    def ensure_tables(self) -> None:
        if self._tables_ensured:
            return
        conn = self._connect()
        if conn is None:
            return
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS monitor_signal_snapshot (
                      id BIGINT AUTO_INCREMENT PRIMARY KEY,
                      variant VARCHAR(64) NOT NULL,
                      instance_id VARCHAR(64) NOT NULL,
                      updated_at DATETIME(6) NOT NULL,
                      bar_dt DATETIME(6) NULL,
                      bar_interval VARCHAR(16) NULL,
                      bar_window INT NULL,
                      payload_json JSON NOT NULL,
                      UNIQUE KEY uk_variant_instance (variant, instance_id),
                      KEY idx_updated_at (updated_at),
                      KEY idx_bar_dt (bar_dt)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS monitor_signal_event (
                      id BIGINT AUTO_INCREMENT PRIMARY KEY,
                      variant VARCHAR(64) NOT NULL,
                      instance_id VARCHAR(64) NOT NULL,
                      vt_symbol VARCHAR(64) NOT NULL,
                      bar_dt DATETIME(6) NULL,
                      event_type VARCHAR(32) NOT NULL,
                      event_key VARCHAR(192) NOT NULL,
                      created_at DATETIME(6) NOT NULL,
                      payload_json JSON NOT NULL,
                      UNIQUE KEY uk_event_key (event_key),
                      KEY idx_variant_created (variant, created_at),
                      KEY idx_symbol_bar (vt_symbol, bar_dt),
                      KEY idx_type_created (event_type, created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
            self._tables_ensured = True
        except Exception:
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def list_available_strategies(self) -> List[Dict[str, Any]]:
        self.ensure_tables()
        conn = self._connect()
        if conn is None:
            return []
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT variant, MAX(updated_at) AS last_update
                    FROM monitor_signal_snapshot
                    GROUP BY variant
                    ORDER BY variant
                    """
                )
                rows = cursor.fetchall() or []
            result = []
            for r in rows:
                dt = r.get("last_update")
                if isinstance(dt, datetime):
                    dt_text = dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    dt_text = str(dt) if dt else ""
                result.append({"variant": r.get("variant", ""), "last_update": dt_text, "file_size": None})
            return result
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_strategy_data(self, variant_name: str) -> Optional[Dict[str, Any]]:
        if not variant_name:
            return None
        self.ensure_tables()
        conn = self._connect()
        if conn is None:
            return None
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT payload_json
                    FROM monitor_signal_snapshot
                    WHERE variant=%s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (variant_name,),
                )
                row = cursor.fetchone()
            if not row:
                return None
            payload = row.get("payload_json")
            if isinstance(payload, (dict, list)):
                return payload if isinstance(payload, dict) else None
            if isinstance(payload, str):
                try:
                    obj = json.loads(payload)
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
            return None
        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_events(
        self,
        variant: str,
        vt_symbol: str = "",
        start: str = "",
        end: str = "",
        event_type: str = "",
        limit: int = 2000,
    ) -> List[Dict[str, Any]]:
        if not variant:
            return []
        self.ensure_tables()
        conn = self._connect()
        if conn is None:
            return []
        start_dt = self._parse_dt(start)
        end_dt = self._parse_dt(end)
        params: List[Any] = [variant]
        where = ["variant=%s"]
        if vt_symbol:
            where.append("vt_symbol=%s")
            params.append(vt_symbol)
        if event_type:
            where.append("event_type=%s")
            params.append(event_type)
        if start_dt:
            where.append("created_at>=%s")
            params.append(start_dt)
        if end_dt:
            where.append("created_at<=%s")
            params.append(end_dt)
        try:
            limit_int = int(limit)
        except Exception:
            limit_int = 2000
        if limit_int <= 0:
            limit_int = 2000
        if limit_int > 5000:
            limit_int = 5000
        try:
            sql = (
                "SELECT id, variant, instance_id, vt_symbol, bar_dt, event_type, event_key, created_at, payload_json "
                "FROM monitor_signal_event "
                f"WHERE {' AND '.join(where)} "
                "ORDER BY id DESC "
                f"LIMIT {limit_int}"
            )
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall() or []
            result: List[Dict[str, Any]] = []
            for r in rows:
                payload = r.get("payload_json")
                if isinstance(payload, str):
                    try:
                        payload_obj = json.loads(payload)
                    except Exception:
                        payload_obj = {"raw": payload}
                elif isinstance(payload, dict):
                    payload_obj = payload
                else:
                    payload_obj = {}
                r["payload"] = payload_obj
                r.pop("payload_json", None)
                result.append(r)
            return result
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_bars(
        self,
        vt_symbol: str,
        start: str,
        end: str,
        interval: str = "1m",
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        symbol, exchange = self._split_vt_symbol(vt_symbol)
        if not symbol or not exchange:
            return []
        start_dt = self._parse_dt(start)
        end_dt = self._parse_dt(end)
        if not start_dt or not end_dt:
            return []
        try:
            from vnpy.trader.database import get_database
            from vnpy.trader.constant import Interval, Exchange
        except Exception:
            return []
        interval_enum = self._map_interval(interval, Interval)
        if interval_enum is None:
            interval_enum = Interval.MINUTE
        try:
            exchange_enum = Exchange(exchange)
        except Exception:
            return []
        try:
            db = get_database()
            bars = db.load_bar_data(
                symbol=symbol,
                exchange=exchange_enum,
                interval=interval_enum,
                start=start_dt,
                end=end_dt,
            )
        except Exception:
            return []
        try:
            limit_int = int(limit)
        except Exception:
            limit_int = 5000
        if limit_int <= 0:
            limit_int = 5000
        if len(bars) > limit_int:
            bars = bars[-limit_int:]
        result: List[Dict[str, Any]] = []
        for b in bars:
            dt = getattr(b, "datetime", None)
            dt_text = dt.isoformat() if isinstance(dt, datetime) else str(dt) if dt else ""
            result.append(
                {
                    "datetime": dt_text,
                    "open": float(getattr(b, "open_price", 0) or 0),
                    "high": float(getattr(b, "high_price", 0) or 0),
                    "low": float(getattr(b, "low_price", 0) or 0),
                    "close": float(getattr(b, "close_price", 0) or 0),
                    "volume": float(getattr(b, "volume", 0) or 0),
                }
            )
        return result

    def _split_vt_symbol(self, vt_symbol: str) -> Tuple[str, str]:
        if not vt_symbol or "." not in vt_symbol:
            return "", ""
        parts = vt_symbol.split(".", 1)
        if len(parts) != 2:
            return "", ""
        return parts[0], parts[1]

    def _parse_dt(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        if isinstance(text, datetime):
            return text
        try:
            return datetime.fromisoformat(text)
        except Exception:
            try:
                return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

    def _map_interval(self, interval_text: str, IntervalEnum) -> Optional[Any]:
        if not interval_text:
            return None
        t = str(interval_text).strip().lower()
        if t in ("1m", "m", "min", "minute"):
            return IntervalEnum.MINUTE
        if t in ("1h", "h", "hour"):
            return IntervalEnum.HOUR
        if t in ("1d", "d", "day", "daily"):
            return IntervalEnum.DAILY
        if t in ("w", "week", "weekly"):
            return IntervalEnum.WEEKLY if hasattr(IntervalEnum, "WEEKLY") else None
        return None
