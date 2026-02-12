# Requirements Document

## Introduction

本需求文档定义了期权量化交易策略框架的三项增强功能：Greeks 风控层、组合级风险聚合、订单执行增强。这三项功能将在现有 DDD 架构基础上扩展，为期权卖方策略提供更精细的风险管理和更智能的订单执行能力。

## Glossary

- **Greeks_Calculator**: 负责计算期权 Greeks（Delta、Gamma、Theta、Vega）的领域服务
- **Portfolio_Risk_Aggregator**: 负责将所有持仓的 Greeks 汇总到组合级别并执行阈值检查的聚合服务
- **Order_Executor**: 负责智能下单、超时撤单、自适应价格调整的订单执行增强组件
- **Greeks**: 期权定价模型中的风险敏感度指标，包括 Delta（标的价格敏感度）、Gamma（Delta 变化率）、Theta（时间衰减）、Vega（波动率敏感度）
- **Implied_Volatility**: 隐含波动率，由期权市场价格反推得到的波动率参数
- **Portfolio_Greeks**: 组合级别的 Greeks 汇总值，等于所有持仓 Greeks 的加权求和
- **Risk_Breach_Event**: 风控阈值被突破时产生的领域事件
- **Adaptive_Price**: 基于市场买卖盘口动态调整的委托价格
- **Order_Timeout**: 订单在指定时间内未成交时触发的超时处理机制
- **Position**: 策略视角的期权持仓实体，追踪开仓信号和生命周期
- **Black_Scholes_Model**: 用于计算欧式期权理论价格和 Greeks 的标准定价模型

## Requirements

### Requirement 1: Greeks 计算

**User Story:** As a 策略开发者, I want to 计算每个期权持仓的 Greeks 指标, so that 我可以量化每个持仓的风险敞口。

#### Acceptance Criteria

1. WHEN 提供期权合约参数（标的价格、行权价、剩余到期时间、无风险利率、隐含波动率、期权类型）时, THE Greeks_Calculator SHALL 返回包含 Delta、Gamma、Theta、Vega 四个值的 Greeks 结果
2. WHEN 隐含波动率为零或负数时, THE Greeks_Calculator SHALL 返回包含错误描述的失败结果而非抛出异常
3. WHEN 剩余到期时间为零时, THE Greeks_Calculator SHALL 返回到期时的内在价值 Greeks（Delta 为 0 或 1，Gamma/Theta/Vega 为 0）
4. FOR ALL 有效的期权参数组合, THE Greeks_Calculator SHALL 满足 Put-Call Parity 关系：Call_Delta - Put_Delta 等于 1（在相同行权价和到期日下）
5. THE Greeks_Calculator SHALL 使用 Black-Scholes 模型作为默认计算引擎

### Requirement 2: 隐含波动率计算

**User Story:** As a 策略开发者, I want to 从期权市场价格反推隐含波动率, so that 我可以使用实时市场数据驱动 Greeks 计算。

#### Acceptance Criteria

1. WHEN 提供期权市场价格和合约参数时, THE Greeks_Calculator SHALL 使用数值方法求解隐含波动率
2. WHEN 数值求解在最大迭代次数内未收敛时, THE Greeks_Calculator SHALL 返回包含错误描述的失败结果
3. FOR ALL 有效的隐含波动率值, 将其代入 Black-Scholes 公式计算出的理论价格与输入的市场价格之差 SHALL 小于 0.01
4. WHEN 市场价格低于期权内在价值时, THE Greeks_Calculator SHALL 返回包含错误描述的失败结果

### Requirement 3: 持仓级 Greeks 风控

**User Story:** As a 风控管理者, I want to 对单个持仓的 Greeks 值设置阈值限制, so that 我可以在开仓前拒绝风险过高的交易。

#### Acceptance Criteria

1. WHEN 开仓前计算的单持仓 Delta 绝对值超过配置的阈值时, THE Portfolio_Risk_Aggregator SHALL 拒绝该开仓请求并返回拒绝原因
2. WHEN 开仓前计算的单持仓 Gamma 绝对值超过配置的阈值时, THE Portfolio_Risk_Aggregator SHALL 拒绝该开仓请求并返回拒绝原因
3. WHEN 开仓前计算的单持仓 Vega 绝对值超过配置的阈值时, THE Portfolio_Risk_Aggregator SHALL 拒绝该开仓请求并返回拒绝原因
4. WHEN 所有单持仓 Greeks 均在阈值范围内时, THE Portfolio_Risk_Aggregator SHALL 允许该开仓请求

