# 需求文档：动态仓位计算与 Greeks 感知开仓决策

## 简介

当前 PositionSizingService 采用固定1手开仓策略，不感知账户资金状况、保证金占用和组合 Greeks 敞口。本需求旨在将仓位计算从固定值升级为基于多维度风控约束的动态计算，使开仓手数能够根据账户可用资金、保证金估算、组合 Greeks 剩余空间综合决策，在最大化资金利用率的同时确保风险可控。

## 术语表

- **PositionSizingService**: 仓位管理领域服务，负责计算开仓手数并生成交易指令
- **PortfolioRiskAggregator**: 组合风险聚合器，负责持仓级和组合级 Greeks 风控检查
- **GreeksResult**: 值对象，包含单手期权的 Delta、Gamma、Theta、Vega
- **PortfolioGreeks**: 值对象，组合级 Greeks 快照（total_delta, total_gamma, total_theta, total_vega）
- **RiskThresholds**: 值对象，风控阈值配置（持仓级和组合级 Greeks 限额）
- **MarginEstimate**: 值对象，保证金估算结果，包含单手保证金和可开手数
- **SizingResult**: 值对象，仓位计算综合结果，包含最终手数和各维度的限制明细
- **OrderInstruction**: 值对象，交易指令（合约、方向、开平、手数、价格）
- **Multiplier**: 合约乘数，将期权价格转换为实际金额的系数
- **Margin_Usage_Ratio**: 保证金使用率，已用保证金占账户总权益的比例
- **Greeks_Budget**: Greeks 预算，组合 Greeks 阈值与当前敞口之间的剩余空间

## 需求

### 需求 1：保证金估算

**用户故事：** 作为期权卖方策略，我需要估算卖出期权的保证金占用，以便在开仓前确认账户资金是否充足。

#### 验收标准

1. WHEN 计算卖出期权保证金时，THE PositionSizingService SHALL 使用公式 `单手保证金 = 权利金 × 合约乘数 + max(标的价格 × 合约乘数 × 保证金比例 - 虚值额, 标的价格 × 合约乘数 × 最低保证金比例)` 估算单手保证金
2. WHEN 估算单手保证金后，THE PositionSizingService SHALL 基于可用资金和单手保证金计算资金维度允许的最大开仓手数，公式为 `floor(可用资金 / 单手保证金)`
3. IF 单手保证金估算值小于等于零，THEN THE PositionSizingService SHALL 拒绝开仓并返回包含错误原因的 SizingResult
4. IF 可用资金不足以覆盖一手保证金，THEN THE PositionSizingService SHALL 拒绝开仓并返回资金不足的 SizingResult

### 需求 2：保证金使用率控制

**用户故事：** 作为风控管理者，我需要控制保证金使用率不超过安全阈值，以便在极端行情下保留足够的资金缓冲。

#### 验收标准

1. THE PositionSizingService SHALL 支持配置保证金使用率上限（margin_usage_limit），默认值为 0.6（60%）
2. WHEN 计算开仓手数时，THE PositionSizingService SHALL 确保开仓后的保证金使用率不超过 margin_usage_limit，公式为 `floor((总权益 × margin_usage_limit - 已用保证金) / 单手保证金)`
3. IF 当前保证金使用率已达到或超过 margin_usage_limit，THEN THE PositionSizingService SHALL 拒绝开仓并返回保证金使用率超限的 SizingResult

### 需求 3：Greeks 预算计算

**用户故事：** 作为期权卖方策略，我需要在开仓前评估新增持仓对组合 Greeks 的边际影响，以便确保组合风险不超过阈值。

#### 验收标准

1. WHEN 计算 Greeks 预算时，THE PositionSizingService SHALL 对 Delta、Gamma、Vega 三个维度分别计算剩余空间，公式为 `Greeks_Budget_X = portfolio_X_limit - |current_portfolio_X|`
2. WHEN 计算 Greeks 维度允许的最大手数时，THE PositionSizingService SHALL 对每个 Greek 维度计算 `floor(Greeks_Budget_X / |单手_X × 合约乘数|)`，取三个维度的最小值
3. IF 任一 Greeks 维度的剩余空间不足以容纳一手新增持仓，THEN THE PositionSizingService SHALL 拒绝开仓并返回 Greeks 超限的 SizingResult，注明具体超限维度
4. IF 新增持仓的某个 Greek 值为零，THEN THE PositionSizingService SHALL 视该维度为无限制，不参与最小值计算

### 需求 4：综合仓位决策

**用户故事：** 作为期权卖方策略，我需要综合保证金、保证金使用率、Greeks 预算等多维度约束，计算出最终的安全开仓手数。

#### 验收标准

1. WHEN 计算最终开仓手数时，THE PositionSizingService SHALL 取保证金维度手数、保证金使用率维度手数、Greeks 预算维度手数的最小值作为最终手数
2. THE PositionSizingService SHALL 将最终手数限制在 `[1, max_volume_per_order]` 范围内，其中 max_volume_per_order 为可配置参数，默认值为 10
3. IF 综合计算后最终手数小于 1，THEN THE PositionSizingService SHALL 拒绝开仓
4. WHEN 计算完成时，THE PositionSizingService SHALL 返回 SizingResult，包含最终手数和各维度的限制明细（保证金维度手数、使用率维度手数、Greeks 维度手数及各 Greek 的具体限制）
5. THE PositionSizingService SHALL 保留现有的风控检查（最大持仓数量、全局日开仓限额、单合约日开仓限额、重复合约检查），在动态仓位计算之前执行

### 需求 5：SizingResult 值对象

**用户故事：** 作为策略开发者，我需要一个结构化的仓位计算结果，以便清晰了解开仓决策的依据和各维度的限制情况。

#### 验收标准

1. THE SizingResult SHALL 包含以下字段：final_volume（最终手数）、margin_volume（保证金维度手数）、usage_volume（使用率维度手数）、greeks_volume（Greeks 维度手数）、passed（是否通过）、reject_reason（拒绝原因）
2. THE SizingResult SHALL 包含 Greeks 明细字段：delta_budget（Delta 剩余空间）、gamma_budget（Gamma 剩余空间）、vega_budget（Vega 剩余空间）
3. THE SizingResult SHALL 为不可变值对象（frozen dataclass）

### 需求 6：配置管理

**用户故事：** 作为策略运维人员，我需要通过配置文件调整动态仓位计算的参数，以便在不修改代码的情况下适应不同的市场环境。

#### 验收标准

1. THE PositionSizingService SHALL 从 strategy_config.yaml 的 `position_sizing` 配置节读取以下参数：margin_ratio（保证金比例，默认 0.12）、min_margin_ratio（最低保证金比例，默认 0.07）、margin_usage_limit（保证金使用率上限，默认 0.6）、max_volume_per_order（单笔最大手数，默认 10）
2. WHEN 配置参数缺失时，THE PositionSizingService SHALL 使用上述默认值正常运行
