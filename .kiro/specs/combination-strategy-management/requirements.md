# 需求文档：组合策略管理

## 简介

当前期权交易系统中，每个 Position 实体独立追踪单腿持仓，缺乏"组合"（Combination）作为一等公民的领域概念。本特性将引入 Combination 实体，支持常见期权组合策略（Straddle、Strangle、Vertical Spread、Calendar Spread、Iron Condor 等）的建模、识别、Greeks 聚合、盈亏追踪和生命周期管理，使系统能够在组合维度进行风控和操作。

## 术语表

- **Combination**：由多个关联的期权 Position（腿）组成的组合策略实体，具有统一的生命周期
- **Leg**：组合中的单个期权持仓，对应一个 Position 实体
- **CombinationType**：组合策略类型枚举，如 STRADDLE、STRANGLE、VERTICAL_SPREAD、CALENDAR_SPREAD、IRON_CONDOR、CUSTOM
- **CombinationGreeks**：组合级别的 Greeks 聚合结果值对象
- **CombinationPnL**：组合级别的盈亏计算结果值对象
- **CombinationStatus**：组合生命周期状态枚举（PENDING、ACTIVE、PARTIALLY_CLOSED、CLOSED）
- **PositionAggregate**：现有的持仓聚合根，管理所有 Position 实体
- **PortfolioRiskAggregator**：现有的组合风险聚合器领域服务
- **Position**：现有的单腿持仓实体
- **OptionContract**：现有的期权合约值对象

## 需求

### 需求 1：组合策略建模

**用户故事：** 作为期权交易员，我希望将多个期权持仓关联为一个组合策略实体，以便在组合维度统一管理和追踪。

#### 验收标准

1. THE Combination 实体 SHALL 包含唯一标识符、CombinationType、关联的 Leg 列表、CombinationStatus、创建时间和标的合约代码
2. WHEN 创建 Combination 时，THE Combination 实体 SHALL 验证 Leg 数量与 CombinationType 的约束一致（如 Straddle 必须恰好 2 腿）
3. WHEN 创建 Combination 时，THE Combination 实体 SHALL 验证所有 Leg 的标的合约代码一致（Calendar Spread 除外，允许不同到期日）
4. IF Leg 数量或结构不满足 CombinationType 约束，THEN THE Combination 实体 SHALL 拒绝创建并返回描述性错误信息
5. THE CombinationType 枚举 SHALL 支持以下类型：STRADDLE、STRANGLE、VERTICAL_SPREAD、CALENDAR_SPREAD、IRON_CONDOR、CUSTOM

### 需求 2：组合策略识别

**用户故事：** 作为期权交易员，我希望系统能够根据现有持仓自动识别组合策略类型，以便快速了解当前持仓的组合结构。

#### 验收标准

1. WHEN 提供一组 Position 和对应的 OptionContract 信息时，THE CombinationRecognizer 服务 SHALL 分析持仓结构并返回匹配的 CombinationType
2. WHEN 两个 Position 为同一标的、同一到期日、相同行权价、一个 Call 一个 Put 时，THE CombinationRecognizer 服务 SHALL 识别为 STRADDLE
3. WHEN 两个 Position 为同一标的、同一到期日、不同行权价、一个 Call 一个 Put 时，THE CombinationRecognizer 服务 SHALL 识别为 STRANGLE
4. WHEN 两个 Position 为同一标的、同一到期日、相同期权类型、不同行权价时，THE CombinationRecognizer 服务 SHALL 识别为 VERTICAL_SPREAD
5. WHEN 两个 Position 为同一标的、不同到期日、相同行权价、相同期权类型时，THE CombinationRecognizer 服务 SHALL 识别为 CALENDAR_SPREAD
6. WHEN 四个 Position 构成两个 Vertical Spread（一个 Put Spread + 一个 Call Spread）且同一标的、同一到期日时，THE CombinationRecognizer 服务 SHALL 识别为 IRON_CONDOR
7. IF 持仓结构不匹配任何预定义类型，THEN THE CombinationRecognizer 服务 SHALL 返回 CUSTOM 类型

### 需求 3：组合级 Greeks 计算

**用户故事：** 作为期权交易员，我希望查看每个组合的 Greeks 聚合值，以便在组合维度评估风险敞口。

#### 验收标准

1. WHEN 请求组合 Greeks 时，THE CombinationGreeksCalculator 服务 SHALL 对组合内所有活跃 Leg 的 Greeks 进行加权求和（权重 = 持仓量 × 合约乘数 × 方向符号）
2. THE CombinationGreeks 值对象 SHALL 包含 delta、gamma、theta、vega 四个聚合字段
3. WHEN 组合中某个 Leg 的 Greeks 计算失败时，THE CombinationGreeksCalculator 服务 SHALL 在结果中标记该 Leg 为失败并继续计算其余 Leg
4. THE CombinationGreeksCalculator 服务 SHALL 正确处理多头和空头方向的符号（多头为正，空头为负）

