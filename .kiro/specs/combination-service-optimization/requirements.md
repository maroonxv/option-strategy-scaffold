# 需求文档：组合策略领域服务优化

## 简介

对 `src/strategy/domain/domain_service/combination/` 下的 5 个组合策略领域服务进行全面优化，包括消除重复代码、表驱动重构、统一约束规则、补充缺失功能、新增编排层。本次优化为重构+功能增强，需确保所有现有测试继续通过。

## 术语表

- **Combination**: 组合策略实体，管理多个期权 Leg 的结构约束和生命周期状态
- **Leg**: 组合中的单个期权持仓值对象，包含合约代码、方向、数量、开仓价等
- **CombinationType**: 组合策略类型枚举（STRADDLE, STRANGLE, VERTICAL_SPREAD, CALENDAR_SPREAD, IRON_CONDOR, CUSTOM）
- **Greeks**: 期权风险指标集合（delta, gamma, theta, vega）
- **CombinationGreeksCalculator**: 组合级 Greeks 聚合计算领域服务
- **CombinationPnLCalculator**: 组合级盈亏计算领域服务
- **CombinationRecognizer**: 组合策略类型识别领域服务
- **CombinationRiskChecker**: 组合级风控检查领域服务
- **CombinationLifecycleService**: 组合生命周期管理领域服务
- **Direction_Sign**: 方向符号映射，long = +1.0, short = -1.0
- **MatchRule**: 组合类型匹配规则数据类，用于表驱动识别
- **CombinationFacade**: 组合策略编排层，提供高层评估接口
- **CombinationEvaluation**: 组合评估结果值对象，包含 Greeks、PnL、风控结果
- **Realized_PnL**: 已实现盈亏，已平仓 Leg 的实际盈亏
- **Unrealized_PnL**: 未实现盈亏，活跃 Leg 基于当前市价的浮动盈亏

## 需求

### 需求 1：消除方向符号重复定义

**用户故事：** 作为开发者，我希望方向符号映射只定义一次，以便消除 `CombinationGreeksCalculator` 和 `CombinationPnLCalculator` 中的重复代码，降低维护成本。

#### 验收标准

1. THE Leg 值对象 SHALL 提供 `direction_sign` 属性，当 direction 为 "long" 时返回 1.0，当 direction 为 "short" 时返回 -1.0
2. WHEN CombinationGreeksCalculator 计算加权 Greeks 时，THE CombinationGreeksCalculator SHALL 使用 Leg 的 `direction_sign` 属性获取方向符号
3. WHEN CombinationPnLCalculator 计算单腿盈亏时，THE CombinationPnLCalculator SHALL 使用 Leg 的 `direction_sign` 属性获取方向符号
4. WHEN 重构完成后，THE 系统 SHALL 不再包含模块级 `_DIRECTION_SIGN` 字典定义
5. WHEN 重构完成后，THE CombinationGreeksCalculator 和 CombinationPnLCalculator SHALL 产生与重构前完全相同的计算结果

### 需求 2：CombinationRecognizer 表驱动化

**用户故事：** 作为开发者，我希望组合类型识别逻辑采用表驱动方式，以便新增组合类型时只需添加规则而无需修改匹配逻辑。

#### 验收标准

1. THE CombinationRecognizer SHALL 定义 `MatchRule` 数据类，包含组合类型、腿数要求和结构匹配谓词
2. THE CombinationRecognizer SHALL 维护一个按优先级排序的 `MatchRule` 列表，优先级为 IRON_CONDOR → STRADDLE → STRANGLE → VERTICAL_SPREAD → CALENDAR_SPREAD
3. WHEN 识别组合类型时，THE CombinationRecognizer SHALL 遍历规则列表，返回第一个匹配的组合类型
4. WHEN 没有规则匹配时，THE CombinationRecognizer SHALL 返回 CombinationType.CUSTOM
5. WHEN 持仓列表为空时，THE CombinationRecognizer SHALL 返回 CombinationType.CUSTOM
6. WHEN 重构完成后，THE CombinationRecognizer SHALL 对所有已有组合类型产生与重构前完全相同的识别结果

### 需求 3：统一结构约束规则

**用户故事：** 作为开发者，我希望 `CombinationRecognizer` 的识别规则和 `Combination.validate()` 的验证规则共享同一套结构约束定义，以便修改约束时只需改一处。

#### 验收标准

