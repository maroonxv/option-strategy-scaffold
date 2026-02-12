# Requirements Document

## Introduction

本需求文档定义了期权量化交易策略框架的三项高级增强功能：高级订单类型（冰山单、TWAP、VWAP）、动态对冲引擎（Delta 中性、Gamma Scalping）、波动率曲面与期限结构。这三项功能将在现有 DDD 架构和已完成的 Greeks 风控层、组合级风险聚合、SmartOrderExecutor 基础上扩展，为期权交易策略提供更精细的执行能力、自动化对冲管理和波动率分析工具。

## Glossary

- **Iceberg_Order_Engine**: 冰山单执行引擎，将大单拆分为多个小单分批提交，隐藏真实交易意图
- **TWAP_Engine**: 时间加权平均价格执行引擎，在指定时间窗口内均匀分批下单
- **VWAP_Engine**: 成交量加权平均价格执行引擎，根据历史成交量分布在时间窗口内按比例分批下单
- **Advanced_Order_Scheduler**: 高级订单调度器，统一管理冰山单、TWAP、VWAP 的子单生命周期
- **Child_Order**: 高级订单类型拆分后的子单，由 SmartOrderExecutor 执行
- **Delta_Hedging_Engine**: Delta 对冲引擎，监控组合 Delta 敞口并自动生成对冲指令使组合趋近 Delta 中性
- **Gamma_Scalping_Engine**: Gamma Scalping 引擎，利用 Gamma 正敞口在标的价格波动时通过 Delta 再平衡获取收益
- **Hedging_Band**: 对冲触发带，当组合 Delta 偏离目标超过此阈值时触发对冲
- **Volatility_Surface**: 波动率曲面，以行权价和到期时间为坐标轴的隐含波动率三维曲面
- **Vol_Surface_Builder**: 波动率曲面构建器，从市场期权报价中提取隐含波动率并插值构建完整曲面
- **Term_Structure**: 期限结构，同一行权价（通常为 ATM）在不同到期月份的隐含波动率序列
- **Volatility_Smile**: 波动率微笑，同一到期月份不同行权价的隐含波动率曲线
- **Vol_Surface_Snapshot**: 波动率曲面快照，某一时刻的完整波动率曲面数据
- **Greeks_Calculator**: 已有的 Greeks 计算领域服务
- **Portfolio_Risk_Aggregator**: 已有的组合级风险聚合领域服务
- **SmartOrderExecutor**: 已有的智能订单执行领域服务
- **OrderInstruction**: 已有的交易指令值对象

## Requirements

### Requirement 1: 冰山单执行

**User Story:** As a 策略开发者, I want to 将大额订单拆分为多个小单分批提交, so that 我可以减少市场冲击并隐藏真实交易意图。

#### Acceptance Criteria

1. WHEN 提交冰山单请求（总量、每批数量）时, THE Iceberg_Order_Engine SHALL 将总量拆分为多个子单，每个子单数量不超过配置的每批数量
2. WHEN 前一批子单完全成交后, THE Iceberg_Order_Engine SHALL 自动提交下一批子单
3. WHEN 所有子单完全成交后, THE Iceberg_Order_Engine SHALL 产生 IcebergCompleteEvent 领域事件
4. WHEN 冰山单被取消时, THE Iceberg_Order_Engine SHALL 撤销所有未成交的子单并产生 IcebergCancelledEvent 领域事件
5. FOR ALL 冰山单执行, THE Iceberg_Order_Engine SHALL 确保所有子单成交量之和等于请求的总量（完全成交时）或小于总量（被取消时）

### Requirement 2: TWAP 执行

**User Story:** As a 策略开发者, I want to 在指定时间窗口内均匀分批下单, so that 我可以获得接近时间加权平均价格的成交效果。

#### Acceptance Criteria

1. WHEN 提交 TWAP 请求（总量、时间窗口、分片数）时, THE TWAP_Engine SHALL 将总量均匀分配到各时间片并按时间间隔依次提交子单
2. WHEN 到达下一个时间片时, THE TWAP_Engine SHALL 提交该时间片对应的子单
3. WHEN 时间窗口结束且所有子单成交后, THE TWAP_Engine SHALL 产生 TWAPCompleteEvent 领域事件
4. FOR ALL TWAP 执行, THE TWAP_Engine SHALL 确保各时间片之间的时间间隔等于时间窗口除以分片数（在整数秒精度内）

### Requirement 3: VWAP 执行

**User Story:** As a 策略开发者, I want to 根据历史成交量分布在时间窗口内按比例分批下单, so that 我可以获得接近成交量加权平均价格的成交效果。

#### Acceptance Criteria

1. WHEN 提交 VWAP 请求（总量、时间窗口、历史成交量分布）时, THE VWAP_Engine SHALL 按成交量分布比例将总量分配到各时间片
2. WHEN 历史成交量分布中某个时间片的成交量占比为 P 时, THE VWAP_Engine SHALL 分配总量的 P 比例给该时间片
3. WHEN 时间窗口结束且所有子单成交后, THE VWAP_Engine SHALL 产生 VWAPCompleteEvent 领域事件
4. FOR ALL VWAP 执行, THE VWAP_Engine SHALL 确保所有时间片分配量之和等于请求的总量

### Requirement 4: 高级订单调度

**User Story:** As a 策略开发者, I want to 统一管理冰山单、TWAP、VWAP 的子单生命周期, so that 我可以追踪每个高级订单的整体执行进度。

#### Acceptance Criteria

