# 需求文档：定价服务增强

## 简介

对 `src/strategy/domain/domain_service/pricing` 目录下的定价领域服务进行两个方向的增强优化：
1. 将隐含波动率（IV）求解逻辑从 `GreeksCalculator` 中独立出来，形成专门的 `IVSolver` 服务，支持多算法和批量求解
2. 创建统一的定价引擎入口 `PricingEngine`，根据行权方式自动路由到合适的定价器，并重组目录结构

## 术语表

- **IVSolver**: 隐含波动率求解器，负责从市场价格反推隐含波动率的独立服务
- **PricingEngine**: 统一定价引擎入口，根据期权行权方式和配置自动选择合适的定价器
- **GreeksCalculator**: 现有的 Greeks 计算器，包含 Delta、Gamma、Theta、Vega 计算及 BS 定价
- **BAWPricer**: Barone-Adesi Whaley 美式期权近似定价器
- **CRRPricer**: Cox-Ross-Rubinstein 二叉树定价器
- **BlackScholesPricer**: Black-Scholes 欧式期权定价器
- **ExerciseStyle**: 期权行权方式枚举（AMERICAN / EUROPEAN）
- **PricingInput**: 定价输入参数值对象
- **PricingResult**: 定价结果值对象
- **IVResult**: 隐含波动率求解结果值对象
- **Brent_Method**: Brent 求根法，一种结合二分法、割线法和逆二次插值的高效求根算法

## 需求

### 需求 1：IVSolver 独立服务

**用户故事：** 作为量化开发者，我希望将隐含波动率求解逻辑独立为专门的 IVSolver 服务，以便复用、扩展和独立测试。

#### 验收标准

1. THE IVSolver SHALL 提供 `solve(market_price, spot_price, strike_price, time_to_expiry, risk_free_rate, option_type)` 方法，返回 IVResult
2. THE IVSolver SHALL 默认使用牛顿法求解隐含波动率，与现有 `GreeksCalculator.calculate_implied_volatility` 行为一致
3. WHEN 牛顿法在指定迭代次数内未收敛, THE IVSolver SHALL 自动回退到二分法继续求解
4. THE IVSolver SHALL 支持 Brent 法作为可选求解算法
5. WHEN 调用方指定求解算法时, THE IVSolver SHALL 使用指定的算法进行求解
6. IF 市场价格小于等于零, THEN THE IVSolver SHALL 返回 success 为 False 的 IVResult 并包含错误描述
7. IF 市场价格低于期权内在价值, THEN THE IVSolver SHALL 返回 success 为 False 的 IVResult 并包含错误描述
8. IF 所有求解算法均未收敛, THEN THE IVSolver SHALL 返回 success 为 False 的 IVResult，包含迭代次数和错误描述

### 需求 2：批量 IV 求解

**用户故事：** 作为量化开发者，我希望能一次性对一组期权报价批量求解隐含波动率，以提高波动率曲面构建的效率。

#### 验收标准

1. THE IVSolver SHALL 提供 `solve_batch(quotes)` 方法，接受一组期权报价并返回对应的 IVResult 列表
2. WHEN 批量求解时, THE IVSolver SHALL 对每个报价独立求解，单个报价失败不影响其他报价的求解
3. THE IVSolver 的 `solve_batch` 返回结果列表 SHALL 与输入报价列表保持相同的顺序和长度

### 需求 3：GreeksCalculator 向后兼容

**用户故事：** 作为量化开发者，我希望 GreeksCalculator 在 IV 求解独立后仍保留原有接口，以避免破坏现有调用方。

#### 验收标准

1. THE GreeksCalculator SHALL 保留 `calculate_implied_volatility` 方法签名不变
2. WHEN `calculate_implied_volatility` 被调用时, THE GreeksCalculator SHALL 委托给 IVSolver 执行实际求解
3. THE GreeksCalculator 的 `calculate_implied_volatility` 方法 SHALL 返回与重构前完全相同格式的 IVResult

### 需求 4：PricingEngine 统一入口

**用户故事：** 作为量化开发者，我希望有一个统一的定价引擎入口，根据期权行权方式自动选择合适的定价器，简化调用方代码。

#### 验收标准

1. THE PricingEngine SHALL 提供 `price(params: PricingInput) -> PricingResult` 方法作为统一定价入口
2. WHEN PricingInput 的 exercise_style 为 EUROPEAN 时, THE PricingEngine SHALL 路由到 BlackScholesPricer 进行定价
3. WHEN PricingInput 的 exercise_style 为 AMERICAN 时, THE PricingEngine SHALL 默认路由到 BAWPricer 进行定价
4. WHERE 调用方通过配置指定美式期权使用 CRR 模型, THE PricingEngine SHALL 路由到 CRRPricer 进行定价
5. IF PricingInput 包含无效参数, THEN THE PricingEngine SHALL 返回 success 为 False 的 PricingResult 并包含错误描述
6. THE PricingEngine SHALL 在 PricingResult 的 model_used 字段中记录实际使用的定价模型名称

### 需求 5：目录结构重组

**用户故事：** 作为量化开发者，我希望 pricing 目录按职责分类组织代码，以提高可维护性和可读性。

#### 验收标准

1. THE pricing 模块 SHALL 将定价器代码组织到 `pricers/` 子目录中
2. THE pricing 模块 SHALL 将 IV 求解器代码组织到 `iv/` 子目录中
3. THE pricing 模块 SHALL 将波动率曲面相关代码组织到 `volatility/` 子目录中
4. THE pricing 模块的顶层 `__init__.py` SHALL 保持所有现有公开类的导出，确保向后兼容
5. WHEN 目录重组完成后, THE pricing 模块 SHALL 保证所有现有测试通过且无需修改测试中的导入路径

### 需求 6：导入路径更新

**用户故事：** 作为量化开发者，我希望重构后所有受影响的源码和测试文件的导入路径都被正确更新，以保证系统正常运行。

#### 验收标准

1. WHEN 目录重组完成后, THE pricing 模块 SHALL 更新 `strategy_entry.py` 中的导入路径或通过顶层 `__init__.py` 兼容
2. WHEN 目录重组完成后, THE pricing 模块 SHALL 更新 `bs_pricer.py` 中对 `GreeksCalculator` 的导入路径
3. WHEN 目录重组完成后, THE pricing 模块 SHALL 更新所有测试文件中的导入路径或通过顶层 `__init__.py` 兼容
4. THE pricing 模块 SHALL 确保所有内部模块间的相对导入路径正确
