# 实现计划：选择服务增强

## 概述

基于设计文档，分步增强 `BaseFutureSelector` 和 `OptionSelectorService`，新增值对象，逐步集成并验证。

## 任务

- [x] 1. 新增值对象和数据模型
  - [x] 1.1 创建选择服务相关值对象
    - 在 `src/strategy/domain/value_object/` 下新建 `selection.py`
    - 定义 `MarketData`、`RolloverRecommendation`、`CombinationSelectionResult`、`SelectionScore` 四个 frozen dataclass
    - _Requirements: 1.1, 3.1, 4.1, 6.1_

- [x] 2. 增强 BaseFutureSelector
  - [x] 2.1 重写 `select_dominant_contract` 方法
    - 接受 `market_data` 参数，计算加权得分（volume × volume_weight + open_interest × oi_weight）
    - 按得分降序排列，得分相同时按到期日升序
    - 无行情数据时回退到按到期日排序
    - 空列表返回 None
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 2.2 编写 select_dominant_contract 属性测试
    - **Property 1: 主力合约得分最高**
    - **Validates: Requirements 1.1, 1.2**

  - [x] 2.3 重写 `filter_by_maturity` 方法
    - 使用 `ContractHelper.get_expiry_from_symbol` 解析到期日
    - 支持 current_month / next_month / custom 三种模式
    - 无法解析到期日的合约排除并记录警告
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 2.4 编写 filter_by_maturity 属性测试
    - **Property 2: 到期日过滤正确性**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [x] 2.5 新增 `check_rollover` 方法
    - 解析当前合约到期日，计算剩余交易日
    - 剩余天数 <= 阈值时生成移仓建议
    - 目标合约选择下月中成交量最大的合约
    - 无目标时返回 has_target=False 的建议
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 2.6 编写 check_rollover 属性测试
    - **Property 3: 移仓触发正确性**
    - **Property 4: 移仓目标为最大成交量合约**
    - **Validates: Requirements 3.1, 3.2, 3.3**

- [x] 3. 检查点 - 期货选择器验证
  - 确保所有测试通过，如有问题请向用户确认。

- [ ] 4. 增强 OptionSelectorService - 组合选择
  - [x] 4.1 新增 `select_combination` 方法
    - 根据 CombinationType 分发到内部方法 `_select_straddle`、`_select_strangle`、`_select_vertical_spread`
    - 每个内部方法复用现有 `_filter_liquidity`、`_filter_trading_days`、`_calculate_otm_ranking` 方法
    - 对选择结果调用 `VALIDATION_RULES` 验证结构合规
    - 任一腿流动性不足时返回 success=False
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 4.2 编写组合选择属性测试
    - **Property 5: 组合选择结构合规**
    - **Property 6: Straddle 选择最接近 ATM**
    - **Property 7: Strangle 选择虚值档位正确**
    - **Property 8: 流动性不足拒绝整个组合**
    - **Validates: Requirements 4.1, 4.2, 4.4, 4.5**

- [ ] 5. 增强 OptionSelectorService - Greeks 感知选择
  - [~] 5.1 新增 `select_by_delta` 方法
    - 接受 `greeks_data: Dict[str, GreeksResult]` 和 `target_delta`
    - 从候选合约中选择 Delta 最接近目标值的合约
    - 支持 delta_tolerance 范围过滤
    - 无 Greeks 数据时回退到 `select_option` 方法
    - _Requirements: 5.1, 5.2, 5.3_

  - [~] 5.2 编写 Delta 选择属性测试
    - **Property 9: Delta 选择最优性**
    - **Property 10: Delta 范围过滤正确性**
    - **Validates: Requirements 5.1, 5.3**

- [ ] 6. 增强 OptionSelectorService - 评分排名
  - [~] 6.1 新增 `score_candidates` 方法及内部评分函数
    - 实现 `_calc_liquidity_score`、`_calc_otm_score`、`_calc_expiry_score` 三个评分函数
    - 计算加权总分并按降序排列
    - 返回 `List[SelectionScore]`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [~] 6.2 编写评分排名属性测试
    - **Property 11: 评分单调性**
    - **Property 12: 评分完整性与排序**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

- [ ] 7. 集成与导出
  - [~] 7.1 更新 `selection/__init__.py` 导出
    - 导出增强后的 `BaseFutureSelector` 和 `OptionSelectorService`
    - 导出新增值对象
    - _Requirements: 全部_

  - [~] 7.2 编写集成测试
    - 测试期货选择器完整流程：选择主力 → 检查移仓 → 过滤到期日
    - 测试期权选择器完整流程：评分 → 组合选择 → Delta 选择
    - _Requirements: 全部_

- [ ] 8. 最终检查点 - 确保所有测试通过
  - 确保所有测试通过，如有问题请向用户确认。

## 备注

- 标记 `*` 的任务为可选任务，可跳过以加速 MVP
- 每个任务引用具体需求以确保可追溯性
- 属性测试使用 Hypothesis 库，每个属性至少 100 次迭代
- 单元测试覆盖边界情况和错误条件
