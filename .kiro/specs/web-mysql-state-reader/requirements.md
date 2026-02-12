# Requirements Document

## Introduction

监控端 `src/web` 目前依赖 pickle 文件（`SnapshotReader`）读取策略状态，同时通过 `MySQLSnapshotReader` 从 `monitor_signal_snapshot` 表读取信号快照。策略端已完成从 pickle 到 MySQL JSON 的迁移，策略状态以 JSON 格式存储在 `strategy_state` 表中。

本特性的目标是让监控端直接从 `strategy_state` 表读取策略状态，完全移除对 pickle 文件的依赖。同时保留 `monitor_signal_snapshot` 表的 events 和 bars 功能。

## Glossary

- **Strategy_State_Reader**: 从 `strategy_state` 表读取策略状态 JSON 并转换为前端格式的组件
- **Strategy_State_Table**: MySQL 中的 `strategy_state` 表，包含 `strategy_name`、`snapshot_json`、`schema_version`、`saved_at` 字段
- **Snapshot_JSON**: `strategy_state` 表中存储的 JSON 快照，包含 `target_aggregate`、`position_aggregate`、`current_dt` 等字段
- **Frontend_Format**: 前端期望的 JSON 数据格式，包含 `timestamp`、`variant`、`instruments`、`positions`、`orders` 字段
- **Special_Type_Marker**: JSON 中的特殊类型标记，如 `__dataframe__`、`__datetime__`、`__enum__`、`__set__` 等
- **Monitor_Signal_Snapshot_Table**: MySQL 中的 `monitor_signal_snapshot` 表，用于存储信号快照和事件数据
- **Web_App**: Flask 应用 `src/web/app.py`，提供 API 接口供前端轮询获取数据
- **SnapshotReader**: 当前从 pickle 文件读取策略状态的组件（将被废弃）

## Requirements

### Requirement 1: 从 strategy_state 表读取策略列表

**User Story:** As a 监控端用户, I want to 在首页看到所有策略实例列表, so that I can 选择要查看的策略。

#### Acceptance Criteria

1. WHEN the Web_App requests the strategy list, THE Strategy_State_Reader SHALL query the `strategy_state` table and return all distinct `strategy_name` values with their latest `saved_at` timestamp
2. WHEN the `strategy_state` table contains no records, THE Strategy_State_Reader SHALL return an empty list
3. WHEN the database connection fails, THE Strategy_State_Reader SHALL return an empty list without raising an exception

### Requirement 2: 从 strategy_state 表读取策略快照并转换为前端格式

**User Story:** As a 监控端用户, I want to 查看策略的实时状态（K线、指标、持仓、挂单）, so that I can 监控策略运行情况。

#### Acceptance Criteria

1. WHEN a valid strategy name is provided, THE Strategy_State_Reader SHALL query the latest `snapshot_json` from the `strategy_state` table for that strategy
2. WHEN the Snapshot_JSON is retrieved, THE Strategy_State_Reader SHALL convert the `current_dt` field to the Frontend_Format `timestamp` string (format: `YYYY-MM-DD HH:MM:SS`)
3. WHEN the Snapshot_JSON is retrieved, THE Strategy_State_Reader SHALL map the `strategy_name` to the Frontend_Format `variant` field
4. WHEN the Snapshot_JSON contains no record for the requested strategy, THE Strategy_State_Reader SHALL return None
5. WHEN the Snapshot_JSON contains malformed JSON, THE Strategy_State_Reader SHALL return None without raising an exception

### Requirement 3: 转换标的数据（instruments）

**User Story:** As a 监控端用户, I want to 查看每个标的的K线图和指标数据, so that I can 分析市场走势。

#### Acceptance Criteria

1. WHEN the Snapshot_JSON contains `target_aggregate.instruments`, THE Strategy_State_Reader SHALL convert each instrument entry to the Frontend_Format instrument structure
2. WHEN an instrument's `bars` field contains a Special_Type_Marker `{"__dataframe__": true, "records": [...]}`, THE Strategy_State_Reader SHALL extract `dates` (datetime strings), `ohlc` (list of `[open, close, low, high]`), and `volumes` from the records
3. WHEN an instrument's `bars` records are empty, THE Strategy_State_Reader SHALL skip that instrument
4. WHEN an instrument contains an `indicators` field, THE Strategy_State_Reader SHALL include the indicators in the Frontend_Format output, resolving any Special_Type_Marker values (e.g., `__enum__`, `__datetime__`)
5. WHEN a `vt_symbol` is provided, THE Strategy_State_Reader SHALL extract the `delivery_month` using the existing extraction logic

