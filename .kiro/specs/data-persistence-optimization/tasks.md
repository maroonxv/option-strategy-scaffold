# Implementation Plan: 数据持久化方案优化

## Overview

基于现有 `StateRepository` / `AutoSaveService` / `JsonSerializer` / `StrategyEntry` 进行增量扩展，按依赖顺序实现六个优化领域。先完成底层序列化和模型变更，再逐步向上构建压缩、去重、异步和清理功能，最后在 StrategyEntry 中集成 CombinationAggregate 持久化。

## Tasks

- [x] 1. JsonSerializer 增强：sort_keys 确定性输出与容错反序列化
  - [x] 1.1 修改 `json_serializer.py` 的 `serialize` 方法，添加 `sort_keys=True` 参数
    - 确保 `json.dumps` 调用包含 `sort_keys=True`
    - 验证现有序列化行为不受影响
    - _Requirements: 2.5, 6.2_

  - [x] 1.2 确认并加固容错反序列化逻辑
    - 确认 `_resolve_enum` 在找不到 Enum 类时返回原始字符串值而非抛出异常
    - 确认 `_resolve_dataclass` 在找不到 dataclass 类时返回原始字典而非抛出异常
    - 如有缺失则补充容错逻辑
    - _Requirements: 6.3, 6.4_

  - [x] 1.3 编写 Property 2 属性测试：JsonSerializer 序列化往返一致性
    - **Property 2: JsonSerializer 序列化往返一致性**
    - 在 `tests/strategy/infrastructure/persistence/test_persistence_serializer_properties.py` 中实现
    - 使用 Hypothesis 生成包含 DataFrame、datetime、date、set、Enum、dataclass 的嵌套字典
    - 验证 `serialize()` 后 `deserialize()` 产生与原始数据等价的结果
    - **Validates: Requirements 1.4, 6.1**

  - [x] 1.4 编写 Property 3 属性测试：JsonSerializer 序列化确定性
    - **Property 3: JsonSerializer 序列化确定性**
    - 在同一测试文件中实现
    - 验证连续两次 `serialize()` 产生完全相同的 JSON 字符串
    - **Validates: Requirements 2.5, 6.2**

  - [x] 1.5 编写 Property 4 属性测试：JsonSerializer 输出合法性
    - **Property 4: JsonSerializer 输出合法性**
    - 在同一测试文件中实现
    - 验证 `serialize()` 输出能被 `json.loads()` 成功解析
    - **Validates: Requirements 6.5**

- [x] 2. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. StateRepository 压缩扩展
  - [x] 3.1 实现 `_maybe_compress` 和 `_maybe_decompress` 方法
    - 在 `state_repository.py` 中添加 `COMPRESSION_PREFIX = "ZLIB:"` 常量和 `DEFAULT_COMPRESSION_THRESHOLD = 10 * 1024`
    - 实现 `_maybe_compress(json_str) -> tuple[str, bool]`：超过阈值时使用 zlib 压缩 + base64 编码 + ZLIB: 前缀
    - 实现 `_maybe_decompress(stored) -> str`：检测 ZLIB: 前缀并解压
    - 压缩后数据更大时保留原始数据
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.2 新增 `save_raw` 方法并修改 `save` 和 `load` 方法
    - 添加 `save_raw(strategy_name, json_str)` 方法，支持保存已序列化的 JSON 字符串（含压缩逻辑）
    - 修改 `save` 方法调用 `save_raw`
    - 修改 `load` 方法在反序列化前调用 `_maybe_decompress`
    - 添加 `compression_threshold` 构造参数
    - _Requirements: 3.1, 3.2_

  - [x] 3.3 编写 Property 6 属性测试：压缩往返一致性
    - **Property 6: 压缩往返一致性**
    - 在 `tests/strategy/infrastructure/persistence/test_persistence_compression_properties.py` 中实现
    - 使用 Hypothesis 生成随机长度 JSON 字符串（含超过/低于阈值的情况）
    - 验证 `_maybe_compress` 后 `_maybe_decompress` 产生与原始 JSON 字符串完全一致的结果
    - **Validates: Requirements 3.1, 3.2, 3.5**

  - [x] 3.4 编写压缩边界条件单元测试
    - 测试压缩后数据更大时保留原始数据（Requirements 3.4）
    - 测试空字符串和小于阈值的字符串不压缩
    - 测试 ZLIB: 前缀检测正确性
    - _Requirements: 3.4_

- [x] 4. StateRepository 自动清理旧快照
  - [x] 4.1 实现 `cleanup` 方法
    - 在 `state_repository.py` 中添加 `cleanup(strategy_name, keep_days=7) -> int` 方法
    - 查询最新记录 ID，删除 `saved_at` 早于保留天数的记录，但排除最新记录
    - 返回删除的记录数
    - _Requirements: 4.3, 4.4_

  - [x] 4.2 编写 Property 7 属性测试：清理保留最新记录
    - **Property 7: 清理保留最新记录**
    - 在 `tests/strategy/infrastructure/persistence/test_persistence_cleanup_properties.py` 中实现
    - 使用 Hypothesis 生成随机时间戳的快照记录列表
    - 验证 cleanup 后至少保留一条最新记录，且过期记录被正确删除
    - **Validates: Requirements 4.3, 4.4**

