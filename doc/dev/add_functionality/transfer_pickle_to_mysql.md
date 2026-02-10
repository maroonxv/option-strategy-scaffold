# transfer_pickle_to_mysql：用 MySQL K 线重建行情信号状态，瘦身 Pickle

## 1. 背景与目标

### 1.1 背景问题
- 当前策略在实盘/模拟盘会把运行态通过 Pickle 保存到 `data/pickle/{strategy_name}.pkl`，用于下次启动恢复。
- 该 Pickle 会无限膨胀，根因是其中包含行情 DataFrame（bars）并持续追加，导致文件越来越大、写入越来越慢、甚至阻塞退出。

### 1.2 目标
- **把“基于行情可重建的状态”从 Pickle 中移除**，启动时改为用 **MySQL 中保存的 K 线数据 replay** 恢复信号状态。
- **仅对“无法由 K 线可靠重建的状态”继续使用 Pickle 保存**，并确保 Pickle 体积长期稳定（常数级或近似常数级）。
- 恢复过程要与当前实盘计算路径一致（尤其是 15m/30m 由 1m 合成的场景），避免信号偏差。

### 1.3 非目标（明确不做）
- 不在本次方案中改变交易逻辑、指标公式、信号定义。
- 不把持仓/订单状态迁移到数据库（仍走现有接口推送 + Pickle）。

---

## 2. 现状梳理（当前保存/恢复机制）

### 2.1 保存/恢复入口
- 实盘/模拟盘启动：
  - `StrategyEntry.on_init` 会优先尝试从 `data/pickle/{strategy_name}.pkl` 恢复（成功则跳过历史数据加载，失败才 warmup）。
  - 停止时 `on_stop` 会保存到同一路径。

### 2.2 被 Pickle 保存的内容（核心问题点）
当前 `VolatilityTrade.dump_state/load_state` 存储的 state 包含：
- `target_aggregate`：内部持有 `TargetInstrument.bars`（pandas DataFrame），会持续 append。
- `position_aggregate`：持仓、pending_orders、managed_symbols 等。
- `_macd_history`、`_dullness_states`、`_divergence_states`
- `daily_open_count_map/global_daily_open_count/last_trading_date`

其中 `target_aggregate` 的 bars DataFrame 是 Pickle 膨胀的主要来源。

### 2.3 信号计算依赖与“可重建性”结论
- 指标列（dif/dea/macd/td/ema）由 `IndicatorService.calculate_all` 基于 bars 计算并回写到 DataFrame。
- 钝化/背离状态由 `SignalService.check_dullness/check_divergence` 基于 bars + `_macd_history` + 前态计算。
- 因此：**只要能从 MySQL 恢复出与实盘一致的 bars 序列（含合成周期一致），则行情相关信号状态可以完全重建**。

---

## 3. 设计总览（“状态拆分 + 两段式恢复”）

### 3.1 状态拆分（哪些用 MySQL 重建，哪些继续 Pickle）

#### A. 由 MySQL K 线 replay 重建（不再 Pickle）
- 行情容器与序列：
  - `TargetInstrumentAggregate` 及其内部 `TargetInstrument.bars`
- 行情派生状态（信号中间态/快照）：
  - `_macd_history`（仅为加速/辅助，replay 后可自然生成）
  - `_dullness_states`、`_divergence_states`
  - 每个 instrument 当前快照：`macd_value/td_value/ema_state/dullness_state/divergence_state`

#### B. 继续用 Pickle 保存（瘦身后体积稳定）
- `PositionAggregate`（持仓、pending orders、managed_symbols）
- 日内限额相关：
  - `daily_open_count_map`
  - `global_daily_open_count`
  - `last_trading_date`
- Universe 快照（强烈建议保存，以保证 warmup 时 bar 不被过滤）：
  - `product -> active_vt_symbol` 映射（即 `target_aggregate._active_contracts` 的等价数据）

> 关键原因：`handle_bars` 会过滤非 active 合约；如果启动后未及时完成 universe validation，warmup/replay 可能全部被跳过，导致信号状态无法建立。

### 3.2 两段式恢复流程（建议实现为统一的“恢复管线”）

1) **Phase 0：进入恢复模式（冻结交易/下单/告警）**
- replay 阶段必须保证不会触发 `_check_and_execute_open/_check_and_execute_close`。
- 实现思路：
  - 恢复期间强制 `strategy_context.trading = False`（恢复完成后再恢复原值）。
  - 或在应用层增加 `self.restoring` 开关，恢复阶段直接跳过交易分支。

2) **Phase 1：从瘦身 Pickle 恢复“非行情状态”**
- 读取并恢复：
  - `PositionAggregate`
  - 日内限额状态
  - `active_contracts` 映射（product->vt_symbol）
- 如果 `active_contracts` 缺失或为空：
  - 调用一次 universe validation 选出主力并订阅，然后把映射写回瘦身 Pickle（下次启动即可直接 warmup）。

