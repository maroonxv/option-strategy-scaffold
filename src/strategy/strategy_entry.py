"""
StrategyEntry - 商品波动率策略入口 (Pragmatic DDD)

VnPy 策略模板实现，同时充当应用层。
on_* 回调直接编排领域逻辑，不再经过独立的 Application Service。

设计原则:
1. StrategyEntry = 接口层 + 应用层 (pragmatic approach)
2. 领域逻辑仍然封装在 domain 层 (聚合根、领域服务)
3. 基础设施逻辑仍然封装在 infrastructure 层 (网关、持久化、监控)
4. 依赖注入: self 直接持有领域服务和基础设施组件
"""
from typing import Any, Dict, List, Optional
from pathlib import Path
import os
from datetime import datetime, date


from vnpy_portfoliostrategy import StrategyTemplate, StrategyEngine
from vnpy.trader.object import BarData, OrderData, TradeData, PositionData, TickData
from vnpy.trader.constant import Interval

from src.strategy.infrastructure.bar_pipeline import BarPipeline
from vnpy.event.engine import Event


from .domain.aggregate.target_instrument_aggregate import InstrumentManager
from .domain.aggregate.position_aggregate import PositionAggregate
from .domain.domain_service.indicator_service import IndicatorService
from .domain.domain_service.signal_service import SignalService
# NOTE: IndicatorService 和 SignalService 是模板类，
# 使用前请根据策略需求实现 calculate_bar() / check_open_signal() / check_close_signal()
from .domain.domain_service.position_sizing_service import PositionSizingService
from .domain.domain_service.option_selector_service import OptionSelectorService
from .domain.domain_service.future_selection_service import BaseFutureSelector
from .domain.domain_service.greeks_calculator import GreeksCalculator
from .domain.domain_service.portfolio_risk_aggregator import PortfolioRiskAggregator
from .domain.domain_service.smart_order_executor import SmartOrderExecutor
from .domain.entity.position import Position
from .domain.event.event_types import (
    EVENT_STRATEGY_ALERT,
    DomainEvent,
    ManualCloseDetectedEvent,
    ManualOpenDetectedEvent,
    RiskLimitExceededEvent,
    GreeksRiskBreachEvent,
    OrderTimeoutEvent,
    OrderRetryExhaustedEvent,
    StrategyAlertData,
)
from .domain.value_object.risk import RiskThresholds
from .domain.value_object.order_execution import OrderExecutionConfig
from .infrastructure.gateway.vnpy_market_data_gateway import VnpyMarketDataGateway
from .infrastructure.gateway.vnpy_account_gateway import VnpyAccountGateway
from .infrastructure.gateway.vnpy_trade_execution_gateway import VnpyTradeExecutionGateway
from .infrastructure.reporting.feishu_handler import FeishuEventHandler
from .infrastructure.logging.logging_utils import setup_strategy_logger
from .infrastructure.monitoring.strategy_monitor import StrategyMonitor
from .infrastructure.persistence.state_repository import StateRepository, ArchiveNotFound
from .infrastructure.persistence.json_serializer import JsonSerializer
from .infrastructure.persistence.migration_chain import MigrationChain
from .infrastructure.persistence.auto_save_service import AutoSaveService
from .infrastructure.persistence.exceptions import CorruptionError
from .infrastructure.persistence.history_data_repository import HistoryDataRepository
from src.main.bootstrap.database_factory import DatabaseFactory
from .infrastructure.utils.contract_helper import ContractHelper


