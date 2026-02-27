"""
回测执行器

编排完整的回测流程：加载配置、生成合约代码、发现期权、注册合约、
配置引擎、加载数据、运行回测、计算结果。
"""

import logging
from datetime import datetime
from typing import Dict, List

from src.backtesting.config import BacktestConfig, PRODUCT_SPECS, DEFAULT_PRODUCT_SPEC
from src.backtesting.contract.contract_registry import ContractRegistry
from src.backtesting.discovery.symbol_generator import SymbolGenerator
from src.backtesting.discovery.option_discovery import OptionDiscoveryService
from src.main.config.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class BacktestRunner:
    """回测执行器，编排完整回测流程。"""

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.registry = ContractRegistry()

    def run(self) -> None:
        """执行完整回测流程。"""
        # 延迟导入 VnPy 依赖（测试环境可能不可用）
        from vnpy.trader.constant import Interval
        from vnpy_portfoliostrategy import BacktestingEngine
        from src.strategy.strategy_entry import StrategyEntry

        # 1. 加载策略配置
        logger.info("正在从 %s 加载配置...", self.config.config_path)
        config = ConfigLoader.load_yaml(self.config.config_path)

        if not config.get("strategies"):
            logger.error("错误: 配置中未找到策略。")
            return

        strategy_config = config["strategies"][0]
        vt_symbols_config: List[str] = strategy_config.get("vt_symbols", [])
        setting: Dict = strategy_config.get("setting", {})

        # 2. 获取品种列表
        target_products: List[str] = vt_symbols_config
        if not vt_symbols_config:
            logger.info("vt_symbols 为空，正在从 trading_target.toml 加载品种列表...")
            target_products = ConfigLoader.load_target_products()

        # 3. 生成 vt_symbols
        vt_symbols: List[str] = []
        for product in target_products:
            generated = SymbolGenerator.generate_recent(product)
            vt_symbols.extend(generated)

        vt_symbols = sorted(set(vt_symbols))

        # 4. 发现关联期权合约
        logger.info("正在从数据库查找关联期权合约...")
        option_symbols = OptionDiscoveryService.discover(vt_symbols)
        if option_symbols:
            logger.info("找到 %d 个期权合约", len(option_symbols))
            vt_symbols.extend(option_symbols)
            vt_symbols = sorted(set(vt_symbols))

        # Req 9.5: 空 vt_symbols 时终止执行
        if not vt_symbols:
            logger.error("无法生成有效的 vt_symbols，终止回测。")
            return

        # 5. 注册合约到 ContractRegistry
        registered = self.registry.register_many(vt_symbols)
        logger.info("已注册 %d 个合约", registered)

        # 6. 初始化回测引擎并注入合约
        engine = BacktestingEngine()
        self.registry.inject_into_engine(engine)

        # 7. 设置引擎参数（按合约动态获取 size/pricetick）
        rates: Dict[str, float] = {s: self.config.rate for s in vt_symbols}
        slippages: Dict[str, float] = {s: self.config.slippage for s in vt_symbols}
        sizes: Dict[str, int] = {}
        priceticks: Dict[str, float] = {}

        for vt_symbol in vt_symbols:
            contract = self.registry.get(vt_symbol)
            if contract:
                sizes[vt_symbol] = contract.size
                priceticks[vt_symbol] = contract.pricetick
            else:
                sizes[vt_symbol] = self.config.default_size
                priceticks[vt_symbol] = self.config.default_pricetick

        end_date = self.config.get_end_date()

        engine.set_parameters(
            vt_symbols=vt_symbols,
            interval=Interval.MINUTE,
            start=datetime.strptime(self.config.start_date, "%Y-%m-%d"),
            end=datetime.strptime(end_date, "%Y-%m-%d"),
            rates=rates,
            slippages=slippages,
            sizes=sizes,
            priceticks=priceticks,
            capital=self.config.capital,
        )

        # 8. 设置策略参数
        if not setting.get("underlying_symbols"):
            setting["underlying_symbols"] = target_products
        setting["backtesting"] = True

        engine.add_strategy(strategy_class=StrategyEntry, setting=setting)

        # 9. 加载数据、运行回测、计算结果
        logger.info("正在加载数据...")
        engine.load_data()

        logger.info("正在运行回测...")
        engine.run_backtesting()

        logger.info("正在计算结果...")
        engine.calculate_result()
        engine.calculate_statistics()

        # Req 9.4: 显示图表
        if self.config.show_chart:
            engine.show_chart()
