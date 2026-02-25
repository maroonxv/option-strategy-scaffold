# 实现计划: Vega 对冲引擎

## 概述

按照现有 DeltaHedgingEngine / GammaScalpingEngine 的模式，新增 VegaHedgingEngine 及其配套值对象和领域事件。

## 任务

- [x] 1. 新增值对象和领域事件
  - [x] 1.1 在 `src/strategy/domain/value_object/hedging.py` 中新增 `VegaHedgingConfig` 和 `VegaHedgeResult` 数据类
    - VegaHedgingConfig: target_vega, hedging_band, hedge_instrument_vt_symbol, hedge_instrument_vega, hedge_instrument_delta, hedge_instrument_gamma, hedge_instrument_theta, hedge_instrument_multiplier
    - VegaHedgeResult: should_hedge, hedge_volume, hedge_direction, instruction, delta_impact, gamma_impact, theta_impact, rejected, reject_reason, reason
    - _Requirements: 1.1, 3.1_

  - [x] 1.2 在 `src/strategy/domain/event/event_types.py` 中新增 `VegaHedgeExecutedEvent` 数据类
    - 字段: hedge_volume, hedge_direction, portfolio_vega_before, portfolio_vega_after, hedge_instrument, delta_impact, gamma_impact, theta_impact
    - _Requirements: 3.2, 6.1_

- [x] 2. 实现 VegaHedgingEngine
  - [x] 2.1 创建 `src/strategy/domain/domain_service/hedging/vega_hedging_engine.py`
    - 实现 `__init__`、`from_yaml_config`、`check_and_hedge` 方法
    - 输入校验: 乘数 <= 0、Vega = 0、价格 <= 0 时返回 rejected
    - 对冲计算: 偏差判断、手数计算、方向确定、附带 Greeks 影响计算
    - 生成 OrderInstruction 和 VegaHedgeExecutedEvent
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 4.1, 4.2, 4.3, 5.1, 5.2, 6.1, 6.2_

  - [x] 2.2 在 `src/strategy/domain/domain_service/hedging/__init__.py` 中导出 VegaHedgingEngine
    - _Requirements: 5.1_

- [x] 3. 检查点 - 确保代码无语法错误
  - 确保所有代码无语法错误，如有问题请询问用户。

- [ ] 4. 编写测试
  - [x] 4.1 编写属性测试: 对冲手数公式正确性
    - **Property 1: 对冲手数公式正确性**
    - **Validates: Requirements 1.1, 1.3**

  - [x] 4.2 编写属性测试: 容忍带内不对冲
    - **Property 2: 容忍带内不对冲**
    - **Validates: Requirements 1.2**

  - [x] 4.3 编写属性测试: 方向与指令正确性
    - **Property 3: 方向与指令正确性**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [x] 4.4 编写属性测试: 附带 Greeks 影响计算正确性
    - **Property 4: 附带 Greeks 影响计算正确性**
    - **Validates: Requirements 3.1**

  - [~] 4.5 编写属性测试: 事件数据一致性
    - **Property 5: 事件数据一致性**
    - **Validates: Requirements 3.2**

  - [~] 4.6 编写属性测试: 无效输入拒绝
    - **Property 6: 无效输入拒绝**
    - **Validates: Requirements 4.1, 4.2, 4.3**

  - [~] 4.7 编写属性测试: YAML 配置加载一致性
    - **Property 7: YAML 配置加载一致性**
    - **Validates: Requirements 5.1, 5.2**

  - [~] 4.8 编写属性测试: 事件列表与对冲结果一致性
    - **Property 8: 事件列表与对冲结果一致性**
    - **Validates: Requirements 6.1, 6.2**

  - [~] 4.9 编写单元测试: 典型场景和边界条件
    - 测试 Vega 偏高需要卖出期权的场景
    - 测试 Vega 偏低需要买入期权的场景
    - 测试偏差恰好等于容忍带的边界条件
    - 测试四舍五入为零的临界值
    - _Requirements: 1.1, 1.2, 1.3, 4.1, 4.2, 4.3_

- [~] 5. 最终检查点 - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

## 备注

- 标记 `*` 的任务为可选任务，可跳过以加速 MVP
- 每个任务引用了具体的需求编号以确保可追溯性
- 属性测试使用 hypothesis 库，每个属性至少 100 次迭代
- 单元测试验证具体示例和边界条件
