# 实施计划：领域服务目录重组

## 概述

将 `src/strategy/domain/domain_service/` 下 12 个领域服务文件按职责分类到 6 个子目录中，更新所有导入路径，确保全量测试通过。纯文件组织重构，不涉及业务逻辑变更。

## 任务

- [x] 1. 创建子目录结构
  - [x] 1.1 在 `src/strategy/domain/domain_service/` 下创建 6 个子目录并添加空 `__init__.py`
    - 创建 `pricing/`、`hedging/`、`execution/`、`selection/`、`risk/`、`signal/` 目录
    - 每个目录下创建空的 `__init__.py`
    - 确认 `calculation_service/` 保持不变
    - _需求：1.1, 1.2, 1.3_

- [x] 2. 移动 pricing 组文件并更新导入
  - [x] 2.1 移动 `greeks_calculator.py` 和 `vol_surface_builder.py` 到 `pricing/`
    - 移动文件到 `pricing/` 子目录
    - 将两个文件中的相对导入 `..` 调整为 `...`（多一层）
    - _需求：2.1_
  - [x] 2.2 更新 `strategy_entry.py` 中 `greeks_calculator` 的导入路径
    - `.domain.domain_service.greeks_calculator` → `.domain.domain_service.pricing.greeks_calculator`
    - _需求：3.1_
  - [x] 2.3 更新测试文件 `test_greeks_calculator.py` 和 `test_vol_surface_builder.py` 的导入路径
    - `src.strategy.domain.domain_service.greeks_calculator` → `src.strategy.domain.domain_service.pricing.greeks_calculator`
    - `src.strategy.domain.domain_service.vol_surface_builder` → `src.strategy.domain.domain_service.pricing.vol_surface_builder`
    - _需求：4.1_

- [x] 3. 移动 hedging 组文件并更新导入
  - [x] 3.1 移动 `delta_hedging_engine.py` 和 `gamma_scalping_engine.py` 到 `hedging/`
    - 移动文件到 `hedging/` 子目录
    - 将两个文件中的相对导入 `..` 调整为 `...`
    - _需求：2.2_
  - [x] 3.2 更新测试文件 `test_delta_hedging_engine.py` 和 `test_gamma_scalping_engine.py` 的导入路径
    - `src.strategy.domain.domain_service.delta_hedging_engine` → `src.strategy.domain.domain_service.hedging.delta_hedging_engine`
    - `src.strategy.domain.domain_service.gamma_scalping_engine` → `src.strategy.domain.domain_service.hedging.gamma_scalping_engine`
    - _需求：4.1_

- [x] 4. 移动 execution 组文件并更新导入
  - [x] 4.1 移动 `smart_order_executor.py` 和 `advanced_order_scheduler.py` 到 `execution/`
    - 移动文件到 `execution/` 子目录
    - `smart_order_executor.py`：将相对导入 `..` 调整为 `...`
    - `advanced_order_scheduler.py`：使用绝对导入，无需调整相对路径
    - _需求：2.3_
  - [x] 4.2 更新 `strategy_entry.py` 中 `smart_order_executor` 的导入路径
    - `.domain.domain_service.smart_order_executor` → `.domain.domain_service.execution.smart_order_executor`
    - _需求：3.1_
  - [x] 4.3 更新测试文件 `test_smart_order_executor.py`、`test_advanced_order_scheduler.py`、`test_order_splitting.py` 的导入路径
    - `src.strategy.domain.domain_service.smart_order_executor` → `src.strategy.domain.domain_service.execution.smart_order_executor`
    - `src.strategy.domain.domain_service.advanced_order_scheduler` → `src.strategy.domain.domain_service.execution.advanced_order_scheduler`
    - _需求：4.1_

