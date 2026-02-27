"""
Tests for snapshot backward compatibility — 单元测试

Feature: data-persistence-optimization

测试旧版快照（无 combination_aggregate 字段）恢复为空实例 — Requirements: 1.3
测试旧版未压缩快照可正常加载 — Requirements: 3.2
测试现有 MigrationChain 与新功能兼容 — Requirements: 1.3, 3.2
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
from src.strategy.infrastructure.persistence.json_serializer import JsonSerializer
from src.strategy.infrastructure.persistence.migration_chain import MigrationChain
from src.strategy.infrastructure.persistence.state_repository import StateRepository


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


class TestCompressionBackwardCompatibility:
    """测试压缩功能的向后兼容性"""

    def test_old_uncompressed_snapshot_loads_correctly(self):
        """
        Requirement 3.2: 旧版未压缩快照可正常加载
        
        当加载旧版本快照时（未压缩的纯 JSON 字符串），
        StateRepository 应该能够正确识别并加载，不需要解压。
        """
        # 创建 StateRepository 实例
        migration_chain = MigrationChain()
        serializer = JsonSerializer(migration_chain)
        
        # 模拟旧版未压缩的 JSON 字符串
        old_uncompressed_json = '{"schema_version": 1, "target_aggregate": {}, "position_aggregate": {}}'
        
        # 测试 _maybe_decompress 方法
        # 创建一个临时的 StateRepository 实例（不需要真实数据库）
        from unittest.mock import MagicMock
        mock_db_factory = MagicMock()
        repo = StateRepository(
            serializer=serializer,
            database_factory=mock_db_factory,
            compression_threshold=10 * 1024
        )
        
        # 验证：未压缩的数据应该原样返回
        decompressed = repo._maybe_decompress(old_uncompressed_json)
        assert decompressed == old_uncompressed_json
        
        # 验证：可以正常反序列化
        data = serializer.deserialize(decompressed)
        assert data["schema_version"] == 1
        assert "target_aggregate" in data
        assert "position_aggregate" in data

    def test_compressed_and_uncompressed_snapshots_deserialize_identically(self):
        """
        验证压缩和未压缩的快照反序列化后结果相同
        
        这确保压缩功能不会改变数据的语义。
        """
        migration_chain = MigrationChain()
        serializer = JsonSerializer(migration_chain)
        
        from unittest.mock import MagicMock
        mock_db_factory = MagicMock()
        repo = StateRepository(
            serializer=serializer,
            database_factory=mock_db_factory,
            compression_threshold=100  # 低阈值，确保会压缩
        )
        
        # 创建一个足够大的快照数据（超过阈值）
        large_snapshot = {
            "target_aggregate": {
                "instruments": {f"instrument_{i}": {"data": "x" * 100} for i in range(10)}
            },
            "position_aggregate": {
                "positions": {f"position_{i}": {"volume": i} for i in range(10)}
            }
        }
        
        # 序列化
        json_str = serializer.serialize(large_snapshot)
        
        # 压缩
        compressed_str, was_compressed = repo._maybe_compress(json_str)
        assert was_compressed, "数据应该被压缩"
        assert compressed_str.startswith("ZLIB:"), "压缩数据应该有 ZLIB: 前缀"
        
        # 解压
        decompressed_str = repo._maybe_decompress(compressed_str)
        
        # 验证：解压后的 JSON 字符串应该与原始相同
        assert decompressed_str == json_str
        
        # 验证：反序列化后的数据应该相同
        original_data = serializer.deserialize(json_str)
        restored_data = serializer.deserialize(decompressed_str)
        
        # 比较关键字段
        assert original_data["schema_version"] == restored_data["schema_version"]
        assert len(original_data["target_aggregate"]["instruments"]) == \
               len(restored_data["target_aggregate"]["instruments"])
        assert len(original_data["position_aggregate"]["positions"]) == \
               len(restored_data["position_aggregate"]["positions"])

    def test_small_snapshot_not_compressed_for_backward_compatibility(self):
        """
        验证小于阈值的快照不会被压缩
        
        这确保小快照保持原始格式，与旧版本行为一致。
        """
        migration_chain = MigrationChain()
        serializer = JsonSerializer(migration_chain)
        
        from unittest.mock import MagicMock
        mock_db_factory = MagicMock()
        repo = StateRepository(
            serializer=serializer,
            database_factory=mock_db_factory,
            compression_threshold=10 * 1024  # 10KB 阈值
        )
        
        # 创建一个小快照（远小于 10KB）
        small_snapshot = {
            "target_aggregate": {},
            "position_aggregate": {}
        }
        
        json_str = serializer.serialize(small_snapshot)
        
        # 尝试压缩
        stored_str, was_compressed = repo._maybe_compress(json_str)
        
        # 验证：不应该被压缩
        assert not was_compressed, "小快照不应该被压缩"
        assert stored_str == json_str, "小快照应该保持原始格式"
        assert not stored_str.startswith("ZLIB:"), "小快照不应该有压缩前缀"


class TestMigrationChainCompatibility:
    """测试 MigrationChain 与新功能的兼容性"""

    def test_migration_chain_works_with_combination_aggregate(self):
        """
        验证 MigrationChain 与 combination_aggregate 字段兼容
        
        即使快照包含新的 combination_aggregate 字段，
        MigrationChain 也应该能够正常处理（不会破坏新字段）。
        """
        migration_chain = MigrationChain()
        serializer = JsonSerializer(migration_chain)
        
        # 创建包含 combination_aggregate 的新版快照
        new_snapshot = {
            "schema_version": 1,
            "target_aggregate": {},
            "position_aggregate": {},
            "combination_aggregate": {
                "combinations": {
                    "combo_1": {
                        "combination_id": "combo_1",
                        "combination_type": "vertical_spread",
                        "underlying_vt_symbol": "IF2401.CFFEX",
                        "legs": [],
                        "status": "active",
                        "create_time": "2024-01-01T10:00:00",
                        "close_time": None
                    }
                },
                "symbol_index": {}
            }
        }
        
        # 序列化
        json_str = serializer.serialize(new_snapshot)
        
        # 反序列化（会触发 MigrationChain 检查）
        restored = serializer.deserialize(json_str)
        
        # 验证：combination_aggregate 字段应该被保留
        assert "combination_aggregate" in restored
        assert "combinations" in restored["combination_aggregate"]
        assert "combo_1" in restored["combination_aggregate"]["combinations"]

    def test_migration_chain_works_with_compressed_data(self):
        """
        验证 MigrationChain 与压缩数据兼容
        
        压缩/解压应该在序列化/反序列化之外进行，
        不应该影响 MigrationChain 的版本迁移逻辑。
        """
        migration_chain = MigrationChain()
        serializer = JsonSerializer(migration_chain)
        
        from unittest.mock import MagicMock
        mock_db_factory = MagicMock()
        repo = StateRepository(
            serializer=serializer,
            database_factory=mock_db_factory,
            compression_threshold=100  # 低阈值
        )
        
        # 创建一个大快照
        large_snapshot = {
            "target_aggregate": {
                "instruments": {f"instrument_{i}": {"data": "x" * 100} for i in range(10)}
            },
            "position_aggregate": {}
        }
        
        # 序列化
        json_str = serializer.serialize(large_snapshot)
        
        # 压缩
        compressed_str, was_compressed = repo._maybe_compress(json_str)
        assert was_compressed
        
        # 解压
        decompressed_str = repo._maybe_decompress(compressed_str)
        
        # 反序列化（会触发 MigrationChain）
        restored = serializer.deserialize(decompressed_str)
        
        # 验证：数据应该正确恢复
        assert restored["schema_version"] == 1
        assert len(restored["target_aggregate"]["instruments"]) == 10

    def test_old_schema_version_migrates_correctly_with_new_features(self):
        """
        验证旧 schema 版本在新功能存在时仍能正确迁移
        
        这是一个前瞻性测试：如果未来添加了 schema v2，
        旧的 v1 快照应该能够迁移，即使它们不包含新字段。
        """
        migration_chain = MigrationChain()
        serializer = JsonSerializer(migration_chain)
        
        # 模拟一个旧版本快照（schema_version=1，无 combination_aggregate）
        old_snapshot_json = '''
        {
            "schema_version": 1,
            "target_aggregate": {},
            "position_aggregate": {}
        }
        '''
        
        # 反序列化（MigrationChain 会检查版本）
        restored = serializer.deserialize(old_snapshot_json)
        
        # 验证：应该成功加载
        assert restored["schema_version"] == 1
        assert "target_aggregate" in restored
        assert "position_aggregate" in restored
        
        # 验证：缺失的 combination_aggregate 字段应该在应用层处理
        # （不是在 MigrationChain 中添加，而是在 StrategyEntry 中检查）
        # 这里只验证 MigrationChain 不会破坏数据
        assert "combination_aggregate" not in restored  # 旧快照不应该自动添加新字段
