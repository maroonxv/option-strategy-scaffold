"""
child_process.py - 工作进程实现

职责:
1. 初始化 VnPy 引擎 (EventEngine, MainEngine, StrategyEngine)
2. 加载并连接 CTP 网关
3. 加载并启动商品波动率策略
4. 处理交易事件和策略回调
5. 优雅退出和资源清理
"""
import os
import sys
import time
import signal
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, Iterable, List, Set, Tuple

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# VnPy 导入
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine

# 组合策略应用
from vnpy_portfoliostrategy import PortfolioStrategyApp

# 内部模块
from src.main.gateway import GatewayManager
from src.main.utils.config_loader import ConfigLoader
from src.main.utils.log_handler import setup_logging
from src.strategy.strategy_entry import StrategyEntry

# 添加策略路径
STRATEGY_PATH = PROJECT_ROOT / "src" / "strategy"
sys.path.insert(0, str(STRATEGY_PATH))


class ChildProcess:
    """
    工作进程
    
    负责运行 VnPy 引擎和策略，是策略的实际执行环境。
    """
    
    def __init__(
        self,
        config_path: str,
        override_config_path: Optional[str] = None,
        log_level: str = "INFO",
        log_dir: str = "logs",
        paper_trading: bool = False
    ) -> None:
        """
        初始化工作进程
        
        Args:
            config_path: 策略配置文件路径
            override_config_path: 覆盖配置文件路径
            log_level: 日志级别
            log_dir: 日志目录
            paper_trading: 是否启用模拟交易模式
        """
        self.config_path = config_path
        self.override_config_path = override_config_path
        self.log_level = log_level
        self.log_dir = log_dir
        self.paper_trading = paper_trading
        
        self.logger = logging.getLogger(__name__)
        
        # VnPy 引擎
        self.event_engine: Optional[EventEngine] = None
        self.main_engine: Optional[MainEngine] = None
        self.strategy_engine: Optional[Any] = None
        self.recorder_engine: Optional[Any] = None
        self.recorder_engine_name: str = ""
        self.recorder_enabled: bool = False
        self._recording_only_subscribed: Set[str] = set()
        self._recording_only_recorded: Set[str] = set()
        self._last_option_recording_update_ts: float = 0.0
        
        # 网关管理器
        self.gateway_manager: Optional[GatewayManager] = None
        
        # 配置
        self.gateway_config: Dict[str, Any] = {}
        self.strategy_config: Dict[str, Any] = {}
        
        # 运行状态
        self.running: bool = False
        self.strategies_started: bool = False
        self._is_shutdown: bool = False
        
        # 设置信号处理
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum: int, frame) -> None:
        """处理关闭信号"""
        self.logger.info(f"收到信号 {signum}，准备关闭")
        self.running = False
    
    def run(self) -> None:
        """
        运行工作进程
        """
        self.running = True
        self.logger.info("工作进程启动")
        
        try:
            # 1. 加载配置
            self._load_configs()

            self._setup_vnpy_database_settings()
            self._patch_data_recorder_setting_path()
            
            # 2. 初始化引擎
            self._init_engines()
            
            # 3. 连接网关
            self._connect_gateways()
            
            # 4. 等待网关连接成功
            self._wait_for_connection()
            
            # 等待合约查询完成
            self.logger.info("等待合约信息同步 (10s)...")
            time.sleep(10.0)
            
            all_contracts = self.main_engine.get_all_contracts()
            self.logger.info(f"MainEngine 获取到的合约总数: {len(all_contracts)}")
            if len(all_contracts) > 0:
                self.logger.info(f"合约示例: {[c.vt_symbol for c in all_contracts]}")
            else:
                self.logger.warning("未能从 MainEngine 获取到任何合约信息！")
            
            # 5. 加载和启动策略
            self._load_strategies()
            self._init_strategies()
            self._start_strategies()
            
            # 6. 进入事件循环
            self._run_event_loop()
            
        except Exception as e:
            self.logger.error(f"工作进程异常: {e}", exc_info=True)
            # 这里不 raise，而是让 finally 块处理清理，然后退出
            sys.exit(1)
        finally:
            self.shutdown()
    
    def _load_configs(self) -> None:
        """加载配置文件"""
        self.logger.info("加载配置文件...")
        
        # 加载网关配置 (from .env)
        try:
            self.gateway_config = ConfigLoader.load_gateway_config()
            self.logger.info("已加载网关配置 (来自 .env)")
        except Exception as e:
            self.logger.error(f"加载网关配置失败: {e}")
            raise
        
        # 加载策略配置
        try:
            strategy_config_path = Path(self.config_path)
            if not strategy_config_path.exists():
                raise FileNotFoundError(f"策略配置文件不存在: {strategy_config_path}")

            base_config = ConfigLoader.load_yaml(str(strategy_config_path))
            
            # 如果有覆盖配置，进行合并
            if self.override_config_path:
                override_path = Path(self.override_config_path)
                if override_path.exists():
                    override_config = ConfigLoader.load_yaml(str(override_path))
                    self.strategy_config = ConfigLoader.merge_strategy_config(base_config, override_config)
                    self.logger.info(f"已加载策略配置: {strategy_config_path} + {self.override_config_path}")
                else:
                    self.logger.warning(f"覆盖配置文件不存在: {self.override_config_path}, 将只使用基础配置")
                    self.strategy_config = base_config
            else:
                self.strategy_config = base_config
                self.logger.info(f"已加载策略配置: {strategy_config_path}")

        except Exception as e:
            self.logger.error(f"加载策略配置失败: {e}")
            raise

    def _setup_vnpy_database_settings(self) -> None:
        try:
            from vnpy.trader.setting import SETTINGS
        except Exception as e:
            self.logger.warning(f"加载 vn.py SETTINGS 失败，跳过数据库注入: {e}")
            self.recorder_enabled = False
            return

        driver = os.getenv("VNPY_DATABASE_DRIVER", "").strip()
        if not driver:
            self.logger.info("未配置 VNPY_DATABASE_DRIVER，数据录制将不启用")
            self.recorder_enabled = False
            return

        database = os.getenv("VNPY_DATABASE_DATABASE", "").strip()
        host = os.getenv("VNPY_DATABASE_HOST", "localhost").strip()
        port_raw = os.getenv("VNPY_DATABASE_PORT", "3306").strip()
        user = os.getenv("VNPY_DATABASE_USER", "").strip()
        password = os.getenv("VNPY_DATABASE_PASSWORD", "")

        try:
            port = int(port_raw)
        except Exception:
            port = 3306

        SETTINGS["database.driver"] = driver
        SETTINGS["database.name"] = driver
        SETTINGS["database.database"] = database
        SETTINGS["database.host"] = host
        SETTINGS["database.port"] = port
        SETTINGS["database.user"] = user
        SETTINGS["database.password"] = password

        self.recorder_enabled = True
        self.logger.info(f"已注入 vn.py 数据库配置: driver={driver}, host={host}, port={port}, database={database}")

    def _patch_data_recorder_setting_path(self) -> None:
        if not self.recorder_enabled:
            return

        try:
            import vnpy.trader.utility as vnpy_utility
        except Exception as e:
            self.logger.warning(f"加载 vn.py utility 失败，跳过 data_recorder_setting.json 重定向: {e}")
            return

        original_get_file_path = vnpy_utility.get_file_path

        config_path = PROJECT_ROOT / "config" / "general" / "data_recorder_setting.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if (not config_path.exists()) or config_path.stat().st_size == 0:
            config_path.write_text("{}", encoding="utf-8")

        def patched_get_file_path(filename: str):
            if filename == "data_recorder_setting.json":
                self.logger.info(f"Redirecting data_recorder_setting.json to: {config_path}")
                return config_path
            return original_get_file_path(filename)

        vnpy_utility.get_file_path = patched_get_file_path

    def _init_engines(self) -> None:
        """初始化 VnPy 引擎"""
        self.logger.info("初始化 VnPy 引擎...")
        
        # 1. 创建事件引擎
        self.event_engine = EventEngine()
        
        # 2. 创建主引擎
        self.main_engine = MainEngine(self.event_engine)
        
        # 3. 初始化网关管理器
        self.gateway_manager = GatewayManager(self.main_engine)
        self.gateway_manager.set_config(self.gateway_config)
        self.gateway_manager.add_gateways()
        
        # 4. 添加组合策略应用
        self.strategy_engine = self.main_engine.add_app(PortfolioStrategyApp)

        self.strategy_engine.init_engine()
        self.logger.info("策略引擎已初始化")

        self.strategy_engine.load_strategy_class_from_module(
            "src.strategy.strategy_entry"
        )
        self.logger.info("已加载策略类: StrategyEntry")

        self._init_data_recorder()

    def _init_data_recorder(self) -> None:
        self.recorder_engine = None
        self.recorder_engine_name = ""

        if not self.recorder_enabled:
            return

        if not self.main_engine:
            self.recorder_enabled = False
            return

        try:
            from vnpy_datarecorder import DataRecorderApp, APP_NAME
        except Exception as e:
            self.logger.warning(f"加载 vnpy_datarecorder 失败，数据录制将降级关闭: {e}")
            self.recorder_enabled = False
            return

        try:
            self.main_engine.add_app(DataRecorderApp)
            self.recorder_engine_name = APP_NAME
            if hasattr(self.main_engine, "get_engine"):
                self.recorder_engine = self.main_engine.get_engine(APP_NAME)
            self.logger.info("DataRecorder 已加载")
        except Exception as e:
            self.logger.warning(f"初始化 DataRecorder 失败，数据录制将降级关闭: {e}")
            self.recorder_enabled = False
            self.recorder_engine = None
    
    def _connect_gateways(self) -> None:
        """连接交易网关"""
        self.logger.info("连接交易网关...")
        self.gateway_manager.connect_all()
    
    def _wait_for_connection(self, timeout: float = 60.0) -> None:
        """等待网关连接成功"""
        self.logger.info(f"等待网关连接 (超时: {timeout}s)...")
        
        if self.gateway_manager.wait_for_connection(timeout):
            self.logger.info("网关连接成功")
        else:
            raise TimeoutError("网关连接超时")
    
    def _load_strategies(self) -> None:
        """加载策略"""
        self.logger.info("加载策略...")
        
        strategies = self.strategy_config.get("strategies", [])
        
        for strategy_setting in strategies:
            class_name = strategy_setting.get("class_name")
            # 如果未配置策略名称，使用默认值
            strategy_name = strategy_setting.get("strategy_name", "default_strategy")
            vt_symbols = strategy_setting.get("vt_symbols", [])
            setting = strategy_setting.get("setting", {})
            
            # 如果是模拟交易模式，注入 paper_trading 配置
            if self.paper_trading:
                setting["paper_trading"] = True
            
            # 注入日志目录配置，以便策略内部 Logger 使用一致的路径
            if self.log_dir:
                setting["log_dir"] = self.log_dir
            
            # 注入飞书 Webhook (优先使用环境变量)
            feishu_webhook_env = os.getenv("FEISHU_WEBHOOK_URL")
            if feishu_webhook_env:
                setting["feishu_webhook"] = feishu_webhook_env
                self.logger.info(f"使用环境变量覆盖飞书 Webhook: {feishu_webhook_env[:10]}...")

            if not class_name:
                self.logger.warning(f"策略配置不完整: {strategy_setting}")
                continue
            
            self.strategy_engine.add_strategy(
                class_name=class_name,
                strategy_name=strategy_name,
                vt_symbols=vt_symbols,
                setting=setting
            )
            
            self.logger.info(f"已添加策略: {strategy_name}")
    
    def _init_strategies(self) -> None:
        """初始化所有策略"""
        self.logger.info("初始化策略...")
        
        # 获取所有策略名称
        for strategy_name in self.strategy_engine.strategies.keys():
            self.strategy_engine.init_strategy(strategy_name)
            self.logger.info(f"策略 {strategy_name} 初始化中...")
        
        # 等待初始化完成
        time.sleep(5.0)
    
    def _start_strategies(self) -> None:
        """启动所有策略"""
        self.logger.info("启动策略...")
        
        for strategy_name, strategy in self.strategy_engine.strategies.items():
            if strategy.inited:
                self.strategy_engine.start_strategy(strategy_name)
                self.logger.info(f"策略 {strategy_name} 已启动")
            else:
                self.logger.warning(f"策略 {strategy_name} 未完成初始化，跳过启动")
        
        self.strategies_started = True
    
    def _run_event_loop(self) -> None:
        """运行事件循环"""
        self.logger.info("进入事件循环")
        
        while self.running:
            self._maybe_update_option_recording_targets()
            time.sleep(1.0)

    def _maybe_update_option_recording_targets(self) -> None:
        if not self.recorder_engine:
            return

        now_ts = time.time()
        if now_ts - self._last_option_recording_update_ts < 60.0:
            return
        self._last_option_recording_update_ts = now_ts

        if not self.main_engine:
            return

        active_underlyings = self._get_active_underlying_vt_symbols()
        if not active_underlyings:
            return

        all_contracts = self.main_engine.get_all_contracts()
        if not all_contracts:
            return

        for underlying_vt_symbol in active_underlyings:
            tick = self.main_engine.get_tick(underlying_vt_symbol)
            underlying_price = float(getattr(tick, "last_price", 0) or 0)
            if underlying_price <= 0:
                continue

            option_targets = self._select_option_vt_symbols_for_recording(
                all_contracts=all_contracts,
                underlying_vt_symbol=underlying_vt_symbol,
                underlying_price=underlying_price,
                otm_level=5,
                buffer_level=5,
            )

            for vt_symbol in option_targets:
                self._subscribe_and_record_bar(vt_symbol, register_to_strategy=False)

    def _get_active_underlying_vt_symbols(self) -> List[str]:
        result: List[str] = []
        seen: Set[str] = set()

        if not self.strategy_engine or not hasattr(self.strategy_engine, "strategies"):
            return result

        strategies = getattr(self.strategy_engine, "strategies", {}) or {}
        for strategy in strategies.values():
            # 优先直接从策略实例获取 target_aggregate (pragmatic DDD)
            # 兼容旧版通过 app_service 间接获取
            target_aggregate = getattr(strategy, "target_aggregate", None)
            if not target_aggregate:
                app_service = getattr(strategy, "app_service", None)
                if app_service:
                    target_aggregate = getattr(app_service, "target_aggregate", None)
            if not target_aggregate or not hasattr(target_aggregate, "get_all_active_contracts"):
                continue
            try:
                vt_symbols = list(target_aggregate.get_all_active_contracts() or [])
            except Exception:
                continue
            for vt_symbol in vt_symbols:
                if vt_symbol and vt_symbol not in seen:
                    seen.add(vt_symbol)
                    result.append(vt_symbol)

        return result

    def _select_option_vt_symbols_for_recording(
        self,
        all_contracts: Iterable[Any],
        underlying_vt_symbol: str,
        underlying_price: float,
        otm_level: int,
        buffer_level: int,
    ) -> List[str]:
        underlying_contract = self.main_engine.get_contract(underlying_vt_symbol) if self.main_engine else None
        underlying_symbol = getattr(underlying_contract, "symbol", "") if underlying_contract else ""
        underlying_exchange = getattr(getattr(underlying_contract, "exchange", None), "value", "") if underlying_contract else ""

        candidates: List[Tuple[str, float]] = []
        for c in all_contracts:
            option_type = getattr(c, "option_type", None)
            if option_type is None:
                continue

            vt_symbol = getattr(c, "vt_symbol", "")
            if not vt_symbol:
                continue

            underlying_field = (
                getattr(c, "underlying_symbol", None)
                or getattr(c, "option_underlying", None)
                or getattr(c, "underlying", None)
                or getattr(c, "underlying_vt_symbol", None)
            )
            if not underlying_field:
                continue

            underlying_field_str = str(underlying_field)
            matches = False
            if underlying_vt_symbol == underlying_field_str:
                matches = True
            elif underlying_symbol and underlying_symbol == underlying_field_str:
                matches = True
            elif underlying_symbol and underlying_exchange and f"{underlying_symbol}.{underlying_exchange}" == underlying_field_str:
                matches = True
            elif underlying_symbol and underlying_field_str.startswith(underlying_symbol):
                matches = True

            if not matches:
                continue

            strike_raw = (
                getattr(c, "option_strike", None)
                or getattr(c, "strike_price", None)
                or getattr(c, "strike", None)
                or getattr(c, "option_strike_price", None)
            )
            try:
                strike = float(strike_raw)
            except Exception:
                continue

            candidates.append((vt_symbol, strike))

        if not candidates:
            return []

        strikes = sorted({s for _, s in candidates})
        atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - underlying_price))
        steps = max(otm_level + buffer_level, 1)
        low_idx = max(atm_idx - steps, 0)
        high_idx = min(atm_idx + steps, len(strikes) - 1)
        selected_strikes = set(strikes[low_idx : high_idx + 1])

        targets: List[str] = []
        seen: Set[str] = set()
        for vt_symbol, strike in candidates:
            if strike in selected_strikes and vt_symbol not in seen:
                seen.add(vt_symbol)
                targets.append(vt_symbol)
        return targets

    def _subscribe_and_record_bar(self, vt_symbol: str, register_to_strategy: bool) -> None:
        if not self.main_engine:
            return

        if vt_symbol in self._recording_only_recorded:
            return

        contract = self.main_engine.get_contract(vt_symbol)
        if not contract:
            return

        try:
            from vnpy.trader.object import SubscribeRequest
        except Exception:
            return

        try:
            if register_to_strategy:
                req = SubscribeRequest(symbol=contract.symbol, exchange=contract.exchange)
                self.main_engine.subscribe(req, contract.gateway_name)
            else:
                if vt_symbol not in self._recording_only_subscribed:
                    req = SubscribeRequest(symbol=contract.symbol, exchange=contract.exchange)
                    self.main_engine.subscribe(req, contract.gateway_name)
                    self._recording_only_subscribed.add(vt_symbol)

            if self.recorder_engine and hasattr(self.recorder_engine, "add_bar_recording"):
                self.recorder_engine.add_bar_recording(vt_symbol)
                self._recording_only_recorded.add(vt_symbol)
        except Exception:
            return
    
    def shutdown(self) -> None:
        """关闭工作进程"""
        if self._is_shutdown:
            return
            
        self.logger.info("工作进程开始关闭流程...")
        self._is_shutdown = True
        self.running = False
        
        # 停止所有策略
        if self.strategy_engine and self.strategies_started:
            self.logger.info("开始停止所有策略...")
            # 这里的 strategies 是一个 dict: {strategy_name: strategy_instance}
            strategies = getattr(self.strategy_engine, "strategies", {})
            for strategy_name in list(strategies.keys()):
                self.logger.info(f"正在停止策略: {strategy_name}")
                try:
                    # 调用 stop_strategy 会触发 on_stop 回调
                    self.strategy_engine.stop_strategy(strategy_name)
                except Exception as e:
                    self.logger.error(f"停止策略 {strategy_name} 时发生异常: {e}")
            self.logger.info("所有策略停止指令已发出")
        
        # 断开网关
        if self.gateway_manager:
            self.logger.info("正在断开网关...")
            self.gateway_manager.disconnect_all()
        elif self.main_engine:
            # 如果没有 gateway_manager，直接关闭主引擎
            self.logger.info("关闭主引擎...")
            self.main_engine.close()
        
        self.logger.info("工作进程关闭流程结束")


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="策略工作进程")
    
    parser.add_argument("--config", required=True)
    parser.add_argument("--override-config", help="覆盖配置文件路径")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument("--log-name", default="strategy.log")
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    # 临时处理 args 中没有 paper 参数的情况 (因为 parse_args 是在这个文件中定义的，而 main.py 也有定义)
    # 为了保持一致性，建议统一由 main.py 启动
    paper_trading = False
    if "--paper" in sys.argv:
        paper_trading = True

    # 配置日志
    setup_logging(args.log_level, args.log_dir, args.log_name)
    
    child = ChildProcess(
        config_path=args.config,
        override_config_path=args.override_config,
        log_level=args.log_level,
        log_dir=args.log_dir,
        paper_trading=paper_trading
    )
    
    child.run()
