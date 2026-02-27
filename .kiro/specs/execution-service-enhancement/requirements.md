# 需求文档: 执行服务增强 (Execution Service Enhancement)

## 简介

系统性增强执行领域服务模块 (`src/strategy/domain/domain_service/execution/`)，使其与对冲、风控、选择等模块在架构一致性上对齐。主要包括：补齐 TOML 配置加载、添加工厂方法、提取 AdvancedOrderScheduler 配置值对象、新增服务协调层、修复已知缺陷（重复方法定义、未使用事件、空 `__init__.py`）、补充集成测试和序列化完整性。

## 术语表

- **SmartOrderExecutor**: 智能订单执行器，负责自适应价格计算、超时管理、重试逻辑
- **AdvancedOrderScheduler**: 高级订单调度器，负责冰山单、TWAP、VWAP、定时拆单等拆单逻辑和子单生命周期管理
- **OrderExecutionConfig**: SmartOrderExecutor 的配置值对象（已存在）
- **AdvancedSchedulerConfig**: AdvancedOrderScheduler 的配置值对象（待新增）
- **ExecutionCoordinator**: 执行协调器，协调 SmartOrderExecutor 与 AdvancedOrderScheduler 的联动（待新增）
- **DomainServiceConfigLoader**: 领域服务 TOML 配置加载器 (`domain_service_config_loader.py`)
- **OrderRetryExhaustedEvent**: 订单重试耗尽领域事件
- **ManagedOrder**: 受管理的订单状态值对象，包含序列化方法
- **ChildOrder**: 高级订单的子单
- **TOML 配置文件**: 存放于 `config/domain_service/` 目录下的服务配置文件

## 需求

### 需求 1: TOML 配置文件与配置加载集成

**用户故事:** 作为开发者，我希望执行服务拥有与定价、风控、选择服务一致的 TOML 配置加载机制，以便通过统一的配置管理方式调整执行参数。

#### 验收标准

1. THE DomainServiceConfigLoader SHALL 提供 `load_smart_order_executor_config(overrides)` 函数，从 `config/domain_service/execution/smart_order_executor.toml` 加载配置并返回 OrderExecutionConfig 实例
2. THE DomainServiceConfigLoader SHALL 提供 `load_advanced_scheduler_config(overrides)` 函数，从 `config/domain_service/execution/advanced_scheduler.toml` 加载配置并返回 AdvancedSchedulerConfig 实例
3. WHEN overrides 参数包含字段值时，THE DomainServiceConfigLoader SHALL 优先使用 overrides 值覆盖 TOML 文件中的值
4. WHEN TOML 配置文件不存在时，THE DomainServiceConfigLoader SHALL 使用 dataclass 默认值创建配置实例
5. THE 系统 SHALL 在 `config/domain_service/execution/` 目录下提供 `smart_order_executor.toml` 和 `advanced_scheduler.toml` 默认配置文件

### 需求 2: 工厂方法 `from_yaml_config()`

**用户故事:** 作为开发者，我希望执行服务提供与对冲服务一致的 `from_yaml_config()` 工厂方法，以便从 YAML 策略配置字典快速创建服务实例。

#### 验收标准

1. THE SmartOrderExecutor SHALL 提供 `from_yaml_config(config_dict)` 类方法，从字典创建实例，缺失字段使用 OrderExecutionConfig 默认值
2. THE AdvancedOrderScheduler SHALL 提供 `from_yaml_config(config_dict)` 类方法，从字典创建实例，缺失字段使用 AdvancedSchedulerConfig 默认值
3. WHEN config_dict 为空字典时，THE `from_yaml_config()` SHALL 使用全部默认值创建实例
4. WHEN config_dict 包含未知字段时，THE `from_yaml_config()` SHALL 忽略未知字段，仅使用已定义字段

### 需求 3: AdvancedSchedulerConfig 配置值对象

**用户故事:** 作为开发者，我希望 AdvancedOrderScheduler 拥有独立的配置值对象，以便将散落在各 submit 方法参数中的默认值集中管理。

#### 验收标准

1. THE AdvancedSchedulerConfig SHALL 包含以下字段：`default_batch_size`（默认冰山单批量）、`default_interval_seconds`（默认拆单间隔）、`default_num_slices`（默认分片数）、`default_volume_randomize_ratio`（默认量随机比例）、`default_price_offset_ticks`（默认价格偏移跳数）、`default_price_tick`（默认最小变动价位）
2. THE AdvancedSchedulerConfig SHALL 为 frozen dataclass，所有字段提供合理默认值
3. THE AdvancedOrderScheduler SHALL 在 `__init__` 中接受 AdvancedSchedulerConfig 参数
4. WHEN submit 方法未显式传入参数时，THE AdvancedOrderScheduler SHALL 使用 AdvancedSchedulerConfig 中的默认值

