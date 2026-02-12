from flask import Flask, render_template, jsonify, request
from reader import SnapshotReader, MySQLSnapshotReader
import os
import json

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

try:
    from flask_socketio import SocketIO, join_room
except Exception:
    SocketIO = None
    join_room = None

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['TEMPLATES_AUTO_RELOAD'] = True

if load_dotenv:
    try:
        load_dotenv()
    except Exception:
        pass

try:
    from vnpy.trader.setting import SETTINGS
except Exception:
    SETTINGS = None

if SETTINGS is not None and os.getenv("VNPY_DATABASE_DRIVER"):
    try:
        SETTINGS["database.driver"] = os.getenv("VNPY_DATABASE_DRIVER")
        SETTINGS["database.database"] = os.getenv("VNPY_DATABASE_DATABASE")
        SETTINGS["database.host"] = os.getenv("VNPY_DATABASE_HOST")
        SETTINGS["database.port"] = int(os.getenv("VNPY_DATABASE_PORT", 3306))
        SETTINGS["database.user"] = os.getenv("VNPY_DATABASE_USER")
        SETTINGS["database.password"] = os.getenv("VNPY_DATABASE_PASSWORD")
    except Exception:
        pass

pickle_reader = SnapshotReader()
mysql_reader = MySQLSnapshotReader()

use_mysql = str(os.getenv("MONITOR_USE_MYSQL", "1")).lower() not in ("0", "false", "no", "off", "")

_mysql_ready_cache = {"ts": 0.0, "ready": False}

def mysql_ready() -> bool:
    if not (use_mysql and mysql_reader._db_available()):
        return False
    import time
    now = time.time()
    if now - _mysql_ready_cache["ts"] < 1.0:
        return bool(_mysql_ready_cache["ready"])
    ready = False
    try:
        mysql_reader.ensure_tables()
        conn = mysql_reader._connect()
        if conn is not None:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM monitor_signal_snapshot LIMIT 1")
                    ready = cursor.fetchone() is not None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    except Exception:
        ready = False
    _mysql_ready_cache["ts"] = now
    _mysql_ready_cache["ready"] = ready
    return ready

def list_strategies_best_effort():
    if mysql_ready():
        rows = mysql_reader.list_available_strategies()
        if rows:
            return rows
    return pickle_reader.list_available_strategies()

def get_snapshot_best_effort(variant_name: str):
    if mysql_ready():
        data = mysql_reader.get_strategy_data(variant_name)
        if data:
            return data
    return pickle_reader.get_strategy_data(variant_name)

socketio = None
if SocketIO is not None:
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

@app.route("/")
def index():
    """首页：策略实例列表"""
    strategies = list_strategies_best_effort()
    front_poll_ms = int(float(os.getenv("MONITOR_FRONT_POLL_MS", "3000") or 3000))
    front_stale_ms = int(float(os.getenv("MONITOR_FRONT_STALE_MS", "5000") or 5000))
    return render_template(
        "index.html",
        strategies=strategies,
        front_poll_ms=front_poll_ms,
        front_stale_ms=front_stale_ms,
    )

@app.route("/api/strategies")
def api_strategies():
    """获取策略列表"""
    strategies = list_strategies_best_effort()
    # 提取变体名称以供前端使用的简单列表
    names = [s['variant'] for s in strategies]
    return jsonify(names)

@app.route("/dashboard/<variant_name>")
def dashboard(variant_name):
    """详情页：渲染外壳"""
    front_poll_ms = int(float(os.getenv("MONITOR_FRONT_POLL_MS", "3000") or 3000))
    front_stale_ms = int(float(os.getenv("MONITOR_FRONT_STALE_MS", "5000") or 5000))
    return render_template(
        "index.html",
        variant=variant_name,
        front_poll_ms=front_poll_ms,
        front_stale_ms=front_stale_ms,
    )

@app.route("/api/data/<variant_name>")
def api_data(variant_name):
    """AJAX 接口：前端轮询获取最新数据"""
    data = get_snapshot_best_effort(variant_name)
    if not data:
        return jsonify({"error": "Not found"}), 404
    return jsonify(data)