- [x] 5. 移动 selection 组文件并更新导入
  - [x] 5.1 移动 `option_selector_service.py` 和 `future_selection_service.py` 到 `selection/`
    - 移动文件到 `selection/` 子目录
    - `option_selector_service.py`：将相对导入 `..` 调整为 `...`
    - `future_selection_service.py`：使用绝对导入，无需调整相对路径
    - _需求：2.4_
  - [x] 5.2 更新 `strategy_entry.py` 中 `option_selector_service` 和 `future_selection_service` 的导入路径
    - `.domain.domain_service.option_selector_service` → `.domain.domain_service.selection.option_selector_service`
    - `.domain.domain_service.future_selection_service` → `.domain.domain_service.selection.future_selection_service`
    - _需求：3.1_
  - [x] 5.3 更新测试文件 `test_base_future_selector.py` 的导入路径
    - `src.strategy.domain.domain_service.future_selection_service` → `src.strategy.domain.domain_service.selection.future_selection_service`
    - _需求：4.1_

- [x] 6. 移动 risk 组文件并更新导入
  - [x] 6.1 移动 `portfolio_risk_aggregator.py` 和 `position_sizing_service.py` 到 `risk/`
    - 移动文件到 `risk/` 子目录
    - 将两个文件中的相对导入 `..` 调整为 `...`
    - _需求：2.5_
  - [x] 6.2 更新 `strategy_entry.py` 中 `portfolio_risk_aggregator` 和 `position_sizing_service` 的导入路径
    - `.domain.domain_service.portfolio_risk_aggregator` → `.domain.domain_service.risk.portfolio_risk_aggregator`
    - `.domain.domain_service.position_sizing_service` → `.domain.domain_service.risk.position_sizing_service`
    - _需求：3.1_
  - [x] 6.3 更新测试文件 `test_portfolio_risk_aggregator.py` 的导入路径
    - `src.strategy.domain.domain_service.portfolio_risk_aggregator` → `src.strategy.domain.domain_service.risk.portfolio_risk_aggregator`
    - _需求：4.1_

- [ ] 7. 移动 signal 组文件并更新导入
  - [-] 7.1 移动 `signal_service.py` 和 `indicator_service.py` 到 `signal/`
    - 移动文件到 `signal/` 子目录
    - 将两个文件中的相对导入 `..` 调整为 `...`
    - _需求：2.6_
  - [~] 7.2 更新 `strategy_entry.py` 中 `indicator_service` 和 `signal_service` 的导入路径
    - `.domain.domain_service.indicator_service` → `.domain.domain_service.signal.indicator_service`
    - `.domain.domain_service.signal_service` → `.domain.domain_service.signal.signal_service`
    - _需求：3.1_

- [~] 8. 全局导入路径扫描与修复
  - 使用 grep 全局搜索 `from.*domain_service\.(greeks_calculator|vol_surface_builder|delta_hedging_engine|gamma_scalping_engine|smart_order_executor|advanced_order_scheduler|option_selector_service|future_selection_service|portfolio_risk_aggregator|position_sizing_service|signal_service|indicator_service)` 确认无遗漏的旧导入路径
  - 修复任何遗漏的导入引用
  - 确认 Domain_Service_Root 下不再有散落的 `.py` 服务文件
  - _需求：2.7, 3.2, 3.3_

- [~] 9. 检查点 - 运行全量测试验证
  - 运行 `pytest tests/strategy/domain/domain_service/` 确认所有领域服务测试通过
  - 运行 `pytest tests/strategy/` 确认策略模块整体无回归
  - 确认所有测试通过，如有问题请向用户确认
  - _需求：4.2, 5.1, 5.2, 5.3_

## 备注

- 本次重构不涉及属性测试（property-based testing），因为没有新业务逻辑
- `test_config_integration.py` 不导入领域服务，无需修改
- `advanced_order_scheduler.py` 和 `future_selection_service.py` 使用绝对导入，移动后无需调整相对路径层级
- 其余 10 个服务文件使用相对导入（`..`），移动到子目录后需调整为 `...`
