# Implementation Plan: 定价服务增强

## Overview

基于已有的定价模块，分步完成 IVSolver 独立、PricingEngine 统一入口、目录重组三项增强。采用先新增后迁移的策略，确保每一步都可验证且不破坏现有功能。

## Tasks

- [ ] 1. 新增 IVQuote 值对象与 IVSolver 核心实现
  - [x] 1.1 在 `src/strategy/domain/value_object/greeks.py` 中追加 `IVQuote` 数据类
    - 定义 market_price, spot_price, strike_price, time_to_expiry, risk_free_rate, option_type 字段
    - _Requirements: 2.1_

  - [x] 1.2 创建 `src/strategy/domain/domain_service/pricing/iv/` 子目录及 `__init__.py`
    - _Requirements: 5.2_

  - [x] 1.3 实现 `src/strategy/domain/domain_service/pricing/iv/iv_solver.py`
    - 实现 `SolveMethod` 枚举（NEWTON, BISECTION, BRENT）
    - 实现 `IVSolver.solve()` 方法：输入校验（market_price ≤ 0、低于内在价值）、牛顿法求解、牛顿法未收敛自动回退二分法
    - 实现 `_solve_newton()`、`_solve_bisection()`、`_solve_brent()` 内部方法
    - 实现 `IVSolver.solve_batch()` 方法：逐个调用 solve，异常隔离，保持输入输出等长等序
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.3_

  - [x] 1.4 创建 `tests/strategy/domain/domain_service/test_iv_solver.py` 单元测试
    - 测试各算法的具体数值验证（已知期权参数 → 已知 IV）
    - 测试边界条件：market_price=0、market_price 低于内在价值、极端参数
    - 测试牛顿法未收敛自动回退二分法
    - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8_

  - [x] 1.5 创建 `tests/strategy/domain/domain_service/test_iv_solver_properties.py` 属性测试（Property 1-3）
    - **Property 1: IV 求解 Round-Trip（跨算法）**
    - **Validates: Requirements 1.1, 1.2, 1.4, 1.5**
    - **Property 2: IVSolver 错误输入处理**
    - **Validates: Requirements 1.6, 1.7**
    - **Property 3: 批量求解不变量（长度、顺序、隔离性）**
    - **Validates: Requirements 2.1, 2.2, 2.3**

- [ ] 2. 修改 GreeksCalculator 委托 IVSolver 并验证向后兼容
  - [~] 2.1 将 `greeks_calculator.py` 移动到 `pricing/iv/greeks_calculator.py`
    - 构造函数增加可选 `iv_solver` 参数，默认创建 `IVSolver()` 实例
    - `calculate_implied_volatility` 方法委托给 `self._iv_solver.solve()`，签名和返回类型不变
    - 其他方法（calculate_greeks, bs_price）保持不变
    - _Requirements: 3.1, 3.2, 3.3_

  - [~] 2.2 创建属性测试 Property 4（追加到 `test_iv_solver_properties.py`）
    - **Property 4: GreeksCalculator 向后兼容（行为等价）**
    - **Validates: Requirements 3.1, 3.2, 3.3**

- [~] 3. Checkpoint - 确保 IVSolver 和 GreeksCalculator 所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 实现 PricingEngine 统一定价入口
  - [~] 4.1 创建 `src/strategy/domain/domain_service/pricing/pricing_engine.py`
    - 实现 `PricingEngine.__init__()` 接受 `american_model` 配置和 `crr_steps` 参数
    - 实现 `PricingEngine.price()` 方法：输入校验 → 根据 exercise_style 和 american_model 路由到对应定价器
    - 实现 `_validate()` 静态方法：校验 spot_price, strike_price, volatility, time_to_expiry
    - 确保 PricingResult.model_used 字段正确记录实际使用的模型名称
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [~] 4.2 创建 `tests/strategy/domain/domain_service/test_pricing_engine.py` 单元测试
    - 测试欧式期权路由到 BS、美式默认路由到 BAW、配置 CRR 后路由到 CRR
    - 测试无效输入返回 success=False
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [~] 4.3 创建 `tests/strategy/domain/domain_service/test_pricing_engine_properties.py` 属性测试（Property 5-6）
    - **Property 5: PricingEngine 路由正确性**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6**
    - **Property 6: PricingEngine 错误输入处理**
    - **Validates: Requirements 4.5**

- [ ] 5. 目录结构重组与导入路径更新
  - [~] 5.1 创建 `pricing/pricers/` 子目录，移动 `bs_pricer.py`、`baw_pricer.py`、`crr_pricer.py` 到其中
    - 创建 `pricers/__init__.py` 导出三个定价器
    - 更新 `bs_pricer.py` 中对 `GreeksCalculator` 的导入路径
    - _Requirements: 5.1, 6.2, 6.4_

  - [~] 5.2 创建 `pricing/volatility/` 子目录，移动 `vol_surface_builder.py` 到其中
    - 创建 `volatility/__init__.py` 导出 `VolSurfaceBuilder`
    - _Requirements: 5.3_

  - [~] 5.3 更新顶层 `pricing/__init__.py`
    - 从新的子目录路径重新导出所有现有公开类
    - 新增导出 `IVSolver`、`SolveMethod`、`PricingEngine`
    - 确保 `__all__` 列表包含所有导出
    - _Requirements: 5.4, 5.5_

  - [~] 5.4 更新 `strategy_entry.py` 及其他源码文件中的导入路径
    - 通过顶层 `__init__.py` 兼容或直接更新导入路径
    - _Requirements: 6.1, 6.3_

- [~] 6. Final checkpoint - 确保所有测试通过且导入兼容
  - 运行全部现有测试（test_greeks_calculator, test_bs_pricer, test_baw_pricer, test_crr_pricer, test_vol_surface_builder, test_pricing_properties）确认无破坏
  - 运行新增测试（test_iv_solver, test_iv_solver_properties, test_pricing_engine, test_pricing_engine_properties）确认功能正确
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 5.5, 6.1, 6.2, 6.3, 6.4_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 采用先新增后迁移策略：先在新位置创建 IVSolver 和 PricingEngine，最后统一做目录重组，降低中间态破坏风险
- 每个属性测试使用 hypothesis 库，至少 200 次迭代
- 每个属性测试标注 `# Feature: pricing-service-enhancement, Property N: <title>`
- 目录重组通过顶层 `__init__.py` 重新导出保证向后兼容，现有测试无需修改导入路径
