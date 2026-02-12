# Implementation Plan: Persistence Resilience Enhancement

## Overview

基于已批准的设计文档，将持久化架构从 pickle 文件迁移到 MySQL JSON 存储，实现周期性自动保存、fail-fast 错误处理、数据库连接验证、JSON 序列化版本迁移和统一数据库工厂。每个任务增量构建，确保无孤立代码。

## Tasks

- [x] 1. 创建异常类和基础类型
  - [x] 1.1 创建 `src/strategy/infrastructure/persistence/exceptions.py`，实现 `CorruptionError`、`DatabaseConfigError`、`DatabaseConnectionError` 异常类
    - 每个异常类包含设计文档中定义的属性和错误消息格式
    - _Requirements: 2.2, 2.4, 3.2, 3.3_
  - [x] 1.2 在 `src/strategy/infrastructure/persistence/state_repository.py` 中添加 `ArchiveNotFound` 数据类
    - 包含 `strategy_name` 字段
    - _Requirements: 2.1_

- [x] 2. 实现 MigrationChain
  - [x] 2.1 创建 `src/strategy/infrastructure/persistence/migration_chain.py`，实现 `MigrationChain` 类
    - 实现 `register(from_version, fn)` 和 `migrate(data, from_version, to_version)` 方法
    - _Requirements: 4.3, 4.4_
  - [x] 2.2 编写 MigrationChain 属性测试
    - **Property 8: Migration chain sequential application**
    - **Validates: Requirements 4.3**

- [x] 3. 实现 JsonSerializer
  - [x] 3.1 创建 `src/strategy/infrastructure/persistence/json_serializer.py`，实现 `JsonSerializer` 类
    - 实现自定义 `JSONEncoder` 处理 DataFrame、datetime、date、set、Enum、dataclass
    - 实现 `serialize()` 方法，自动注入 `schema_version`
    - 实现 `deserialize()` 方法，支持类型还原和版本迁移
    - _Requirements: 4.1, 4.2, 4.5, 4.6_
  - [x] 3.2 编写 JsonSerializer 属性测试
    - **Property 7: JSON serialization round-trip**
    - **Validates: Requirements 4.1, 4.2, 4.5, 4.6, 4.8**
  - [x] 3.3 编写 JsonSerializer 单元测试
    - 测试空 DataFrame、嵌套 datetime、Enum、set 等边界情况
    - _Requirements: 4.5, 4.6_

- [x] 4. Checkpoint - 序列化层验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 实现 DatabaseFactory
  - [x] 5.1 创建 `src/main/bootstrap/database_factory.py`，实现 `DatabaseFactory` 单例类
    - 实现 `get_instance()`、`initialize(eager, timeout)`、`get_database()`、`get_peewee_db()`
    - 实现 `validate_env_vars()` 静态方法和 `validate_connection()` 方法
    - 内部封装 `vnpy_mysql` 表名配置 (dbbardata, dbtickdata)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 3.1, 3.2, 3.4, 3.5_
  - [x] 5.2 创建 `src/strategy/infrastructure/persistence/strategy_state_model.py`，定义 `StrategyStateModel` Peewee 模型
    - 包含 id (AutoField)、strategy_name、snapshot_json、schema_version、saved_at 字段
    - 定义复合索引 (strategy_name, saved_at)
    - _Requirements: 1.4_
  - [x] 5.3 编写 DatabaseFactory 属性测试
    - **Property 6: Missing environment variables detection**
    - **Validates: Requirements 3.3**
    - **Property 9: Database factory singleton identity**
    - **Validates: Requirements 5.6**
  - [x] 5.4 编写 DatabaseFactory 单元测试
    - 测试 eager vs lazy 初始化、不回退 SQLite、日志输出
    - _Requirements: 3.4, 3.5, 5.5_

