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
# src/web -> src -> 根目录
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

class SnapshotJsonTransformer:
    """将 strategy_state 的 snapshot_json 转换为前端格式"""

    @staticmethod
    def resolve_special_markers(obj: Any) -> Any:
        """递归解析 JSON 中的特殊类型标记

        解析规则:
        - __dataframe__: 返回 records 列表（递归解析）
        - __datetime__: 解析 ISO 字符串，返回 "YYYY-MM-DD HH:MM:SS" 格式
        - __date__: 原样返回日期字符串
        - __enum__: 原样返回枚举字符串
        - __set__: 返回 values 列表（递归解析）
        - __dataclass__: 移除 __dataclass__ 键，返回剩余字段（递归解析）
        - 未知标记/普通 dict: 递归解析所有值
        - list: 递归解析每个元素
        - 基本类型 (str, int, float, bool, None): 原样返回
        """
        if isinstance(obj, dict):
            # __dataframe__ 标记
            if "__dataframe__" in obj:
                records = obj.get("records", [])
                return [SnapshotJsonTransformer.resolve_special_markers(r) for r in records]

            # __datetime__ 标记
            if "__datetime__" in obj:
                raw = obj["__datetime__"]
                try:
                    dt = datetime.fromisoformat(str(raw))
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    return str(raw)

            # __date__ 标记
            if "__date__" in obj:
                return str(obj["__date__"])

            # __enum__ 标记
            if "__enum__" in obj:
                return str(obj["__enum__"])

            # __set__ 标记
            if "__set__" in obj:
                values = obj.get("values", [])
                return [SnapshotJsonTransformer.resolve_special_markers(v) for v in values]

            # __dataclass__ 标记
            if "__dataclass__" in obj:
                return {
                    k: SnapshotJsonTransformer.resolve_special_markers(v)
                    for k, v in obj.items()
                    if k != "__dataclass__"
                }

            # 普通 dict: 递归解析所有值
            return {
                k: SnapshotJsonTransformer.resolve_special_markers(v)
                for k, v in obj.items()
            }

        if isinstance(obj, list):
            return [SnapshotJsonTransformer.resolve_special_markers(item) for item in obj]

        # 基本类型: str, int, float, bool, None
        return obj

    @staticmethod
    def extract_delivery_month(vt_symbol: str) -> str:
        """从合约代码提取到期月份

        支持格式:
        - pp2601.DCE -> 2601
        - SH601.CZCE -> 601 -> 2601 (补全)
        """
        try:
            symbol = vt_symbol.split('.')[0]

            # 尝试匹配 4 位数字 (如 2601): 字母开头 + 2 + 3位数字
            match_4 = re.search(r'[a-zA-Z]+(2\d{3})', symbol)
            if match_4:
                return match_4.group(1)

            # 尝试匹配 3 位数字 (如 601): 字母开头 + 6/7/8/9 + 2位数字
            match_3 = re.search(r'[a-zA-Z]+([6-9]\d{2})', symbol)
            if match_3:
                short_month = match_3.group(1)
                return "2" + short_month
        except Exception:
            pass

        return "Other"

    @staticmethod
    def transform_instruments(target_aggregate: dict) -> dict:
        """转换标的数据为前端格式

        Args:
            target_aggregate: snapshot_json 中的 target_aggregate 字段

        Returns:
            {vt_symbol: {dates, ohlc, volumes, indicators, status, last_price, delivery_month}}
        """
        instruments = target_aggregate.get("instruments", {})
        result = {}

        for vt_symbol, instrument_data in instruments.items():
            # 获取 bars 字段并解析特殊标记（如 __dataframe__）
            raw_bars = instrument_data.get("bars", [])
            bars = SnapshotJsonTransformer.resolve_special_markers(raw_bars)

            # 跳过 bars 为空的标的
            if not bars:
                continue

            # 提取 dates, ohlc, volumes
            dates = []
            ohlc = []
            volumes = []

            for record in bars:
                # datetime 可能是字符串或 __datetime__ 标记（已被 resolve 处理）
                dt_val = record.get("datetime", "")
                if isinstance(dt_val, dict):
                    dt_val = SnapshotJsonTransformer.resolve_special_markers(dt_val)
                dates.append(str(dt_val))

                ohlc.append([
                    record.get("open", 0),
                    record.get("close", 0),
                    record.get("low", 0),
                    record.get("high", 0),
                ])
                volumes.append(record.get("volume", 0))

            # last_price: 最后一条记录的 close
            last_price = bars[-1].get("close", 0)

            # indicators: 解析特殊标记
            raw_indicators = instrument_data.get("indicators", {})
            indicators = SnapshotJsonTransformer.resolve_special_markers(raw_indicators)

            # delivery_month
            delivery_month = SnapshotJsonTransformer.extract_delivery_month(vt_symbol)

            result[vt_symbol] = {
                "dates": dates,
                "ohlc": ohlc,
                "volumes": volumes,
                "indicators": indicators,
                "last_price": last_price,
                "delivery_month": delivery_month,
            }

        return result

    @staticmethod
    def transform_positions(position_aggregate: dict) -> list:
        """转换持仓数据为前端格式

        Args:
            position_aggregate: snapshot_json 中的 position_aggregate 字段

        Returns:
            [{"vt_symbol": ..., "direction": ..., "volume": ..., "price": ..., "pnl": ...}, ...]
        """
        positions = position_aggregate.get("positions", {})
        result = []

        for _key, pos_data in positions.items():
            direction = pos_data.get("direction", "")
            if isinstance(direction, dict):
                direction = SnapshotJsonTransformer.resolve_special_markers(direction)

            result.append({
                "vt_symbol": pos_data.get("vt_symbol", ""),
                "direction": direction,
                "volume": pos_data.get("volume", 0),
                "price": pos_data.get("open_price", 0),
                "pnl": pos_data.get("pnl", 0),
            })

        return result

    @staticmethod
    def transform_orders(position_aggregate: dict) -> list:
        """转换挂单数据为前端格式

        Args:
            position_aggregate: snapshot_json 中的 position_aggregate 字段

        Returns:
            [{"vt_orderid": ..., "vt_symbol": ..., "direction": ..., "offset": ..., "volume": ..., "price": ..., "status": ...}, ...]
        """
        pending_orders = position_aggregate.get("pending_orders", {})
        result = []

        for _key, order_data in pending_orders.items():
            direction = order_data.get("direction", "")
            if isinstance(direction, dict):
                direction = SnapshotJsonTransformer.resolve_special_markers(direction)

            offset = order_data.get("offset", "")
            if isinstance(offset, dict):
                offset = SnapshotJsonTransformer.resolve_special_markers(offset)

            status = order_data.get("status", "")
            if isinstance(status, dict):
                status = SnapshotJsonTransformer.resolve_special_markers(status)

            result.append({
                "vt_orderid": order_data.get("vt_orderid", ""),
                "vt_symbol": order_data.get("vt_symbol", ""),
                "direction": direction,
                "offset": offset,
                "volume": order_data.get("volume", 0),
                "price": order_data.get("price", 0),
                "status": status,
            })

        return result

    @staticmethod
    def transform(snapshot: dict, strategy_name: str) -> dict:
        """主转换入口

        Args:
            snapshot: strategy_state 表中的 snapshot_json（已解析为 dict）
            strategy_name: 策略名称

        Returns:
            {
                "timestamp": "2025-01-15 14:30:00",
                "variant": "15m",
                "instruments": {...},
                "positions": [...],
                "orders": [...]
            }
        """
        # 1. Extract timestamp from current_dt
        current_dt = snapshot.get("current_dt", "")
        if isinstance(current_dt, dict):
            timestamp = SnapshotJsonTransformer.resolve_special_markers(current_dt)
        elif isinstance(current_dt, str) and current_dt:
            try:
                dt = datetime.fromisoformat(current_dt)
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                timestamp = current_dt
        else:
            timestamp = ""

        # 2. variant = strategy_name
        variant = strategy_name

        # 3. instruments from target_aggregate
        target_aggregate = snapshot.get("target_aggregate", {})
        instruments = SnapshotJsonTransformer.transform_instruments(target_aggregate)

        # 4. positions and orders from position_aggregate
        position_aggregate = snapshot.get("position_aggregate", {})
        positions = SnapshotJsonTransformer.transform_positions(position_aggregate)
        orders = SnapshotJsonTransformer.transform_orders(position_aggregate)

        return {
            "timestamp": timestamp,
            "variant": variant,
            "instruments": instruments,
            "positions": positions,
            "orders": orders,
        }


