# Implementation Plan: Web MySQL State Reader

## Overview

将监控端数据源从 pickle 文件迁移到 MySQL `strategy_state` 表。实现 `SnapshotJsonTransformer` 转换器和 `StrategyStateReader` 读取器，更新 `app.py` 数据源优先级，移除 pickle 依赖。

## Tasks

- [x] 1. 实现 SnapshotJsonTransformer 转换器
  - [x] 1.1 实现 `resolve_special_markers` 方法
    - 在 `src/web/reader.py` 中新增 `SnapshotJsonTransformer` 类
    - 实现递归解析 `__dataframe__`、`__datetime__`、`__date__`、`__enum__`、`__set__`、`__dataclass__` 标记
    - 未知标记保留原始值
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 1.2 编写 `resolve_special_markers` 的属性测试
    - **Property 1: Special marker resolution produces only JSON-primitive types**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 3.4, 4.5**

  - [x] 1.3 实现 `transform_instruments` 方法
    - 从 `target_aggregate.instruments` 提取每个标的的 bars → dates/ohlc/volumes
    - 解析 indicators 中的特殊标记
    - 提取 delivery_month（复用 `extract_delivery_month` 逻辑）
    - 提取 last_price（从 bars 最后一条记录的 close）
    - 跳过 bars 为空的标的
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 1.4 编写 bars 提取的属性测试
    - **Property 2: Bars extraction preserves record count and data**
    - **Validates: Requirements 3.1, 3.2**

  - [x] 1.5 实现 `transform_positions` 和 `transform_orders` 方法
    - 将 positions 字典转换为列表，包含 vt_symbol/direction/volume/price/pnl 字段
    - 将 pending_orders 字典转换为列表，包含 vt_orderid/vt_symbol/direction/offset/volume/price/status 字段
    - 解析字段中的 `__enum__` 标记为字符串
    - 空字典返回空列表
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 1.6 编写 positions/orders 转换的属性测试
    - **Property 3: Positions and orders dict-to-list transformation**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [x] 1.7 实现 `transform` 主入口方法
    - 组合 timestamp（从 current_dt）、variant（从 strategy_name）、instruments、positions、orders
    - 处理缺失字段的默认值
    - _Requirements: 2.2, 2.3_

  - [x] 1.8 编写完整快照转换的属性测试
    - **Property 4: Full snapshot transform produces all required Frontend_Format fields**
    - **Validates: Requirements 2.2, 2.3, 3.1**

- [x] 2. Checkpoint - 确保转换器测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 实现 StrategyStateReader
  - [x] 3.1 实现 `StrategyStateReader` 类
    - 在 `src/web/reader.py` 中新增 `StrategyStateReader` 类
    - 使用 pymysql 连接 MySQL，从环境变量读取配置
    - 实现 `list_available_strategies`: 查询 `strategy_state` 表的 distinct strategy_name 和 MAX(saved_at)
    - 实现 `get_strategy_data`: 查询最新 snapshot_json，调用 `SnapshotJsonTransformer.transform` 转换
    - 所有方法捕获异常，不抛出
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.4, 2.5_

  - [x] 3.2 编写 StrategyStateReader 的单元测试
    - 测试数据库连接失败返回空列表/None
    - 测试 malformed JSON 返回 None
    - 测试正常快照的完整转换流程
    - _Requirements: 1.2, 1.3, 2.4, 2.5_

- [ ] 4. 更新 Web App 数据源
  - [x] 4.1 修改 `src/web/app.py` 数据源优先级
    - 新增 `StrategyStateReader` 实例（使用环境变量配置）
    - 修改 `list_strategies_best_effort`: StrategyStateReader → MySQLSnapshotReader
    - 修改 `get_snapshot_best_effort`: StrategyStateReader → MySQLSnapshotReader
    - 修改 `mysql_ready` 函数适配新的数据源检查逻辑
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 4.2 移除 pickle 依赖
    - 移除 `SnapshotReader` 的 import 和 `pickle_reader` 实例
    - 移除 `list_strategies_best_effort` 和 `get_snapshot_best_effort` 中的 pickle 回退逻辑
    - 保留 `MySQLSnapshotReader` 用于 events/bars API
    - _Requirements: 7.1, 7.2, 7.3_

  - [-] 4.3 更新 WebSocket poll_db 函数
    - 将 `poll_db` 中的快照轮询改为查询 `strategy_state` 表
    - 保留事件轮询逻辑（仍使用 `monitor_signal_event` 表）
    - _Requirements: 8.3_

- [~] 5. Final checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- `SnapshotJsonTransformer` 是纯函数式转换器，不依赖数据库，易于测试
- `StrategyStateReader` 使用 pymysql 直连（与现有 `MySQLSnapshotReader` 风格一致），不引入策略端的 Peewee 依赖
- `extract_delivery_month` 逻辑从 `SnapshotReader` 迁移到 `SnapshotJsonTransformer`（静态方法）
- Property tests use `hypothesis` library with minimum 100 iterations per test