- [-] 6. 改造 StateRepository
  - [x] 6.1 重写 `src/strategy/infrastructure/persistence/state_repository.py`
    - 构造函数接受 `JsonSerializer` 和 `DatabaseFactory`
    - 实现 `save(strategy_name, data)` — INSERT 追加到 strategy_state 表
    - 实现 `load(strategy_name)` — 查询最新记录，返回 Dict 或 ArchiveNotFound，损坏时抛出 CorruptionError
    - 实现 `verify_integrity(strategy_name)` — 验证 JSON 可解析且包含 schema_version
    - 实现 `cleanup(strategy_name, keep_days)` — 清理旧快照
    - _Requirements: 1.4, 2.1, 2.2, 2.4, 2.5, 4.1, 4.8_
  - [-] 6.2 编写 StateRepository 属性测试
    - **Property 2: Save then load returns latest snapshot**
    - **Validates: Requirements 1.4**
    - **Property 3: Non-existent strategy returns ArchiveNotFound**
    - **Validates: Requirements 2.1**
    - **Property 4: Corrupted record raises CorruptionError with details**
    - **Validates: Requirements 2.2, 2.4**
    - **Property 5: Integrity check without full deserialization**
    - **Validates: Requirements 2.5**
  - [~] 6.3 编写 StateRepository 单元测试
    - 测试 cleanup 清理旧快照、CorruptionError 包含正确信息
    - _Requirements: 2.3, 2.4_

- [~] 7. Checkpoint - 持久化层验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. 实现 AutoSaveService
  - [~] 8.1 创建 `src/strategy/infrastructure/persistence/auto_save_service.py`，实现 `AutoSaveService` 类
    - 构造函数接受 `StateRepository`、`strategy_name`、`interval_seconds`（默认 60）、`logger`
    - 实现 `maybe_save(snapshot_fn)` — 基于 `time.monotonic()` 判断是否到达保存间隔
    - 实现 `force_save(snapshot_fn)` — 强制保存
    - 保存失败时捕获异常并记录日志，不中断策略执行
    - _Requirements: 1.1, 1.2, 1.3, 1.5_
  - [~] 8.2 编写 AutoSaveService 属性测试
    - **Property 1: Auto-save interval gating**
    - **Validates: Requirements 1.1, 1.3**
  - [~] 8.3 编写 AutoSaveService 单元测试
    - 测试默认间隔 60 秒、写入失败不中断
    - _Requirements: 1.2, 1.5_

- [ ] 9. 集成到 StrategyEntry
  - [~] 9.1 修改 `src/strategy/strategy_entry.py`
    - 在 `on_init` 中：创建 `JsonSerializer`、`MigrationChain`、`StateRepository`（注入 DatabaseFactory）
    - 在 `on_init` 中：非回测模式下创建 `AutoSaveService`
    - 在 `on_init` 中：调用 `StateRepository.load()`，ArchiveNotFound 时使用空状态，CorruptionError 时 fail-fast
    - 在 `on_bars` 中：非回测模式下调用 `auto_save_service.maybe_save()`
    - 在 `on_stop` 中：非回测模式下调用 `auto_save_service.force_save()`
    - 移除旧的 pickle 文件路径逻辑和 `_load_state`/`_dump_state` 方法
    - _Requirements: 1.1, 1.6, 2.1, 2.3_

- [ ] 10. 集成 DatabaseFactory 到启动流程
  - [~] 10.1 修改 `src/main/bootstrap/database_setup.py`，改为调用 `DatabaseFactory.get_instance().initialize()`
    - 替换原有的直接 SETTINGS 注入逻辑
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - [~] 10.2 修改 `src/backtesting/run_backtesting.py`，使用 `DatabaseFactory` 替代 monkey-patch
    - 移除 `force_mysql_database` 函数和 `vnpy.trader.database.get_database` 替换
    - 改为调用 `DatabaseFactory.get_instance().initialize()` 和 `DatabaseFactory.get_instance().get_database()`
    - _Requirements: 5.1, 5.2, 5.3_

- [~] 11. Final checkpoint - 全量验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 数据库测试使用 SQLite 内存数据库模拟 Peewee 操作，避免依赖真实 MySQL
- Property tests 使用 hypothesis 库，每个测试最少 100 次迭代
- 每个 property test 标注格式: `Feature: persistence-resilience-enhancement, Property {N}: {title}`