### Requirement 4: 组合级 Greeks 聚合

**User Story:** As a 风控管理者, I want to 将所有持仓的 Greeks 汇总到组合级别, so that 我可以监控整体风险敞口。

#### Acceptance Criteria

1. THE Portfolio_Risk_Aggregator SHALL 计算所有活跃持仓的 Greeks 加权求和（权重为持仓手数乘以合约乘数）
2. WHEN 新增或移除持仓时, THE Portfolio_Risk_Aggregator SHALL 重新计算组合级 Greeks
3. WHEN 组合级 Delta 绝对值超过配置的阈值时, THE Portfolio_Risk_Aggregator SHALL 产生 Risk_Breach_Event 领域事件
4. WHEN 组合级 Gamma 绝对值超过配置的阈值时, THE Portfolio_Risk_Aggregator SHALL 产生 Risk_Breach_Event 领域事件
5. WHEN 组合级 Vega 绝对值超过配置的阈值时, THE Portfolio_Risk_Aggregator SHALL 产生 Risk_Breach_Event 领域事件

### Requirement 5: Greeks 风控配置

**User Story:** As a 策略开发者, I want to 通过 YAML 配置文件设置 Greeks 风控阈值, so that 我可以在不修改代码的情况下调整风控参数。

#### Acceptance Criteria

1. THE Portfolio_Risk_Aggregator SHALL 从 YAML 配置文件读取单持仓和组合级的 Greeks 阈值
2. WHEN 配置文件中缺少某个阈值参数时, THE Portfolio_Risk_Aggregator SHALL 使用预定义的默认值
3. THE Greeks_Calculator SHALL 从 YAML 配置文件读取无风险利率参数

### Requirement 6: 订单超时管理

**User Story:** As a 策略开发者, I want to 自动撤销超时未成交的订单, so that 我可以避免挂单长时间占用资金。

#### Acceptance Criteria

1. WHEN 限价单在配置的超时时间内未完全成交时, THE Order_Executor SHALL 自动撤销该订单
2. WHEN 订单被超时撤销后, THE Order_Executor SHALL 产生 OrderTimeoutEvent 领域事件
3. WHEN 订单在超时检查前已完全成交时, THE Order_Executor SHALL 不执行撤销操作

### Requirement 7: 自适应委托价格

**User Story:** As a 策略开发者, I want to 根据市场盘口动态调整委托价格, so that 我可以在流动性不足时提高成交概率。

#### Acceptance Criteria

1. WHEN 生成卖出开仓指令时, THE Order_Executor SHALL 基于买一价和配置的滑点跳数计算委托价格
2. WHEN 生成买入平仓指令时, THE Order_Executor SHALL 基于卖一价和配置的滑点跳数计算委托价格
3. WHEN 盘口数据不可用时, THE Order_Executor SHALL 使用原始指令价格作为委托价格
4. FOR ALL 计算出的委托价格, THE Order_Executor SHALL 确保价格为合约最小变动价位的整数倍

### Requirement 8: 订单执行重试

**User Story:** As a 策略开发者, I want to 在订单超时撤销后自动以调整后的价格重新下单, so that 我可以提高整体成交率。

#### Acceptance Criteria

1. WHEN 订单因超时被撤销且重试次数未达到上限时, THE Order_Executor SHALL 以更激进的价格重新提交订单
2. WHEN 重试次数达到配置的上限时, THE Order_Executor SHALL 停止重试并产生 OrderRetryExhaustedEvent 领域事件
3. WHEN 重试下单时, THE Order_Executor SHALL 在前一次价格基础上增加一个滑点跳数

### Requirement 9: Greeks 与订单执行的序列化

**User Story:** As a 策略开发者, I want to 将 Greeks 计算结果和订单执行状态持久化, so that 策略重启后可以恢复风控状态。

#### Acceptance Criteria

1. THE Portfolio_Risk_Aggregator SHALL 将组合级 Greeks 快照序列化为 JSON 格式
2. FOR ALL 有效的组合级 Greeks 快照, 序列化后再反序列化 SHALL 产生与原始快照等价的对象
3. THE Order_Executor SHALL 将活跃订单的执行状态（重试次数、超时时间戳）序列化为 JSON 格式
4. FOR ALL 有效的订单执行状态, 序列化后再反序列化 SHALL 产生与原始状态等价的对象
