"""
回测模块

提供回测所需的核心组件：配置管理、合约处理、合约发现和回测执行。

使用延迟导入以避免在 vnpy 未安装的环境中（如测试环境）触发 ImportError。
"""


def __getattr__(name: str):
    if name == "BacktestConfig":
        from src.backtesting.config import BacktestConfig
        return BacktestConfig
    if name == "ContractFactory":
        from src.backtesting.contract.contract_factory import ContractFactory
        return ContractFactory
    if name == "ContractRegistry":
        from src.backtesting.contract.contract_registry import ContractRegistry
        return ContractRegistry
    if name == "SymbolGenerator":
        from src.backtesting.discovery.symbol_generator import SymbolGenerator
        return SymbolGenerator
    if name == "BacktestRunner":
        from src.backtesting.runner import BacktestRunner
        return BacktestRunner
    raise AttributeError(f"module 'src.backtesting' has no attribute {name!r}")


__all__ = [
    "BacktestConfig",
    "BacktestRunner",
    "SymbolGenerator",
    "ContractFactory",
    "ContractRegistry",
]
