# Implementation Plan: 动态仓位计算与 Greeks 感知开仓决策

## Overview

将 PositionSizingService 从固定1手开仓重构为基于保证金、保证金使用率、Greeks 预算三维度约束的动态仓位计算。新增 SizingResult 值对象，扩展配置文件，保留现有风控检查逻辑。

## Tasks

- [x] 1. 创建 SizingResult 值对象
  - [x] 1.1 在 `src/strategy/domain/value_object/sizing.py` 创建 SizingResult frozen dataclass
    - 包含字段：final_volume, margin_volume, usage_volume, greeks_volume, delta_budget, gamma_budget, vega_budget, passed, reject_reason
    - 在 `src/strategy/domain/value_object/__init__.py` 中导出
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 2. 扩展配置文件
  - [x] 2.1 在 `config/strategy_config.yaml` 中新增 `position_sizing` 配置节
    - 添加 margin_ratio (0.12), min_margin_ratio (0.07), margin_usage_limit (0.6), max_volume_per_order (10)
    - _Requirements: 6.1_

- [ ] 3. 重构 PositionSizingService
  - [x] 3.1 重构 `__init__` 方法，新增 margin_ratio, min_margin_ratio, margin_usage_limit, max_volume_per_order 参数
    - 保留现有 max_positions, global_daily_limit, contract_daily_limit 参数
    - 移除 position_ratio 参数（不再使用）
    - _Requirements: 6.1, 6.2_

  - [x] 3.2 实现 `estimate_margin` 方法
    - 公式：`权利金 × 合约乘数 + max(标的价格 × 合约乘数 × margin_ratio - 虚值额, 标的价格 × 合约乘数 × min_margin_ratio)`
    - 虚值额：put 为 `max(行权价 - 标的价格, 0) × 合约乘数`，call 为 `max(标的价格 - 行权价, 0) × 合约乘数`
    - _Requirements: 1.1_

  - [x] 3.3 编写 estimate_margin 属性测试
    - **Property 1: 保证金估算公式正确性**
    - **Validates: Requirements 1.1**

  - [x] 3.4 实现 `_calc_margin_volume` 方法
    - 公式：`floor(available_funds / margin_per_lot)`
    - _Requirements: 1.2_

  - [x] 3.5 实现 `_calc_usage_volume` 方法
    - 公式：`floor((total_equity × margin_usage_limit - used_margin) / margin_per_lot)`
    - _Requirements: 2.2_

  - [x] 3.6 编写 _calc_usage_volume 属性测试
    - **Property 2: 保证金使用率不变量**
    - **Validates: Requirements 2.2**

  - [x] 3.7 实现 `_calc_greeks_volume` 方法
    - 对 Delta/Gamma/Vega 分别计算 `floor((limit - |current|) / |greek × multiplier|)`
    - Greek 值为零的维度视为无限制
    - 返回 (允许手数, delta_budget, gamma_budget, vega_budget)
    - _Requirements: 3.1, 3.2, 3.4_

  - [x] 3.8 编写 _calc_greeks_volume 属性测试
    - **Property 3: Greeks 预算计算正确性**
    - **Validates: Requirements 3.1, 3.2**

  - [x] 3.9 实现 `compute_sizing` 纯计算方法
    - 调用 estimate_margin、_calc_margin_volume、_calc_usage_volume、_calc_greeks_volume
    - 取三维度最小值，clamp 到 [1, max_volume_per_order]
    - 处理所有拒绝场景（保证金 <= 0、资金不足、使用率超限、Greeks 超限、综合手数 < 1）
    - 返回 SizingResult
    - _Requirements: 1.3, 1.4, 2.3, 3.3, 4.1, 4.2, 4.3, 4.4_

  - [x] 3.10 编写 compute_sizing 属性测试
    - **Property 4: 综合决策不变量**
    - **Validates: Requirements 4.1, 4.2, 4.4**

- [ ] 4. Checkpoint - 确保所有属性测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [ ] 5. 重构开仓与平仓方法
  - [~] 5.1 重构 `calculate_open_volume` 方法（修正拼写 volumn → volume）
    - 保留现有风控前置检查（最大持仓、全局日限额、单合约日限额、重复合约）
    - 新增参数：total_equity, used_margin, underlying_price, strike_price, option_type, multiplier, greeks, portfolio_greeks, risk_thresholds
    - 调用 compute_sizing 获取 SizingResult
    - SizingResult.passed 为 False 时返回 None
    - SizingResult.passed 为 True 时使用 final_volume 生成 OrderInstruction
    - _Requirements: 4.5, 1.3, 1.4, 2.3, 3.3_

  - [~] 5.2 重命名 `calculate_close_volumn` 为 `calculate_close_volume`（修正拼写）
    - 保持平仓逻辑不变
    - _Requirements: 设计决策 2_

  - [~] 5.3 编写单元测试覆盖编排逻辑和边界条件
    - 测试前置风控检查保留（最大持仓、日限额、重复合约）
    - 测试 compute_sizing 拒绝时 calculate_open_volume 返回 None
    - 测试保证金 <= 0、资金不足一手、使用率超限、Greeks 超限等边界条件
    - 测试 Greek 值为零的维度不参与最小值计算
    - 测试配置默认值
    - 测试 calculate_close_volume 保持不变
    - _Requirements: 1.3, 1.4, 2.3, 3.3, 3.4, 4.3, 4.5, 6.2_

- [ ] 6. 更新调用方适配新接口
  - [~] 6.1 查找所有调用 `calculate_open_volumn` 和 `calculate_close_volumn` 的代码，更新为新方法签名
    - 传入新增参数（total_equity, used_margin, underlying_price, strike_price, option_type, multiplier, greeks, portfolio_greeks, risk_thresholds）
    - 更新 PositionSizingService 的初始化代码，从 strategy_config.yaml 读取 position_sizing 配置节
    - _Requirements: 6.1, 6.2_

- [ ] 7. Final checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

## Notes

- 测试文件放置在 `tests/strategy/domain/domain_service/` 目录下
- 属性测试使用 `hypothesis` 库，每个属性测试至少运行 100 次迭代
- 标记 `*` 的子任务为可选，可跳过以加速 MVP
- 属性测试标注格式：`Feature: dynamic-position-sizing, Property N: {property_text}`