3) **Phase 2：从 MySQL 拉取 K 线并 replay，重建行情信号状态**
- 对每个 active vt_symbol 拉取足够长的历史 bars（见 4.2 的窗口长度建议）。
- 以与实盘一致的路径将 bars 注入策略计算链路（见 4.3）。

4) **Phase 3：退出恢复模式，进入正常交易**
- replay 完成后恢复 `trading` 标志；
- 再执行一次 universe validation（补漏/重新订阅），进入实时行情驱动。

---

## 4. MySQL K 线加载与 replay 细化

### 4.1 数据源：复用 VnPy 的 MySQL 数据库接口
仓库已有用于排查的脚本表明使用方式为：
- `vnpy.trader.database.get_database().load_bar_data(...)`
- MySQL 表通常是 `dbbardata`（脚本里也有直接 SQL 的检查逻辑）

建议在策略侧不要直接写 SQL（避免表结构耦合），优先复用 VnPy DatabaseManager：
- 优点：兼容 vnpy_mysql 的表结构与字段映射、支持 Interval 枚举、统一返回 BarData。
- 配置注入方式：通过 VnPy `SETTINGS["database.*"]` 或环境变量注入（见 debug_db 的写法）。

### 4.2 warmup 长度（必须覆盖背离/钝化的结构需求）
当前信号计算使用了以下窗口：
- 指标计算最低需求：至少 30 根 bars（策略内也检查）
- 背离检测：
  - 函数门槛：bars 与 macd_history 至少 20
  - 峰值检测需要结构稳定；策略当前每次取 `instrument.get_bar_history(500)` 作为“视野”

建议 warmup 目标：
- **至少 600 根“窗口后 bars”**（比 500 多留冗余，避免开头边界效应）
- 若策略运行周期为 1m：直接拉取 600 根 1m bars 即可。
- 若策略运行周期为 15m/30m（由 1m 合成）：
  - 目标是 600 根 15m/30m bars
  - MySQL 侧需拉取至少 `600 * bar_window` 根 1m bars（并留少量冗余）

### 4.3 replay 必须走“与实盘一致的合成链路”
实盘路径是：Tick/Bar -> `PortfolioBarGenerator` -> `on_window_bars` -> `app_service.handle_bars` -> `handle_bar_update`

因此恢复 replay 建议也遵循：
- 若 `bar_window == 1`：可直接把 1m bars 组装成 `{vt_symbol: BarData}` 逐条推给 `app_service.handle_bars`。
- 若 `bar_window > 1`：应将 1m bars 逐条推给 `pbg.update_bars`，让 pbg 产生窗口 bars 再进入 app_service，保证合成逻辑一致。

### 4.4 replay 过程的排序与对齐
必须确保：
- 单个 vt_symbol 内 bars 严格按 datetime 升序。
- 多 vt_symbol replay 时建议按“时间轴”对齐推进：
  - 把每个 vt_symbol 的 bars 先拉出来
  - 用多路归并（按 datetime）逐时刻把同一时刻的 bars 打包成 dict 推给 `handle_bars`
  - 这样更接近实盘“同一时刻多合约同时到达”的行为，且便于合成器按时间推进

---

## 5. Pickle 瘦身格式设计

### 5.1 新的 state schema（建议版本化）
建议使用新的文件名与版本字段，避免旧大文件继续被读写：
- 文件：`data/pickle/{strategy_name}.state.pkl`（示例）
- 内容字段（建议）：
  - `version`: 2
  - `saved_at`: datetime
  - `active_contracts`: Dict[product, vt_symbol]
  - `position_aggregate`: PositionAggregate
  - `daily_open_count_map`, `global_daily_open_count`, `last_trading_date`

不再保存：
- `target_aggregate`
- `macd_history/dullness/divergence`
- 监控 snapshot 中也不要再序列化包含 bars 的对象（见 8.2）

### 5.2 旧 state 兼容迁移（平滑过渡）
启动时若发现旧 `{strategy_name}.pkl`：
- 只提取其中“非行情状态”字段写入新 `.state.pkl`
- 行情派生字段全部丢弃（由 MySQL replay 重建）
- 旧文件保留作为备份，但后续不再写入，避免再次膨胀

---

## 6. 实现结构建议（便于直接落代码）

### 6.1 推荐新增/调整的逻辑入口
- 在 `StrategyEntry.on_init` 的“状态处理”分支中，将逻辑从：
  - “尝试 load_state -> 成功跳过历史数据加载”
  - 改成：
    1) 读取瘦身 state（若存在）
    2) 再做 MySQL warmup replay（无论 state 是否存在，都执行；只是 warmup 的 active_contracts 来源不同）

### 6.2 建议抽象的内部方法（伪代码）

#### (1) 读取瘦身 state
```text
load_non_market_state(path):
  if not exists(path): return EmptyState
  state = pickle.load(path)
  restore position_aggregate
  restore daily limits
  restore active_contracts
  return state
```

