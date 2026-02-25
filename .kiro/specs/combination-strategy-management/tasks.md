# Implementation Plan: 组合策略管理

## Overview

基于现有 DDD 架构，引入 CombinationAggregate 作为独立聚合根，实现组合策略的建模、识别、Greeks 聚合、盈亏追踪、风控检查和生命周期管理。实现顺序：值对象 → 实体 → 领域服务 → 聚合根 → 事件集成 → 配置扩展。

## Tasks

- [x] 1. 创建组合策略值对象和枚举
  - [x] 1.1 创建 `src/strategy/domain/value_object/combination.py`，实现 CombinationType、CombinationStatus 枚举，Leg 值对象（frozen dataclass），CombinationGreeks 值对象（含 failed_legs），LegPnL 值对象，CombinationPnL 值对象（含 timestamp），CombinationRiskConfig 值对象（含默认值 delta_limit=2.0, gamma_limit=0.5, vega_limit=200.0）
    - Leg 使用 OptionType（复用 `option_contract.py` 中的 Literal["call", "put"]）
    - direction 字段使用 "long" / "short" 字符串，与现有 Position 一致
    - _Requirements: 1.1, 1.5, 3.2, 4.2, 5.1, 8.2_

  - [x] 1.2 编写值对象单元测试 `tests/strategy/domain/value_object/test_combination_vo.py`
    - 测试枚举值完整性、Leg frozen 不可变性、CombinationRiskConfig 默认值
    - _Requirements: 1.5, 5.1, 8.2_

- [x] 2. 实现 Combination 实体
  - [x] 2.1 创建 `src/strategy/domain/entity/combination.py`，实现 Combination dataclass，包含 validate()、update_status()、get_active_legs()、to_dict()、from_dict() 方法
    - validate() 按 CombinationType 验证 Leg 数量和结构约束（STRADDLE: 2腿同标的同到期同行权价一Call一Put；STRANGLE: 2腿同标的同到期不同行权价一Call一Put；VERTICAL_SPREAD: 2腿同标的同到期同类型不同行权价；CALENDAR_SPREAD: 2腿同标的不同到期同行权价同类型；IRON_CONDOR: 4腿同标的同到期构成1个Put Spread+1个Call Spread；CUSTOM: 至少1腿无结构约束）
    - update_status() 接受 closed_vt_symbols 集合，判定状态转换
    - to_dict()/from_dict() 支持序列化往返
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 6.3, 6.4, 9.1, 9.2, 9.3_

  - [x] 2.2 编写 Combination 实体属性测试（Property 1: 组合结构验证）
    - 文件：`tests/strategy/domain/entity/test_combination_properties.py`
    - **Property 1: 组合结构验证**
    - 使用 Hypothesis 生成随机 CombinationType 和 Leg 列表，验证满足约束时通过、不满足时抛出 ValueError
    - **Validates: Requirements 1.2, 1.3, 1.4**

  - [x] 2.3 编写 Combination 实体属性测试（Property 7: 组合状态反映腿的平仓状态）
    - 文件：`tests/strategy/domain/entity/test_combination_properties.py`（追加）
    - **Property 7: 组合状态反映腿的平仓状态**
    - 使用 Hypothesis 生成随机 Combination 和 closed_vt_symbols 集合，验证 PARTIALLY_CLOSED / CLOSED / 不变的状态转换逻辑
    - **Validates: Requirements 6.3, 6.4**

  - [x] 2.4 编写 Combination 实体属性测试（Property 11: 序列化往返一致性）
    - 文件：`tests/strategy/domain/entity/test_combination_properties.py`（追加）
    - **Property 11: 序列化往返一致性**
    - 使用 Hypothesis 生成随机有效 Combination，验证 from_dict(to_dict(c)) 等价于 c
    - **Validates: Requirements 9.3**

- [x] 3. Checkpoint - 确保值对象和实体测试通过
  - 运行 `pytest tests/strategy/domain/value_object/test_combination_vo.py tests/strategy/domain/entity/ -v`，确保所有测试通过，有问题请询问用户。

- [x] 4. 实现 CombinationRecognizer 识别服务
  - [x] 4.1 创建 `src/strategy/domain/domain_service/combination/__init__.py` 和 `src/strategy/domain/domain_service/combination/combination_recognizer.py`
    - 实现 recognize(positions, contracts) 方法，按优先级匹配：IRON_CONDOR → STRADDLE → STRANGLE → VERTICAL_SPREAD → CALENDAR_SPREAD → CUSTOM
    - 输入为 List[Position] 和 Dict[str, OptionContract]，复用现有 Position 和 OptionContract 类型
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 4.2 编写 CombinationRecognizer 属性测试（Property 2: 组合类型识别）
    - 文件：`tests/strategy/domain/domain_service/combination/test_combination_recognizer.py`
    - **Property 2: 组合类型识别**
    - 使用 Hypothesis 生成满足特定类型结构的随机持仓，验证识别结果正确；不匹配时返回 CUSTOM
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

