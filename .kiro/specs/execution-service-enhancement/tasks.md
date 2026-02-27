# Implementation Plan: 执行服务增强 (Execution Service Enhancement)

## Overview

分步增强执行领域服务模块，使其与对冲、风控、选择等模块在架构一致性上对齐。采用先修复缺陷、再新增配置值对象和加载、然后添加工厂方法和序列化、最后新增协调层的策略，确保每一步可验证。

## Tasks

- [x] 1. 修复已知缺陷
  - [x] 1.1 删除 `advanced_order_scheduler.py` 中重复的 `submit_timed_split` 方法定义
    - 保留第一个定义（约第 69-120 行），删除第二个重复定义（约第 122-172 行）
    - 确保删除后功能不变
    - _Requirements: 5.1, 5.2_

  - [x] 1.2 修复 `smart_order_executor.py` 中 `prepare_retry` 方法，重试耗尽时返回 OrderRetryExhaustedEvent
    - 将返回类型从 `Optional[OrderInstruction]` 改为 `Tuple[Optional[OrderInstruction], List[DomainEvent]]`
    - 重试耗尽时返回 `(None, [OrderRetryExhaustedEvent(...)])`，包含正确的 vt_symbol、total_retries、original_price、final_price
    - 未耗尽时返回 `(new_instruction, [])`
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 2. 新增 AdvancedSchedulerConfig 配置值对象与 TOML 配置
  - [x] 2.1 在 `src/strategy/domain/value_object/trading/order_execution.py` 中新增 `AdvancedSchedulerConfig` frozen dataclass
    - 包含字段：default_batch_size(10)、default_interval_seconds(60)、default_num_slices(5)、default_volume_randomize_ratio(0.1)、default_price_offset_ticks(1)、default_price_tick(0.01)
    - _Requirements: 3.1, 3.2_

  - [x] 2.2 创建 TOML 配置文件
    - 创建 `config/domain_service/execution/smart_order_executor.toml`，包含 timeout、retry、price 分节
    - 创建 `config/domain_service/execution/advanced_scheduler.toml`，包含 iceberg、split、randomize、price 分节
    - _Requirements: 1.5_

  - [-] 2.3 在 `domain_service_config_loader.py` 中新增 `load_smart_order_executor_config` 和 `load_advanced_scheduler_config` 函数
    - 遵循 overrides > TOML > dataclass 默认值优先级
    - TOML 文件不存在时使用 dataclass 默认值
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [~] 2.4 创建 `tests/strategy/domain/domain_service/test_execution_config_properties.py` 属性测试（属性 1, 2, 5）
    - **Property 1: SmartOrderExecutor 配置加载优先级**
    - **Validates: Requirements 1.1, 1.3, 1.4**
    - **Property 2: AdvancedScheduler 配置加载优先级**
    - **Validates: Requirements 1.2, 1.3, 1.4**
    - **Property 5: AdvancedSchedulerConfig 不可变性**
    - **Validates: Requirements 3.2**

- [~] 3. Checkpoint - 确保配置加载和缺陷修复测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 添加工厂方法与修改构造函数
  - [~] 4.1 修改 `AdvancedOrderScheduler.__init__` 接受可选 `AdvancedSchedulerConfig` 参数
    - 默认创建 `AdvancedSchedulerConfig()` 实例
    - submit 方法未显式传入参数时使用 config 中的默认值
    - _Requirements: 3.3, 3.4_

  - [~] 4.2 为 `SmartOrderExecutor` 添加 `from_yaml_config(config_dict)` 类方法
    - 缺失字段使用 OrderExecutionConfig 默认值
    - 空字典使用全部默认值
    - 忽略未知字段
    - _Requirements: 2.1, 2.3, 2.4_

  - [~] 4.3 为 `AdvancedOrderScheduler` 添加 `from_yaml_config(config_dict)` 类方法
    - 缺失字段使用 AdvancedSchedulerConfig 默认值
    - 空字典使用全部默认值
    - 忽略未知字段
    - _Requirements: 2.2, 2.3, 2.4_

  - [~] 4.4 在 `test_execution_config_properties.py` 中追加属性测试（属性 3, 4）
    - **Property 3: SmartOrderExecutor from_yaml_config 一致性**
    - **Validates: Requirements 2.1, 2.3, 2.4**
    - **Property 4: AdvancedOrderScheduler from_yaml_config 一致性**
    - **Validates: Requirements 2.2, 2.3, 2.4**


  - [~] 4.5 在 `test_execution_config_properties.py` 中追加属性测试（属性 8, 9）
    - **Property 8: 重试耗尽产生正确的 OrderRetryExhaustedEvent**
    - **Validates: Requirements 6.1, 6.2**
    - **Property 9: 定时拆单子单总量守恒**
    - **Validates: Requirements 5.2**