1. THE 系统 SHALL 定义共享的结构约束规则集，描述每种 CombinationType 的腿数、到期日、行权价、期权类型等约束
2. WHEN CombinationRecognizer 识别组合类型时，THE CombinationRecognizer SHALL 基于共享规则集进行匹配
3. WHEN Combination.validate() 验证结构时，THE Combination 实体 SHALL 基于共享规则集进行验证
4. WHEN 共享规则集中某个组合类型的约束被修改时，THE CombinationRecognizer 和 Combination.validate() SHALL 同时反映该修改
5. WHEN 重构完成后，THE Combination.validate() SHALL 对所有合法和非法输入产生与重构前完全相同的验证结果

### 需求 4：统一方向映射逻辑

**用户故事：** 作为开发者，我希望 `CombinationLifecycleService` 中的方向映射逻辑统一为类方法，以便消除手写 if-else 的重复代码。

#### 验收标准

1. THE Direction 枚举 SHALL 提供 `from_leg_direction(leg_direction: str)` 类方法，将 "long" 映射为 Direction.LONG，将 "short" 映射为 Direction.SHORT
2. THE Direction 枚举 SHALL 提供 `reverse()` 方法，将 Direction.LONG 转换为 Direction.SHORT，将 Direction.SHORT 转换为 Direction.LONG
3. WHEN CombinationLifecycleService 生成开仓指令时，THE CombinationLifecycleService SHALL 使用 `Direction.from_leg_direction()` 获取方向
4. WHEN CombinationLifecycleService 生成平仓指令时，THE CombinationLifecycleService SHALL 使用 `Direction.from_leg_direction()` 获取方向后调用 `reverse()` 取反
5. WHEN 重构完成后，THE CombinationLifecycleService SHALL 对所有输入产生与重构前完全相同的指令结果

### 需求 5：补充 Theta 风控检查

**用户故事：** 作为风控管理者，我希望组合级风控检查覆盖 theta 指标，以便完整监控组合的时间衰减风险。

#### 验收标准

1. THE CombinationRiskConfig SHALL 包含 `theta_limit` 字段，默认值为 100.0
2. WHEN CombinationRiskChecker 执行风控检查时，THE CombinationRiskChecker SHALL 检查 |theta| 是否超过 theta_limit
3. IF theta 超限，THEN THE CombinationRiskChecker SHALL 在 reject_reason 中包含 theta 的超限信息，格式与现有 delta/gamma/vega 一致
4. WHEN theta 未超限且其他 Greeks 也未超限时，THE CombinationRiskChecker SHALL 返回 passed=True
5. WHEN 新增 theta 检查后，THE CombinationRiskChecker SHALL 对现有 delta/gamma/vega 检查逻辑保持不变

### 需求 6：新增 CombinationFacade 编排层

**用户故事：** 作为上层应用服务开发者，我希望有一个统一的编排接口来评估组合策略，以便无需手动依次调用多个领域服务。

#### 验收标准

1. THE CombinationFacade SHALL 提供 `evaluate(combination, greeks_map, current_prices, multiplier)` 方法
2. WHEN evaluate 被调用时，THE CombinationFacade SHALL 依次调用 CombinationGreeksCalculator 计算 Greeks、CombinationPnLCalculator 计算 PnL、CombinationRiskChecker 执行风控检查
3. WHEN evaluate 完成时，THE CombinationFacade SHALL 返回 CombinationEvaluation 值对象，包含 greeks、pnl 和 risk_result 三个字段
4. IF 任一子服务抛出异常，THEN THE CombinationFacade SHALL 将异常传播给调用方，不进行静默吞没

### 需求 7：PnL 计算支持已实现盈亏

**用户故事：** 作为交易员，我希望组合级 PnL 包含已实现盈亏，以便在部分平仓场景下获得完整的盈亏视图。

#### 验收标准

1. THE LegPnL 值对象 SHALL 包含 `realized_pnl` 字段，默认值为 0.0
2. THE CombinationPnL 值对象 SHALL 包含 `total_realized_pnl` 字段，默认值为 0.0
3. WHEN CombinationPnLCalculator 计算盈亏时，THE CombinationPnLCalculator SHALL 接受 `realized_pnl_map: Dict[str, float]` 参数，键为 vt_symbol，值为该腿的已实现盈亏
4. WHEN realized_pnl_map 中包含某个 Leg 的已实现盈亏时，THE CombinationPnLCalculator SHALL 将其记入对应 LegPnL 的 realized_pnl 字段
5. THE CombinationPnLCalculator SHALL 将所有 Leg 的 realized_pnl 求和得到 total_realized_pnl
6. WHEN realized_pnl_map 参数未提供或为空时，THE CombinationPnLCalculator SHALL 将所有 realized_pnl 视为 0.0，保持与现有行为兼容
