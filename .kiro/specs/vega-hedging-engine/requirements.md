# 需求文档

## 简介

Vega 对冲引擎用于管理期权组合的 Vega 敞口。当组合 Vega 偏离目标值超过容忍带时，引擎生成对冲指令。与 Delta 对冲使用期货不同，Vega 对冲使用期权合约作为对冲工具，因此对冲工具本身也携带 Delta、Gamma、Theta 等 Greeks，需要在计算中考虑这些附带影响。

## 术语表

- **Vega_Hedging_Engine**: Vega 对冲引擎，负责监控组合 Vega 敞口并生成对冲指令的领域服务
- **Vega**: 期权价格对标的资产隐含波动率变化的敏感度
- **Portfolio_Greeks**: 组合级 Greeks 快照，包含 total_delta、total_gamma、total_theta、total_vega
- **Vega_Hedging_Config**: Vega 对冲配置值对象，定义目标 Vega、容忍带、对冲工具信息及其 Greeks
- **Vega_Hedge_Result**: Vega 对冲计算结果值对象，包含是否需要对冲、对冲手数、方向、指令及附带 Greeks 影响
- **Vega_Hedge_Executed_Event**: Vega 对冲执行领域事件，记录对冲前后的 Vega 敞口及附带 Greeks 影响
- **Order_Instruction**: 交易指令值对象，包含合约代码、方向、开平、手数、价格
- **对冲工具 Vega**: 对冲期权合约每手的 Vega 值
- **附带 Greeks 影响**: 使用期权对冲 Vega 时，对冲工具本身携带的 Delta、Gamma、Theta 变化量

## 需求

### 需求 1: Vega 对冲计算

**用户故事:** 作为交易员，我希望系统能在组合 Vega 偏离目标时自动计算对冲手数，以便及时管理波动率风险。

#### 验收标准

1. WHEN 组合 Vega 与目标 Vega 的偏差绝对值超过容忍带, THE Vega_Hedging_Engine SHALL 计算对冲手数为 `round((target_vega - portfolio_vega) / (hedge_instrument_vega * hedge_instrument_multiplier))` 并生成包含对冲手数和方向的 Vega_Hedge_Result
2. WHEN 组合 Vega 与目标 Vega 的偏差绝对值在容忍带内, THE Vega_Hedging_Engine SHALL 返回 should_hedge=False 的 Vega_Hedge_Result
3. WHEN 对冲手数经四舍五入后为零, THE Vega_Hedging_Engine SHALL 返回 should_hedge=False 的 Vega_Hedge_Result

### 需求 2: 对冲指令生成

**用户故事:** 作为交易员，我希望引擎生成可执行的交易指令，以便对冲服务可以直接下单。

#### 验收标准

1. WHEN Vega_Hedging_Engine 确定需要对冲, THE Vega_Hedging_Engine SHALL 生成包含对冲工具合约代码、方向、开平标志、手数和价格的 Order_Instruction
2. WHEN 计算出的对冲手数为正, THE Vega_Hedging_Engine SHALL 生成方向为 LONG 的 Order_Instruction
3. WHEN 计算出的对冲手数为负, THE Vega_Hedging_Engine SHALL 生成方向为 SHORT 的 Order_Instruction 且手数取绝对值

### 需求 3: 附带 Greeks 影响报告

**用户故事:** 作为交易员，我希望了解 Vega 对冲操作对组合其他 Greeks 的影响，以便评估对冲的副作用。

#### 验收标准

1. WHEN Vega_Hedging_Engine 生成对冲指令, THE Vega_Hedge_Result SHALL 包含对冲操作预计引入的 Delta 变化量、Gamma 变化量和 Theta 变化量
2. WHEN Vega_Hedge_Executed_Event 被创建, THE Vega_Hedge_Executed_Event SHALL 记录对冲前的组合 Vega、预计对冲后的组合 Vega、以及附带的 Delta、Gamma、Theta 变化量

### 需求 4: 配置与输入校验

**用户故事:** 作为交易员，我希望引擎在无效配置或输入时安全拒绝执行，以避免错误的对冲操作。

#### 验收标准

1. IF 对冲工具合约乘数小于等于零, THEN THE Vega_Hedging_Engine SHALL 返回 rejected=True 的 Vega_Hedge_Result 并附带拒绝原因
2. IF 对冲工具 Vega 为零, THEN THE Vega_Hedging_Engine SHALL 返回 rejected=True 的 Vega_Hedge_Result 并附带拒绝原因
3. IF 当前价格小于等于零, THEN THE Vega_Hedging_Engine SHALL 返回 rejected=True 的 Vega_Hedge_Result 并附带拒绝原因

### 需求 5: YAML 配置加载

**用户故事:** 作为交易员，我希望通过 YAML 配置文件初始化 Vega 对冲引擎，以便灵活调整参数。

#### 验收标准

1. WHEN 提供 YAML 配置字典, THE Vega_Hedging_Engine SHALL 使用字典中的值创建 Vega_Hedging_Config 实例
2. WHEN YAML 配置字典中缺少某个字段, THE Vega_Hedging_Engine SHALL 使用 Vega_Hedging_Config 的默认值填充该字段

### 需求 6: 领域事件发布

**用户故事:** 作为系统架构师，我希望 Vega 对冲操作产生领域事件，以便其他模块（如日志、告警）可以响应。

#### 验收标准

1. WHEN Vega_Hedging_Engine 执行对冲, THE Vega_Hedging_Engine SHALL 返回包含 Vega_Hedge_Executed_Event 的事件列表
2. WHEN Vega_Hedging_Engine 不需要对冲或被拒绝, THE Vega_Hedging_Engine SHALL 返回空的事件列表