- [x] 5. 实现 CombinationGreeksCalculator 服务
  - [x] 5.1 创建 `src/strategy/domain/domain_service/combination/combination_greeks_calculator.py`
    - 实现 calculate(combination, greeks_map, multiplier) 方法
    - 加权公式：greek_total += greek_per_unit × volume × multiplier × direction_sign（long=+1, short=-1）
    - 某个 Leg 的 GreeksResult.success 为 False 时，记入 failed_legs 并继续计算其余 Leg
    - _Requirements: 3.1, 3.3, 3.4_

  - [x] 5.2 编写 CombinationGreeksCalculator 属性测试（Property 3: Greeks 加权求和）
    - 文件：`tests/strategy/domain/domain_service/combination/test_combination_greeks_calculator.py`
    - **Property 3: Greeks 加权求和**
    - 使用 Hypothesis 生成随机 Combination 和 GreeksResult，验证聚合结果等于手动加权求和
    - **Validates: Requirements 3.1, 3.4**

- [x] 6. 实现 CombinationPnLCalculator 服务
  - [x] 6.1 创建 `src/strategy/domain/domain_service/combination/combination_pnl_calculator.py`
    - 实现 calculate(combination, current_prices, multiplier) 方法
    - 单腿公式：(current_price - open_price) × volume × multiplier × direction_sign
    - 价格不可用时 LegPnL.price_available = False，该腿盈亏计为 0
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 6.2 编写 CombinationPnLCalculator 属性测试（Property 4: 盈亏计算正确性）
    - 文件：`tests/strategy/domain/domain_service/combination/test_combination_pnl_calculator.py`
    - **Property 4: 盈亏计算正确性**
    - 使用 Hypothesis 生成随机 Combination 和价格，验证总盈亏等于各腿公式之和
    - **Validates: Requirements 4.1, 4.3**

- [ ] 7. 实现 CombinationRiskChecker 服务
  - [x] 7.1 创建 `src/strategy/domain/domain_service/combination/combination_risk_checker.py`
    - 实现 check(greeks) 方法，返回 RiskCheckResult（复用现有值对象）
    - 通过条件：|delta| ≤ delta_limit 且 |gamma| ≤ gamma_limit 且 |vega| ≤ vega_limit
    - 失败时 reject_reason 包含超限的 Greek 名称和数值
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 7.2 编写 CombinationRiskChecker 属性测试（Property 5: 风控检查正确性）
    - 文件：`tests/strategy/domain/domain_service/combination/test_combination_risk_checker.py`
    - **Property 5: 风控检查正确性**
    - 使用 Hypothesis 生成随机 CombinationGreeks 和阈值，验证通过当且仅当所有 Greeks 绝对值在阈值内
    - **Validates: Requirements 5.2, 5.3**

- [~] 8. Checkpoint - 确保领域服务测试通过
  - 运行 `pytest tests/strategy/domain/domain_service/combination/ -v`，确保所有测试通过，有问题请询问用户。

- [ ] 9. 实现 CombinationLifecycleService 服务
  - [~] 9.1 创建 `src/strategy/domain/domain_service/combination/combination_lifecycle_service.py`
    - 实现 generate_open_instructions(combination, price_map)：为每个 Leg 生成开仓 OrderInstruction
    - 实现 generate_close_instructions(combination, price_map)：为所有活跃 Leg 生成平仓 OrderInstruction，已平仓 Leg 跳过
    - 实现 generate_adjust_instruction(combination, leg_vt_symbol, new_volume, current_price)：生成调整指令（增仓为开仓，减仓为平仓）
    - 复用现有 OrderInstruction、Direction、Offset 值对象
    - _Requirements: 6.1, 6.2, 6.5, 6.6_

  - [~] 9.2 编写 CombinationLifecycleService 属性测试（Property 6: 生命周期指令生成）
    - 文件：`tests/strategy/domain/domain_service/combination/test_combination_lifecycle_service.py`
    - **Property 6: 生命周期指令生成**
    - 使用 Hypothesis 生成随机 Combination，验证 open_instructions 数量等于 Leg 数量，close_instructions 数量等于活跃 Leg 数量
    - **Validates: Requirements 6.1, 6.2, 6.6**

  - [~] 9.3 编写 CombinationLifecycleService 属性测试（Property 8: 调整指令生成）
    - 文件：`tests/strategy/domain/domain_service/combination/test_combination_lifecycle_service.py`（追加）
    - **Property 8: 调整指令生成**
    - 使用 Hypothesis 生成随机调整参数，验证增仓生成开仓指令、减仓生成平仓指令
    - **Validates: Requirements 6.5**