class StrategyStateReader:
    """从 strategy_state 表读取策略状态并转换为前端格式"""

    def __init__(self, db_config: dict):
        """
        Args:
            db_config: 数据库连接配置 {host, port, user, password, database}
        """
        self._db_config = db_config or {}

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
                port=int(self._db_config.get("port", 3306)),
                user=self._db_config["user"],
                password=self._db_config.get("password", ""),
                database=self._db_config["database"],
                charset="utf8mb4",
                autocommit=True,
                cursorclass=pymysql.cursors.DictCursor,
            )
        except Exception:
            return None

    def list_available_strategies(self) -> List[Dict[str, Any]]:
        """查询所有策略名称及最新更新时间

        Returns:
            [{"variant": "15m", "last_update": "2025-01-15 14:30:00", "file_size": None}, ...]
            出错时返回空列表
        """
        conn = self._connect()
        if conn is None:
            return []
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT strategy_name, MAX(saved_at) AS last_update
                    FROM strategy_state
                    GROUP BY strategy_name
                    ORDER BY strategy_name
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
                result.append({
                    "variant": r.get("strategy_name", ""),
                    "last_update": dt_text,
                    "file_size": None,
                })
            return result
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_strategy_data(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """读取指定策略的最新快照并转换为前端格式

        Args:
            strategy_name: 策略名称（对应前端的 variant）

        Returns:
            前端格式的字典，或 None（无数据/解析失败）
        """
        if not strategy_name:
            return None
        conn = self._connect()
        if conn is None:
            return None
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT snapshot_json
                    FROM strategy_state
                    WHERE strategy_name=%s
                    ORDER BY saved_at DESC
                    LIMIT 1
                    """,
                    (strategy_name,),
                )
                row = cursor.fetchone()
            if not row:
                return None
            snapshot = row.get("snapshot_json")
            if snapshot is None:
                return None
            # snapshot_json 可能是 dict（pymysql JSON 自动解析）或 str
            if isinstance(snapshot, str):
                try:
                    snapshot = json.loads(snapshot)
                except (json.JSONDecodeError, ValueError):
                    return None
            if not isinstance(snapshot, dict):
                return None
            return SnapshotJsonTransformer.transform(snapshot, strategy_name)
        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass


class SnapshotReader:
    def __init__(self, monitor_dir="data/monitor"):
        # 将项目根目录添加到 sys.path 以允许反序列化策略对象
        # src/web -> src -> 项目根目录
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
            "instruments": self._parse_instruments(raw_data["instruments"]),
            "positions": self._parse_positions(raw_data["positions"]),
            "orders": self._parse_orders(raw_data["positions"])
        }

    def _parse_instruments(self, aggregate):
        """解析标的数据（通用格式，不依赖具体策略逻辑）"""
        result = {}

        for symbol in aggregate.get_all_symbols():
            instrument = aggregate.get_instrument(symbol)
            if not instrument:
                continue

            # 获取 K 线数据 - 支持 DataFrame 和 deque 两种格式
            ohlc = []
            dates = []
            volumes = []

            if hasattr(instrument, "bars") and isinstance(instrument.bars, pd.DataFrame):
                bars_df = instrument.bars
                if bars_df.empty:
                    continue
                for _idx, row in bars_df.iterrows():
                    dt = row.get("datetime")
                    dt_str = dt if isinstance(dt, str) else (dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "")
                    dates.append(dt_str)
                    ohlc.append([row.get("open"), row.get("close"), row.get("low"), row.get("high")])
                    volumes.append(row.get("volume", 0))
            elif hasattr(instrument, "bar_history"):
                bars = list(instrument.bar_history)
                if not bars:
                    continue
                for bar in bars:
                    dates.append(bar.datetime.strftime("%Y-%m-%d %H:%M:%S"))
                    ohlc.append([bar.open_price, bar.close_price, bar.low_price, bar.high_price])
                    volumes.append(bar.volume)
            else:
                continue

            # 指标数据由具体策略实现决定，web 层不做假设
            indicator_data = getattr(instrument, "indicators", {})

            result[symbol] = {
                "dates": dates,
                "ohlc": ohlc,
                "volumes": volumes,
                "indicators": indicator_data,
                "last_price": instrument.latest_close,
                "delivery_month": self.extract_delivery_month(symbol),
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