1. THE Advanced_Order_Scheduler SHALL 维护每个高级订单的状态（待执行、执行中、已完成、已取消）
2. WHEN 子单成交回报到达时, THE Advanced_Order_Scheduler SHALL 更新对应高级订单的已成交量
3. WHEN 高级订单的所有子单完全成交时, THE Advanced_Order_Scheduler SHALL 将该订单状态标记为已完成
4. THE Advanced_Order_Scheduler SHALL 将高级订单的执行状态序列化为 JSON 格式
5. FOR ALL 有效的高级订单执行状态, 序列化后再反序列化 SHALL 产生与原始状态等价的对象

### Requirement 5: Delta 对冲引擎

**User Story:** As a 策略开发者, I want to 自动监控组合 Delta 敞口并生成对冲指令, so that 我可以维持组合的 Delta 中性。

#### Acceptance Criteria

1. WHEN 组合 Delta 偏离目标值超过配置的 Hedging_Band 时, THE Delta_Hedging_Engine SHALL 计算所需的对冲手数并生成对冲 OrderInstruction
2. WHEN 计算对冲手数时, THE Delta_Hedging_Engine SHALL 使用公式: 对冲手数 = round((目标Delta - 当前Delta) / (对冲工具Delta * 合约乘数))
3. WHEN 计算出的对冲手数为零时, THE Delta_Hedging_Engine SHALL 不生成对冲指令
4. WHEN 对冲指令生成后, THE Delta_Hedging_Engine SHALL 产生 HedgeExecutedEvent 领域事件
5. THE Delta_Hedging_Engine SHALL 从 YAML 配置文件读取目标 Delta、Hedging_Band 和对冲工具参数

### Requirement 6: Gamma Scalping 引擎

**User Story:** As a 策略开发者, I want to 在持有正 Gamma 敞口时通过 Delta 再平衡获取收益, so that 我可以利用标的价格波动赚取 Gamma 收益。

#### Acceptance Criteria

1. WHEN 标的价格变动导致组合 Delta 偏离零超过配置的再平衡阈值时, THE Gamma_Scalping_Engine SHALL 生成 Delta 再平衡的对冲 OrderInstruction
2. WHEN 组合 Gamma 为负值时, THE Gamma_Scalping_Engine SHALL 拒绝执行 Gamma Scalping 并返回拒绝原因
3. WHEN 再平衡指令生成后, THE Gamma_Scalping_Engine SHALL 产生 GammaScalpEvent 领域事件记录再平衡详情
4. FOR ALL Gamma Scalping 再平衡操作, THE Gamma_Scalping_Engine SHALL 确保再平衡后的目标 Delta 为零

### Requirement 7: 对冲引擎配置

**User Story:** As a 策略开发者, I want to 通过 YAML 配置文件设置对冲参数, so that 我可以在不修改代码的情况下调整对冲策略。

#### Acceptance Criteria

1. THE Delta_Hedging_Engine SHALL 从 YAML 配置文件读取目标 Delta、Hedging_Band、对冲工具合约代码和合约乘数
2. THE Gamma_Scalping_Engine SHALL 从 YAML 配置文件读取再平衡阈值和对冲工具参数
3. WHEN 配置文件中缺少某个对冲参数时, THE Delta_Hedging_Engine SHALL 使用预定义的默认值
4. WHEN 配置文件中缺少某个 Gamma Scalping 参数时, THE Gamma_Scalping_Engine SHALL 使用预定义的默认值

### Requirement 8: 波动率曲面构建

**User Story:** As a 策略开发者, I want to 从市场期权报价中构建波动率曲面, so that 我可以分析不同行权价和到期时间的隐含波动率分布。

#### Acceptance Criteria

1. WHEN 提供一组期权市场报价（行权价、到期时间、隐含波动率）时, THE Vol_Surface_Builder SHALL 构建波动率曲面对象
2. WHEN 查询曲面上某个（行权价、到期时间）坐标点的隐含波动率时, THE Vol_Surface_Builder SHALL 使用双线性插值返回估计值
3. WHEN 查询坐标超出已知数据范围时, THE Vol_Surface_Builder SHALL 返回包含错误描述的失败结果而非抛出异常
4. THE Vol_Surface_Builder SHALL 将波动率曲面快照序列化为 JSON 格式
5. FOR ALL 有效的波动率曲面快照, 序列化后再反序列化 SHALL 产生与原始快照等价的对象

### Requirement 9: 波动率微笑提取

**User Story:** As a 策略开发者, I want to 从波动率曲面中提取特定到期月份的波动率微笑曲线, so that 我可以分析该月份的偏度和凸度特征。

#### Acceptance Criteria

1. WHEN 指定到期时间时, THE Vol_Surface_Builder SHALL 从波动率曲面中提取该到期时间对应的行权价-隐含波动率序列
2. WHEN 指定的到期时间不在已知数据点上时, THE Vol_Surface_Builder SHALL 通过插值生成该到期时间的波动率微笑
3. FOR ALL 提取的波动率微笑, THE Vol_Surface_Builder SHALL 确保返回的行权价序列按升序排列

### Requirement 10: 期限结构提取

**User Story:** As a 策略开发者, I want to 从波动率曲面中提取特定行权价的期限结构, so that 我可以分析不同到期月份的隐含波动率变化趋势。

#### Acceptance Criteria

1. WHEN 指定行权价时, THE Vol_Surface_Builder SHALL 从波动率曲面中提取该行权价对应的到期时间-隐含波动率序列
2. WHEN 指定的行权价不在已知数据点上时, THE Vol_Surface_Builder SHALL 通过插值生成该行权价的期限结构
3. FOR ALL 提取的期限结构, THE Vol_Surface_Builder SHALL 确保返回的到期时间序列按升序排列

