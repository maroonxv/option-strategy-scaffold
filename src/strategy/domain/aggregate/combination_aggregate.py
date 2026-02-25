"""
CombinationAggregate - 组合策略聚合根

管理组合策略的注册、查询、状态同步和领域事件。
独立于 PositionAggregate，通过领域事件协调状态同步。
"""
from typing import Any, Dict, List, Optional, Set

from ..entity.combination import Combination
from ..value_object.combination import CombinationStatus
from ..event.event_types import DomainEvent, CombinationStatusChangedEvent


class CombinationAggregate:
    """
    组合策略聚合根

    职责:
    1. 管理 Combination 注册表（按 combination_id 索引）
    2. 维护 vt_symbol → combination_id 的反向索引（用于事件驱动的状态同步）
    3. 保护 Combination 的结构不变量（创建时验证）
    4. 协调 Combination 状态机转换
    5. 管理领域事件队列
    """

    def __init__(self) -> None:
        """初始化聚合根"""
        # 组合注册表 (按 combination_id 索引)
        self._combinations: Dict[str, Combination] = {}
        # 反向索引: vt_symbol → {combination_id}
        self._symbol_index: Dict[str, Set[str]] = {}
        # 领域事件队列
        self._domain_events: List[DomainEvent] = []

    # ========== 持久化接口 ==========

    def to_snapshot(self) -> Dict[str, Any]:
        """
        生成状态快照

        Returns:
            包含 combinations 和 symbol_index 的字典
        """
        return {
            "combinations": {
                cid: combo.to_dict()
                for cid, combo in self._combinations.items()
            },
            "symbol_index": {
                symbol: list(cids)
                for symbol, cids in self._symbol_index.items()
            },
        }

    @classmethod
    def from_snapshot(cls, snapshot: Dict[str, Any]) -> "CombinationAggregate":
        """
        从快照恢复状态

        Args:
            snapshot: 快照字典

        Returns:
            恢复的 CombinationAggregate 实例
        """
        obj = cls()

        # 恢复 combinations
        combinations_data = snapshot.get("combinations", {})
        for cid, combo_dict in combinations_data.items():
            obj._combinations[cid] = Combination.from_dict(combo_dict)

        # 恢复 symbol_index
        symbol_index_data = snapshot.get("symbol_index", {})
        for symbol, cids in symbol_index_data.items():
            obj._symbol_index[symbol] = set(cids)

        return obj

    # ========== 组合管理接口 ==========

    def register_combination(self, combination: Combination) -> None:
        """
        注册新组合（验证结构约束后注册）

        - 调用 combination.validate() 验证结构
        - 注册到 _combinations 字典
        - 建立 vt_symbol → combination_id 反向索引

        Args:
            combination: 要注册的 Combination 实体

        Raises:
            ValueError: 如果组合结构不满足约束
        """
        # 验证结构约束
        combination.validate()

        # 注册到组合字典
        self._combinations[combination.combination_id] = combination

        # 建立反向索引
        for leg in combination.legs:
            if leg.vt_symbol not in self._symbol_index:
                self._symbol_index[leg.vt_symbol] = set()
            self._symbol_index[leg.vt_symbol].add(combination.combination_id)

    def get_combination(self, combination_id: str) -> Optional[Combination]:
        """
        按 combination_id 获取组合

        Args:
            combination_id: 组合唯一标识符

        Returns:
            Combination 实体，不存在则返回 None
        """
        return self._combinations.get(combination_id)

    def get_combinations_by_underlying(
        self, underlying: str
    ) -> List[Combination]:
        """
        按标的合约查询所有关联的 Combination

        Args:
            underlying: 标的合约代码

        Returns:
            匹配该标的的 Combination 列表
        """
        return [
            combo
            for combo in self._combinations.values()
            if combo.underlying_vt_symbol == underlying
        ]

    def get_active_combinations(self) -> List[Combination]:
        """
        获取所有活跃（非 CLOSED）的 Combination

        Returns:
            活跃的 Combination 列表
        """
        return [
            combo
            for combo in self._combinations.values()
            if combo.status != CombinationStatus.CLOSED
        ]

    def get_combinations_by_symbol(self, vt_symbol: str) -> List[Combination]:
        """
        通过反向索引查找引用指定 vt_symbol 的所有 Combination

        Args:
            vt_symbol: 期权合约代码

        Returns:
            引用该 vt_symbol 的 Combination 列表
        """
        combination_ids = self._symbol_index.get(vt_symbol, set())
        return [
            self._combinations[cid]
            for cid in combination_ids
            if cid in self._combinations
        ]

    # ========== 状态同步接口 ==========

    def sync_combination_status(
        self,
        vt_symbol: str,
        closed_vt_symbols: Set[str],
    ) -> None:
        """
        当 Position 状态变化时，同步更新关联的 Combination 状态。

        由应用服务在收到 PositionClosedEvent 后调用。

        流程:
        1. 通过 _symbol_index 查找引用该 vt_symbol 的所有 Combination
        2. 对每个 Combination 调用 update_status(closed_vt_symbols)
        3. 如果状态发生变化，产生 CombinationStatusChangedEvent

        Args:
            vt_symbol: 发生状态变化的期权合约代码
            closed_vt_symbols: 所有已平仓的 vt_symbol 集合
        """
        # 通过反向索引查找关联的 Combination
        combination_ids = self._symbol_index.get(vt_symbol, set())

        for cid in combination_ids:
            combination = self._combinations.get(cid)
            if combination is None:
                continue

            # 记录旧状态
            old_status = combination.status

            # 更新状态
            new_status = combination.update_status(closed_vt_symbols)

            # 如果状态发生变化，产生领域事件
            if new_status is not None:
                self._domain_events.append(
                    CombinationStatusChangedEvent(
                        combination_id=combination.combination_id,
                        old_status=old_status.value,
                        new_status=new_status.value,
                        combination_type=combination.combination_type.value,
                    )
                )

    # ========== 领域事件接口 ==========

    def pop_domain_events(self) -> List[DomainEvent]:
        """
        获取并清空领域事件队列

        Returns:
            领域事件列表
        """
        events = self._domain_events.copy()
        self._domain_events.clear()
        return events

    def has_pending_events(self) -> bool:
        """
        检查是否有待处理的领域事件

        Returns:
            True 如果有待处理事件
        """
        return len(self._domain_events) > 0

    # ========== 辅助方法 ==========

    def __repr__(self) -> str:
        total = len(self._combinations)
        active = len(self.get_active_combinations())
        return f"CombinationAggregate(total={total}, active={active})"
