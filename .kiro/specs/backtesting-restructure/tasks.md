# 实现计划：回测模块重构

## 概述

将 `src/backtesting` 从两个散乱文件重构为职责清晰的模块结构，按照设计文档中的架构逐步实现各组件，确保每一步都可增量验证。

## 任务

- [x] 1. 创建模块结构和静态配置
  - [x] 1.1 创建目录结构和 `__init__.py` 文件
    - 创建 `src/backtesting/__init__.py`、`src/backtesting/contract/__init__.py`、`src/backtesting/discovery/__init__.py`
    - _Requirements: 1.1_
  - [x] 1.2 创建 `src/backtesting/config.py`，提取静态配置数据和 BacktestConfig 数据类
    - 从 `vt_symbol_generator.py` 提取 EXCHANGE_MAP、FUTURE_OPTION_MAP、OPTION_FUTURE_MAP、PRODUCT_SPECS、MANUAL_EXPIRY_CONFIG
    - 实现 BacktestConfig dataclass，支持 from_args() 方法
    - 不包含任何硬编码日期值
    - _Requirements: 1.2, 8.1, 8.2, 8.4, 8.5_

- [x] 2. 实现合约基础组件
  - [x] 2.1 实现 `src/backtesting/contract/exchange_resolver.py`
    - ExchangeResolver.resolve()：从 EXCHANGE_MAP 查找，未知品种抛出 ValueError
    - ExchangeResolver.is_czce()：判断是否郑商所品种
    - _Requirements: 3.1, 3.2_
  - [x] 2.2 为 ExchangeResolver 编写属性测试
    - **Property 2: 交易所解析一致性**
    - **Validates: Requirements 3.1**
  - [x] 2.3 实现 `src/backtesting/contract/expiry_calculator.py`
    - ExpiryCalculator.calculate()：根据交易所规则计算到期日
    - ExpiryCalculator.get_trading_days()：获取交易日列表
    - 支持手动配置优先、chinese_calendar 节假日排除
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - [x] 2.4 为 ExpiryCalculator 编写属性测试
    - **Property 4: 到期日计算交易所规则正确性**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

- [x] 3. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [ ] 4. 实现合约工厂和注册表
  - [x] 4.1 实现 `src/backtesting/contract/contract_factory.py`
    - ContractFactory.create()：解析 vt_symbol 构建 ContractData
    - 支持期货格式（rb2505.SHFE）和期权格式（MO2601-C-6300.CFFEX、rb2505C3000.SHFE）
    - 期权反向映射（MO→IM）、自动填充 size/pricetick
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [x] 4.2 为 ContractFactory 编写属性测试
    - **Property 5: 期货合约构建正确性**
    - **Property 6: 期权合约构建正确性**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
  - [-] 4.3 实现 `src/backtesting/contract/contract_registry.py`
    - ContractRegistry：register()、get()、get_all()、register_many()、inject_into_engine()
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [~] 4.4 为 ContractRegistry 编写属性测试
    - **Property 7: 合约注册表 round-trip**
    - **Validates: Requirements 7.1, 7.2, 7.3**

- [~] 5. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [ ] 6. 实现合约发现组件
  - [~] 6.1 实现 `src/backtesting/discovery/symbol_generator.py`
    - SymbolGenerator.generate_for_range()：生成时间范围内的 vt_symbol
    - SymbolGenerator.generate_recent()：生成近期合约代码（无硬编码开始日期）
    - 郑商所三位格式、其他交易所四位格式
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [~] 6.2 为 SymbolGenerator 编写属性测试
    - **Property 1: 合约代码生成格式正确性**
    - **Validates: Requirements 2.1, 2.2, 2.3**
  - [~] 6.3 实现 `src/backtesting/discovery/option_discovery.py`
    - OptionDiscoveryService.discover()：从数据库查找关联期权
    - 使用 FUTURE_OPTION_MAP 进行前缀匹配
    - 数据库失败时返回空列表
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 7. 实现回测执行器和 CLI
  - [~] 7.1 实现 `src/backtesting/runner.py`
    - BacktestRunner.run()：完整回测流程编排
    - 使用 ContractRegistry 替代 monkey-patching
    - 空 vt_symbols 时终止执行
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [~] 7.2 实现 `src/backtesting/cli.py`
    - argparse CLI 入口
    - 支持 config、start、end、capital、rate、slippage、no-chart 参数
    - _Requirements: 10.1, 10.2, 10.3_
  - [~] 7.3 为 BacktestConfig 编写属性测试
    - **Property 8: 配置 CLI 覆盖优先级**
    - **Validates: Requirements 8.4**

- [ ] 8. 更新模块导出和清理旧代码
  - [~] 8.1 更新 `src/backtesting/__init__.py`，导出核心公共接口
    - 导出 BacktestConfig、BacktestRunner、SymbolGenerator、ContractFactory、ContractRegistry
    - _Requirements: 1.1_
  - [~] 8.2 删除旧文件 `src/backtesting/run_backtesting.py` 和 `src/backtesting/vt_symbol_generator.py`
    - 确认所有功能已迁移到新组件
    - 更新项目中其他引用旧模块的代码
    - _Requirements: 1.3, 1.4_

- [~] 9. Final checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

## 备注

- 标记 `*` 的任务为可选测试任务，可跳过以加快 MVP 进度
- 每个任务引用了具体的需求编号以便追溯
- Checkpoint 确保增量验证
- 属性测试使用 hypothesis 库，每个测试至少 100 次迭代
- 单元测试验证边界条件和错误处理