#### (2) 确定需要 warmup 的 active vt_symbols
```text
resolve_active_contracts(state):
  if state.active_contracts not empty:
    apply into app_service.target_aggregate active map
    return list(state.active_contracts.values())
  else:
    app_service.handle_universe_validation()
    read back from target_aggregate active map
    persist into state (for next run)
    return active vt_symbols
```

#### (3) 从 MySQL 加载 bars（以 1m 为基础）
```text
load_mysql_1m_bars(vt_symbol, start_dt, end_dt):
  parse vt_symbol -> (symbol, exchange)
  db = get_database()
  bars = db.load_bar_data(symbol, exchange, Interval.MINUTE, start, end)
  sort by datetime asc
  return bars
```

#### (4) replay（支持 bar_window 合成）
```text
replay_bars(active_symbols, warmup_target_window_bars):
  set trading = False
  for each symbol:
    bars_1m = load enough 1m bars
  if bar_window == 1:
    merge by datetime, at each dt:
      push dict{vt_symbol: bar} into app_service.handle_bars
  else:
    merge by datetime, at each dt:
      push dict{vt_symbol: bar} into pbg.update_bars
      (pbg will call on_window_bars -> app_service.handle_bars)
  set trading back to original
```

### 6.3 时间范围选择策略（start_dt/end_dt）
建议用 end_dt = 当前时刻（或最新一根 bar 的时间），start_dt 由目标根数倒推：
- 如果 MySQL 可以按时间范围查询，倒推的粗略策略：
  - 1m：`start_dt = now - (warmup_bars_count + buffer) minutes`
  - 15m：`start_dt = now - (warmup_window_bars*15 + buffer) minutes`
- 更稳妥策略（推荐）：先按较长时间段拉取（比如最近 N 天），再在内存截取最后需要的根数。

---

## 7. 风险点与规避策略

### 7.1 数据缺口/停盘导致根数不足
风险：MySQL 数据不连续、缺少部分交易日，导致 bars 根数达不到背离检测需要的结构。
规避：
- warmup 目标按“根数”而不是“天数”，不足则扩大回溯窗口（例如倍增天数或分钟数）。
- 若最终仍不足：降级为“仅建立基础指标，不启用背离/钝化交易”（恢复模式下可打告警，但不要交易）。

### 7.2 vt_symbol 与 MySQL symbol/exchange 映射不一致
风险：VnPy DB API 通常用 (symbol, exchange, interval) 查询；vt_symbol 是 `symbol.exchange`。
规避：
- 统一用 vt_symbol split 得到 symbol + exchange 枚举；
- 对于特殊交易所字符串，提供映射表或兜底处理（记录错误并跳过该合约）。

### 7.3 active_contracts 为空导致 warmup 被过滤
风险：`handle_bars` 会过滤非 active 合约，warmup 时如果 active 未提前写入，会导致 replay 无效。
规避：
- Phase 1 必须先把 active_contracts 写入 app_service.target_aggregate；
- 如无则先做 validation 得到 active，再 warmup。

### 7.4 恢复期间误触发下单
规避：
- 恢复期间强制 `trading=False`；
- 或在应用层恢复开关下跳过交易分支。

---

## 8. 额外优化建议（与本迁移强相关）

### 8.1 `_macd_history` 是否还需要保留
replay 后 `_macd_history` 可以自然生成，但它当前只保留最近 100 条（内存常量级）。
建议保留在内存，但不再 pickle。

### 8.2 监控 snapshot 也会膨胀（需要同步处理）
目前 snapshot 保存了 `target_aggregate`，等价于把 bars DataFrame 再存一份到 `data/monitor/snapshot_{variant}.pkl`。
建议将 snapshot 改为“轻量快照”：
- 仅保存每个合约的最新 bar、最新指标值、状态摘要、持仓摘要
- 绝不保存完整 bars DataFrame

---

## 9. 实施清单（按落地顺序）

1) 定义新的瘦身 state schema（version=2），并实现读写（替换现有 dump_state/load_state 的字段集合）。
2) 启动流程改造：
   - Phase 1：读瘦身 state，恢复 position/限额/active_contracts
   - Phase 2：从 MySQL 拉取 1m bars，按 bar_window replay 到现有计算链路
3) 降级策略与日志：
   - 数据不足、查询失败、映射失败时的处理策略
4) 监控 snapshot 瘦身（避免 snapshot 再次膨胀）
5) 旧 state 兼容迁移：
   - 发现旧大文件时只提取非行情状态写入新文件

---

## 10. 验收标准（你写完代码后对照检查）

- Pickle 文件大小：
  - 连续运行多天，`data/pickle/*.state.pkl` 体积基本稳定（不随 bars 增长）。
- 启动恢复一致性：
  - 恢复后 `target_aggregate` 中各 active 合约 bars 数量符合预期（>=600 window bars）
  - 恢复后 `dullness/divergence` 状态与连续运行未重启前在同一时刻一致（允许极小的边界差异，但不应频繁翻转）
- 安全性：
  - 恢复期间不下单、不触发交易分支
- 兼容性：
  - 1m/15m/30m 配置下均能正常恢复