- [ ] 5. 实现序列化与反序列化
  - [~] 5.1 为 `SmartOrderExecutor` 添加 `to_dict()` 和 `from_dict(data, config)` 方法
    - 序列化 config 和 _orders 字典为 JSON 兼容字典
    - _orders 中每个 ManagedOrder 委托 ManagedOrder.to_dict()
    - from_dict 支持可选 config 参数，未提供时从字典恢复
    - _Requirements: 9.1, 9.2, 9.3_

  - [~] 5.2 为 `AdvancedOrderScheduler` 添加 `to_dict()` 和 `from_dict(data, config)` 方法
    - 序列化 config 和 _orders 字典为 JSON 兼容字典
    - _orders 中每个 AdvancedOrder 委托 AdvancedOrder.to_dict()
    - from_dict 支持可选 config 参数，未提供时从字典恢复
    - _Requirements: 9.4, 9.5_

  - [~] 5.3 创建 `tests/strategy/domain/domain_service/test_execution_serialization_properties.py` 属性测试（属性 10, 11）
    - **Property 10: SmartOrderExecutor 序列化 round-trip**
    - **Validates: Requirements 9.1, 9.2, 9.3**
    - **Property 11: AdvancedOrderScheduler 序列化 round-trip**
    - **Validates: Requirements 9.4, 9.5**

- [~] 6. Checkpoint - 确保工厂方法和序列化测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. 新增 ExecutionCoordinator 协调器
  - [~] 7.1 创建 `src/strategy/domain/domain_service/execution/execution_coordinator.py`
    - 实现 `__init__` 持有 SmartOrderExecutor 和 AdvancedOrderScheduler 引用
    - 实现 `process_pending_children`：从 scheduler 获取到期子单，用 executor 计算自适应价格，返回指令列表和事件列表
    - 实现 `on_child_order_submitted`：注册子单到 executor 超时管理
    - 实现 `check_timeouts_and_retry`：检查超时、准备重试指令、重试耗尽产生事件
    - 实现 `on_child_filled`：委托给 scheduler 处理子单成交
    - 不直接调用交易网关，仅返回领域事件列表
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [~] 7.2 创建 `tests/strategy/domain/domain_service/test_execution_coordinator_properties.py` 属性测试（属性 6, 7）
    - **Property 6: 协调器使用自适应价格计算**
    - **Validates: Requirements 4.2**
    - **Property 7: 协调器注册子单到超时管理**
    - **Validates: Requirements 4.3**

  - [~] 7.3 创建 `tests/strategy/domain/domain_service/test_execution_integration.py` 集成测试
    - 验证高级订单子单使用自适应价格计算后的价格
    - 验证子单超时后触发重试流程
    - 验证重试耗尽时产生 OrderRetryExhaustedEvent 事件
    - 验证高级订单全部子单成交后产生完成事件
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 8. 补充 `__init__.py` 导出并完成最终集成
  - [~] 8.1 更新 `src/strategy/domain/domain_service/execution/__init__.py`
    - 导出 SmartOrderExecutor、AdvancedOrderScheduler、ExecutionCoordinator
    - 定义 `__all__` 列表
    - _Requirements: 7.1, 7.2, 7.3_

- [~] 9. Final checkpoint - 确保所有测试通过
  - 运行全部测试确认无破坏
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 采用先修复后新增策略：先修复重复方法和未使用事件，再添加配置和工厂方法，最后新增协调层
- 每个属性测试使用 hypothesis 库，至少 100 次迭代
- 每个属性测试标注 `# Feature: execution-service-enhancement, Property N: <title>`
- 属性测试分布在三个文件中：test_execution_config_properties.py（属性 1-5, 8-9）、test_execution_coordinator_properties.py（属性 6-7）、test_execution_serialization_properties.py（属性 10-11）
