# 需求文档：期权定价引擎

## 简介

在现有期权策略交易基础设施的 `pricing` 模块下新增三个独立的期权定价器（BAWPricer、CRRPricer、BlackScholesPricer），支持商品期权（美式）和金融期权（欧式）的定价需求。策略层直接使用各定价器，各定价器各自负责输入校验和错误处理。

## 术语表

- **ExerciseStyle**: 期权行权方式，分为美式（american）和欧式（european）
- **PricingModel**: 定价模型枚举，包括 BAW、CRR、BLACK_SCHOLES
- **BAWPricer**: Barone-Adesi Whaley 美式期权近似解析定价器
- **CRRPricer**: Cox-Ross-Rubinstein 二叉树定价器，支持美式和欧式期权
- **BlackScholesPricer**: Black-Scholes 欧式期权解析定价器，委托给现有 GreeksCalculator
- **PricingInput**: 定价输入值对象，包含标的价格、行权价、到期时间、无风险利率、波动率、期权类型和行权方式
- **PricingResult**: 定价结果值对象，包含理论价格、使用的模型名称、成功标志和错误信息
- **GreeksCalculator**: 现有的 Black-Scholes Greeks 计算器

## 需求

### 需求 1：期权行权方式建模

**用户故事：** 作为策略开发者，我需要在期权合约中区分美式和欧式行权方式，以便定价器能根据行权方式进行合适的定价计算。

#### 验收标准

1. THE PricingInput SHALL 包含 exercise_style 字段，取值为 "american" 或 "european"
2. THE PricingInput SHALL 包含 spot_price、strike_price、time_to_expiry、risk_free_rate、volatility、option_type 字段，与现有 GreeksInput 保持一致的语义
3. THE PricingResult SHALL 包含 price（理论价格）、model_used（使用的模型名称）、success（是否成功）和 error_message（错误描述）字段

### 需求 2：BAW 美式期权定价

**用户故事：** 作为策略开发者，我需要使用 BAWPricer 对美式期权进行快速近似定价，以便在实时交易中获得高效的美式期权理论价格。

#### 验收标准

1. WHEN PricingInput 的 exercise_style 为 "american"，THE BAWPricer SHALL 使用 Barone-Adesi Whaley 近似解析方法计算美式期权理论价格
2. WHEN BAWPricer 计算美式看涨期权价格，THE BAWPricer SHALL 返回不低于对应欧式 Black-Scholes 价格的结果
3. WHEN BAWPricer 计算美式看跌期权价格，THE BAWPricer SHALL 返回不低于期权内在价值的结果
4. WHEN time_to_expiry 为 0，THE BAWPricer SHALL 返回期权的内在价值
5. WHEN PricingInput 包含无效参数（spot_price <= 0 或 strike_price <= 0 或 volatility <= 0 或 time_to_expiry < 0），THE BAWPricer SHALL 返回 success 为 False 的 PricingResult，error_message 描述具体的校验失败原因
6. IF 定价计算过程中发生数值溢出或异常，THEN THE BAWPricer SHALL 捕获异常并返回 success 为 False 的 PricingResult，error_message 包含异常描述

### 需求 3：CRR 二叉树定价

**用户故事：** 作为策略开发者，我需要使用 CRRPricer 对美式和欧式期权进行定价，以便在需要更高精度时获得可靠的理论价格。

#### 验收标准

1. WHEN 调用 CRRPricer，THE CRRPricer SHALL 使用 Cox-Ross-Rubinstein 二叉树方法计算期权理论价格
2. WHEN CRRPricer 对欧式期权定价，THE CRRPricer SHALL 返回与 Black-Scholes 价格在合理误差范围内一致的结果
3. WHEN CRRPricer 对美式期权定价，THE CRRPricer SHALL 在每个节点检查提前行权条件并返回考虑提前行权价值的价格
4. THE CRRPricer SHALL 支持通过 steps 参数配置二叉树步数，默认值为 100 步
5. WHEN time_to_expiry 为 0，THE CRRPricer SHALL 返回期权的内在价值
6. WHEN PricingInput 包含无效参数（spot_price <= 0 或 strike_price <= 0 或 volatility <= 0 或 time_to_expiry < 0），THE CRRPricer SHALL 返回 success 为 False 的 PricingResult，error_message 描述具体的校验失败原因
7. IF 定价计算过程中发生数值溢出或异常，THEN THE CRRPricer SHALL 捕获异常并返回 success 为 False 的 PricingResult，error_message 包含异常描述

### 需求 4：BlackScholesPricer 欧式定价

**用户故事：** 作为策略开发者，我需要使用 BlackScholesPricer 对欧式期权进行定价，以便复用已有的 GreeksCalculator 实现。

#### 验收标准

1. WHEN 使用 BlackScholesPricer 定价，THE BlackScholesPricer SHALL 委托给现有的 GreeksCalculator.bs_price 方法执行计算
2. THE BlackScholesPricer SHALL 作为纯计算服务实现，无副作用，遵循现有领域服务的设计模式
3. WHEN PricingInput 包含无效参数（spot_price <= 0 或 strike_price <= 0 或 volatility <= 0 或 time_to_expiry < 0），THE BlackScholesPricer SHALL 返回 success 为 False 的 PricingResult，error_message 描述具体的校验失败原因
4. IF 定价计算过程中发生数值溢出或异常，THEN THE BlackScholesPricer SHALL 捕获异常并返回 success 为 False 的 PricingResult，error_message 包含异常描述