### 需求 4: 执行协调器 (ExecutionCoordinator)

**用户故事:** 作为开发者，我希望有一个协调层展示 SmartOrderExecutor 与 AdvancedOrderScheduler 的联动方式，以便高级订单的子单能利用自适应定价和超时重试能力。

#### 验收标准

1. THE ExecutionCoordinator SHALL 持有 SmartOrderExecutor 和 AdvancedOrderScheduler 的引用
2. WHEN 高级订单产生待提交子单时，THE ExecutionCoordinator SHALL 调用 SmartOrderExecutor 的自适应价格计算为子单计算委托价格
3. WHEN 子单提交后，THE ExecutionCoordinator SHALL 通过 SmartOrderExecutor 注册子单到超时管理
4. WHEN 子单超时被撤销时，THE ExecutionCoordinator SHALL 通过 SmartOrderExecutor 的重试逻辑准备重试指令
5. THE ExecutionCoordinator SHALL 返回领域事件列表，不直接调用交易网关

### 需求 5: 修复重复方法定义

**用户故事:** 作为开发者，我希望 AdvancedOrderScheduler 中的 `submit_timed_split` 方法不存在重复定义，以避免代码混淆和潜在的维护风险。

#### 验收标准

1. THE AdvancedOrderScheduler SHALL 仅包含一个 `submit_timed_split` 方法定义
2. WHEN 修复完成后，THE AdvancedOrderScheduler 的 `submit_timed_split` 功能 SHALL 与修复前保持一致

### 需求 6: 修复未使用的 OrderRetryExhaustedEvent

**用户故事:** 作为开发者，我希望 SmartOrderExecutor 在重试耗尽时正确发出 OrderRetryExhaustedEvent 事件，以便上层能感知重试失败并做出响应。

#### 验收标准

1. WHEN `prepare_retry` 检测到重试次数已达上限时，THE SmartOrderExecutor SHALL 返回 OrderRetryExhaustedEvent 事件
2. THE OrderRetryExhaustedEvent SHALL 包含正确的 `vt_symbol`、`total_retries`、`original_price` 和 `final_price` 字段值
3. THE `prepare_retry` 方法的返回类型 SHALL 调整为包含可选事件的元组 `Tuple[Optional[OrderInstruction], List[DomainEvent]]`

### 需求 7: 补充 `__init__.py` 导出

**用户故事:** 作为开发者，我希望 `execution/__init__.py` 导出核心类，以便通过包级别导入方便使用。

#### 验收标准

1. THE `execution/__init__.py` SHALL 导出 SmartOrderExecutor 类
2. THE `execution/__init__.py` SHALL 导出 AdvancedOrderScheduler 类
3. THE `execution/__init__.py` SHALL 导出 ExecutionCoordinator 类（新增后）

### 需求 8: 集成测试

**用户故事:** 作为开发者，我希望有集成测试验证 SmartOrderExecutor 与 AdvancedOrderScheduler 的协调工作流程，以确保两个服务联动时行为正确。

#### 验收标准

1. THE 集成测试 SHALL 验证高级订单子单使用自适应价格计算后的价格
2. THE 集成测试 SHALL 验证子单超时后触发重试流程
3. THE 集成测试 SHALL 验证重试耗尽时产生 OrderRetryExhaustedEvent 事件
4. THE 集成测试 SHALL 验证高级订单全部子单成交后产生完成事件

### 需求 9: SmartOrderExecutor 状态序列化完整性

**用户故事:** 作为开发者，我希望 SmartOrderExecutor 的完整内部状态（包括所有 ManagedOrder）能够序列化和反序列化，以便支持服务重启后的状态恢复。

#### 验收标准

1. THE SmartOrderExecutor SHALL 提供 `to_dict()` 方法，将内部 `_orders` 字典和 `config` 序列化为 JSON 兼容字典
2. THE SmartOrderExecutor SHALL 提供 `from_dict(data, config)` 类方法，从字典恢复内部状态
3. FOR ALL 有效的 SmartOrderExecutor 状态，序列化后反序列化 SHALL 产生等价的内部状态（round-trip 属性）
4. THE AdvancedOrderScheduler SHALL 提供 `to_dict()` 和 `from_dict(data, config)` 方法，支持完整状态的序列化与反序列化
5. FOR ALL 有效的 AdvancedOrderScheduler 状态，序列化后反序列化 SHALL 产生等价的内部状态（round-trip 属性）
