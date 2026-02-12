# 需求文档：回测模块重构

## 简介

对 `src/backtesting` 模块进行重构，将当前散乱的两个文件按照职责分离原则重新组织为清晰的模块结构。重构后的模块需要更好地支持期货和期权的回测场景，消除硬编码值，移除 monkey-patching，并提供可测试的组件。

## 术语表

- **Backtesting_Engine**: VnPy 提供的 `BacktestingEngine`，用于执行组合策略回测
- **Contract_Registry**: 合约注册表，负责管理回测中所有合约的 `ContractData` 信息
- **Symbol_Generator**: 合约代码生成器，根据品种代码和时间范围生成标准 vt_symbol
- **Option_Discovery_Service**: 期权发现服务，从数据库中查找与期货合约关联的期权合约
- **Backtest_Config**: 回测配置对象，封装回测所需的全部参数（日期范围、资金、费率等）
- **Product_Spec**: 品种规格，包含合约乘数（size）和最小价格变动（pricetick）
- **Contract_Factory**: 合约工厂，根据 vt_symbol 解析并生成 `ContractData` 对象
- **Expiry_Calculator**: 到期日计算器，根据交易所规则计算合约到期日
- **Exchange_Resolver**: 交易所解析器，根据品种代码查找对应的交易所

## 需求

### 需求 1：模块结构组织

**用户故事：** 作为开发者，我希望回测模块按照职责分门别类组织代码，以便于维护和扩展。

#### 验收标准

1. THE Backtesting_Module SHALL 提供 `__init__.py` 文件，导出核心公共接口
2. THE Backtesting_Module SHALL 将交易所映射、品种规格等静态配置数据集中存放在独立的配置模块中
3. THE Backtesting_Module SHALL 将合约代码生成、到期日计算、合约数据构建分离为独立的组件
4. THE Backtesting_Module SHALL 将回测执行流程（引擎配置、数据加载、结果计算）封装为独立的运行器组件

### 需求 2：合约代码生成

**用户故事：** 作为量化交易员，我希望能够根据品种代码和时间范围自动生成正确的 vt_symbol，以便快速配置回测。

#### 验收标准

1. WHEN 提供品种代码和时间范围时，THE Symbol_Generator SHALL 生成该范围内所有月份的标准 vt_symbol
2. WHEN 品种属于郑商所时，THE Symbol_Generator SHALL 使用三位数字格式（如 AP601）生成合约代码
3. WHEN 品种属于其他交易所时，THE Symbol_Generator SHALL 使用四位数字格式（如 rb2601）生成合约代码
4. WHEN 品种代码已包含交易所后缀（含"."）时，THE Symbol_Generator SHALL 直接返回该代码而不做额外处理

### 需求 3：交易所与品种规格解析

**用户故事：** 作为量化交易员，我希望系统能自动识别品种对应的交易所和合约规格，以便回测使用正确的参数。

#### 验收标准

1. WHEN 提供品种代码时，THE Exchange_Resolver SHALL 返回该品种对应的交易所代码
2. IF 品种代码不在已知映射中，THEN THE Exchange_Resolver SHALL 返回明确的错误信息
3. WHEN 提供品种代码时，THE Product_Spec SHALL 返回该品种的合约乘数和最小价格变动
4. IF 品种代码不在已知规格中，THEN THE Product_Spec SHALL 返回默认值（size=10, pricetick=1.0）

### 需求 4：合约到期日计算

**用户故事：** 作为量化交易员，我希望系统能根据交易所规则正确计算合约到期日，以便期权回测中的到期日判断准确。

#### 验收标准

1. WHEN 品种属于中金所时，THE Expiry_Calculator SHALL 计算合约月份的第三个周五作为到期日
2. WHEN 品种属于大商所时，THE Expiry_Calculator SHALL 计算交割月前一个月的第12个交易日作为到期日
3. WHEN 品种属于郑商所时，THE Expiry_Calculator SHALL 计算交割月前一个月的第15个交易日作为到期日
4. WHEN 品种属于上期所或能源中心时，THE Expiry_Calculator SHALL 计算交割月前一个月的倒数第5个交易日作为到期日
5. WHEN 手动到期日配置中存在该合约时，THE Expiry_Calculator SHALL 优先使用手动配置的到期日
6. WHEN 安装了 chinese_calendar 库时，THE Expiry_Calculator SHALL 在计算交易日时排除法定节假日

