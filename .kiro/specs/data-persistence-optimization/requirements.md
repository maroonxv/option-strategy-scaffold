# 需求文档：数据持久化方案优化

## 简介

当前期权策略框架的数据持久化方案基于 PostgreSQL JSON 存储，通过 `StateRepository` 保存策略状态快照，`AutoSaveService` 提供周期性自动保存，`JsonSerializer` 处理序列化/反序列化，`MigrationChain` 支持 schema 版本迁移。

经过代码分析，发现以下优化空间：

1. 每次保存都序列化完整状态快照，缺少增量/差异保存机制，对大状态对象造成不必要的序列化和存储开销
2. `CombinationAggregate` 未纳入持久化快照，策略重启后组合状态丢失
3. 数据库保存操作为同步阻塞，在 `on_bars` 热路径上可能影响策略执行延迟
4. 大 JSON 快照未压缩，占用数据库存储空间
5. 仅依赖 PostgreSQL 单一存储，缺少高可用或容灾机制
6. 旧快照清理 (`cleanup`) 未自动触发，历史记录持续增长
7. 状态未变化时仍重复保存相同快照，浪费 I/O 和存储
8. 监控快照使用 pickle 格式，与主持久化层的 JSON 格式不一致

本优化旨在提升持久化层的性能、可靠性和完整性。

## 术语表

- **State_Repository**: 策略状态仓库，负责将策略状态快照保存到 PostgreSQL `strategy_state` 表并从中加载
- **Auto_Save_Service**: 周期性自动保存服务，在 `on_bars` 回调中按时间间隔触发保存
- **Json_Serializer**: JSON 序列化器，支持 DataFrame、datetime、Enum、dataclass 等特殊类型的序列化与反序列化
- **Migration_Chain**: Schema 版本迁移链，支持从低版本依次升级到高版本
- **Strategy_Entry**: 策略入口类，协调领域服务和基础设施组件的生命周期
- **Snapshot**: 策略状态快照，包含 `target_aggregate`、`position_aggregate` 等聚合根的序列化数据
- **Combination_Aggregate**: 组合策略聚合根，管理期权组合的注册、查询和状态同步
- **Database_Factory**: 统一数据库连接工厂（单例），管理 VnPy 数据库实例和 Peewee 连接
- **Digest**: 快照内容的哈希摘要，用于检测状态是否发生变化

## 需求

### 需求 1：组合聚合根持久化补全

**用户故事：** 作为策略运维人员，我希望 CombinationAggregate 的状态也被持久化，以便策略重启后组合策略状态不会丢失。

#### 验收标准

1. WHEN Strategy_Entry 创建快照时，THE Strategy_Entry SHALL 将 Combination_Aggregate 的状态包含在 Snapshot 中
2. WHEN Strategy_Entry 从 Snapshot 恢复状态时，THE Strategy_Entry SHALL 恢复 Combination_Aggregate 的状态
3. WHEN Snapshot 中不包含 `combination_aggregate` 字段时（兼容旧版本），THE Strategy_Entry SHALL 创建空的 Combination_Aggregate 实例
4. THE Json_Serializer SHALL 正确序列化和反序列化 Combination_Aggregate 的快照数据（包含 combinations 字典和 symbol_index）
5. FOR ALL 有效的 Combination_Aggregate 快照数据，序列化后反序列化 SHALL 产生等价的对象（往返一致性）

### 需求 2：快照变更检测与去重

**用户故事：** 作为策略运维人员，我希望系统在状态未变化时跳过保存操作，以减少不必要的数据库写入和存储消耗。

#### 验收标准

1. WHEN Auto_Save_Service 触发保存时，THE Auto_Save_Service SHALL 计算当前 Snapshot 的 Digest
2. WHEN 当前 Snapshot 的 Digest 与上次成功保存的 Digest 相同时，THE Auto_Save_Service SHALL 跳过本次保存操作
3. WHEN 当前 Snapshot 的 Digest 与上次成功保存的 Digest 不同时，THE Auto_Save_Service SHALL 执行保存操作并更新已保存的 Digest
4. WHEN force_save 被调用时（如 on_stop），THE Auto_Save_Service SHALL 无条件执行保存操作，忽略 Digest 比较
5. THE Digest 计算 SHALL 使用确定性的序列化输出（排序键、稳定的浮点表示）以保证相同状态产生相同的 Digest

