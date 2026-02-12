# Implementation Plan: 高级订单类型、动态对冲引擎、波动率曲面

## Overview

基于已批准的需求和设计文档，按模块递增实现：先构建值对象和领域事件，再逐个实现 AdvancedOrderScheduler、DeltaHedgingEngine、GammaScalpingEngine、VolSurfaceBuilder，最后集成配置加载和 StrategyEntry 编排。每个模块实现后紧跟属性测试和单元测试。

## Tasks

- [x] 1. 新增值对象、枚举和领域事件定义
  - [x] 1.1 创建 `src/strategy/domain/value_object/advanced_order.py`，定义 AdvancedOrderType、AdvancedOrderStatus 枚举，AdvancedOrderRequest、AdvancedOrder、ChildOrder、SliceEntry 数据类
    - 包含 `to_dict()` / `from_dict()` 序列化方法
    - _Requirements: 4.4, 4.5_
  - [x] 1.2 创建 `src/strategy/domain/value_object/hedging.py`，定义 HedgingConfig、HedgeResult、GammaScalpConfig、ScalpResult 数据类
    - _Requirements: 5.1, 5.2, 6.1_
  - [x] 1.3 创建 `src/strategy/domain/value_object/vol_surface.py`，定义 VolQuote、VolQueryResult、VolSmile、TermStructure、VolSurfaceSnapshot 数据类
    - VolSurfaceSnapshot 包含 `to_dict()` / `from_dict()` 序列化方法
    - _Requirements: 8.1, 8.4, 8.5_
  - [x] 1.4 扩展 `src/strategy/domain/event/event_types.py`，新增 IcebergCompleteEvent、IcebergCancelledEvent、TWAPCompleteEvent、VWAPCompleteEvent、HedgeExecutedEvent、GammaScalpEvent
    - _Requirements: 1.3, 1.4, 2.3, 3.3, 5.4, 6.3_
  - [x] 1.5 更新 `src/strategy/domain/value_object/__init__.py` 导出新增值对象
    - _Requirements: 4.4, 5.1, 8.1_

- [x] 2. 实现 AdvancedOrderScheduler
  - [x] 2.1 创建 `src/strategy/domain/domain_service/advanced_order_scheduler.py`，实现 submit_iceberg 方法
    - 拆分总量为子单，每个子单 volume <= batch_size，sum == total_volume
    - _Requirements: 1.1, 1.5_
  - [x] 2.2 编写冰山单拆分属性测试
    - **Property 1: 冰山单拆分正确性**
    - **Validates: Requirements 1.1, 1.5**
  - [x] 2.3 实现 submit_twap 方法
    - 均匀分配总量到时间片，计算 slice_schedule
    - _Requirements: 2.1, 2.4_
  - [x] 2.4 编写 TWAP 调度属性测试
    - **Property 3: TWAP 调度正确性**
    - **Validates: Requirements 2.1, 2.3, 2.4**
  - [x] 2.5 实现 submit_vwap 方法
    - 按 volume_profile 权重比例分配总量
    - _Requirements: 3.1, 3.2, 3.4_
  - [x] 2.6 编写 VWAP 分配属性测试
    - **Property 4: VWAP 分配正确性**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
  - [x] 2.7 实现 on_child_filled、get_pending_children、cancel_order 方法
    - on_child_filled: 更新 filled_volume，检查是否全部成交并产生完成事件
    - get_pending_children: 返回当前时刻应提交的子单 (冰山单: 前一批已成交; TWAP/VWAP: 到达调度时间)
    - cancel_order: 标记取消状态，返回未提交子单 ID 列表和取消事件
    - _Requirements: 1.2, 1.3, 1.4, 2.2, 3.3, 4.1, 4.2, 4.3_
  - [x] 2.8 编写冰山单生命周期属性测试
    - **Property 2: 冰山单生命周期**
    - **Validates: Requirements 1.2, 1.3, 1.4**
  - [x] 2.9 编写高级订单成交量追踪属性测试
    - **Property 5: 高级订单成交量追踪**
    - **Validates: Requirements 4.2, 4.3**
  - [x] 2.10 编写高级订单序列化 Round-Trip 属性测试
    - **Property 6: 高级订单序列化 Round-Trip**
    - **Validates: Requirements 4.4, 4.5**
  - [x] 2.11 编写 AdvancedOrderScheduler 单元测试
    - 冰山单具体拆分 (100 总量 / 30 每批 = 4 子单)
    - TWAP 具体时间片 (300 秒 / 5 片 = 60 秒间隔)
    - VWAP 具体分配 ([0.1, 0.3, 0.6] 分布)
    - 参数校验错误 (总量 <= 0, batch_size <= 0, num_slices <= 0, 空 volume_profile)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4_

