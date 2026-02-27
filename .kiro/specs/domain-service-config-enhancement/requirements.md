# 需求文档：领域服务配置增强

## 简介

参照 OptionSelectorService 使用 OptionSelectorConfig 的模式，为 PositionSizingService、PricingEngine、BaseFutureSelector 三个领域服务提取配置值对象，将散装参数和硬编码常量收拢为统一的不可变配置对象，提升可配置性和可测试性。新增的配置值对象统一存放在 `src/strategy/domain/value_object/config/` 子目录下。

## 术语表

- **PositionSizingService**: 仓位管理领域服务，负责计算开仓手数、保证金估算等
- **PricingEngine**: 统一定价引擎，根据期权行权方式路由到合适的定价器
- **BaseFutureSelector**: 期货合约选择基类，提供主力合约选择和移仓换月检查
- **PositionSizingConfig**: PositionSizingService 的配置值对象
- **PricingEngineConfig**: PricingEngine 的配置值对象
- **FutureSelectorConfig**: BaseFutureSelector 的配置值对象
- **Config_Directory**: `src/strategy/domain/value_object/config/` 子目录，用于集中存放配置值对象

## 需求

### 需求 1：创建配置值对象目录

**用户故事：** 作为开发者，我希望有一个专门的目录来存放配置值对象，以便与其他值对象分离，保持项目结构清晰。

#### 验收标准

1. THE Config_Directory SHALL 位于 `src/strategy/domain/value_object/config/` 路径下
2. THE Config_Directory SHALL 包含 `__init__.py` 模块初始化文件
3. THE `__init__.py` SHALL 导出该目录下所有配置值对象类

### 需求 2：PositionSizingConfig 配置值对象

**用户故事：** 作为开发者，我希望将 PositionSizingService 的 7 个散装初始化参数提取为一个不可变配置值对象，以便集中管理仓位管理相关配置。

#### 验收标准

1. THE PositionSizingConfig SHALL 使用 `@dataclass(frozen=True)` 定义为不可变值对象
2. THE PositionSizingConfig SHALL 包含以下字段并提供默认值：max_positions (int, 默认 5)、global_daily_limit (int, 默认 50)、contract_daily_limit (int, 默认 2)、margin_ratio (float, 默认 0.12)、min_margin_ratio (float, 默认 0.07)、margin_usage_limit (float, 默认 0.6)、max_volume_per_order (int, 默认 10)
3. THE PositionSizingConfig SHALL 存放在 `src/strategy/domain/value_object/config/position_sizing_config.py` 文件中
4. WHEN PositionSizingService 初始化时，THE PositionSizingService SHALL 通过 `__init__(self, config: Optional[PositionSizingConfig] = None)` 接收配置对象
5. WHEN 未提供配置对象时，THE PositionSizingService SHALL 使用默认配置（即 `PositionSizingConfig()` 的默认值）
6. THE PositionSizingService SHALL 从配置对象读取所有原先的散装参数，行为与重构前保持一致

### 需求 3：PricingEngineConfig 配置值对象

**用户故事：** 作为开发者，我希望将 PricingEngine 的初始化参数提取为一个不可变配置值对象，以便集中管理定价引擎相关配置。

#### 验收标准

1. THE PricingEngineConfig SHALL 使用 `@dataclass(frozen=True)` 定义为不可变值对象
2. THE PricingEngineConfig SHALL 包含以下字段并提供默认值：american_model (PricingModel, 默认 PricingModel.BAW)、crr_steps (int, 默认 100)
3. THE PricingEngineConfig SHALL 存放在 `src/strategy/domain/value_object/config/pricing_engine_config.py` 文件中
4. WHEN PricingEngine 初始化时，THE PricingEngine SHALL 通过 `__init__(self, config: Optional[PricingEngineConfig] = None)` 接收配置对象
5. WHEN 未提供配置对象时，THE PricingEngine SHALL 使用默认配置（即 `PricingEngineConfig()` 的默认值）
6. THE PricingEngine SHALL 从配置对象读取所有原先的散装参数，行为与重构前保持一致

### 需求 4：FutureSelectorConfig 配置值对象

**用户故事：** 作为开发者，我希望将 BaseFutureSelector 方法签名中的硬编码参数提取为一个不可变配置值对象，以便集中管理期货选择相关配置。

#### 验收标准

1. THE FutureSelectorConfig SHALL 使用 `@dataclass(frozen=True)` 定义为不可变值对象
2. THE FutureSelectorConfig SHALL 包含以下字段并提供默认值：volume_weight (float, 默认 0.6)、oi_weight (float, 默认 0.4)、rollover_days (int, 默认 5)
3. THE FutureSelectorConfig SHALL 存放在 `src/strategy/domain/value_object/config/future_selector_config.py` 文件中
4. WHEN BaseFutureSelector 初始化时，THE BaseFutureSelector SHALL 通过 `__init__(self, config: Optional[FutureSelectorConfig] = None)` 接收配置对象
5. WHEN 未提供配置对象时，THE BaseFutureSelector SHALL 使用默认配置（即 `FutureSelectorConfig()` 的默认值）
6. THE BaseFutureSelector 的 select_dominant_contract 方法 SHALL 从配置对象读取 volume_weight 和 oi_weight，移除方法签名中的对应参数
7. THE BaseFutureSelector 的 check_rollover 方法 SHALL 从配置对象读取 rollover_days，移除方法签名中的对应参数

### 需求 5：向后兼容与行为一致性

**用户故事：** 作为开发者，我希望重构后的服务在不提供配置对象时行为与重构前完全一致，以确保现有功能不受影响。

#### 验收标准

1. WHEN 使用默认配置实例化 PositionSizingService 时，THE PositionSizingService SHALL 产生与重构前使用默认参数时相同的计算结果
2. WHEN 使用默认配置实例化 PricingEngine 时，THE PricingEngine SHALL 产生与重构前使用默认参数时相同的定价结果
3. WHEN 使用默认配置实例化 BaseFutureSelector 时，THE BaseFutureSelector SHALL 产生与重构前使用默认参数时相同的选择和移仓结果
4. THE 三个配置值对象的默认字段值 SHALL 与各服务重构前的默认参数值完全一致

### 需求 6：现有调用方适配

**用户故事：** 作为开发者，我希望更新所有直接使用旧参数签名的调用方代码，以适配新的配置对象注入方式。

#### 验收标准

1. WHEN 项目中存在直接传递散装参数实例化 PositionSizingService 的调用方时，THE 调用方 SHALL 改为通过 PositionSizingConfig 传递配置
2. WHEN 项目中存在直接传递散装参数实例化 PricingEngine 的调用方时，THE 调用方 SHALL 改为通过 PricingEngineConfig 传递配置
3. WHEN 项目中存在直接传递 volume_weight、oi_weight、rollover_days 参数调用 BaseFutureSelector 方法的调用方时，THE 调用方 SHALL 移除这些参数传递
