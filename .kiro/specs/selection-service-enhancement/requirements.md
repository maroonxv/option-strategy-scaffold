# 需求文档

## 简介

增强 `src/strategy/domain/domain_service/selection/` 下的合约选择服务，包括期货主力合约选择（基于成交量/持仓量、到期日解析、移仓换月）和期权选择服务（组合策略联合选择、Greeks 感知选择、选择结果评分机制）。当前实现过于简单，无法满足实际交易场景中对合约选择精度和智能化的要求。

## 术语表

- **Selection_Service**: 合约选择领域服务，负责从可用合约中筛选出最优合约
- **Future_Selector**: 期货合约选择器，负责主力合约判断、到期日过滤和移仓换月
- **Option_Selector**: 期权合约选择器，负责单腿和组合策略的期权选择
- **Dominant_Contract**: 主力合约，成交量和持仓量最大的活跃合约
- **Rollover**: 移仓换月，临近到期时从当月合约切换到下月合约的过程
- **ContractHelper**: 基础设施层的合约解析工具类，提供到期日解析等功能
- **OptionContract**: 期权合约值对象，包含行权价、到期日、Greeks 等属性
- **CombinationType**: 组合策略类型枚举（STRADDLE、STRANGLE、VERTICAL_SPREAD 等）
- **GreeksResult**: Greeks 计算结果值对象（delta、gamma、theta、vega）
- **Selection_Score**: 选择评分结果，对候选合约进行多维度评分排名
- **OTM_Level**: 虚值档位，期权行权价偏离标的价格的程度排序位置

## 需求

### 需求 1：基于成交量/持仓量的主力合约选择

**用户故事：** 作为一名量化交易员，我希望系统能基于成交量和持仓量来判断主力合约，以便选择流动性最好的期货合约进行交易。

#### 验收标准

1. WHEN 传入一组期货合约及其行情数据, THE Future_Selector SHALL 按成交量和持仓量的加权得分降序排列合约，并选择得分最高的合约作为 Dominant_Contract
2. WHEN 多个合约的加权得分相同, THE Future_Selector SHALL 优先选择到期日较近的合约
3. WHEN 所有合约的成交量和持仓量均为零, THE Future_Selector SHALL 回退到按到期日排序选择最近月合约
4. IF 传入的合约列表为空, THEN THE Future_Selector SHALL 返回 None

### 需求 2：基于到期日解析的合约过滤

**用户故事：** 作为一名量化交易员，我希望系统能正确解析合约到期日并据此过滤合约，以便精确控制交易合约的到期时间范围。

#### 验收标准

1. WHEN 过滤当月合约, THE Future_Selector SHALL 使用 ContractHelper.get_expiry_from_symbol 解析每个合约的到期日，并仅返回到期日在当月范围内的合约
2. WHEN 过滤次月合约, THE Future_Selector SHALL 返回到期日在下一个自然月范围内的合约
3. WHEN 指定自定义日期范围进行过滤, THE Future_Selector SHALL 返回到期日在该范围内的所有合约
4. IF 合约代码无法解析出到期日, THEN THE Future_Selector SHALL 将该合约排除并记录警告日志

### 需求 3：期货移仓换月逻辑

**用户故事：** 作为一名量化交易员，我希望系统能在合约临近到期时自动建议切换到下月合约，以避免交割风险和流动性枯竭。

#### 验收标准

1. WHEN 当前持有合约的剩余交易日小于等于配置的移仓阈值天数, THE Future_Selector SHALL 返回移仓建议，包含当前合约和建议切换的目标合约
2. WHEN 生成移仓建议时, THE Future_Selector SHALL 选择下一个到期月份中成交量最大的合约作为目标合约
3. WHEN 当前合约剩余交易日大于移仓阈值, THE Future_Selector SHALL 不生成移仓建议
4. IF 无法找到合适的目标合约, THEN THE Future_Selector SHALL 返回包含警告信息的移仓建议

### 需求 4：组合策略联合选择

**用户故事：** 作为一名量化交易员，我希望系统能根据组合策略类型（如 Straddle、Strangle）同时选择多个期权腿，以便快速构建符合策略要求的组合。

#### 验收标准

1. WHEN 请求选择 STRADDLE 组合, THE Option_Selector SHALL 选择同一到期日、同一行权价的一个 Call 和一个 Put，行权价最接近标的当前价格
2. WHEN 请求选择 STRANGLE 组合, THE Option_Selector SHALL 选择同一到期日的一个虚值 Call 和一个虚值 Put，虚值档位由配置参数决定
3. WHEN 请求选择 VERTICAL_SPREAD 组合, THE Option_Selector SHALL 选择同一到期日、同一期权类型、不同行权价的两个期权，行权价间距由配置参数决定
4. WHEN 选择组合的任一腿不满足流动性要求, THE Option_Selector SHALL 拒绝整个组合选择并返回失败原因
5. THE Option_Selector SHALL 对选择结果调用 combination_rules 中对应的验证函数，确保结构合规

### 需求 5：Greeks 感知的期权选择

**用户故事：** 作为一名量化交易员，我希望系统能结合 Delta 目标值来选择最优期权合约，以便更精确地控制组合的风险敞口。

#### 验收标准

1. WHEN 指定目标 Delta 值进行期权选择, THE Option_Selector SHALL 从候选合约中选择实际 Delta 最接近目标值的合约
2. WHEN 候选合约均无可用的 Greeks 数据, THE Option_Selector SHALL 回退到基于虚值档位的选择方式
3. WHEN 指定 Delta 范围约束进行选择, THE Option_Selector SHALL 仅返回 Delta 在指定范围内的合约

### 需求 6：选择结果评分与排名

**用户故事：** 作为一名量化交易员，我希望系统能对候选合约进行多维度评分，以便我了解每个合约的综合质量并做出更优决策。

#### 验收标准

1. THE Option_Selector SHALL 对每个候选合约计算 Selection_Score，评分维度包括流动性得分、虚值程度得分和到期日得分
2. WHEN 计算流动性得分, THE Option_Selector SHALL 基于买卖价差跳数和买一量进行评分，价差越小且买一量越大则得分越高
3. WHEN 计算虚值程度得分, THE Option_Selector SHALL 基于实际虚值档位与目标档位的偏差进行评分，偏差越小则得分越高
4. WHEN 计算到期日得分, THE Option_Selector SHALL 基于剩余交易日与目标范围中点的偏差进行评分，越接近中点则得分越高
5. THE Option_Selector SHALL 支持配置各评分维度的权重，并按加权总分降序排列候选合约