- [x] 5. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. AutoSaveService 增强：Digest 去重与异步保存
  - [x] 6.1 添加 digest 计算和去重逻辑
    - 在 `auto_save_service.py` 中添加 `_compute_digest(json_str) -> str` 方法（SHA-256）
    - 添加 `_last_digest: Optional[str]` 内部状态
    - 修改 `_do_save` 方法：计算 digest，与 `_last_digest` 比较，相同则跳过
    - AutoSaveService 需持有 JsonSerializer 引用
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 6.2 实现异步保存机制
    - 添加 `ThreadPoolExecutor(max_workers=1)` 和 `_pending_future: Optional[Future]`
    - 修改 `_do_save`：digest 变化时 submit 到后台线程执行
    - 上一次异步保存未完成时跳过本次并记录调试日志
    - 后台线程异常时记录错误日志，不影响主线程
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [x] 6.3 实现 `force_save` 方法
    - 等待当前异步保存完成（timeout=30）
    - 无条件执行同步保存，忽略 digest 比较
    - _Requirements: 2.4, 5.4_

  - [x] 6.4 实现自动清理触发逻辑
    - 添加 `_last_cleanup_time`、`_cleanup_interval_seconds`、`_keep_days` 字段
    - 在 `_save_in_background` 中调用 `_maybe_cleanup`
    - 按可配置频率（默认 24 小时）触发 `StateRepository.cleanup`
    - 清理失败时记录错误日志，不影响策略运行
    - _Requirements: 4.1, 4.2, 4.5_

  - [x] 6.5 实现 `shutdown` 方法
    - 调用 `self._executor.shutdown(wait=True)` 关闭线程池
    - _Requirements: 5.4_

  - [x] 6.6 编写 Property 5 属性测试：Digest 去重正确性
    - **Property 5: Digest 去重正确性**
    - 在 `tests/strategy/infrastructure/persistence/test_persistence_autosave_properties.py` 中实现
    - 使用 Hypothesis 生成随机 Snapshot 字典对（相同/不同）
    - 验证相同 Snapshot 第二次保存被跳过，不同 Snapshot 第二次保存执行
    - **Validates: Requirements 2.2, 2.3**

  - [x] 6.7 编写 Property 8 属性测试：异步保存跳过未完成请求
    - **Property 8: 异步保存跳过未完成请求**
    - 在同一测试文件中实现
    - 验证上一次异步保存未完成时新请求被跳过
    - **Validates: Requirements 5.3**

  - [x] 6.8 编写 AutoSaveService 单元测试
    - 测试 force_save 忽略 digest 比较（Requirements 2.4）
    - 测试 force_save 等待异步完成（Requirements 5.4）
    - 测试 cleanup 频率控制（Requirements 4.2）
    - 测试 cleanup 失败不影响策略运行（Requirements 4.5）
    - 测试异步保存异常不影响主线程（Requirements 5.5）
    - _Requirements: 2.4, 4.2, 4.5, 5.4, 5.5_

- [-] 7. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. CombinationAggregate 持久化补全
  - [~] 8.1 实现 CombinationAggregate 的 `to_snapshot` 和 `from_snapshot` 方法
    - 在 `combination_aggregate.py` 中添加 `to_snapshot() -> Dict[str, Any]` 方法
    - 添加 `@classmethod from_snapshot(cls, data: Dict[str, Any]) -> CombinationAggregate` 方法
    - 序列化 `combinations` 字典和 `symbol_index`
    - _Requirements: 1.1, 1.2_

  - [~] 8.2 修改 StrategyEntry 的快照创建和恢复逻辑
    - 修改 `_create_snapshot` 方法，将 `combination_aggregate` 纳入快照
    - 修改 `on_init` 恢复逻辑，从快照中恢复 `combination_aggregate`
    - 旧版快照（无 `combination_aggregate` 字段）时创建空实例（向后兼容）
    - _Requirements: 1.1, 1.2, 1.3_

  - [~] 8.3 编写 Property 1 属性测试：CombinationAggregate 快照往返一致性
    - **Property 1: CombinationAggregate 快照往返一致性**
    - 在 `tests/strategy/infrastructure/persistence/test_persistence_combination_properties.py` 中实现
    - 使用 Hypothesis 生成随机 Combination 实体（随机 legs、status、timestamps）
    - 验证 `to_snapshot()` 后 `from_snapshot()` 恢复的实例与原始实例等价
    - **Validates: Requirements 1.1, 1.2, 1.5**

  - [~] 8.4 编写旧版快照兼容性单元测试
    - 测试旧版快照（无 combination_aggregate 字段）恢复为空实例
    - _Requirements: 1.3_

- [ ] 9. 集成与连接
  - [~] 9.1 更新 StrategyEntry 中 AutoSaveService 的初始化
    - 传入新增的构造参数（cleanup_interval_hours、keep_days）
    - 传入 JsonSerializer 引用
    - 在 `on_stop` 中调用 `force_save` 和 `shutdown`
    - _Requirements: 1.1, 2.4, 4.1, 5.4_

  - [~] 9.2 确保向后兼容性
    - 验证旧版未压缩快照可正常加载
    - 验证旧版无 combination_aggregate 的快照可正常恢复
    - 验证现有 MigrationChain 与新功能兼容
    - _Requirements: 1.3, 3.2_

- [~] 10. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 所有属性测试使用 Hypothesis 库，每个属性至少运行 100 次迭代
- 属性测试标签格式：Feature: data-persistence-optimization, Property {number}: {property_text}
- 实现顺序按依赖关系排列：JsonSerializer → StateRepository → AutoSaveService → CombinationAggregate → 集成
- 压缩使用 ZLIB: 前缀 + base64 编码，兼容现有 TEXT 字段，无需数据库 schema 变更
