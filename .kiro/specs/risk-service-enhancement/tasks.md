# 实现计划：风险管理服务增强

## 概述

基于设计文档，分步实现五个新的风险监控领域服务：StopLossManager（止损管理）、RiskBudgetAllocator（风险预算分配）、LiquidityRiskMonitor（持仓流动性监控）、ConcentrationMonitor（集中度风险监控）、TimeDecayMonitor（时间衰减监控）。每个服务作为独立的领域服务类实现，遵循 DDD 架构原则，与现有的 PortfolioRiskAggregator 和 PositionSizingService 协同工作。

## 任务

- [x] 1. 新增风险服务相关值对象和领域事件
  - [x] 1.1 创建止损相关值对象
    - 在 `src/strategy/domain/value_object/` 下新建或扩展 `risk.py`
    - 定义 `StopLossConfig`、`StopLossTrigger`、`PortfolioStopLossTrigger` 三个 frozen dataclass
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 1.2 创建风险预算相关值对象
    - 在 `risk.py` 中定义 `RiskBudgetConfig`、`GreeksBudget`、`GreeksUsage`、`BudgetCheckResult` 四个 dataclass
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 1.3 创建流动性监控相关值对象
    - 在 `risk.py` 中定义 `LiquidityMonitorConfig`、`MarketData`、`LiquidityScore`、`LiquidityWarning` 四个 frozen dataclass
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 1.4 创建集中度监控相关值对象
    - 在 `risk.py` 中定义 `ConcentrationConfig`、`ConcentrationMetrics`、`ConcentrationWarning` 三个 dataclass
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 1.5 创建时间衰减监控相关值对象
    - 在 `risk.py` 中定义 `TimeDecayConfig`、`ThetaMetrics`、`ExpiringPosition`、`ExpiryGroup` 四个 dataclass
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 1.6 创建风险监控领域事件
    - 在 `src/strategy/domain/event/` 下新建或扩展 `risk_events.py`
    - 定义 `StopLossTriggeredEvent`、`RiskBudgetExceededEvent`、`LiquidityDeterioratedEvent`、`ConcentrationExceededEvent`、`ExpiryWarningEvent` 五个领域事件
    - _Requirements: 1.6, 2.3, 3.5, 4.4, 5.3_

- [x] 2. 实现 StopLossManager（止损管理服务）
  - [x] 2.1 创建 `src/strategy/domain/domain_service/risk/stop_loss_manager.py`
    - 实现 `__init__` 接受 `StopLossConfig` 参数
    - 实现 `check_position_stop_loss` 方法：检查单个持仓是否触发固定止损或移动止损
    - 实现 `check_portfolio_stop_loss` 方法：检查组合总亏损是否超过每日止损限额
    - 实现内部辅助方法 `_calculate_position_pnl`、`_check_fixed_stop`、`_check_trailing_stop`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 2.2 编写 StopLossManager 单元测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_stop_loss_manager.py`
    - 测试固定止损触发场景
    - 测试移动止损触发场景
    - 测试组合止损触发场景
    - 测试边界情况：空持仓、全部盈利、亏损未达阈值
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 2.3 编写 StopLossManager 属性测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_stop_loss_properties.py`
    - **Property 1: 止损触发正确性**
    - **Validates: Requirements 1.1, 1.2, 1.4, 1.5, 1.6**
    - **Property 2: 组合止损全平仓**
    - **Validates: Requirements 1.3**
    - **Property 3: 止损计算一致性**
    - **Validates: Requirements 1.2**

