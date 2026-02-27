"""
Tests for snapshot backward compatibility — 单元测试

Feature: data-persistence-optimization

测试旧版快照（无 combination_aggregate 字段）恢复为空实例 — Requirements: 1.3
"""

import sys
from unittest.mock import MagicMock

import pytest

# Mock vnpy modules before importing anything
for _mod_name in [
    "vnpy", "vnpy.event", "vnpy.event.engine", "vnpy.trader", 
    "vnpy.trader.setting", "vnpy.trader.engine", "vnpy.trader.database", 
    "vnpy_mysql",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

sys.modules["vnpy.trader.setting"].SETTINGS = {}

from src.strategy.domain.aggregate.combination_aggregate import CombinationAggregate


class TestSnapshotBackwardCompatibility:
    """测试快照向后兼容性"""

    def test_old_snapshot_without_combination_aggregate_creates_empty_instance(self):
        """
        Requirement 1.3: 旧版快照（无 combination_aggregate 字段）恢复为空实例
        
        当加载旧版本快照时（不包含 combination_aggregate 字段），
        系统应该创建一个空的 CombinationAggregate 实例，而不是失败。
        
        这模拟了 StrategyEntry.on_init 中的逻辑：
        ```python
        if "combination_aggregate" in result:
            self.combination_aggregate = CombinationAggregate.from_snapshot(
                result["combination_aggregate"]
            )
        else:
            # 兼容旧版本快照（无 combination_aggregate 字段）
            self.combination_aggregate = CombinationAggregate()
        ```
        """
        # 模拟旧版快照（不包含 combination_aggregate 字段）
        old_snapshot = {
            "schema_version": 1,
            "target_aggregate": {
                "instruments": {},
                "active_contracts": []
            },
            "position_aggregate": {
                "positions": {}
            },
            "current_dt": {"__datetime__": "2024-01-01T15:00:00"}
        }
        
        # 模拟 StrategyEntry 的恢复逻辑
        if "combination_aggregate" in old_snapshot:
            combination_aggregate = CombinationAggregate.from_snapshot(
                old_snapshot["combination_aggregate"]
            )
        else:
            # 兼容旧版本快照（无 combination_aggregate 字段）
            combination_aggregate = CombinationAggregate()
        
        # 验证：创建了空的 CombinationAggregate 实例
        assert combination_aggregate is not None
        assert isinstance(combination_aggregate, CombinationAggregate)
        
        # 验证：实例为空（无组合）
        assert len(combination_aggregate.get_active_combinations()) == 0
        assert combination_aggregate.to_snapshot() == {
            "combinations": {},
            "symbol_index": {}
        }

    def test_new_snapshot_with_combination_aggregate_restores_correctly(self):
        """
        验证新版快照（包含 combination_aggregate 字段）能正确恢复
        
        这确保向后兼容性不会破坏新版本的功能。
        """
        # 模拟新版快照（包含 combination_aggregate 字段）
        new_snapshot = {
            "schema_version": 1,
            "target_aggregate": {
                "instruments": {},
                "active_contracts": []
            },
            "position_aggregate": {
                "positions": {}
            },
            "combination_aggregate": {
                "combinations": {
                    "combo_1": {
                        "combination_id": "combo_1",
                        "combination_type": "vertical_spread",
                        "underlying_vt_symbol": "IF2401.CFFEX",
                        "legs": [
                            {
                                "vt_symbol": "IO2401-C-4000.CFFEX",
                                "option_type": "call",
                                "strike_price": 4000.0,
                                "expiry_date": "2024-01-15",
                                "direction": "long",
                                "volume": 1,
                                "open_price": 100.0
                            },
                            {
                                "vt_symbol": "IO2401-C-4100.CFFEX",
                                "option_type": "call",
                                "strike_price": 4100.0,
                                "expiry_date": "2024-01-15",
                                "direction": "short",
                                "volume": 1,
                                "open_price": 50.0
                            }
                        ],
                        "status": "active",
                        "create_time": "2024-01-01T10:00:00",
                        "close_time": None
                    }
                },
                "symbol_index": {
                    "IO2401-C-4000.CFFEX": ["combo_1"],
                    "IO2401-C-4100.CFFEX": ["combo_1"]
                }
            },
            "current_dt": {"__datetime__": "2024-01-01T15:00:00"}
        }
        
        # 模拟 StrategyEntry 的恢复逻辑
        if "combination_aggregate" in new_snapshot:
            combination_aggregate = CombinationAggregate.from_snapshot(
                new_snapshot["combination_aggregate"]
            )
        else:
            combination_aggregate = CombinationAggregate()
        
        # 验证：正确恢复了 CombinationAggregate
        assert combination_aggregate is not None
        assert isinstance(combination_aggregate, CombinationAggregate)
        
        # 验证：恢复了组合数据
        active_combinations = combination_aggregate.get_active_combinations()
        assert len(active_combinations) == 1
        assert active_combinations[0].combination_id == "combo_1"
        
        # 验证：恢复了反向索引
        combos_by_symbol = combination_aggregate.get_combinations_by_symbol(
            "IO2401-C-4000.CFFEX"
        )
        assert len(combos_by_symbol) == 1
        assert combos_by_symbol[0].combination_id == "combo_1"

    def test_empty_combination_aggregate_snapshot_restores_correctly(self):
        """
        验证空的 combination_aggregate 快照能正确恢复
        
        这测试边界情况：快照包含 combination_aggregate 字段，但内容为空。
        """
        # 模拟包含空 combination_aggregate 的快照
        snapshot_with_empty_combo = {
            "schema_version": 1,
            "target_aggregate": {
                "instruments": {},
                "active_contracts": []
            },
            "position_aggregate": {
                "positions": {}
            },
            "combination_aggregate": {
                "combinations": {},
                "symbol_index": {}
            },
            "current_dt": {"__datetime__": "2024-01-01T15:00:00"}
        }
        
        # 恢复
        combination_aggregate = CombinationAggregate.from_snapshot(
            snapshot_with_empty_combo["combination_aggregate"]
        )
        
        # 验证：创建了空的 CombinationAggregate 实例
        assert combination_aggregate is not None
        assert isinstance(combination_aggregate, CombinationAggregate)
        assert len(combination_aggregate.get_active_combinations()) == 0
        
        # 验证：快照往返一致性
        restored_snapshot = combination_aggregate.to_snapshot()
        assert restored_snapshot == {
            "combinations": {},
            "symbol_index": {}
        }