class StrategyEntry(StrategyTemplate):
    """
    商品波动率策略 (Pragmatic DDD)

    职责:
    1. VnPy 回调入口 (on_* 方法)
    2. 编排领域逻辑 (原 StrategyEngine 的 handle_* 职责)
    3. 组装依赖 (在 on_init 中初始化领域服务和基础设施)

    参数:
    - feishu_webhook: 飞书群机器人 Webhook URL
    - max_positions: 最大持仓数量
    - position_ratio: 单次开仓资金比例
    - strike_level: 虚值档位
    """

    # 策略参数
    author = "Hongxu Lai"

    # 标的合约列表 (期货)
    underlying_symbols: list = []

    # 飞书通知
    feishu_webhook: str = ""

    # 仓位管理
    max_positions: int = 5
    position_ratio: float = 0.1

    # 期权选择
    strike_level: int = 3

    # VnPy 参数声明
    parameters = [
        "feishu_webhook",
        "max_positions",
        "position_ratio",
        "strike_level",
    ]

    def __init__(
        self,
        strategy_engine: StrategyEngine,
        strategy_name: str,
        vt_symbols: list,
        setting: dict
    ) -> None:
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        # ── 日志 ──
        log_dir_setting = setting.get("log_dir", "")
        log_filename = "strategy.log"
        if log_dir_setting:
            sep = "data/logs" if "data/logs" in log_dir_setting else (
                "data\\logs" if "data\\logs" in log_dir_setting else ""
            )
            if sep:
                relative_log_dir = os.path.relpath(log_dir_setting, os.path.join("data", "logs"))
                if relative_log_dir != ".":
                    log_filename = os.path.join(relative_log_dir, "strategy.log")
        self.logger = setup_strategy_logger(self.strategy_name, log_filename)

        # ── 基础设施: 历史数据仓库 ──
        self.history_repo = HistoryDataRepository(self.logger)

        # ── 运行模式标志 ──
        self.paper_trading = setting.get("paper_trading", False)
        self.backtesting = setting.get("backtesting", False)
        self.warmup_days: int = int(setting.get("warmup_days", 5 if self.backtesting else 30))

        # ── 领域聚合根 (在 on_init 中初始化) ──
        self.target_aggregate: Optional[InstrumentManager] = None
        self.position_aggregate: Optional[PositionAggregate] = None

        # ── 领域服务 (在 on_init 中初始化) ──
        self.indicator_service: Optional[IndicatorService] = None
        self.signal_service: Optional[SignalService] = None
        self.position_sizing_service: Optional[PositionSizingService] = None
        self.future_selection_service: Optional[BaseFutureSelector] = None
        self.option_selector_service: Optional[OptionSelectorService] = None
        self.greeks_calculator: Optional[GreeksCalculator] = None
        self.portfolio_risk_aggregator: Optional[PortfolioRiskAggregator] = None
        self.smart_order_executor: Optional[SmartOrderExecutor] = None

        # ── 基础设施网关 (在 on_init 中初始化) ──
        self.market_gateway: Optional[VnpyMarketDataGateway] = None
        self.account_gateway: Optional[VnpyAccountGateway] = None
        self.exec_gateway: Optional[VnpyTradeExecutionGateway] = None

        # ── 基础设施: 监控与持久化 (在 on_init 中初始化) ──
        self.monitor: Optional[StrategyMonitor] = None
        self.state_repository: Optional[StateRepository] = None
        self.auto_save_service: Optional[AutoSaveService] = None

        # ── 飞书 ──
        self.feishu_handler: Optional[FeishuEventHandler] = None

        # ── K线合成管道 ──
        self.bar_pipeline: Optional[BarPipeline] = None

        # ── 配置上下文 ──
        self.target_products: List[str] = []

        # ── 运行时状态 ──
        self.rollover_check_done: bool = False
        self.universe_check_interval: int = 0
        self.universe_check_threshold: int = 60
        self.last_bars: Dict[str, BarData] = {}
        self.warming_up: bool = False
        self.current_dt: datetime = datetime.now()

    # ═══════════════════════════════════════════════════════════════════
    #  VnPy 生命周期回调
    # ═══════════════════════════════════════════════════════════════════

    def on_init(self) -> None:
        """
        策略初始化回调

        组装依赖并初始化:
        1. 加载交易品种配置
        2. 创建领域服务
        3. 创建领域聚合根
        4. 创建基础设施组件 (网关、监控、持久化)
        5. 初始化K线生成器
        6. warmup
        7. 注册飞书告警
        """
        self.logger.info("策略初始化...")

        # ______________________________  1. 加载交易品种配置  ______________________________

        from src.main.config.config_loader import ConfigLoader
        self.target_products = ConfigLoader.load_target_products()
        if not self.target_products:
            self.logger.error("未配置任何交易品种，请先检查并配置 target_products.yaml")
            raise RuntimeError("策略初始化失败：未配置交易品种")
        self.logger.info(f"已加载配置的标的: {len(self.target_products)} 个品种")

        # ______________________________  2. 创建领域服务  ______________________________

        self.indicator_service = IndicatorService()
        self.signal_service = SignalService()
        self.position_sizing_service = PositionSizingService(
            max_positions=self.max_positions,
            position_ratio=self.position_ratio
        )
        self.future_selection_service = BaseFutureSelector()
        self.option_selector_service = OptionSelectorService(
            strike_level=self.strike_level
        )

        # ── Greeks 风控 & 订单执行增强 ──
        try:
            strategy_config_path = str(Path(__file__).resolve().parents[2] / "config" / "strategy_config.yaml")
            full_config = ConfigLoader.load_yaml(strategy_config_path)
        except Exception:
            full_config = {}

        greeks_risk_cfg = full_config.get("greeks_risk", {})
        position_limits = greeks_risk_cfg.get("position_limits", {})
        portfolio_limits = greeks_risk_cfg.get("portfolio_limits", {})

        risk_thresholds = RiskThresholds(
            position_delta_limit=position_limits.get("delta", 0.8),
            position_gamma_limit=position_limits.get("gamma", 0.1),
            position_vega_limit=position_limits.get("vega", 50.0),
            portfolio_delta_limit=portfolio_limits.get("delta", 5.0),
            portfolio_gamma_limit=portfolio_limits.get("gamma", 1.0),
            portfolio_vega_limit=portfolio_limits.get("vega", 500.0),
        )

        order_exec_cfg = full_config.get("order_execution", {})
        order_config = OrderExecutionConfig(
            timeout_seconds=order_exec_cfg.get("timeout_seconds", 30),
            max_retries=order_exec_cfg.get("max_retries", 3),
            slippage_ticks=order_exec_cfg.get("slippage_ticks", 2),
        )

        self.greeks_calculator = GreeksCalculator()
        self.portfolio_risk_aggregator = PortfolioRiskAggregator(risk_thresholds)
        self.smart_order_executor = SmartOrderExecutor(order_config)
        self.logger.info(f"Greeks 风控已启用: position_limits={position_limits}, portfolio_limits={portfolio_limits}")
        self.logger.info(f"订单执行增强已启用: timeout={order_config.timeout_seconds}s, max_retries={order_config.max_retries}")

        # ______________________________  3. 创建领域聚合根  ______________________________

        self.target_aggregate = InstrumentManager()
        self.position_aggregate = PositionAggregate()

        # ______________________________  4. 创建基础设施组件  ______________________________

        self.market_gateway = VnpyMarketDataGateway(self)
        self.account_gateway = VnpyAccountGateway(self)
        self.exec_gateway = VnpyTradeExecutionGateway(self)

        variant_name = self.strategy_name
        project_root = Path(__file__).resolve().parents[2]
        snapshot_path = str(project_root / "data" / "monitor" / f"snapshot_{variant_name}.pkl")

        monitor_db_config = {
            "host": os.getenv("VNPY_DATABASE_HOST", "") or "",
            "port": int(os.getenv("VNPY_DATABASE_PORT", "3306") or 3306),
            "user": os.getenv("VNPY_DATABASE_USER", "") or "",
            "password": os.getenv("VNPY_DATABASE_PASSWORD", "") or "",
            "database": os.getenv("VNPY_DATABASE_DATABASE", "") or "",
        }
        self.monitor = StrategyMonitor(
            variant_name=variant_name,
            monitor_instance_id=os.getenv("MONITOR_INSTANCE_ID", "default") or "default",
            snapshot_path=snapshot_path,
            monitor_db_config=monitor_db_config,
            logger=self.logger
        )
        self.state_repository = StateRepository(
            serializer=JsonSerializer(MigrationChain()),
            database_factory=DatabaseFactory.get_instance(),
            logger=self.logger,
        )

        # AutoSaveService 仅在非回测模式下创建
        if not self.backtesting:
            self.auto_save_service = AutoSaveService(
                state_repository=self.state_repository,
                strategy_name=self.strategy_name,
                interval_seconds=60.0,
                logger=self.logger,
            )

        # 初始快照
        self._record_snapshot()

        # ______________________________  5. 初始化K线合成管道  ______________________________

        bar_window = int(self.setting.get("bar_window", 0))
        if bar_window > 0:
            bar_interval_str = self.setting.get("bar_interval", "MINUTE")
            interval_map = {
                "MINUTE": Interval.MINUTE,
                "HOUR": Interval.HOUR,
                "DAILY": Interval.DAILY,
            }
            interval = interval_map.get(bar_interval_str, Interval.MINUTE)
            self.bar_pipeline = BarPipeline(
                bar_callback=self._process_bars,
                window=bar_window,
                interval=interval,
            )
            self.logger.info(f"K线合成管道已启用: {bar_window}{bar_interval_str}")
        else:
            self.logger.info("未配置K线合成，使用直通模式")

        # ______________________________  6. warmup  ______________________________

        original_trading = getattr(self, "trading", True)

        if self.backtesting:
            self.logger.info("当前处于回测模式，跳过状态恢复，直接加载历史数据进行初始化")
            self.warming_up = True
            setattr(self, "trading", False)
            try:
                self.load_bars(self.warmup_days)
            except Exception:
                self.logger.error("回测 warmup 失败", exc_info=True)
                raise
            finally:
                setattr(self, "trading", original_trading)
                self.warming_up = False
        else:
            # 实盘 warmup: load_state + universe_validation + MySQL replay
            try:
                result = self.state_repository.load(self.strategy_name)
                if isinstance(result, ArchiveNotFound):
                    self.logger.info(f"首次启动，无历史状态: {self.strategy_name}")
                else:
                    # Restore aggregates from snapshot
                    if "target_aggregate" in result:
                        self.target_aggregate = InstrumentManager.from_snapshot(result["target_aggregate"])
                    if "position_aggregate" in result:
                        self.position_aggregate = PositionAggregate.from_snapshot(result["position_aggregate"])
                    if "current_dt" in result:
                        self.current_dt = result["current_dt"]
                    self.logger.info(f"策略状态已恢复: {self.strategy_name}")
            except CorruptionError as e:
                self.logger.error(f"策略状态损坏，拒绝启动: {e}")
                raise
            except Exception:
                self.logger.error(f"加载策略状态失败: {self.strategy_name}", exc_info=True)
                raise

            try:
                self._validate_universe()
            except Exception:
                self.logger.error("实盘补漏/主力合约初始化失败", exc_info=True)
                raise

            active_contracts = list(self.target_aggregate.get_all_active_contracts() or [])
            if isinstance(getattr(self, "vt_symbols", None), list):
                for vt_symbol in active_contracts:
                    if vt_symbol and vt_symbol not in self.vt_symbols:
                        self.vt_symbols.append(vt_symbol)

            self.warming_up = True
            setattr(self, "trading", False)
            try:
                vt_symbols = list(self.target_aggregate.get_all_active_contracts() or [])
                if not vt_symbols and isinstance(getattr(self, "vt_symbols", None), list):
                    vt_symbols = list(self.vt_symbols)

                ok = self.history_repo.replay_bars_from_database(
                    vt_symbols=vt_symbols,
                    days=self.warmup_days,
                    on_bars_callback=self.on_bars,  # on_bars 内部根据 bar_pipeline 分支
                )
                if not ok:
                    self.logger.error("实盘 warmup 失败: MySQL 中未能回放到有效 K 线")
                    raise RuntimeError("live warmup failed")
            except Exception:
                self.logger.error("实盘 warmup 执行失败（可能是 BarPipeline 处理异常）", exc_info=True)
                raise
            finally:
                setattr(self, "trading", original_trading)
                self.warming_up = False

        # ______________________________  7. 注册飞书告警  ______________________________

        if self.feishu_webhook:
            self.feishu_handler = FeishuEventHandler(
                webhook_url=self.feishu_webhook,
                strategy_name=self.strategy_name
            )
            if hasattr(self, "strategy_engine") and hasattr(self.strategy_engine, "event_engine"):
                self.strategy_engine.event_engine.register(
                    EVENT_STRATEGY_ALERT,
                    self.feishu_handler.handle_alert_event
                )
                self.logger.info("飞书通知已启用")

        self.logger.info("策略初始化完成")

    def on_start(self) -> None:
        """策略启动回调"""
        try:
            super().on_start()
        except Exception:
            pass
        self.logger.info("策略启动")
        self._validate_universe()

    def on_stop(self) -> None:
        """策略停止回调"""
        try:
            super().on_stop()
        except Exception:
            pass
        self.logger.info("策略停止")

        # 保存状态 - 仅在非回测模式下
        if self.auto_save_service:
            self.auto_save_service.force_save(self._create_snapshot)

        # 注销飞书处理器
        if self.feishu_handler:
            if hasattr(self, "strategy_engine") and hasattr(self.strategy_engine, "event_engine"):
                try:
                    self.strategy_engine.event_engine.unregister(
                        EVENT_STRATEGY_ALERT,
                        self.feishu_handler.handle_alert_event
                    )
                except Exception:
                    pass

    # ═══════════════════════════════════════════════════════════════════
    #  VnPy 数据回调 — 直接编排领域逻辑
    # ═══════════════════════════════════════════════════════════════════

    def on_tick(self, tick: TickData) -> None:
        """Tick 推送回调"""
        if self.bar_pipeline:
            self.bar_pipeline.handle_tick(tick)

    def on_bars(self, bars: Dict[str, BarData]) -> None:
        """
        K 线推送回调（1分钟K线）

        如果启用了K线合成器，则推送给合成器；否则直接处理。
        同时处理换月检查和补漏检查。
        """
        self.last_bars.update(bars)

        if self.target_aggregate and not self.warming_up:
            first_bar = next(iter(bars.values()))
            current_dt = first_bar.datetime

            # 每日换月检查 (14:50)
            if current_dt.hour == 14 and current_dt.minute == 50:
                if not self.rollover_check_done:
                    self.logger.info(f"触发每日换月检查: {current_dt}")
                    self._check_universe_rollover(current_dt)
                    self.rollover_check_done = True
            else:
                self.rollover_check_done = False

            # 定期补漏检查
            self.universe_check_interval += 1
            if self.universe_check_interval >= self.universe_check_threshold:
                self.universe_check_interval = 0
                self._validate_universe()

        if self.bar_pipeline:
            self.bar_pipeline.handle_bars(bars)
        else:
            self._process_bars(bars)

        # 周期性自动保存 (非回测模式)
        if self.auto_save_service and not self.warming_up:
            self.auto_save_service.maybe_save(self._create_snapshot)

    def on_order(self, order: OrderData) -> None:
        """
        订单推送回调 — 直接更新 PositionAggregate
        """
        if not self.position_aggregate:
            return
        order_data = {
            "vt_orderid": order.vt_orderid,
            "vt_symbol": order.vt_symbol,
            "direction": order.direction.value if hasattr(order.direction, "value") else str(order.direction),
            "offset": order.offset.value if hasattr(order.offset, "value") else str(order.offset),
            "price": order.price,
            "volume": order.volume,
            "traded": order.traded,
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
        }
        self.position_aggregate.update_from_order(order_data)
        self._publish_domain_events()

    def on_trade(self, trade: TradeData) -> None:
        """
        成交推送回调 — 直接更新 PositionAggregate
        """
        if not self.position_aggregate:
            return
        trade_data = {
            "vt_tradeid": trade.vt_tradeid,
            "vt_orderid": trade.vt_orderid,
            "vt_symbol": trade.vt_symbol,
            "direction": trade.direction.value if hasattr(trade.direction, "value") else str(trade.direction),
            "offset": trade.offset.value if hasattr(trade.offset, "value") else str(trade.offset),
            "price": trade.price,
            "volume": trade.volume,
            "datetime": trade.datetime,
        }
        self.position_aggregate.update_from_trade(trade_data)
        self._publish_domain_events()

    def process_position_event(self, event: Event) -> None:
        """自定义的持仓事件处理函数"""
        self.on_position(event.data)

    def on_position(self, position: PositionData) -> None:
        """
        持仓推送回调 — 直接更新 PositionAggregate (检测手动平仓)
        """
        if not self.position_aggregate:
            return
        position_data = {
            "vt_symbol": position.vt_symbol,
            "direction": position.direction.value if hasattr(position.direction, "value") else str(position.direction),
            "volume": position.volume,
            "frozen": position.frozen,
            "price": position.price,
            "pnl": position.pnl,
        }
        self.position_aggregate.update_from_position(position_data)
        self._publish_domain_events()

    # ═══════════════════════════════════════════════════════════════════
    #  核心编排逻辑 (原 StrategyEngine.handle_* 的职责)
    # ═══════════════════════════════════════════════════════════════════

    def _process_bars(self, bars: Dict[str, BarData]) -> None:
        """
        处理 K 线更新 — 编排领域逻辑

        流程:
        1. 更新行情数据到 InstrumentManager
        2. 调用 IndicatorService 计算指标
        3. 调用 SignalService 检查开平仓信号
        4. 协调开平仓业务流程
        5. 记录监控快照
        """
        if not self.target_aggregate:
            return

        for vt_symbol, bar in bars.items():
            bar_data = {
                "datetime": bar.datetime,
                "open": bar.open_price,
                "high": bar.high_price,
                "low": bar.low_price,
                "close": bar.close_price,
                "volume": bar.volume,
            }
            self.current_dt = bar.datetime

            try:
                # 1. 更新行情数据
                instrument = self.target_aggregate.update_bar(vt_symbol, bar_data)

                # 2. 计算指标
                try:
                    self.indicator_service.calculate_bar(instrument, bar_data)
                except Exception as e:
                    self.logger.error(f"指标计算失败 [{vt_symbol}]: {e}")
                    continue

                # 3. 检查开仓信号
                try:
                    open_signal = self.signal_service.check_open_signal(instrument)
                    if open_signal:
                        self.logger.info(f"检测到开仓信号 [{vt_symbol}]: {open_signal}")
                        self._execute_open(vt_symbol, open_signal)
                except Exception as e:
                    self.logger.error(f"开仓信号检查失败 [{vt_symbol}]: {e}")

                # 4. 检查平仓信号
                try:
                    positions = self.position_aggregate.get_positions_by_underlying(vt_symbol)
                    for position in positions:
                        close_signal = self.signal_service.check_close_signal(
                            instrument, position
                        )
                        if close_signal:
                            self.logger.info(
                                f"检测到平仓信号 [{position.vt_symbol}]: {close_signal}"
                            )
                            self._execute_close(position, close_signal)
                except Exception as e:
                    self.logger.error(f"平仓信号检查失败 [{vt_symbol}]: {e}")

            except Exception as e:
                self.logger.error(f"处理 K 线更新失败 [{vt_symbol}]: {e}")

        # 5. 记录快照
        self._record_snapshot()

    def _execute_open(self, underlying_vt_symbol: str, signal: str) -> None:
        """
        执行开仓逻辑

        Args:
            underlying_vt_symbol: 标的合约代码
            signal: 开仓信号字符串
        """
        # TODO: 实现完整开仓逻辑
        # 1. 调用 OptionSelectorService 选择期权合约
        # 2. 调用 PositionSizingService 计算仓位
        # 3. 调用 VnpyTradeExecutionGateway 下单
        # 4. 在 PositionAggregate 中创建持仓记录
        self.logger.info(f"执行开仓: {underlying_vt_symbol}, 信号: {signal}")

    def _execute_close(self, position: Position, signal: str) -> None:
        """
        执行平仓逻辑

        Args:
            position: 持仓对象
            signal: 平仓信号字符串
        """
        # TODO: 实现完整平仓逻辑
        # 1. 调用 PositionSizingService 计算平仓量
        # 2. 调用 VnpyTradeExecutionGateway 下单
        self.logger.info(f"执行平仓: {position.vt_symbol}, 信号: {signal}")

    # ═══════════════════════════════════════════════════════════════════
    #  Universe 管理 (原 handle_universe_validation / handle_universe_rollover_check)
    # ═══════════════════════════════════════════════════════════════════

    def _validate_universe(self) -> None:
        """
        验证并初始化主力合约 (补漏)

        遍历 target_products，为每个品种:
        1. 检查是否已有活跃合约
        2. 如果没有，通过 FutureSelectionService 选择主力合约
        3. 订阅行情并注册到 InstrumentManager
        """
        if not self.target_aggregate or not self.market_gateway:
            return

        for product in self.target_products:
            existing = self.target_aggregate.get_active_contract(product)
            if existing:
                continue

            try:
                all_contracts = self.market_gateway.get_all_contracts()
                product_contracts = [
                    c for c in all_contracts
                    if ContractHelper.is_contract_of_product(c, product)
                ]
                if not product_contracts:
                    self.logger.warning(f"品种 {product} 未找到可用合约")
                    continue

                dominant = self.future_selection_service.select_dominant_contract(
                    product_contracts, date.today(), log_func=self.logger.info
                )
                if dominant:
                    vt_symbol = dominant.vt_symbol
                    self.target_aggregate.set_active_contract(product, vt_symbol)
                    self.target_aggregate.get_or_create_instrument(vt_symbol)
                    self.market_gateway.subscribe(vt_symbol)
                    self.logger.info(f"品种 {product} 主力合约: {vt_symbol}")
            except Exception as e:
                self.logger.error(f"品种 {product} 主力合约初始化失败: {e}")

    def _check_universe_rollover(self, current_dt: datetime) -> None:
        """
        检查合约换月

        遍历 target_products，检查是否需要切换到新的主力合约。
        """
        if not self.target_aggregate or not self.market_gateway:
            return

        for product in self.target_products:
            try:
                current_vt = self.target_aggregate.get_active_contract(product)
                if not current_vt:
                    continue

                all_contracts = self.market_gateway.get_all_contracts()
                product_contracts = [
                    c for c in all_contracts
                    if ContractHelper.is_contract_of_product(c, product)
                ]
                if not product_contracts:
                    continue

                dominant = self.future_selection_service.select_dominant_contract(
                    product_contracts, current_dt.date(), log_func=self.logger.info
                )
                if dominant and dominant.vt_symbol != current_vt:
                    new_vt = dominant.vt_symbol
                    self.logger.info(
                        f"品种 {product} 换月: {current_vt} -> {new_vt}"
                    )
                    self.target_aggregate.set_active_contract(product, new_vt)
                    self.target_aggregate.get_or_create_instrument(new_vt)
                    self.market_gateway.subscribe(new_vt)
            except Exception as e:
                self.logger.error(f"品种 {product} 换月检查失败: {e}")

    # ═══════════════════════════════════════════════════════════════════
    #  状态持久化
    # ═══════════════════════════════════════════════════════════════════

    def _create_snapshot(self) -> Dict[str, Any]:
        """创建聚合根快照用于持久化"""
        return {
            "target_aggregate": self.target_aggregate.to_snapshot(),
            "position_aggregate": self.position_aggregate.to_snapshot(),
            "current_dt": self.current_dt,
        }

    # ═══════════════════════════════════════════════════════════════════
    #  监控与事件
    # ═══════════════════════════════════════════════════════════════════

    def _record_snapshot(self) -> None:
        """记录状态快照到监控系统"""
        if not self.monitor or not self.target_aggregate:
            return
        try:
            self.monitor.record_snapshot(
                self.target_aggregate,
                self.position_aggregate,
                self
            )
        except Exception as e:
            self.logger.error(f"记录快照失败: {e}")

    def _publish_domain_events(self) -> None:
        """
        从 PositionAggregate 提取领域事件并发布到 VnPy EventEngine
        """
        if not self.position_aggregate:
            return

        events = self.position_aggregate.pop_domain_events()
        if not events:
            return

        event_engine = None
        if hasattr(self, "strategy_engine") and hasattr(self.strategy_engine, "event_engine"):
            event_engine = self.strategy_engine.event_engine

        for domain_event in events:
            # 日志记录
            self.logger.info(f"领域事件: {domain_event.event_name} - {domain_event}")

            # 发布到 EventEngine (飞书等订阅者会收到)
            if event_engine:
                if isinstance(domain_event, (ManualCloseDetectedEvent, ManualOpenDetectedEvent)):
                    alert_type = "manual_close" if isinstance(domain_event, ManualCloseDetectedEvent) else "manual_open"
                    alert_data = StrategyAlertData.from_domain_event(
                        event=domain_event,
                        strategy_name=self.strategy_name,
                        alert_type=alert_type,
                        message=f"{domain_event.event_name}: {domain_event.vt_symbol} x{domain_event.volume}"
                    )
                    vnpy_event = Event(type=EVENT_STRATEGY_ALERT, data=alert_data)
                    event_engine.put(vnpy_event)

                elif isinstance(domain_event, RiskLimitExceededEvent):
                    alert_data = StrategyAlertData.from_domain_event(
                        event=domain_event,
                        strategy_name=self.strategy_name,
                        alert_type="risk_limit",
                        message=f"风控限额超标: {domain_event.limit_type} {domain_event.current_volume}/{domain_event.limit_volume}"
                    )
                    vnpy_event = Event(type=EVENT_STRATEGY_ALERT, data=alert_data)
                    event_engine.put(vnpy_event)
