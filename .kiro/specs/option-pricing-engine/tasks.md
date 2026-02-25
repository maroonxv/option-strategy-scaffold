# 实现计划：期权定价引擎

## 概述

基于设计文档，在 `src/strategy/domain/domain_service/pricing/` 模块下实现三个独立的期权定价器（BAWPricer、CRRPricer、BlackScholesPricer）。采用增量方式：先建值对象，再逐个实现定价器（各自含输入校验），最后更新模块导出。

## 任务

- [x] 1. 创建值对象定义
  - [x] 1.1 创建 `src/strategy/domain/value_object/pricing.py`，定义 ExerciseStyle、PricingModel、PricingInput、PricingResult
    - ExerciseStyle 枚举: AMERICAN, EUROPEAN
    - PricingModel 枚举: BAW, CRR, BLACK_SCHOLES
    - PricingInput: frozen dataclass，包含 spot_price, strike_price, time_to_expiry, risk_free_rate, volatility, option_type, exercise_style
    - PricingResult: frozen dataclass，包含 price, model_used, success, error_message
    - 更新 `src/strategy/domain/value_object/__init__.py` 导出新值对象
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. 实现 BlackScholesPricer
  - [x] 2.1 创建 `src/strategy/domain/domain_service/pricing/bs_pricer.py`
    - 接收 GreeksCalculator 实例
    - 内部输入校验（spot_price, strike_price, volatility, time_to_expiry）
    - 将 PricingInput 转换为 GreeksInput 调用 bs_price
    - 异常捕获，返回 error PricingResult
    - 返回 PricingResult(model_used="black_scholes")
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 2.2 编写 Property 4 属性测试：BS 委托一致性
    - **Property 4: BS 委托一致性**
    - *For any* 有效欧式 PricingInput，BlackScholesPricer 结果应与 GreeksCalculator.bs_price 完全一致
    - **Validates: Requirements 4.1**

- [x] 3. 实现 BAWPricer
  - [x] 3.1 创建 `src/strategy/domain/domain_service/pricing/baw_pricer.py`
    - 内部输入校验（spot_price, strike_price, volatility, time_to_expiry）
    - 实现 Barone-Adesi Whaley 近似解析算法
    - 处理 T=0 边界返回内在价值
    - 处理看涨和看跌两种情况
    - 异常捕获，返回 error PricingResult
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.2 编写 Property 1 属性测试：美式期权价格不低于欧式 BS 价格
    - **Property 1: 美式期权价格不低于欧式 BS 价格**
    - *For any* 有效参数，BAW 美式价格 >= BlackScholesPricer 欧式价格
    - **Validates: Requirements 2.2, 3.3**

  - [x] 3.3 编写 Property 2 属性测试：美式看跌价格不低于内在价值
    - **Property 2: 美式看跌价格不低于内在价值**
    - *For any* 有效美式看跌参数，BAW 价格 >= max(K - S, 0)
    - **Validates: Requirements 2.3**

- [ ] 4. 实现 CRRPricer
  - [-] 4.1 创建 `src/strategy/domain/domain_service/pricing/crr_pricer.py`
    - 内部输入校验（spot_price, strike_price, volatility, time_to_expiry）
    - 实现 Cox-Ross-Rubinstein 二叉树算法
    - 支持美式和欧式期权
    - 支持 steps 参数配置，默认 100
    - 处理 T=0 边界返回内在价值
    - 异常捕获，返回 error PricingResult
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [~] 4.2 编写 Property 3 属性测试：CRR 欧式定价收敛到 BS
    - **Property 3: CRR 欧式定价收敛到 BS**
    - *For any* 有效欧式参数，|CRR_price - BS_price| < max(BS_price * 0.02, 0.05)
    - **Validates: Requirements 3.2**

- [~] 5. Checkpoint - 确保各定价器独立测试通过
  - 确保所有测试通过，如有问题请向用户确认。

- [ ] 6. 编写跨定价器属性测试
  - [~] 6.1 编写 Property 5 属性测试：无效输入返回错误
    - **Property 5: 无效输入返回错误**
    - *For any* 包含无效参数的输入，BAWPricer、CRRPricer、BlackScholesPricer 均应返回 success=False
    - **Validates: Requirements 2.5, 3.6, 4.3**

- [~] 7. 更新模块导出
  - 更新 `src/strategy/domain/domain_service/pricing/__init__.py` 导出各定价器
  - 更新 `src/strategy/domain/value_object/__init__.py` 导出新增值对象（如 1.1 中未完成）
  - _Requirements: 4.2_

- [~] 8. Final checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请向用户确认。

## 备注

- 标记 `*` 的子任务为可选测试任务，可跳过以加速 MVP
- 每个任务引用了具体的需求编号以保证可追溯性
- 属性测试使用 hypothesis 库，每个测试至少运行 100 次
- 单元测试覆盖边界条件和具体示例