### Requirement 4: 转换持仓和挂单数据

**User Story:** As a 监控端用户, I want to 查看当前持仓和挂单信息, so that I can 了解策略的交易状态。

#### Acceptance Criteria

1. WHEN the Snapshot_JSON contains `position_aggregate.positions`, THE Strategy_State_Reader SHALL convert the positions dictionary to a list of position objects with `vt_symbol`, `direction`, `volume`, `price`, `pnl` fields
2. WHEN the Snapshot_JSON contains `position_aggregate.pending_orders`, THE Strategy_State_Reader SHALL convert the pending orders dictionary to a list of order objects with `vt_orderid`, `vt_symbol`, `direction`, `offset`, `volume`, `price`, `status` fields
3. WHEN the positions dictionary is empty, THE Strategy_State_Reader SHALL return an empty positions list
4. WHEN the pending_orders dictionary is empty, THE Strategy_State_Reader SHALL return an empty orders list
5. WHEN position or order fields contain Special_Type_Marker values (e.g., `__enum__` for direction/offset/status), THE Strategy_State_Reader SHALL resolve the markers to their string representation

### Requirement 5: 处理 JSON 中的特殊类型标记

**User Story:** As a 开发者, I want to 正确解析 strategy_state 表中 JSON 的特殊类型标记, so that 数据能被准确转换为前端格式。

#### Acceptance Criteria

1. WHEN the JSON contains `{"__datetime__": "ISO 8601 string"}`, THE Strategy_State_Reader SHALL convert the value to a datetime string
2. WHEN the JSON contains `{"__enum__": "ClassName.VALUE"}`, THE Strategy_State_Reader SHALL convert the value to the string `"ClassName.VALUE"`
3. WHEN the JSON contains `{"__set__": true, "values": [...]}`, THE Strategy_State_Reader SHALL convert the value to a plain list
4. WHEN the JSON contains `{"__dataframe__": true, "records": [...]}`, THE Strategy_State_Reader SHALL convert the value to a list of record dictionaries
5. WHEN the JSON contains `{"__dataclass__": "module.ClassName", ...fields}`, THE Strategy_State_Reader SHALL convert the value to a plain dictionary of the fields
6. WHEN the JSON contains `{"__date__": "ISO 8601 date string"}`, THE Strategy_State_Reader SHALL convert the value to a date string

### Requirement 6: 更新 Web_App 数据源优先级

**User Story:** As a 监控端用户, I want to 从最可靠的数据源获取策略状态, so that 我看到的数据是最新的。

#### Acceptance Criteria

1. WHEN the Web_App initializes, THE Web_App SHALL create a Strategy_State_Reader instance configured with database connection parameters from environment variables
2. WHEN the Web_App requests strategy data, THE Web_App SHALL prioritize the Strategy_State_Reader (strategy_state table) as the primary data source
3. WHEN the Strategy_State_Reader returns no data, THE Web_App SHALL fall back to the Monitor_Signal_Snapshot_Table reader as secondary source
4. WHEN both data sources return no data, THE Web_App SHALL return an appropriate error response

### Requirement 7: 废弃 pickle 依赖

**User Story:** As a 开发者, I want to 移除对 pickle 文件的依赖, so that 系统架构更简洁且不依赖文件系统。

#### Acceptance Criteria

1. WHEN the migration is complete, THE Web_App SHALL remove the SnapshotReader import and instantiation
2. WHEN the migration is complete, THE Web_App SHALL remove the pickle-based fallback logic from `list_strategies_best_effort` and `get_snapshot_best_effort`
3. WHEN the migration is complete, THE Web_App SHALL retain the Monitor_Signal_Snapshot_Table reader for events and bars API endpoints

### Requirement 8: 保留 monitor_signal_snapshot 功能

**User Story:** As a 监控端用户, I want to 继续使用事件查询和K线查询功能, so that 我可以查看历史信号事件和K线数据。

#### Acceptance Criteria

1. WHILE the events API endpoint is active, THE Web_App SHALL continue using the Monitor_Signal_Snapshot_Table reader for event queries
2. WHILE the bars API endpoint is active, THE Web_App SHALL continue using the Monitor_Signal_Snapshot_Table reader for bar data queries
3. WHILE the WebSocket polling is active, THE Web_App SHALL use the Strategy_State_Reader for snapshot updates instead of the Monitor_Signal_Snapshot_Table reader
