import json
import os
import pickle
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

from ...domain.aggregate.target_instrument_aggregate import InstrumentManager
from ...domain.aggregate.position_aggregate import PositionAggregate


class StrategyMonitor:
    """
    负责策略的监控与快照逻辑
    """
    
    def __init__(
        self,
        variant_name: str,
        monitor_instance_id: str,
        snapshot_path: str,
        monitor_db_config: Optional[Dict[str, Any]] = None,
        logger: Any = None
    ):
        self.variant_name = variant_name
        self.monitor_instance_id = monitor_instance_id
        self.snapshot_path = snapshot_path
        self._monitor_db_config = monitor_db_config or {}
        self.logger = logger
        
        self.monitor_db_enabled = str(os.getenv("MONITOR_DB_ENABLED", "1")).lower() not in ("0", "false", "no", "off", "")
        if not self._monitor_db_config.get("host"):
             self.monitor_db_enabled = False

        self._monitor_tables_ensured = False
        self._last_status_map: Dict[str, Dict[str, bool]] = {}

    def _monitor_db_available(self) -> bool:
        if not self.monitor_db_enabled:
            return False
        cfg = self._monitor_db_config
        return bool(cfg.get("host") and cfg.get("user") and cfg.get("database"))

    def _monitor_db_connect(self):
        try:
            import pymysql
        except Exception:
            return None
        if not self._monitor_db_available():
            return None
        try:
            return pymysql.connect(
                host=self._monitor_db_config["host"],
                port=int(self._monitor_db_config["port"]),
                user=self._monitor_db_config["user"],
                password=self._monitor_db_config["password"],
                database=self._monitor_db_config["database"],
                charset="utf8mb4",
                autocommit=True,
            )
        except Exception:
            return None

    def _ensure_monitor_tables(self) -> None:
        if self._monitor_tables_ensured:
            return
        conn = self._monitor_db_connect()
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
            self._monitor_tables_ensured = True
        except Exception:
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _upsert_monitor_snapshot(
        self,
        payload: Dict[str, Any],
        bar_dt: Optional[datetime],
        bar_interval: Optional[str],
        bar_window: Optional[int],
    ) -> None:
        self._ensure_monitor_tables()
        conn = self._monitor_db_connect()
        if conn is None:
            return
        now_dt = datetime.now()
        try:
            payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO monitor_signal_snapshot
                      (variant, instance_id, updated_at, bar_dt, bar_interval, bar_window, payload_json)
                    VALUES
                      (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      updated_at=VALUES(updated_at),
                      bar_dt=VALUES(bar_dt),
                      bar_interval=VALUES(bar_interval),
                      bar_window=VALUES(bar_window),
                      payload_json=VALUES(payload_json)
                    """,
                    (
                        self.variant_name,
                        self.monitor_instance_id,
                        now_dt,
                        bar_dt,
                        bar_interval,
                        bar_window,
                        payload_text,
                    ),
                )
        except Exception:
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def insert_monitor_event(
        self,
        event_type: str,
        event_key: str,
        payload: Dict[str, Any],
        vt_symbol: str,
        bar_dt: Optional[datetime],
        created_at: Optional[datetime] = None,
    ) -> None:
        self._ensure_monitor_tables()
        conn = self._monitor_db_connect()
        if conn is None:
            return
        if not created_at:
            created_at = datetime.now()
        try:
            payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT IGNORE INTO monitor_signal_event
                      (variant, instance_id, vt_symbol, bar_dt, event_type, event_key, created_at, payload_json)
                    VALUES
                      (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        self.variant_name,
                        self.monitor_instance_id,
                        vt_symbol or "",
                        bar_dt,
                        event_type,
                        event_key,
                        created_at,
                        payload_text,
                    ),
                )
        except Exception:
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def parse_bar_dt(self, bar_dt_value: Any) -> Optional[datetime]:
        if isinstance(bar_dt_value, datetime):
            return bar_dt_value
        if isinstance(bar_dt_value, str) and bar_dt_value:
            try:
                return datetime.fromisoformat(bar_dt_value)
            except Exception:
                try:
                    return datetime.strptime(bar_dt_value, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    return None
        return None

    def record_snapshot(
        self,
        target_aggregate: InstrumentManager,
        position_aggregate: PositionAggregate,
        strategy_context: Any
    ) -> None:
        """
        生成并保存用于 Web 监控的快照数据 (轻量级)
        """
        try:
            max_bars = 300
            instruments_data: Dict[str, Any] = {}
            snapshot_bar_dt: Optional[datetime] = None

            for vt_symbol in target_aggregate.get_all_symbols():
                instrument = target_aggregate.get_instrument(vt_symbol)
                if not instrument:
                    continue

                bars_df = getattr(instrument, "bars", None)
                dates: List[str] = []
                ohlc: List[List[Any]] = []
                volumes: List[Any] = []
                tail_df = None

                if bars_df is not None and not getattr(bars_df, "empty", True):
                    tail_df = bars_df.tail(max_bars).copy()

                if tail_df is not None:
                    for _, row in tail_df.iterrows():
                        dt = row.get("datetime")
                        if isinstance(dt, str):
                            dt_str = dt
                        else:
                            dt_str = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""

                        dates.append(dt_str)
                        low = row.get("low")
                        high = row.get("high")
                        ohlc.append([
                            row.get("open"),
                            row.get("close"),
                            low,
                            high
                        ])
                        volumes.append(row.get("volume", 0))

                # 指标数据和状态由具体策略实现决定，此处仅记录基础 OHLCV
                status = {}

                tail_last_dt = None
                try:
                    if tail_df is not None and not tail_df.empty:
                        tail_last_dt = tail_df.iloc[-1].get("datetime")
                except Exception:
                    tail_last_dt = None
                tail_last_dt_parsed = self.parse_bar_dt(tail_last_dt)
                if tail_last_dt_parsed and (snapshot_bar_dt is None or tail_last_dt_parsed > snapshot_bar_dt):
                    snapshot_bar_dt = tail_last_dt_parsed
                instruments_data[vt_symbol] = {
                    "dates": dates,
                    "ohlc": ohlc,
                    "volumes": volumes,
                    "indicators": instrument.indicators if hasattr(instrument, "indicators") else {},
                    "status": status,
                    "last_price": float(getattr(instrument, "latest_close", 0.0) or 0.0),
                    "delivery_month": "Other"
                }

            positions_list: List[Dict[str, Any]] = []
            try:
                for pos in position_aggregate.get_all_positions():
                    positions_list.append({
                        "vt_symbol": getattr(pos, "vt_symbol", ""),
                        "direction": str(getattr(pos, "direction", "")),
                        "volume": getattr(pos, "volume", 0),
                        "price": getattr(pos, "open_price", 0),
                        "pnl": 0.0
                    })
            except Exception:
                positions_list = []

            orders_list: List[Dict[str, Any]] = []
            try:
                if hasattr(position_aggregate, "get_all_pending_orders"):
                    orders = position_aggregate.get_all_pending_orders()
                else:
                    orders = getattr(position_aggregate, "_pending_orders", {}).values()
                for order in orders:
                    orders_list.append({
                        "vt_orderid": getattr(order, "vt_orderid", ""),
                        "vt_symbol": getattr(order, "vt_symbol", ""),
                        "direction": str(getattr(order, "direction", "")),
                        "offset": str(getattr(order, "offset", "")),
                        "volume": getattr(order, "volume", 0),
                        "price": getattr(order, "price", 0),
                        "status": str(getattr(order, "status", "Unknown"))
                    })
            except Exception:
                orders_list = []

            snapshot_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "variant": self.variant_name,
                "instruments": instruments_data,
                "positions": positions_list,
                "orders": orders_list
            }

            bar_interval = str(getattr(strategy_context, "bar_interval", "") or "") or None
            bar_window_raw = getattr(strategy_context, "bar_window", None)
            try:
                bar_window = int(bar_window_raw) if bar_window_raw is not None else None
            except Exception:
                bar_window = None

            for vt_symbol, inst_data in instruments_data.items():
                prev = self._last_status_map.get(vt_symbol) or {}
                cur = (inst_data.get("status") or {}) if isinstance(inst_data, dict) else {}
                for state_name in cur.keys():
                    old_v = bool(prev.get(state_name, False))
                    new_v = bool(cur.get(state_name, False))
                    if old_v == new_v:
                        continue
                    state_event_key = (
                        f"{self.variant_name}|{self.monitor_instance_id}|{vt_symbol}|"
                        f"{(snapshot_bar_dt.isoformat() if snapshot_bar_dt else '')}|{state_name}|{old_v}->{new_v}"
                    )
                    self.insert_monitor_event(
                        event_type="state_change",
                        event_key=state_event_key,
                        payload={
                            "state_name": state_name,
                            "old_value": old_v,
                            "new_value": new_v,
                            "bar_dt": snapshot_bar_dt.isoformat() if snapshot_bar_dt else "",
                        },
                        vt_symbol=vt_symbol,
                        bar_dt=snapshot_bar_dt,
                    )
                self._last_status_map[vt_symbol] = {k: bool(cur.get(k, False)) for k in cur.keys()}

            self._upsert_monitor_snapshot(
                payload=snapshot_data,
                bar_dt=snapshot_bar_dt,
                bar_interval=bar_interval,
                bar_window=bar_window,
            )
            
            # 确保目录存在
            if self.logger:
                self.logger.info(f"Dumping snapshot to: {self.snapshot_path}")
            os.makedirs(os.path.dirname(self.snapshot_path), exist_ok=True)
            
            # 使用临时文件写入 + 重命名原子操作
            temp_path = self.snapshot_path + ".tmp"
            with open(temp_path, "wb") as f:
                pickle.dump(snapshot_data, f)
            
            # 原子替换
            if os.path.exists(self.snapshot_path):
                try:
                    os.replace(temp_path, self.snapshot_path)
                except OSError:
                    if self.logger:
                        self.logger.warning(f"Snapshot update failed (locked?): {self.snapshot_path}")
                    try:
                        os.remove(temp_path)
                    except:
                        pass
            else:
                os.rename(temp_path, self.snapshot_path)
                
        except Exception as e:
            # 记录错误
            if self.logger:
                self.logger.error(f"保存监控快照失败: {str(e)}")
            pass
