import calendar
from datetime import date
from typing import Dict, List, Optional, Callable, Tuple
from vnpy.trader.object import ContractData
from src.strategy.infrastructure.parsing.contract_helper import ContractHelper
from src.strategy.domain.value_object.selection import MarketData


class BaseFutureSelector:
    """
    Base class for future selection strategies.
    Provides common utilities for contract filtering and selection.
    """

    def select_dominant_contract(
        self,
        contracts: List[ContractData],
        current_date: date,
        market_data: Optional[Dict[str, MarketData]] = None,
        volume_weight: float = 0.6,
        oi_weight: float = 0.4,
        log_func: Optional[Callable[[str], None]] = None
    ) -> Optional[ContractData]:
        """
        基于成交量/持仓量加权得分选择主力合约。
        若无行情数据则回退到按到期日排序。

        Args:
            contracts: 可用合约列表
            current_date: 当前日期
            market_data: 行情数据字典，key 为 vt_symbol
            volume_weight: 成交量权重，默认 0.6
            oi_weight: 持仓量权重，默认 0.4
            log_func: 日志回调函数

        Returns:
            选中的主力合约，空列表返回 None
        """
        if not contracts:
            return None

        # 辅助函数：解析合约到期日，用于排序
        def _get_expiry(contract: ContractData) -> date:
            expiry = ContractHelper.get_expiry_from_symbol(contract.symbol)
            if expiry is None:
                # 无法解析时使用最大日期，排到最后
                return date.max
            return expiry

        # 无行情数据时回退到按到期日排序
        if not market_data:
            if log_func:
                log_func("无行情数据，回退到按到期日排序选择最近月合约")
            sorted_contracts = sorted(contracts, key=_get_expiry)
            return sorted_contracts[0]

        # 计算每个合约的加权得分
        def _calc_score(contract: ContractData) -> float:
            md = market_data.get(contract.vt_symbol)
            if md is None:
                return 0.0
            return md.volume * volume_weight + md.open_interest * oi_weight

        # 检查是否所有合约得分均为零
        scores = [(c, _calc_score(c)) for c in contracts]
        all_zero = all(score == 0.0 for _, score in scores)

        if all_zero:
            if log_func:
                log_func("所有合约成交量和持仓量均为零，回退到按到期日排序")
            sorted_contracts = sorted(contracts, key=_get_expiry)
            return sorted_contracts[0]

        # 按得分降序排列，得分相同时按到期日升序
        sorted_scores = sorted(
            scores,
            key=lambda x: (-x[1], _get_expiry(x[0]))
        )

        selected = sorted_scores[0][0]
        if log_func:
            log_func(
                f"选择主力合约: {selected.vt_symbol}, "
                f"得分: {sorted_scores[0][1]:.2f}"
            )
        return selected

    def filter_by_maturity(
        self,
        contracts: List[ContractData],
        current_date: date,
        mode: str = "current_month",
        date_range: Optional[Tuple[date, date]] = None,
        log_func: Optional[Callable[[str], None]] = None
    ) -> List[ContractData]:
        """
        基于真实到期日解析过滤合约。

        Args:
            contracts: 可用合约列表
            current_date: 当前日期
            mode: 过滤模式 - "current_month" | "next_month" | "custom"
            date_range: 仅 mode="custom" 时使用，(start_date, end_date) 闭区间
            log_func: 日志回调函数

        Returns:
            过滤后的合约列表
        """
        if not contracts:
            return []

        # 确定目标日期范围
        if mode == "current_month":
            range_start = date(current_date.year, current_date.month, 1)
            last_day = calendar.monthrange(current_date.year, current_date.month)[1]
            range_end = date(current_date.year, current_date.month, last_day)
        elif mode == "next_month":
            if current_date.month == 12:
                next_year = current_date.year + 1
                next_month = 1
            else:
                next_year = current_date.year
                next_month = current_date.month + 1
            range_start = date(next_year, next_month, 1)
            last_day = calendar.monthrange(next_year, next_month)[1]
            range_end = date(next_year, next_month, last_day)
        elif mode == "custom":
            if date_range is None:
                if log_func:
                    log_func("custom 模式需要提供 date_range 参数")
                return []
            range_start, range_end = date_range
        else:
            if log_func:
                log_func(f"未知的过滤模式: {mode}")
            return []

        # 过滤合约
        result = []
        for contract in contracts:
            expiry = ContractHelper.get_expiry_from_symbol(contract.symbol)
            if expiry is None:
                if log_func:
                    log_func(f"无法解析合约 {contract.symbol} 的到期日，已排除")
                continue
            if range_start <= expiry <= range_end:
                result.append(contract)

        return result