### 需求 3：快照压缩

**用户故事：** 作为策略运维人员，我希望大体积的 JSON 快照在存储前被压缩，以减少数据库存储空间占用。

#### 验收标准

1. WHEN Json_Serializer 序列化的 JSON 字符串长度超过可配置阈值（默认 10KB）时，THE State_Repository SHALL 使用 zlib 压缩后存储
2. WHEN State_Repository 加载快照时，THE State_Repository SHALL 自动检测数据是否为压缩格式并正确解压
3. THE State_Repository SHALL 在 `strategy_state` 表记录中标记压缩状态（通过 `compressed` 字段或数据前缀标识）
4. WHEN 压缩后的数据大小不小于原始数据时，THE State_Repository SHALL 存储未压缩的原始数据
5. FOR ALL 有效的 Snapshot 数据，压缩后解压 SHALL 产生与原始数据完全一致的 JSON 字符串（往返一致性）

### 需求 4：自动清理旧快照

**用户故事：** 作为策略运维人员，我希望系统自动清理过期的历史快照，以防止数据库存储无限增长。

#### 验收标准

1. WHEN Auto_Save_Service 成功保存一个新快照后，THE Auto_Save_Service SHALL 检查是否需要触发清理操作
2. THE Auto_Save_Service SHALL 按可配置的频率（默认每 24 小时一次）触发清理操作，避免每次保存都执行清理
3. WHEN 触发清理操作时，THE State_Repository SHALL 删除 `saved_at` 早于可配置保留天数（默认 7 天）的历史快照
4. THE State_Repository SHALL 保留至少一条最新的快照记录，即使该记录已超过保留天数
5. IF 清理操作执行失败，THEN THE Auto_Save_Service SHALL 记录错误日志并继续正常运行，不影响策略执行

### 需求 5：异步保存机制

**用户故事：** 作为策略开发者，我希望状态保存操作不阻塞 `on_bars` 回调的执行，以降低策略执行延迟。

#### 验收标准

1. WHEN Auto_Save_Service 决定执行保存时，THE Auto_Save_Service SHALL 在后台线程中执行序列化和数据库写入操作
2. THE Auto_Save_Service SHALL 使用单线程执行器（ThreadPoolExecutor(max_workers=1)）保证保存操作的顺序性
3. WHEN 上一次异步保存尚未完成时，THE Auto_Save_Service SHALL 跳过本次保存请求并记录调试日志
4. WHEN force_save 被调用时（如 on_stop），THE Auto_Save_Service SHALL 等待当前异步保存完成后再执行最终保存，确保数据不丢失
5. IF 异步保存操作抛出异常，THEN THE Auto_Save_Service SHALL 在后台线程中记录错误日志，不影响策略主线程

### 需求 6：Json_Serializer 往返一致性保障

**用户故事：** 作为策略开发者，我希望序列化和反序列化过程是严格可逆的，以确保持久化数据的完整性。

#### 验收标准

1. FOR ALL 包含 DataFrame、datetime、date、set、Enum、dataclass 类型的有效 Snapshot 数据，THE Json_Serializer 的 serialize 后 deserialize SHALL 产生与原始数据等价的结果
2. THE Json_Serializer SHALL 使用 `sort_keys=True` 参数确保序列化输出的确定性
3. WHEN 反序列化遇到无法还原的 Enum 引用时，THE Json_Serializer SHALL 保留原始字符串值而非抛出异常
4. WHEN 反序列化遇到无法还原的 dataclass 引用时，THE Json_Serializer SHALL 保留原始字典而非抛出异常
5. THE Json_Serializer 的 serialize 方法 SHALL 产生合法的 JSON 字符串（可被 `json.loads` 解析）