- [x] 3. 实现 RiskBudgetAllocator（风险预算分配服务）
  - [x] 3.1 创建 `src/strategy/domain/domain_service/risk/risk_budget_allocator.py`
    - 实现 `__init__` 接受 `RiskBudgetConfig` 参数
    - 实现 `allocate_budget_by_underlying` 方法：按品种分配 Greeks 预算
    - 实现 `calculate_usage` 方法：计算当前 Greeks 使用量（支持按品种或策略维度）
    - 实现 `check_budget_limit` 方法：检查是否超过预算限额
    - 实现内部辅助方法 `_validate_allocation_ratios`、`_calculate_remaining_budget`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 3.2 编写 RiskBudgetAllocator 单元测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_risk_budget_allocator.py`
    - 测试按品种分配预算
    - 测试按策略分配预算
    - 测试使用量计算
    - 测试预算超限检测
    - 测试边界情况：空持仓、单一品种、分配比例总和不为 1
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 3.3 编写 RiskBudgetAllocator 属性测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_risk_budget_properties.py`
    - **Property 4: 预算分配守恒**
    - **Validates: Requirements 2.7**
    - **Property 5: 使用量计算正确性**
    - **Validates: Requirements 2.4**
    - **Property 6: 预算超限检测**
    - **Validates: Requirements 2.3**
    - **Property 7: 剩余预算一致性**
    - **Validates: Requirements 2.5**
    - **Property 8: 多维度预算分配**
    - **Validates: Requirements 2.1, 2.2, 2.6**

- [x] 4. 检查点 - 止损和预算服务验证
  - 确保所有测试通过，如有问题请向用户确认。

- [~] 5. 实现 LiquidityRiskMonitor（持仓流动性监控服务）
  - [x] 5.1 创建 `src/strategy/domain/domain_service/risk/liquidity_risk_monitor.py`
    - 实现 `__init__` 接受 `LiquidityMonitorConfig` 参数
    - 实现 `calculate_liquidity_score` 方法：计算流动性评分（成交量、价差、持仓量三个维度）
    - 实现 `monitor_positions` 方法：监控所有持仓的流动性并生成警告
    - 实现内部辅助方法 `_calculate_volume_score`、`_calculate_spread_score`、`_calculate_oi_score`、`_identify_trend`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [~] 5.2 编写 LiquidityRiskMonitor 单元测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_liquidity_risk_monitor.py`
    - 测试流动性评分计算
    - 测试流动性趋势识别（improving、stable、deteriorating）
    - 测试流动性警告触发
    - 测试边界情况：零成交量、极大价差、空历史数据
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [~] 5.3 编写 LiquidityRiskMonitor 属性测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_liquidity_properties.py`
    - **Property 9: 流动性评分范围**
    - **Validates: Requirements 3.1, 3.6**
    - **Property 10: 流动性趋势识别**
    - **Validates: Requirements 3.2, 3.3, 3.4**
    - **Property 11: 流动性警告触发**
    - **Validates: Requirements 3.5**
    - **Property 12: 持仓过滤正确性**
    - **Validates: Requirements 3.8**

- [~] 6. 实现 ConcentrationMonitor（集中度风险监控服务）
  - [~] 6.1 创建 `src/strategy/domain/domain_service/risk/concentration_monitor.py`
    - 实现 `__init__` 接受 `ConcentrationConfig` 参数
    - 实现 `calculate_concentration` 方法：计算品种、到期日、行权价三个维度的集中度和 HHI
    - 实现 `check_concentration_limits` 方法：检查集中度是否超限并生成警告
    - 实现内部辅助方法 `_calculate_dimension_concentration`、`_calculate_hhi`、`_group_by_strike_range`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [~] 6.2 编写 ConcentrationMonitor 单元测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_concentration_monitor.py`
    - 测试品种集中度计算
    - 测试到期日集中度计算
    - 测试行权价集中度计算
    - 测试 HHI 计算
    - 测试集中度超限警告
    - 测试边界情况：单一持仓、均匀分布、空持仓
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [~] 6.3 编写 ConcentrationMonitor 属性测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_concentration_properties.py`
    - **Property 13: 集中度占比计算**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.7**
    - **Property 14: HHI 计算正确性**
    - **Validates: Requirements 4.6**
    - **Property 15: 集中度警告触发**
    - **Validates: Requirements 4.4, 4.5**
    - **Property 16: 集中度单调性**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.6**

