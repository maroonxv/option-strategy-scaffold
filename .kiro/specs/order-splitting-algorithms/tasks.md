# 实现计划：订单拆分算法

## 概述

基于现有 `AdvancedOrderScheduler` 和 `AdvancedOrder` 体系，新增定时拆单、经典冰山单和增强型 TWAP 三种拆分算法。采用增量实现方式，每步构建在前一步基础上，最终集成到统一的调度器中。

## 任务

- [x] 1. 扩展值对象和领域事件
  - [x] 1.1 扩展 AdvancedOrderType 枚举和 AdvancedOrderRequest 数据类
    - 在 `src/strategy/domain/value_object/advanced_order.py` 中新增 `TIMED_SPLIT`、`CLASSIC_ICEBERG`、`ENHANCED_TWAP` 枚举值
    - 在 `AdvancedOrderRequest` 中新增 `interval_seconds`、`per_order_volume`、`volume_randomize_ratio`、`price_offset_ticks`、`price_tick` 字段
    - 在 `ChildOrder` 中新增 `price_offset: float = 0.0` 字段
    - _Requirements: 1.1, 2.1, 2.3, 3.1_
  - [x] 1.2 更新 AdvancedOrder 的 to_dict/from_dict 以支持新字段
    - 在 `to_dict` 中序列化新增的 `AdvancedOrderRequest` 字段和 `ChildOrder.price_offset`
    - 在 `from_dict` 中反序列化新增字段
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 1.3 新增领域事件类型
    - 在 `src/strategy/domain/event/event_types.py` 中新增 `TimedSplitCompleteEvent`、`ClassicIcebergCompleteEvent`、`ClassicIcebergCancelledEvent`、`EnhancedTWAPCompleteEvent`
    - _Requirements: 1.4, 2.5, 2.6, 3.4_

- [-] 2. 实现定时拆单算法
  - [x] 2.1 实现 submit_timed_split 方法
    - 在 `AdvancedOrderScheduler` 中新增 `submit_timed_split(instruction, interval_seconds, per_order_volume, start_time)` 方法
    - 实现参数校验、子单拆分和时间调度逻辑
    - _Requirements: 1.1, 1.2, 1.5_
  - [x] 2.2 扩展 get_pending_children 支持 TIMED_SPLIT 类型
    - 在 `get_pending_children` 中新增 `TIMED_SPLIT` 分支：按 scheduled_time 提交
    - _Requirements: 1.3_
  - [-] 2.3 扩展 on_child_filled 支持 TIMED_SPLIT 完成事件
    - 在 `on_child_filled` 中新增 `TIMED_SPLIT` 分支：全部成交时发布 `TimedSplitCompleteEvent`
    - _Requirements: 1.4_
  - [~] 2.4 编写定时拆单属性测试
    - **Property 1: 定时拆单拆分正确性**
    - **Validates: Requirements 1.1, 1.2**

- [ ] 3. 实现经典冰山单算法
  - [~] 3.1 实现 submit_classic_iceberg 方法
    - 在 `AdvancedOrderScheduler` 中新增 `submit_classic_iceberg(instruction, per_order_volume, volume_randomize_ratio, price_offset_ticks, price_tick)` 方法
    - 实现参数校验、子单拆分（含随机化）和价格偏移逻辑
    - 确保随机化后总量精确等于原始委托总量
    - _Requirements: 2.1, 2.2, 2.3, 2.7, 2.8_
  - [~] 3.2 扩展 get_pending_children 支持 CLASSIC_ICEBERG 类型
    - 在 `get_pending_children` 中新增 `CLASSIC_ICEBERG` 分支：前一笔成交后才提交下一笔
    - _Requirements: 2.4_
  - [~] 3.3 扩展 on_child_filled 和 cancel_order 支持经典冰山单事件
    - 在 `on_child_filled` 中新增 `CLASSIC_ICEBERG` 分支：全部成交时发布 `ClassicIcebergCompleteEvent`
    - 在 `cancel_order` 中新增 `CLASSIC_ICEBERG` 分支：发布 `ClassicIcebergCancelledEvent`
    - _Requirements: 2.5, 2.6_
  - [~] 3.4 编写经典冰山单属性测试
    - **Property 2: 经典冰山单拆分正确性（含随机化不变量）**
    - **Property 3: 经典冰山单价格偏移范围**
    - **Property 4: 经典冰山单生命周期——顺序执行与完成**
    - **Property 5: 经典冰山单取消正确性**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

- [~] 4. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请向用户确认。

- [ ] 5. 实现增强型 TWAP 算法
  - [~] 5.1 实现 submit_enhanced_twap 方法
    - 在 `AdvancedOrderScheduler` 中新增 `submit_enhanced_twap(instruction, time_window_seconds, num_slices, start_time)` 方法
    - 实现参数校验、均匀分配和时间调度逻辑
    - _Requirements: 3.1, 3.2, 3.6_
  - [~] 5.2 扩展 get_pending_children 支持 ENHANCED_TWAP 类型
    - 在 `get_pending_children` 中新增 `ENHANCED_TWAP` 分支：按 scheduled_time 提交
    - _Requirements: 3.3_
  - [~] 5.3 扩展 on_child_filled 和 cancel_order 支持增强型 TWAP 事件
    - 在 `on_child_filled` 中新增 `ENHANCED_TWAP` 分支：全部成交时发布 `EnhancedTWAPCompleteEvent`
    - 在 `cancel_order` 中扩展取消逻辑
    - _Requirements: 3.4, 3.5_
  - [~] 5.4 编写增强型 TWAP 属性测试
    - **Property 6: 增强型 TWAP 拆分正确性**
    - **Validates: Requirements 3.1, 3.2**

- [ ] 6. 实现跨算法通用测试
  - [~] 6.1 编写成交量追踪不变量属性测试
    - **Property 7: 成交量追踪不变量**
    - **Validates: Requirements 4.1, 4.2**
  - [~] 6.2 编写序列化 Round-Trip 属性测试
    - **Property 8: 序列化 Round-Trip**
    - **Validates: Requirements 5.1, 5.2, 5.3**
  - [~] 6.3 编写无效参数拒绝属性测试
    - **Property 9: 无效参数拒绝**
    - **Validates: Requirements 1.5, 2.7, 2.8, 3.6**

- [~] 7. Final Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请向用户确认。

## 备注

- 标记 `*` 的子任务为可选测试任务，可跳过以加速 MVP
- 每个任务引用具体需求以确保可追溯性
- 属性测试使用 hypothesis 库，每个测试至少 100 次迭代
- 单元测试聚焦于具体示例和边界情况
