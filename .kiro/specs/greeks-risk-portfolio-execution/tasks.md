# Implementation Plan: Greeks 风控层、组合级风险聚合、订单执行增强

## Overview

基于现有 DDD 架构，增量实现三个领域服务及其配套的值对象、领域事件和配置。使用 Python + hypothesis 进行属性测试。每个任务构建在前一个任务之上，最终在 StrategyEntry 中完成编排集成。

## Tasks

- [x] 1. 新增值对象和领域事件
  - [x] 1.1 创建 Greeks 相关值对象 (GreeksInput, GreeksResult, IVResult)
    - 在 `src/strategy/domain/value_object/` 下新建 `greeks.py`
    - 定义 GreeksInput, GreeksResult, IVResult 三个 frozen dataclass
    - _Requirements: 1.1, 2.1_
  - [x] 1.2 创建风控相关值对象 (RiskThresholds, RiskCheckResult, PortfolioGreeks, PositionGreeksEntry)
    - 在 `src/strategy/domain/value_object/` 下新建 `risk.py`
    - 定义 RiskThresholds, RiskCheckResult, PortfolioGreeks, PositionGreeksEntry
    - PortfolioGreeks 需包含 to_dict / from_dict 方法用于 JSON 序列化
    - _Requirements: 3.1, 4.1, 9.1_
  - [x] 1.3 创建订单执行相关值对象 (OrderExecutionConfig, ManagedOrder)
    - 在 `src/strategy/domain/value_object/` 下新建 `order_execution.py`
    - ManagedOrder 需包含 to_dict / from_dict 方法用于 JSON 序列化
    - _Requirements: 6.1, 9.3_
  - [x] 1.4 扩展领域事件 (GreeksRiskBreachEvent, OrderTimeoutEvent, OrderRetryExhaustedEvent)
    - 在 `src/strategy/domain/event/event_types.py` 中新增三个事件 dataclass
    - _Requirements: 4.3, 6.2, 8.2_

- [ ] 2. 实现 GreeksCalculator 领域服务
  - [ ] 2.1 实现 Black-Scholes Greeks 计算
    - 在 `src/strategy/domain/domain_service/` 下新建 `greeks_calculator.py`
    - 实现 calculate_greeks 方法 (Delta, Gamma, Theta, Vega)
    - 实现 bs_price 方法
    - 处理边界条件: time_to_expiry=0, volatility<=0
    - _Requirements: 1.1, 1.2, 1.3, 1.5_
  - [ ] 2.2 Property test: Greeks 计算有效性
    - **Property 1: Greeks 计算对所有有效输入产生有效结果**
    - **Validates: Requirements 1.1**
  - [ ] 2.3 Property test: Put-Call Parity
    - **Property 2: Put-Call Parity 不变量**
    - **Validates: Requirements 1.4**
  - [ ] 2.4 Property test: 到期时 Greeks 边界值
    - **Property 3: 到期时 Greeks 边界值**
    - **Validates: Requirements 1.3**
  - [ ] 2.5 实现隐含波动率求解
    - 在 greeks_calculator.py 中实现 calculate_implied_volatility 方法
    - 使用牛顿法迭代求解
    - 处理边界条件: 未收敛、市场价格低于内在价值
    - _Requirements: 2.1, 2.2, 2.4_
  - [ ] 2.6 Property test: IV Round-Trip
    - **Property 4: 隐含波动率 Round-Trip**
    - **Validates: Requirements 2.1, 2.3**

- [ ] 3. Checkpoint - Greeks 计算验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 实现 PortfolioRiskAggregator 领域服务
  - [ ] 4.1 实现持仓级风控检查
    - 在 `src/strategy/domain/domain_service/` 下新建 `portfolio_risk_aggregator.py`
    - 实现 check_position_risk 方法
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [ ] 4.2 Property test: 持仓级风控检查正确性
    - **Property 5: 持仓级风控检查正确性**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
  - [ ] 4.3 实现组合级 Greeks 聚合
    - 在 portfolio_risk_aggregator.py 中实现 aggregate_portfolio_greeks 方法
    - 返回 PortfolioGreeks 快照和 GreeksRiskBreachEvent 列表
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [ ] 4.4 Property test: 组合级 Greeks 聚合正确性
    - **Property 6: 组合级 Greeks 聚合为正确的加权求和**
    - **Validates: Requirements 4.1, 4.2**
  - [ ] 4.5 Property test: 组合级阈值突破事件
    - **Property 7: 组合级阈值突破事件产生**
    - **Validates: Requirements 4.3, 4.4, 4.5**
  - [ ] 4.6 Property test: PortfolioGreeks 序列化 Round-Trip
    - **Property 12: PortfolioGreeks 序列化 Round-Trip**
    - **Validates: Requirements 9.2**

- [ ] 5. Checkpoint - 风控聚合验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. 实现 SmartOrderExecutor 领域服务
  - [ ] 6.1 实现自适应价格计算和价格对齐
    - 在 `src/strategy/domain/domain_service/` 下新建 `smart_order_executor.py`
    - 实现 calculate_adaptive_price 和 round_price_to_tick 方法
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [ ] 6.2 Property test: 自适应委托价格计算
    - **Property 9: 自适应委托价格计算**
    - **Validates: Requirements 7.1, 7.2**
  - [ ] 6.3 Property test: 价格对齐到最小变动价位
    - **Property 10: 价格对齐到最小变动价位**
    - **Validates: Requirements 7.4**
  - [ ] 6.4 实现订单超时管理
    - 实现 register_order, check_timeouts, mark_order_filled, mark_order_cancelled 方法
    - _Requirements: 6.1, 6.2, 6.3_
  - [ ] 6.5 Property test: 订单超时检查正确性
    - **Property 8: 订单超时检查正确性**
    - **Validates: Requirements 6.1, 6.2, 6.3**
  - [ ] 6.6 实现订单重试逻辑
    - 实现 prepare_retry 方法
    - _Requirements: 8.1, 8.2, 8.3_
  - [ ] 6.7 Property test: 订单重试逻辑
    - **Property 11: 订单重试逻辑**
    - **Validates: Requirements 8.1, 8.2, 8.3**
  - [ ] 6.8 Property test: ManagedOrder 序列化 Round-Trip
    - **Property 13: ManagedOrder 序列化 Round-Trip**
    - **Validates: Requirements 9.4**

- [ ] 7. Checkpoint - 订单执行验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. 配置集成与编排
  - [ ] 8.1 扩展 YAML 配置
    - 在 `config/strategy_config.yaml` 中新增 greeks_risk 和 order_execution 配置节
    - _Requirements: 5.1, 5.2, 5.3_
  - [ ] 8.2 在 StrategyEntry 中集成新服务
    - 在 StrategyEntry.__init__ 中初始化 GreeksCalculator, PortfolioRiskAggregator, SmartOrderExecutor
    - 在开仓流程中插入 Greeks 风控检查
    - 在下单流程中使用 SmartOrderExecutor 的自适应价格
    - 在 on_timer 或 on_bar 中调用超时检查
    - _Requirements: 1.1, 3.1, 4.1, 6.1, 7.1_
  - [ ] 8.3 单元测试: 配置加载与默认值回退
    - 测试 YAML 配置解析
    - 测试缺失配置时的默认值
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 9. Final checkpoint - 全量测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks are required (no optional tasks)
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using hypothesis
- Unit tests validate specific examples and edge cases