- [x] 3. Checkpoint - 高级订单模块验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 实现 DeltaHedgingEngine
  - [x] 4.1 创建 `src/strategy/domain/domain_service/delta_hedging_engine.py`，实现 check_and_hedge 和 from_yaml_config 方法
    - check_and_hedge: 判断 |portfolio_delta - target_delta| > hedging_band，计算 hedge_volume = round((target_delta - portfolio_delta) / (hedge_instrument_delta * hedge_instrument_multiplier))，hedge_volume == 0 时不生成指令
    - from_yaml_config: 从字典创建实例，缺失字段使用 HedgingConfig 默认值
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.1, 7.3_
  - [x] 4.2 编写 Delta 对冲正确性属性测试
    - **Property 7: Delta 对冲正确性**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
  - [x] 4.3 编写 DeltaHedgingEngine 单元测试
    - 具体数值验证 (已知 Delta 偏离的对冲手数)
    - 无效配置 (multiplier <= 0, delta == 0)
    - from_yaml_config 默认值回退
    - _Requirements: 5.1, 5.2, 5.3, 7.1, 7.3_

- [x] 5. 实现 GammaScalpingEngine
  - [x] 5.1 创建 `src/strategy/domain/domain_service/gamma_scalping_engine.py`，实现 check_and_rebalance 和 from_yaml_config 方法
    - check_and_rebalance: gamma <= 0 时拒绝; |portfolio_delta| > rebalance_threshold 时计算再平衡手数使 delta 归零
    - from_yaml_config: 从字典创建实例，缺失字段使用 GammaScalpConfig 默认值
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.2, 7.4_
  - [x] 5.2 编写 Gamma Scalping 正确性属性测试
    - **Property 8: Gamma Scalping 正确性**
    - **Validates: Requirements 6.1, 6.3, 6.4**
  - [x] 5.3 编写 Gamma Scalping 负 Gamma 拒绝属性测试
    - **Property 9: Gamma Scalping 负 Gamma 拒绝**
    - **Validates: Requirements 6.2**
  - [x] 5.4 编写 GammaScalpingEngine 单元测试
    - 负 Gamma 拒绝
    - 具体再平衡数值验证
    - from_yaml_config 默认值回退
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.2, 7.4_

- [x] 6. Checkpoint - 对冲引擎模块验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 实现 VolSurfaceBuilder
  - [x] 7.1 创建 `src/strategy/domain/domain_service/vol_surface_builder.py`，实现 build_surface 方法
    - 从 VolQuote 列表构建 VolSurfaceSnapshot，过滤 implied_vol <= 0 的报价
    - strikes 和 expiries 升序排列，vol_matrix 维度 = len(expiries) x len(strikes)
    - _Requirements: 8.1_
  - [x] 7.2 编写波动率曲面构建正确性属性测试
    - **Property 10: 波动率曲面构建正确性**
    - **Validates: Requirements 8.1**
  - [x] 7.3 实现 query_vol 方法 (双线性插值)
    - 查询点在网格内时双线性插值，超出范围返回 VolQueryResult(success=False)
    - _Requirements: 8.2, 8.3_
  - [x] 7.4 编写波动率曲面插值有界性属性测试
    - **Property 11: 波动率曲面插值有界性**
    - **Validates: Requirements 8.2**
  - [x] 7.5 实现 extract_smile 方法
    - 提取指定 time_to_expiry 的波动率微笑，支持插值
    - _Requirements: 9.1, 9.2, 9.3_
  - [x] 7.6 编写波动率微笑提取属性测试
    - **Property 13: 波动率微笑提取正确性与排序**
    - **Validates: Requirements 9.1, 9.2, 9.3**
  - [x] 7.7 实现 extract_term_structure 方法
    - 提取指定 strike 的期限结构，支持插值
    - _Requirements: 10.1, 10.2, 10.3_
  - [x] 7.8 编写期限结构提取属性测试
    - **Property 14: 期限结构提取正确性与排序**
    - **Validates: Requirements 10.1, 10.2, 10.3**
  - [x] 7.9 编写波动率曲面序列化 Round-Trip 属性测试
    - **Property 12: 波动率曲面序列化 Round-Trip**
    - **Validates: Requirements 8.4, 8.5**
  - [x] 7.10 编写 VolSurfaceBuilder 单元测试
    - 边界查询 (超出范围返回错误)
    - 报价不足 (< 2 strikes 或 < 2 expiries)
    - 无效报价过滤 (implied_vol <= 0)
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 8. Checkpoint - 波动率曲面模块验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 配置集成与 StrategyEntry 编排
  - [x] 9.1 扩展 `config/strategy_config.yaml`，新增 hedging 和 advanced_orders 配置节
    - _Requirements: 7.1, 7.2_
  - [x] 9.2 扩展 `src/main/config/config_loader.py`，支持加载 hedging 和 advanced_orders 配置
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] 9.3 编写配置加载单元测试
    - 完整配置加载
    - 缺失字段默认值回退
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 10. Final checkpoint - 全模块集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks are required (comprehensive coverage from start)
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (hypothesis, min 100 iterations)
- Unit tests validate specific examples and edge cases
