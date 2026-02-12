"""
合约注册表

统一管理回测中的合约信息，替代 monkey-patching 方式将合约注入回测引擎。
"""

import logging
from typing import Dict, List, Optional

from vnpy.trader.object import ContractData

from src.backtesting.contract.contract_factory import ContractFactory

logger = logging.getLogger(__name__)


class ContractRegistry:
    """合约注册表，以 vt_symbol 为键管理 ContractData。"""

    def __init__(self) -> None:
        self._contracts: Dict[str, ContractData] = {}

    def register(self, contract: ContractData) -> None:
        """注册合约。以 vt_symbol 为键存储。"""
        self._contracts[contract.vt_symbol] = contract

    def get(self, vt_symbol: str) -> Optional[ContractData]:
        """查询合约。不存在返回 None。"""
        return self._contracts.get(vt_symbol)

    def get_all(self) -> List[ContractData]:
        """获取全部合约。"""
        return list(self._contracts.values())

    def register_many(self, vt_symbols: List[str]) -> int:
        """批量注册：使用 ContractFactory 构建并注册。返回成功数量。"""
        count = 0
        for vt_symbol in vt_symbols:
            contract = ContractFactory.create(vt_symbol)
            if contract is not None:
                self.register(contract)
                count += 1
            else:
                logger.warning("无法构建合约，跳过: %s", vt_symbol)
        return count

    def inject_into_engine(self, engine) -> None:
        """将合约信息注入回测引擎（替代 monkey-patching）。"""
        registry = self

        engine.all_contracts_map = {
            c.vt_symbol: c for c in self._contracts.values()
        }

        def get_all_contracts():
            return registry.get_all()

        def get_contract(vt_symbol):
            return registry.get(vt_symbol)

        engine.get_all_contracts = get_all_contracts
        engine.get_contract = get_contract

        logger.info("已注入 %d 个合约信息到回测引擎", len(self._contracts))
