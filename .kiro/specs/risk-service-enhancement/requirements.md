# 需求文档

## 介绍

本文档定义期权交易策略系统中风险管理领域服务的增强需求。当前系统已实现基础的组合风险聚合（PortfolioRiskAggregator）和仓位管理（PositionSizingService）功能。本次增强将添加持仓后风险监控的领域服务，包括止损管理、风险预算分配、持仓流动性监控、集中度风险监控和时间衰减监控等功能。

本服务聚焦于持仓后的风险管理，与 selection 服务形成清晰的职责边界：
- selection 服务负责：开仓前的合约选择、流动性检查、虚值档位选择、到期日过滤等
- risk 服务负责：持仓后的风险监控、止损触发、风险预算管理、集中度监控、时间衰减监控等

## 术语表

- **Risk_System**: 风险管理系统，负责监控和控制交易风险
- **Stop_Loss_Manager**: 止损管理器，负责监控持仓盈亏并触发止损
- **Risk_Budget_Allocator**: 风险预算分配器，负责在不同策略/品种间分配风险额度
- **Liquidity_Risk_Monitor**: 流动性风险监控器，负责监控已持仓合约的流动性变化
- **Concentration_Monitor**: 集中度监控器，负责监控持仓的集中度风险
- **Time_Decay_Monitor**: 时间衰减监控器，负责监控组合的时间衰减风险
- **Position**: 持仓实体，包含合约代码、手数、开仓价格等信息
- **PortfolioGreeks**: 组合级 Greeks 快照，包含 Delta/Gamma/Theta/Vega 总值
- **Greeks**: 期权风险指标，包括 Delta、Gamma、Theta、Vega 等
- **Drawdown**: 回撤，从峰值到谷底的最大跌幅
- **HHI**: 赫芬达尔指数（Herfindahl-Hirschman Index），衡量集中度的综合指标

## 需求

### 需求 1: 止损管理服务

**用户故事:** 作为交易系统，我希望自动监控持仓盈亏并触发止损，以便控制单笔交易和组合的最大损失。

#### 验收标准

1. WHEN 持仓浮动亏损超过止损阈值，THE Stop_Loss_Manager SHALL 生成平仓指令
2. THE Stop_Loss_Manager SHALL 支持按金额止损和按百分比止损两种模式
3. WHEN 组合总亏损超过每日止损限额，THE Stop_Loss_Manager SHALL 生成所有持仓的平仓指令
4. THE Stop_Loss_Manager SHALL 记录每次止损触发的时间、合约、亏损金额和触发原因
5. WHILE 持仓处于盈利状态，THE Stop_Loss_Manager SHALL 支持移动止损功能
6. FOR ALL 止损触发事件，THE Stop_Loss_Manager SHALL 生成 StopLossTriggeredEvent 领域事件

### 需求 2: 风险预算分配服务

**用户故事:** 作为风险管理人员，我希望在不同策略或品种间分配风险额度，以便实现风险的多元化配置。

#### 验收标准

1. THE Risk_Budget_Allocator SHALL 支持按品种分配 Greeks 预算
2. THE Risk_Budget_Allocator SHALL 支持按策略类型分配 Greeks 预算
3. WHEN 某品种或策略的 Greeks 使用量超过分配额度，THE Risk_Budget_Allocator SHALL 返回预算超限标志
4. THE Risk_Budget_Allocator SHALL 计算每个品种/策略的当前 Greeks 使用量
5. THE Risk_Budget_Allocator SHALL 计算每个品种/策略的剩余 Greeks 预算
6. THE Risk_Budget_Allocator SHALL 支持动态调整预算分配比例
7. FOR ALL 预算分配，总预算之和 SHALL 不超过组合级 Greeks 限额

### 需求 3: 持仓流动性监控服务

**用户故事:** 作为交易系统，我希望监控已持仓合约的流动性变化，以便及时发现流动性恶化的风险。

#### 验收标准

1. WHEN 提供持仓合约的市场数据，THE Liquidity_Risk_Monitor SHALL 计算流动性评分
2. THE Liquidity_Risk_Monitor SHALL 基于成交量变化监控流动性趋势
3. THE Liquidity_Risk_Monitor SHALL 基于买卖价差变化监控流动性趋势
4. THE Liquidity_Risk_Monitor SHALL 基于持仓量变化监控流动性趋势
5. WHEN 持仓合约的流动性评分低于阈值，THE Liquidity_Risk_Monitor SHALL 生成流动性恶化警告
6. THE Liquidity_Risk_Monitor SHALL 支持配置流动性评分的权重参数
7. THE Liquidity_Risk_Monitor SHALL 跟踪持仓合约的流动性历史变化
8. FOR ALL 流动性监控，THE Liquidity_Risk_Monitor SHALL 仅针对已持仓合约进行评估

### 需求 4: 集中度风险监控服务

**用户故事:** 作为风险管理人员，我希望监控持仓的集中度风险，以便避免过度集中于单一品种或到期日。

#### 验收标准

1. THE Concentration_Monitor SHALL 计算单一品种的持仓占比
2. THE Concentration_Monitor SHALL 计算单一到期日的持仓占比
3. THE Concentration_Monitor SHALL 计算单一行权价区间的持仓占比
4. WHEN 任一维度的集中度超过阈值，THE Concentration_Monitor SHALL 返回集中度超限警告
5. THE Concentration_Monitor SHALL 支持配置各维度的集中度阈值
6. THE Concentration_Monitor SHALL 计算 HHI（赫芬达尔指数）作为集中度综合指标
7. FOR ALL 集中度计算，THE Concentration_Monitor SHALL 基于持仓的名义价值或保证金占用

### 需求 5: 时间衰减风险监控服务

**用户故事:** 作为交易系统，我希望监控组合的时间衰减风险，以便及时调整临近到期的持仓。

#### 验收标准

1. THE Time_Decay_Monitor SHALL 计算组合的总 Theta 值
2. THE Time_Decay_Monitor SHALL 识别距离到期日少于 N 天的持仓
3. WHEN 持仓距离到期日少于配置的临界天数，THE Time_Decay_Monitor SHALL 生成到期提醒事件
4. THE Time_Decay_Monitor SHALL 计算每日预期的时间价值衰减金额
5. THE Time_Decay_Monitor SHALL 按到期日分组统计持仓分布
6. THE Time_Decay_Monitor SHALL 支持配置到期提醒的临界天数
7. FOR ALL 时间衰减计算，THE Time_Decay_Monitor SHALL 使用当前持仓的 Theta 值