### 需求 4：组合级盈亏追踪

**用户故事：** 作为期权交易员，我希望查看每个组合的整体盈亏，以便评估组合策略的表现。

#### 验收标准

1. WHEN 请求组合盈亏时，THE CombinationPnLCalculator 服务 SHALL 基于每个 Leg 的开仓价和当前市场价计算组合整体未实现盈亏
2. THE CombinationPnL 值对象 SHALL 包含总未实现盈亏、每腿盈亏明细列表和计算时间戳
3. WHEN 计算单腿盈亏时，THE CombinationPnLCalculator 服务 SHALL 使用公式：(当前价 - 开仓价) × 持仓量 × 合约乘数 × 方向符号
4. IF 某个 Leg 的当前市场价不可用，THEN THE CombinationPnLCalculator 服务 SHALL 在结果中标记该 Leg 为价格缺失并使用零值

### 需求 5：组合级风控

**用户故事：** 作为期权交易员，我希望系统能够针对单个组合进行 Greeks 风控检查，以便在组合维度控制风险。

#### 验收标准

1. THE CombinationRiskChecker 服务 SHALL 接受组合级 Greeks 阈值配置（delta_limit、gamma_limit、vega_limit）
2. WHEN 组合的 Greeks 绝对值超过配置的阈值时，THE CombinationRiskChecker 服务 SHALL 返回风控检查失败结果并包含超限的 Greek 名称和数值
3. WHEN 组合的 Greeks 绝对值在阈值范围内时，THE CombinationRiskChecker 服务 SHALL 返回风控检查通过结果
4. THE CombinationRiskChecker 服务 SHALL 独立于现有的 PortfolioRiskAggregator 运行，不影响整体组合级风控

### 需求 6：组合生命周期管理

**用户故事：** 作为期权交易员，我希望能够对组合进行统一的生命周期操作（建仓、调整、平仓），以便高效管理组合策略。

#### 验收标准

1. WHEN 创建组合时，THE CombinationLifecycleService 服务 SHALL 为每个 Leg 生成对应的 OrderInstruction 列表
2. WHEN 平仓组合时，THE CombinationLifecycleService 服务 SHALL 为所有活跃 Leg 生成平仓 OrderInstruction 列表
3. WHEN 组合中某个 Leg 完全平仓而其他 Leg 仍活跃时，THE Combination 实体 SHALL 将状态更新为 PARTIALLY_CLOSED
4. WHEN 组合中所有 Leg 完全平仓时，THE Combination 实体 SHALL 将状态更新为 CLOSED
5. WHEN 调整组合中某个 Leg 的持仓量时，THE CombinationLifecycleService 服务 SHALL 生成对应的调整 OrderInstruction 并更新 Combination 状态
6. IF 平仓指令生成时某个 Leg 已经处于平仓状态，THEN THE CombinationLifecycleService 服务 SHALL 跳过该 Leg 并继续处理其余 Leg

### 需求 7：组合与 PositionAggregate 集成

**用户故事：** 作为系统开发者，我希望组合管理能够与现有的 PositionAggregate 无缝集成，以便保持架构一致性。

#### 验收标准

1. THE PositionAggregate SHALL 维护一个 Combination 注册表，记录所有活跃的 Combination 实体
2. WHEN 通过 PositionAggregate 创建 Combination 时，THE PositionAggregate SHALL 将 Combination 中的每个 Leg 关联到对应的 Position 实体
3. WHEN Position 的状态发生变化（成交、平仓）时，THE PositionAggregate SHALL 同步更新关联的 Combination 状态
4. WHEN Combination 状态变更时，THE PositionAggregate SHALL 产生 CombinationStatusChangedEvent 领域事件
5. THE PositionAggregate SHALL 提供按标的合约查询关联 Combination 的接口

### 需求 8：组合策略配置

**用户故事：** 作为期权交易员，我希望通过 YAML 配置文件定义组合级风控参数，以便灵活调整组合策略的风控阈值。

#### 验收标准

1. THE 配置系统 SHALL 在 strategy_config.yaml 中支持 combination_risk 配置节
2. THE combination_risk 配置节 SHALL 包含 delta_limit、gamma_limit、vega_limit 三个阈值字段
3. WHEN 配置文件中缺少 combination_risk 配置节时，THE 配置系统 SHALL 使用合理的默认值（delta_limit=2.0、gamma_limit=0.5、vega_limit=200.0）

### 需求 9：组合策略序列化

**用户故事：** 作为系统开发者，我希望 Combination 实体能够序列化为字典并从字典反序列化，以便支持状态持久化和恢复。

#### 验收标准

1. THE Combination 实体 SHALL 提供 to_dict 方法将自身序列化为 Python 字典
2. THE Combination 实体 SHALL 提供 from_dict 类方法从 Python 字典反序列化恢复实例
3. FOR ALL 有效的 Combination 实例，序列化后再反序列化 SHALL 产生等价的 Combination 实例（往返一致性）
