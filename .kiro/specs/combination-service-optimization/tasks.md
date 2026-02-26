# Implementation Plan: 组合策略领域服务优化

## Overview

按需求分组实施，先完成重构优化（需求 1-4），再完成功能增强（需求 5-7）。每个阶段结束后设置检查点确保测试通过。重构阶段保持行为不变，功能增强阶段新增能力。

## Tasks

- [ ] 1. Leg.direction_sign 属性与方向符号去重（需求 1）
  - [x] 1.1 在 `src/strategy/domain/value_object/combination.py` 的 `Leg` dataclass 上新增 `direction_sign` 计算属性，direction 为 "long" 返回 1.0，为 "short" 返回 -1.0
    - _Requirements: 1.1_
  - [-] 1.2 重构 `CombinationGreeksCalculator`：删除模块级 `_DIRECTION_SIGN` 字典，将 `sign = _DIRECTION_SIGN[leg.direction]` 替换为 `sign = leg.direction_sign`
    - _Requirements: 1.2, 1.4_
  - [~] 1.3 重构 `CombinationPnLCalculator`：删除模块级 `_DIRECTION_SIGN` 字典，将 `sign = _DIRECTION_SIGN[leg.direction]` 替换为 `sign = leg.direction_sign`
    - _Requirements: 1.3, 1.4_
  - [~] 1.4 编写属性测试验证 direction_sign 正确性
    - **Property 1: direction_sign 正确性**
    - **Validates: Requirements 1.1**
  - [~] 1.5 编写属性测试验证 Greeks 计算方向加权正确性
    - **Property 2: Greeks 计算方向加权正确性**
    - **Validates: Requirements 1.2, 1.3, 1.5**
  - [~] 1.6 编写属性测试验证 PnL 计算方向加权正确性
    - **Property 3: PnL 计算方向加权正确性**
    - **Validates: Requirements 1.3, 1.5**

- [ ] 2. Direction 类方法与 LifecycleService 重构（需求 4）
  - [~] 2.1 在 `src/strategy/domain/value_object/order_instruction.py` 的 `Direction` 枚举上新增 `from_leg_direction(cls, leg_direction: str)` 类方法和 `reverse(self)` 方法
    - _Requirements: 4.1, 4.2_
  - [~] 2.2 重构 `CombinationLifecycleService`：将所有 `if leg.direction == "long"` 的 if-else 方向映射替换为 `Direction.from_leg_direction()` 和 `.reverse()` 调用
    - _Requirements: 4.3, 4.4_
  - [~] 2.3 编写属性测试验证 Direction.reverse 对合性
    - **Property 7: Direction.reverse round-trip**
    - **Validates: Requirements 4.2**
  - [~] 2.4 编写属性测试验证 Lifecycle 指令生成等价性
    - **Property 8: Lifecycle 指令生成等价性**
    - **Validates: Requirements 4.5**

- [~] 3. 检查点 - 重构阶段 1
  - 运行所有现有测试确保通过，ask the user if questions arise.

- [ ] 4. CombinationRecognizer 表驱动化（需求 2）
  - [~] 4.1 在 `combination_recognizer.py` 中定义 `MatchRule` dataclass，包含 combination_type、leg_count、predicate 字段
    - _Requirements: 2.1_
  - [~] 4.2 将现有 `_is_straddle`、`_is_strangle`、`_is_vertical_spread`、`_is_calendar_spread`、`_is_iron_condor` 方法转换为静态谓词函数，构建按优先级排序的 `_RULES` 列表
    - _Requirements: 2.2_
  - [~] 4.3 重写 `recognize()` 方法为遍历规则列表的表驱动逻辑
    - _Requirements: 2.3, 2.4, 2.5_
  - [~] 4.4 编写属性测试验证 Recognizer 行为等价性
    - **Property 4: Recognizer 表驱动行为等价性**
    - **Validates: Requirements 2.3, 2.4, 2.5, 2.6**

