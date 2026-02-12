import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# 1. 优先加载环境变量
load_dotenv()

# 添加项目根目录到 sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 2. 在导入其他 VnPy 模块之前，先配置数据库
from src.main.bootstrap.database_factory import DatabaseFactory

# 通过 DatabaseFactory 统一初始化数据库
try:
    factory = DatabaseFactory.get_instance()
    factory.initialize(eager=True)
    print(f"[Database] DatabaseFactory 初始化完成")
except Exception as e:
    print(f"[Database Error] 数据库初始化失败: {e}")
    raise

# 4. 开启 Peewee SQL 日志 (Debug) - 保持开启以便验证
import logging
logger = logging.getLogger('peewee')
for handler in logger.handlers[:]:
    logger.removeHandler(handler)
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.setLevel(logging.DEBUG)

# 5. 现在才导入其他 VnPy 模块
from vnpy.trader.constant import Interval
from vnpy_portfoliostrategy import BacktestingEngine
from src.strategy.strategy_entry import StrategyEntry
from src.main.config.config_loader import ConfigLoader
from src.backtesting.vt_symbol_generator import VtSymbolGenerator

def run_backtesting(
    config_path: str = "config/strategy_config.yaml",
    start_date: str = "2025-12-29",
    end_date: str = None,
    capital: int = 1_000_000,
    rate: float = 2.5e-5,
    slippage: float = 0.2,
    size: int = 10,
    pricetick: float = 1.0,
    show_chart: bool = True
):
    """
    运行回测
    """
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # 加载策略配置
    print(f"正在从 {config_path} 加载配置...")
    config = ConfigLoader.load_yaml(config_path)
    
    if not config.get("strategies"):
        print("错误: 配置中未找到策略。")
        return

    strategy_config = config["strategies"][0]
    vt_symbols_config = strategy_config.get("vt_symbols", [])
    setting = strategy_config.get("setting", {})
    strategy_class_name = strategy_config["class_name"]

    target_products = []
    if not vt_symbols_config:
        print("检测到 strategy_config.yaml 中 vt_symbols 为空，正在从 config/general/trading_target.yaml 加载品种列表...")
        target_products = ConfigLoader.load_target_products()
    else:
        target_products = vt_symbols_config

    # 生成标准 vt_symbols
    vt_symbols = []
    for product in target_products:
        generated = VtSymbolGenerator.generate_recent_symbols(product)
        vt_symbols.extend(generated)
    
    vt_symbols = list(set(vt_symbols))
    vt_symbols.sort()

    # --- 新增: 从数据库补全期权合约 ---
    print("正在从数据库查找关联期权合约...")
    try:
        # 此时数据库已通过 DatabaseFactory 初始化
        option_symbols = VtSymbolGenerator.get_available_options_from_db(vt_symbols)
        if option_symbols:
            print(f"找到 {len(option_symbols)} 个期权合约，将加入回测列表")
            vt_symbols.extend(option_symbols)
            # 再次去重排序
            vt_symbols = list(set(vt_symbols))
            vt_symbols.sort()
        else:
            print("未在数据库中找到相关期权合约 (可能是尚未录制数据)")
    except Exception as e:
        print(f"查找期权合约时出错: {e}")
    # -----------------------------------

    if not setting.get("underlying_symbols"):
        setting["underlying_symbols"] = target_products

    # 强制设置 backtesting 标志
    setting["backtesting"] = True

    print(f"策略: {strategy_config['strategy_name']}")
    print(f"类: {strategy_class_name}")
    print(f"原始品种: {target_products}")
    print(f"生成的合约代码 (Total {len(vt_symbols)}): {vt_symbols}")
    print(f"回测范围: {start_date} 至 {end_date}")

    if not vt_symbols:
        print("错误: 无法生成有效的 'vt_symbols'，无法运行回测。")
        return

    db_instance = DatabaseFactory.get_instance().get_database()
    print(f"[Debug] verify get_database() returns: {type(db_instance)}")
    
    # 2. 初始化回测引擎
    engine = BacktestingEngine()

    # --- HACK: 注入合约信息到回测引擎 ---
    print("正在生成 ContractData 对象并注入引擎...")
    all_contracts = []
    for vt_symbol in vt_symbols:
        contract = VtSymbolGenerator.generate_contract_data(vt_symbol)
        if contract:
            all_contracts.append(contract)
            
    # Monkey patch engine
    engine.all_contracts_map = {c.vt_symbol: c for c in all_contracts}
    
    def get_all_contracts():
        return list(engine.all_contracts_map.values())
        
    def get_contract(vt_symbol):
        return engine.all_contracts_map.get(vt_symbol)
        
    engine.get_all_contracts = get_all_contracts
    engine.get_contract = get_contract
    print(f"已注入 {len(all_contracts)} 个合约信息")
    # -----------------------------------
    
    # 3. 设置回测参数
    rates = {vt_symbol: rate for vt_symbol in vt_symbols}
    slippages = {vt_symbol: slippage for vt_symbol in vt_symbols}
    
    # 动态获取每个合约的 size 和 pricetick (不再使用全局参数覆盖)
    sizes = {}
    priceticks = {}
    for vt_symbol in vt_symbols:
        contract = engine.get_contract(vt_symbol)
        if contract:
            sizes[vt_symbol] = contract.size
            priceticks[vt_symbol] = contract.pricetick
        else:
            sizes[vt_symbol] = size
            priceticks[vt_symbol] = pricetick

    engine.set_parameters(
        vt_symbols=vt_symbols,
        interval=Interval.MINUTE,
        start=datetime.strptime(start_date, "%Y-%m-%d"),
        end=datetime.strptime(end_date, "%Y-%m-%d"),
        rates=rates,
        slippages=slippages,
        sizes=sizes,
        priceticks=priceticks,
        capital=capital
    )
    
    engine.add_strategy(
        strategy_class=StrategyEntry,
        setting=setting
    )
    
    print("正在加载数据...")
    engine.load_data()
    
    print("正在运行回测...")
    engine.run_backtesting()
    
    print("正在计算结果...")
    engine.calculate_result()
    engine.calculate_statistics()
    
    if show_chart:
        engine.show_chart()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="运行商品波动率策略回测")
    parser.add_argument("--config", type=str, default="config/strategy_config.yaml", help="策略配置文件路径")
    parser.add_argument("--start", type=str, default="2025-12-29", help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=datetime.now().strftime("%Y-%m-%d"), help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--capital", type=int, default=1000000, help="初始资金")
    parser.add_argument("--rate", type=float, default=2.5e-5, help="手续费率")
    parser.add_argument("--slippage", type=float, default=0.2, help="滑点")
    parser.add_argument("--size", type=int, default=10, help="合约乘数")
    parser.add_argument("--pricetick", type=float, default=1.0, help="最小价格变动")
    parser.add_argument("--no-chart", action="store_true", help="不显示图表")
    
    args = parser.parse_args()
    
    run_backtesting(
        config_path=args.config,
        start_date=args.start,
        end_date=args.end,
        capital=args.capital,
        rate=args.rate,
        slippage=args.slippage,
        size=args.size,
        pricetick=args.pricetick,
        show_chart=not args.no_chart
    )