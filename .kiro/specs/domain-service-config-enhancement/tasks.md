# 实现计划：领域服务配置增强

## 概述

将 PositionSizingService、PricingEngine、BaseFutureSelector 三个领域服务的散装参数和硬编码常量提取为统一的不可变配置值对象，遵循 OptionSelectorConfig 的设计模式。

## 任务列表

- [x] 1. 创建配置值对象目录结构
  - 创建 `src/strategy/domain/value_object/config/` 目录
  - 创建 `__init__.py` 模块初始化文件
  - _需求: 1.1, 1.2, 1.3_

- [x] 2. 实现 PositionSizingConfig 配置值对象
  - [x] 2.1 创建 PositionSizingConfig 类
    - 在 `src/strategy/domain/value_object/config/position_sizing_config.py` 创建配置类
    - 使用 `@dataclass(frozen=True)` 定义不可变值对象
    - 包含 7 个字段：max_positions、global_daily_limit、contract_daily_limit、margin_ratio、min_margin_ratio、margin_usage_limit、max_volume_per_order
    - 所有字段提供与 PositionSizingService 原默认参数一致的默认值
    - _需求: 2.1, 2.2, 2.3_

  - [x] 2.2 重构 PositionSizingService 使用配置对象
    - 修改 `__init__` 方法签名为 `__init__(self, config: Optional[PositionSizingConfig] = None)`
    - 未提供配置时使用默认配置 `PositionSizingConfig()`
    - 从配置对象读取所有原先的散装参数
    - _需求: 2.4, 2.5, 2.6_

  - [x] 2.3 编写 PositionSizingService 行为一致性属性测试
    - **属性 2: PositionSizingService 行为一致性**
    - **验证需求: 2.6, 5.1**

- [x] 3. 实现 PricingEngineConfig 配置值对象
  - [x] 3.1 创建 PricingEngineConfig 类
    - 在 `src/strategy/domain/value_object/config/pricing_engine_config.py` 创建配置类
    - 使用 `@dataclass(frozen=True)` 定义不可变值对象
    - 包含 2 个字段：american_model、crr_steps
    - 所有字段提供与 PricingEngine 原默认参数一致的默认值
    - _需求: 3.1, 3.2, 3.3_

  - [x] 3.2 重构 PricingEngine 使用配置对象
    - 修改 `__init__` 方法签名为 `__init__(self, config: Optional[PricingEngineConfig] = None)`
    - 未提供配置时使用默认配置 `PricingEngineConfig()`
    - 从配置对象读取所有原先的散装参数
    - _需求: 3.4, 3.5, 3.6_

  - [x] 3.3 编写 PricingEngine 行为一致性属性测试
    - **属性 3: PricingEngine 行为一致性**
    - **验证需求: 3.6, 5.2**

- [ ] 4. 实现 FutureSelectorConfig 配置值对象
  - [x] 4.1 创建 FutureSelectorConfig 类
    - 在 `src/strategy/domain/value_object/config/future_selector_config.py` 创建配置类
    - 使用 `@dataclass(frozen=True)` 定义不可变值对象
    - 包含 3 个字段：volume_weight、oi_weight、rollover_days
    - 所有字段提供与 BaseFutureSelector 原默认参数一致的默认值
    - _需求: 4.1, 4.2, 4.3_

  - [x] 4.2 重构 BaseFutureSelector 使用配置对象
    - 添加 `__init__` 方法接收配置对象
    - 修改 `select_dominant_contract` 方法，从配置读取 volume_weight 和 oi_weight
    - 修改 `check_rollover` 方法，从配置读取 rollover_days
    - 移除方法签名中的对应参数
    - _需求: 4.4, 4.5, 4.6, 4.7_

  - [x] 4.3 编写 BaseFutureSelector 一致性属性测试
    - **属性 4: BaseFutureSelector 主力合约选择一致性**
    - **属性 5: BaseFutureSelector 移仓检查一致性**
    - **验证需求: 5.3**

- [~] 5. 检查点 - 确保核心功能测试通过
  - 确保所有测试通过，如有问题请询问用户

- [ ] 6. 更新 __init__.py 导出和调用方适配
  - [~] 6.1 更新配置目录 __init__.py
    - 导出 PositionSizingConfig、PricingEngineConfig、FutureSelectorConfig
    - _需求: 1.3_

  - [~] 6.2 更新调用方代码
    - 查找并更新所有直接传递散装参数实例化服务的调用方
    - 改为通过配置对象传递配置
    - _需求: 6.1, 6.2, 6.3_

- [ ] 7. 编写配置值对象通用属性测试
  - [~] 7.1 编写配置不可变性属性测试
    - **属性 1: 配置值对象不可变性**
    - **验证需求: 2.1, 3.1, 4.1**

  - [~] 7.2 编写配置字段可自定义属性测试
    - **属性 6: 配置字段可自定义**
    - **验证需求: 2.4, 3.4, 4.4**

- [~] 8. 最终检查点 - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户

## 备注

- 标记 `*` 的任务为可选任务，可跳过以加快 MVP 进度
- 每个任务引用具体需求以确保可追溯性
- 检查点确保增量验证
- 属性测试验证通用正确性属性
- 单元测试验证具体示例和边界情况