### 需求 5：合约数据构建

**用户故事：** 作为量化交易员，我希望系统能根据 vt_symbol 自动构建完整的 ContractData 对象，以便回测引擎获取正确的合约信息。

#### 验收标准

1. WHEN 提供期货格式的 vt_symbol（如 rb2505.SHFE）时，THE Contract_Factory SHALL 生成 product 为 FUTURES 的 ContractData
2. WHEN 提供期权格式的 vt_symbol（如 MO2601-C-6300.CFFEX）时，THE Contract_Factory SHALL 生成 product 为 OPTION 的 ContractData，包含正确的 strike_price、option_type 和 option_expiry
3. WHEN 期权的品种代码存在反向映射（如 MO→IM）时，THE Contract_Factory SHALL 将 option_underlying 设置为对应的期货品种代码
4. THE Contract_Factory SHALL 根据品种代码自动填充正确的 size 和 pricetick
5. IF vt_symbol 格式无法解析，THEN THE Contract_Factory SHALL 返回 None 并记录警告日志

### 需求 6：期权合约发现

**用户故事：** 作为量化交易员，我希望系统能从数据库中自动发现与期货合约关联的期权合约，以便回测时自动包含相关期权。

#### 验收标准

1. WHEN 提供期货 vt_symbol 列表时，THE Option_Discovery_Service SHALL 从数据库中查找所有关联的期权合约
2. WHEN 期货品种存在期权映射（如 IF→IO）时，THE Option_Discovery_Service SHALL 使用映射后的期权品种前缀进行匹配
3. THE Option_Discovery_Service SHALL 仅返回数据库中存在 1 分钟 K 线数据的期权合约
4. IF 数据库查询失败，THEN THE Option_Discovery_Service SHALL 记录错误日志并返回空列表

### 需求 7：合约注册表

**用户故事：** 作为开发者，我希望通过合约注册表统一管理回测中的合约信息，以替代当前的 monkey-patching 方式。

#### 验收标准

1. THE Contract_Registry SHALL 提供注册合约、查询单个合约和获取全部合约的接口
2. WHEN 注册合约时，THE Contract_Registry SHALL 以 vt_symbol 为键存储 ContractData
3. WHEN 查询不存在的合约时，THE Contract_Registry SHALL 返回 None
4. THE Contract_Registry SHALL 提供将自身注入 Backtesting_Engine 的方法，替代直接 monkey-patching

### 需求 8：回测配置管理

**用户故事：** 作为量化交易员，我希望回测参数可配置且无硬编码值，以便灵活调整回测条件。

#### 验收标准

1. THE Backtest_Config SHALL 封装所有回测参数：日期范围、初始资金、费率、滑点、合约乘数、最小价格变动
2. WHEN 未指定结束日期时，THE Backtest_Config SHALL 默认使用当前日期
3. THE Backtest_Config SHALL 支持从 YAML 配置文件加载参数
4. THE Backtest_Config SHALL 支持从命令行参数覆盖配置文件中的值
5. THE Backtest_Config SHALL 不包含任何硬编码的日期值

### 需求 9：回测执行器

**用户故事：** 作为量化交易员，我希望有一个清晰的回测执行流程，以便一键运行完整的回测。

#### 验收标准

1. THE Backtest_Runner SHALL 按顺序执行：加载配置、生成合约代码、发现期权、注册合约、配置引擎、加载数据、运行回测、计算结果
2. WHEN 配置中 vt_symbols 为空时，THE Backtest_Runner SHALL 从 trading_target.yaml 加载品种列表
3. WHEN 回测完成时，THE Backtest_Runner SHALL 输出统计结果
4. WHERE show_chart 选项启用时，THE Backtest_Runner SHALL 显示回测图表
5. IF 生成的 vt_symbols 为空，THEN THE Backtest_Runner SHALL 终止执行并输出错误信息

### 需求 10：命令行接口

**用户故事：** 作为量化交易员，我希望通过命令行参数灵活控制回测，以便快速调整回测条件。

#### 验收标准

1. THE CLI SHALL 支持以下参数：config（配置文件路径）、start（开始日期）、end（结束日期）、capital（初始资金）、rate（费率）、slippage（滑点）、no-chart（禁用图表）
2. WHEN 未提供参数时，THE CLI SHALL 使用合理的默认值
3. THE CLI SHALL 将命令行参数传递给 Backtest_Config 进行处理