- [~] 7. 实现 TimeDecayMonitor（时间衰减监控服务）
  - [~] 7.1 创建 `src/strategy/domain/domain_service/risk/time_decay_monitor.py`
    - 实现 `__init__` 接受 `TimeDecayConfig` 参数
    - 实现 `calculate_portfolio_theta` 方法：计算组合总 Theta 和每日预期衰减金额
    - 实现 `identify_expiring_positions` 方法：识别临近到期的持仓
    - 实现 `calculate_expiry_distribution` 方法：按到期日分组统计持仓分布
    - 实现内部辅助方法 `_calculate_days_to_expiry`、`_determine_urgency`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [~] 7.2 编写 TimeDecayMonitor 单元测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_time_decay_monitor.py`
    - 测试组合 Theta 计算
    - 测试临近到期持仓识别
    - 测试到期提醒事件生成
    - 测试到期日分组统计
    - 测试边界情况：空持仓、所有持仓同一到期日、已到期持仓
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [~] 7.3 编写 TimeDecayMonitor 属性测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_time_decay_properties.py`
    - **Property 17: Theta 聚合正确性**
    - **Validates: Requirements 5.1, 5.4, 5.7**
    - **Property 18: 到期识别正确性**
    - **Validates: Requirements 5.2, 5.3, 5.6**
    - **Property 19: 到期分组完整性**
    - **Validates: Requirements 5.5**

- [~] 8. 检查点 - 流动性、集中度和时间衰减服务验证
  - 确保所有测试通过，如有问题请向用户确认。

- [~] 9. 配置文件和配置加载
  - [~] 9.1 创建 TOML 配置文件
    - 创建 `config/domain_service/risk/stop_loss_manager.toml`，包含固定止损、移动止损、组合止损配置
    - 创建 `config/domain_service/risk/risk_budget_allocator.toml`，包含分配维度和分配比例配置
    - 创建 `config/domain_service/risk/liquidity_risk_monitor.toml`，包含权重和阈值配置
    - 创建 `config/domain_service/risk/concentration_monitor.toml`，包含各维度集中度阈值和 HHI 阈值
    - 创建 `config/domain_service/risk/time_decay_monitor.toml`，包含到期提醒天数配置
    - _Requirements: 全部_

  - [~] 9.2 在 `domain_service_config_loader.py` 中新增配置加载函数
    - 新增 `load_stop_loss_config`、`load_risk_budget_config`、`load_liquidity_monitor_config`、`load_concentration_config`、`load_time_decay_config` 五个函数
    - 遵循 overrides > TOML > dataclass 默认值优先级
    - TOML 文件不存在时使用 dataclass 默认值
    - _Requirements: 全部_

- [~] 10. 集成与导出
  - [~] 10.1 更新 `src/strategy/domain/domain_service/risk/__init__.py` 导出
    - 导出五个新增的风险监控服务类
    - 导出所有相关值对象和配置类
    - 定义 `__all__` 列表
    - _Requirements: 全部_

  - [~] 10.2 编写风险服务集成测试
    - 创建 `tests/strategy/domain/domain_service/risk/test_risk_integration.py`
    - 测试止损管理器与持仓实体的交互
    - 测试风险预算分配器与 PortfolioRiskAggregator 的协同
    - 测试流动性监控器的完整流程
    - 测试集中度监控器的完整流程
    - 测试时间衰减监控器的完整流程
    - 测试多个风险服务同时工作的场景
    - _Requirements: 全部_

- [~] 11. 最终检查点 - 确保所有测试通过
  - 确保所有测试通过，如有问题请向用户确认。

## 备注

- 每个任务引用具体需求以确保可追溯性
- 属性测试使用 Hypothesis 库，每个属性至少 100 次迭代
- 每个属性测试标注 `# Feature: risk-service-enhancement, Property N: <title>`
- 单元测试覆盖边界情况和错误条件
- 所有服务遵循 DDD 架构原则，作为无状态领域服务实现
- 核心计算逻辑为纯函数，便于测试和验证
- 所有风险事件通过领域事件发布，实现解耦