- [ ] 10. 实现 CombinationAggregate 聚合根
  - [~] 10.1 创建 `src/strategy/domain/aggregate/combination_aggregate.py`
    - 实现 _combinations 字典、_symbol_index 反向索引、_domain_events 事件队列
    - 实现 register_combination()（调用 validate 后注册并建立反向索引）
    - 实现 get_combination()、get_combinations_by_underlying()、get_active_combinations()、get_combinations_by_symbol()
    - 实现 sync_combination_status()（通过反向索引查找关联 Combination，更新状态，产生 CombinationStatusChangedEvent）
    - 实现 to_snapshot()/from_snapshot() 快照序列化
    - 实现 pop_domain_events()/has_pending_events()
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [~] 10.2 编写 CombinationAggregate 属性测试（Property 9: 聚合根注册与查询一致性）
    - 文件：`tests/strategy/domain/aggregate/test_combination_aggregate_properties.py`
    - **Property 9: 聚合根注册与查询一致性**
    - 使用 Hypothesis 生成随机 Combination 集合注册后，验证按 id/underlying/vt_symbol 查询的一致性
    - **Validates: Requirements 7.2, 7.5**

  - [~] 10.3 编写 CombinationAggregate 属性测试（Property 10: 跨聚合根状态同步）
    - 文件：`tests/strategy/domain/aggregate/test_combination_aggregate_properties.py`（追加）
    - **Property 10: 跨聚合根状态同步**
    - 使用 Hypothesis 生成随机 Combination 和平仓事件序列，验证 sync_combination_status 正确更新状态并产生事件
    - **Validates: Requirements 7.3, 7.4**

  - [~] 10.4 编写 CombinationAggregate 属性测试（Property 12: 聚合根快照往返一致性）
    - 文件：`tests/strategy/domain/aggregate/test_combination_aggregate_properties.py`（追加）
    - **Property 12: 聚合根快照往返一致性**
    - 使用 Hypothesis 生成随机 CombinationAggregate 状态，验证 from_snapshot(to_snapshot(agg)) 恢复等价状态
    - **Validates: Requirements 7.1**

  - [~] 10.5 编写 CombinationAggregate 属性测试（Property 13: 反向索引一致性）
    - 文件：`tests/strategy/domain/aggregate/test_combination_aggregate_properties.py`（追加）
    - **Property 13: 反向索引一致性**
    - 使用 Hypothesis 生成随机 Combination 集合注册后，验证 _symbol_index 与 _combinations 的双向一致性
    - **Validates: Requirements 7.2**

- [ ] 11. 扩展领域事件
  - [~] 11.1 在 `src/strategy/domain/event/event_types.py` 中新增 CombinationStatusChangedEvent 事件类
    - 继承 DomainEvent，包含 combination_id、old_status、new_status、combination_type 字段
    - _Requirements: 7.4_

- [~] 12. Checkpoint - 确保聚合根和事件测试通过
  - 运行 `pytest tests/strategy/domain/aggregate/ tests/strategy/domain/entity/ -v`，确保所有测试通过，有问题请询问用户。

- [ ] 13. 扩展 YAML 配置支持
  - [~] 13.1 在 `config/strategy_config.yaml` 中新增 combination_risk 配置节，包含 delta_limit、gamma_limit、vega_limit 三个字段
    - _Requirements: 8.1, 8.2_

  - [~] 13.2 在策略配置加载逻辑中支持读取 combination_risk 配置节，缺失时使用默认值（delta_limit=2.0, gamma_limit=0.5, vega_limit=200.0）
    - _Requirements: 8.3_

- [ ] 14. 集成测试与最终验证
  - [~] 14.1 创建 `tests/strategy/domain/domain_service/combination/__init__.py` 和集成测试文件 `tests/strategy/domain/domain_service/combination/test_combination_integration.py`
    - 测试完整流程：创建 Combination → 注册到 CombinationAggregate → 计算 Greeks → 计算 PnL → 风控检查 → 生成平仓指令 → 状态同步
    - _Requirements: 7.2, 7.3, 7.4_

- [~] 15. Final Checkpoint - 确保所有测试通过
  - 运行 `pytest tests/strategy/domain/ -v`，确保所有测试通过，有问题请询问用户。

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 所有属性测试使用 Hypothesis 库，每个属性至少 100 次迭代
- 属性测试标签格式：`Feature: combination-strategy-management, Property N: <property_text>`
- 复用现有值对象：OrderInstruction、Direction、Offset、RiskCheckResult、GreeksResult、OptionContract、Position
- CombinationAggregate 与 PositionAggregate 通过领域事件松耦合，不直接引用