- [ ] 5. 共享结构约束规则（需求 3）
  - [~] 5.1 新建 `src/strategy/domain/value_object/combination_rules.py`，定义 `LegStructure` dataclass 和各类型验证函数（validate_straddle 等），导出 `VALIDATION_RULES` 字典
    - _Requirements: 3.1_
  - [~] 5.2 重构 `Combination.validate()`：删除 `_validate_straddle` 等私有方法，改为将 Leg 转换为 LegStructure 后调用 `VALIDATION_RULES[self.combination_type]`
    - _Requirements: 3.2, 3.3_
  - [~] 5.3 重构 `CombinationRecognizer` 的 `MatchRule.predicate`：内部将 OptionContract 转换为 LegStructure 后复用 `validate_xxx` 函数
    - _Requirements: 3.2, 3.4_
  - [~] 5.4 编写属性测试验证 validate() 行为等价性
    - **Property 5: validate() 行为等价性**
    - **Validates: Requirements 3.5**

- [~] 6. 检查点 - 重构阶段 2
  - 运行所有现有测试确保通过，ask the user if questions arise.

- [ ] 7. CombinationRiskChecker theta 检查（需求 5）
  - [~] 7.1 在 `src/strategy/domain/value_object/combination.py` 的 `CombinationRiskConfig` 中新增 `theta_limit: float = 100.0` 字段
    - _Requirements: 5.1_
  - [~] 7.2 在 `CombinationRiskChecker.check()` 中新增 theta 检查逻辑，格式与现有 delta/gamma/vega 一致
    - _Requirements: 5.2, 5.3, 5.4, 5.5_
  - [~] 7.3 编写属性测试验证风控检查 theta 集成正确性
    - **Property 9: 风控检查 theta 集成正确性**
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5**

- [ ] 8. PnL 已实现盈亏支持（需求 7）
  - [~] 8.1 在 `src/strategy/domain/value_object/combination.py` 中为 `LegPnL` 新增 `realized_pnl: float = 0.0` 字段，为 `CombinationPnL` 新增 `total_realized_pnl: float = 0.0` 字段
    - _Requirements: 7.1, 7.2_
  - [~] 8.2 修改 `CombinationPnLCalculator.calculate()` 新增可选参数 `realized_pnl_map: Optional[Dict[str, float]] = None`，在计算中将 realized_pnl 记入 LegPnL 并求和得到 total_realized_pnl
    - _Requirements: 7.3, 7.4, 7.5, 7.6_
  - [~] 8.3 编写属性测试验证 PnL 已实现盈亏正确性
    - **Property 11: PnL 已实现盈亏正确性**
    - **Validates: Requirements 7.4, 7.5, 7.6**

- [ ] 9. CombinationFacade 编排层（需求 6）
  - [~] 9.1 在 `src/strategy/domain/value_object/combination.py` 中新增 `CombinationEvaluation` 值对象（greeks, pnl, risk_result）
    - _Requirements: 6.3_
  - [~] 9.2 新建 `src/strategy/domain/domain_service/combination/combination_facade.py`，实现 `CombinationFacade.evaluate()` 方法，依次调用 GreeksCalculator、PnLCalculator、RiskChecker
    - _Requirements: 6.1, 6.2, 6.4_
  - [~] 9.3 编写属性测试验证 Facade evaluate 组合正确性
    - **Property 10: Facade evaluate 组合正确性**
    - **Validates: Requirements 6.2, 6.3**
  - [~] 9.4 编写单元测试验证 Facade 子服务异常传播
    - 测试当子服务抛出异常时 evaluate 不静默吞没
    - _Requirements: 6.4_

- [~] 10. 最终检查点
  - 运行所有测试确保通过，ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 重构阶段（任务 1-6）不改变外部行为，所有现有测试应继续通过
- 功能增强阶段（任务 7-9）新增能力，需新增对应测试
- 属性测试使用 `hypothesis` 库，每个属性至少 100 次迭代
- 每个属性测试标签格式：`Feature: combination-service-optimization, Property N: <property_text>`