@app.route("/api/snapshot/<variant_name>")
def api_snapshot(variant_name):
    data = get_snapshot_best_effort(variant_name)
    if not data:
        return jsonify({"error": "Not found"}), 404
    return jsonify(data)

@app.route("/api/events/<variant_name>")
def api_events(variant_name):
    vt_symbol = request.args.get("vt_symbol", "")
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    event_type = request.args.get("type", "")
    limit = request.args.get("limit", "2000")
    if mysql_ready():
        events = mysql_reader.get_events(
            variant=variant_name,
            vt_symbol=vt_symbol,
            start=start,
            end=end,
            event_type=event_type,
            limit=int(limit) if str(limit).isdigit() else 2000,
        )
        return jsonify(events)
    return jsonify([])

@app.route("/api/bars")
def api_bars():
    vt_symbol = request.args.get("vt_symbol", "")
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    interval = request.args.get("interval", "1m")
    limit = request.args.get("limit", "5000")
    if mysql_ready():
        bars = mysql_reader.get_bars(
            vt_symbol=vt_symbol,
            start=start,
            end=end,
            interval=interval,
            limit=int(limit) if str(limit).isdigit() else 5000,
        )
        return jsonify(bars)
    return jsonify([])

if socketio is not None:
    @socketio.on("subscribe")
    def handle_subscribe(data):
        try:
            variant = ""
            if isinstance(data, dict):
                variant = str(data.get("variant", "") or "")
            if variant:
                join_room(f"variant:{variant}")
        except Exception:
            return

    def poll_db():
        mysql_reader.ensure_tables()
        last_snapshot: dict = {}
        last_event_id = 0
        poll_interval = float(os.getenv("MONITOR_POLL_INTERVAL", "1.0") or 1.0)
        while True:
            if not mysql_ready():
                socketio.sleep(poll_interval)
                continue
            try:
                conn = mysql_reader._connect()
                if conn is None:
                    socketio.sleep(poll_interval)
                    continue
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT variant, updated_at FROM monitor_signal_snapshot")
                        snapshot_rows = cursor.fetchall() or []
                        for r in snapshot_rows:
                            variant = r.get("variant", "")
                            updated_at = r.get("updated_at", None)
                            last = last_snapshot.get(variant)
                            if last is None or (updated_at and updated_at > last):
                                last_snapshot[variant] = updated_at
                                payload = mysql_reader.get_strategy_data(variant)
                                if payload:
                                    socketio.emit("snapshot_update", payload, room=f"variant:{variant}")

                        cursor.execute(
                            "SELECT id, variant, instance_id, vt_symbol, bar_dt, event_type, event_key, created_at, payload_json "
                            "FROM monitor_signal_event WHERE id>%s ORDER BY id ASC LIMIT 500",
                            (last_event_id,),
                        )
                        event_rows = cursor.fetchall() or []
                        for e in event_rows:
                            last_event_id = max(last_event_id, int(e.get("id", 0) or 0))
                            variant = e.get("variant", "")
                            payload = e.get("payload_json")
                            if isinstance(payload, str):
                                try:
                                    payload_obj = json.loads(payload)
                                except Exception:
                                    payload_obj = {"raw": payload}
                            elif isinstance(payload, dict):
                                payload_obj = payload
                            else:
                                payload_obj = {}
                            out = dict(e)
                            out["payload"] = payload_obj
                            out.pop("payload_json", None)
                            if variant:
                                socketio.emit("event_new", out, room=f"variant:{variant}")
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                pass
            socketio.sleep(poll_interval)

    try:
        socketio.start_background_task(poll_db)
    except Exception:
        pass

if __name__ == "__main__":
    if socketio is not None:
        socketio.run(
            app,
            host="0.0.0.0",
            port=5007,
            debug=True,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )
    else:
        app.run(host="0.0.0.0", port=5007, debug=True, use_reloader=False)
