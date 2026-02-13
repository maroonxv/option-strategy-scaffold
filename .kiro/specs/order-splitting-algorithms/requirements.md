# 需求文档：订单拆分算法

## 简介

本功能为期权量化交易策略框架新增三种算法订单拆分类型：定时拆单、经典冰山单和增强型 TWAP（时间加权平均价交易）。这三种算法用于将大单委托拆分为多笔小单，以降低市场冲击、隐匿交易踪迹，并在指定时间范围内实现更优的成交均价。功能需与现有的 `AdvancedOrderScheduler`、`AdvancedOrder` 值对象和领域事件体系集成。

## 术语表

- **OrderSplittingScheduler**: 订单拆分调度器，负责管理三种拆分算法的子单生命周期
- **ChildOrder**: 子单，由拆分算法生成的单笔委托
- **SliceEntry**: 时间片条目，记录子单的计划提交时间和数量
- **OrderInstruction**: 交易指令值对象，包含合约代码、方向、开平、数量、价格等信息
- **定时拆单（TimedSplit）**: 按固定时间间隔提交等量子单的拆分算法
- **经典冰山单（ClassicIceberg）**: 按指定单笔数量拆单，前一笔成交后才提交下一笔的拆分算法
- **TWAP**: 时间加权平均价交易，在指定总时长内均匀分配子单，使成交均价接近时间加权平均价
- **interval_seconds**: 定时拆单中每笔子单之间的固定时间间隔（秒）
- **per_order_volume**: 经典冰山单中每笔子单的指定数量
- **volume_randomize_ratio**: 经典冰山单中子单数量的随机浮动比例（如 0.2 表示 ±20%）
- **price_offset_ticks**: 经典冰山单中子单价格相对于基准价的偏移跳数
- **time_window_seconds**: TWAP 算法的总执行时长（秒）
- **num_slices**: TWAP 算法的分片数量

## 需求

### 需求 1：定时拆单

**用户故事：** 作为交易员，我希望将大单委托按照指定时间间隔自动拆分提交，以便分散成交时间、降低市场冲击。

#### 验收标准

1. WHEN 交易员提交定时拆单请求（包含 OrderInstruction、interval_seconds、per_order_volume）THEN OrderSplittingScheduler SHALL 将总量拆分为多笔子单，每笔子单数量等于 per_order_volume（最后一笔为剩余量）
2. WHEN 定时拆单生成子单 THEN OrderSplittingScheduler SHALL 为每笔子单分配计划提交时间，第 i 笔子单的计划时间为 start_time + i × interval_seconds
3. WHEN 当前时间到达某笔子单的计划提交时间 THEN OrderSplittingScheduler SHALL 将该子单标记为可提交状态
4. WHEN 所有子单均已成交 THEN OrderSplittingScheduler SHALL 将父订单状态更新为 COMPLETED 并发布 TimedSplitCompleteEvent
5. IF 定时拆单请求的总量小于等于 0 或 interval_seconds 小于等于 0 或 per_order_volume 小于等于 0 THEN OrderSplittingScheduler SHALL 拒绝请求并抛出 ValueError

### 需求 2：经典冰山单

**用户故事：** 作为交易员，我希望将大单委托按指定单笔数量拆分，前一笔成交后才提交下一笔，以便隐匿交易踪迹、只露冰山一角。

#### 验收标准

1. WHEN 交易员提交经典冰山单请求（包含 OrderInstruction、per_order_volume）THEN OrderSplittingScheduler SHALL 将总量拆分为多笔子单，每笔子单基础数量等于 per_order_volume（最后一笔为剩余量）
2. WHERE 经典冰山单配置了 volume_randomize_ratio THEN OrderSplittingScheduler SHALL 对每笔子单数量在 per_order_volume × (1 ± volume_randomize_ratio) 范围内随机浮动，且保证总量精确等于原始委托总量
3. WHERE 经典冰山单配置了 price_offset_ticks 和 price_tick THEN OrderSplittingScheduler SHALL 对每笔子单价格在基准价 ± price_offset_ticks × price_tick 范围内随机偏移
4. WHEN 查询可提交子单时 THEN OrderSplittingScheduler SHALL 仅在前一笔子单已成交的情况下返回下一笔子单
5. WHEN 所有子单均已成交 THEN OrderSplittingScheduler SHALL 将父订单状态更新为 COMPLETED 并发布 ClassicIcebergCompleteEvent
6. WHEN 经典冰山单被取消 THEN OrderSplittingScheduler SHALL 将父订单状态更新为 CANCELLED，返回需撤销的已提交未成交子单 ID 列表，并发布 ClassicIcebergCancelledEvent
7. IF 经典冰山单请求的总量小于等于 0 或 per_order_volume 小于等于 0 THEN OrderSplittingScheduler SHALL 拒绝请求并抛出 ValueError
8. IF volume_randomize_ratio 小于 0 或大于等于 1 THEN OrderSplittingScheduler SHALL 拒绝请求并抛出 ValueError

### 需求 3：增强型 TWAP

**用户故事：** 作为交易员，我希望在指定时间段内将大单委托均匀拆分成交，使成交均价接近该时间段的时间加权平均价。

#### 验收标准

1. WHEN 交易员提交 TWAP 请求（包含 OrderInstruction、time_window_seconds、num_slices、start_time）THEN OrderSplittingScheduler SHALL 将总量均匀分配到 num_slices 个时间片，各片数量差异不超过 1
2. WHEN TWAP 生成子单 THEN OrderSplittingScheduler SHALL 为每个时间片分配计划提交时间，间隔为 time_window_seconds / num_slices
3. WHEN 当前时间到达某个时间片的计划提交时间 THEN OrderSplittingScheduler SHALL 将该时间片对应的子单标记为可提交状态
4. WHEN 所有子单均已成交 THEN OrderSplittingScheduler SHALL 将父订单状态更新为 COMPLETED 并发布 EnhancedTWAPCompleteEvent
5. WHEN TWAP 订单被取消 THEN OrderSplittingScheduler SHALL 将父订单状态更新为 CANCELLED，返回需撤销的已提交未成交子单 ID 列表
6. IF TWAP 请求的总量小于等于 0 或 time_window_seconds 小于等于 0 或 num_slices 小于等于 0 THEN OrderSplittingScheduler SHALL 拒绝请求并抛出 ValueError

### 需求 4：子单生命周期管理

**用户故事：** 作为交易员，我希望系统能统一追踪所有拆分算法的子单状态，以便实时了解订单执行进度。

#### 验收标准

1. WHEN 子单成交回报到达 THEN OrderSplittingScheduler SHALL 更新该子单的 is_filled 状态并累加父订单的 filled_volume
2. THE OrderSplittingScheduler SHALL 保证 filled_volume 始终等于所有已成交子单的 volume 之和
3. WHEN 查询订单状态 THEN OrderSplittingScheduler SHALL 返回包含所有子单详情的 AdvancedOrder 对象

### 需求 5：序列化与反序列化

**用户故事：** 作为开发者，我希望新增的订单类型支持序列化和反序列化，以便持久化存储和状态恢复。

#### 验收标准

1. THE AdvancedOrder SHALL 支持将定时拆单、经典冰山单、增强型 TWAP 三种类型的订单序列化为字典（JSON 兼容格式）
2. THE AdvancedOrder SHALL 支持从字典反序列化恢复为等价的 AdvancedOrder 对象
3. FOR ALL 有效的 AdvancedOrder 对象，序列化后再反序列化 SHALL 产生与原始对象等价的结果（round-trip 属性）
