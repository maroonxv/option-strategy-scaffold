# 实施任务：K线生成器解耦

## 任务 1：创建 BarPipeline 具体类

- [x] 1.1 创建目录和包文件
  - 创建目录 `src/strategy/infrastructure/bar_pipeline/`
  - 创建 `src/strategy/infrastructure/bar_pipeline/__init__.py`，导出 `BarPipeline` 类：
    ```python
    from .bar_pipeline import BarPipeline
    __all__ = ["BarPipeline"]
    ```
  - **Validates: Requirements 2.1**

- [x] 1.2 实现 BarPipeline 具体类
  - 文件：`src/strategy/infrastructure/bar_pipeline/bar_pipeline.py`
  - BarPipeline 是一个**具体类**（非抽象基类），不使用 ABC、不使用继承体系
  - 构造函数签名：
    ```python
    def __init__(
        self,
        bar_callback: Callable[[Dict[str, "BarData"]], None],
        window: int,
        interval: Interval,
    ) -> None:
    ```
  - 构造函数内部创建 `PortfolioBarGenerator` 实例：
    ```python
    from vnpy_portfoliostrategy.utility import PortfolioBarGenerator
    self._pbg = PortfolioBarGenerator(
        on_bars=self._on_intermediate_bars,
        window=window,
        on_window_bars=self._on_window_bars,
        interval=interval,
    )
    ```
  - 实现 `_on_intermediate_bars(self, bars)` — PBG 内部中间回调（不对外暴露）
  - 实现 `_on_window_bars(self, bars)` — PBG 合成完成后调用 `self._bar_callback(bars)`
  - 实现 `handle_tick(self, tick: TickData) -> None` — 调用 `self._pbg.update_tick(tick)`
  - 实现 `handle_bars(self, bars: Dict[str, BarData]) -> None` — 调用 `self._pbg.update_bars(bars)`
  - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

## 任务 2：重构 StrategyEntry

- [x] 2.1 移除策略级K线合成参数
  - 文件：`src/strategy/strategy_entry.py`
  - 从类属性中移除以下两行：
    ```python
    bar_window: int = 15       # 删除
    bar_interval: str = "MINUTE"  # 删除
    ```
  - 从 `parameters` 列表中移除 `"bar_window"` 和 `"bar_interval"` 两项：
    ```python
    # 修改前
    parameters = [
        "feishu_webhook",
        "max_positions",
        "position_ratio",
        "strike_level",
        "bar_window",      # 删除
        "bar_interval",    # 删除
    ]
    # 修改后
    parameters = [
        "feishu_webhook",
        "max_positions",
        "position_ratio",
        "strike_level",
    ]
    ```
  - **Validates: Requirements 4.1**

- [x] 2.2 重构 `__init__` 方法中的 PBG 属性声明
  - 文件：`src/strategy/strategy_entry.py`，`__init__` 方法
  - 将 `self.pbg: Optional[PortfolioBarGenerator] = None` 替换为：
    ```python
    self.bar_pipeline: Optional["BarPipeline"] = None
    ```
  - 在文件顶部添加导入（或使用延迟导入）：
    ```python
    from src.strategy.infrastructure.bar_pipeline import BarPipeline
    ```
  - **Validates: Requirements 3.4**

- [x] 2.3 重构 `on_init` 中的K线生成器初始化（第5步）
  - 文件：`src/strategy/strategy_entry.py`，`on_init` 方法，"5. 初始化组合K线生成器" 部分
  - 删除当前的 PBG 初始化代码（约第 310-325 行）：
    ```python
    # 删除以下代码块
    interval_map = { ... }
    interval = interval_map.get(self.bar_interval, Interval.MINUTE)
    self.pbg = PortfolioBarGenerator(
        on_bars=self.on_bars,
        window=self.bar_window,
        on_window_bars=self.on_window_bars,
        interval=interval
    )
    self.logger.info(f"K线生成器已启用: {self.bar_window}{self.bar_interval}")
    ```
  - 替换为条件创建 BarPipeline 的逻辑，从 `self.setting` 字典读取参数：
    ```python
    bar_window = int(self.setting.get("bar_window", 0))
    if bar_window > 0:
        bar_interval_str = self.setting.get("bar_interval", "MINUTE")
        interval_map = {
            "MINUTE": Interval.MINUTE,
            "HOUR": Interval.HOUR,
            "DAILY": Interval.DAILY,
        }
        interval = interval_map.get(bar_interval_str, Interval.MINUTE)
        self.bar_pipeline = BarPipeline(
            bar_callback=self._process_bars,
            window=bar_window,
            interval=interval,
        )
        self.logger.info(f"K线合成管道已启用: {bar_window}{bar_interval_str}")
    else:
        self.logger.info("未配置K线合成，使用直通模式")
    ```
  - **Validates: Requirements 3.1, 4.2, 4.3**

- [x] 2.4 重构 `on_bars` 方法
  - 文件：`src/strategy/strategy_entry.py`，`on_bars` 方法
  - 当前代码（约第 484-487 行）：
    ```python
    if self.pbg:
        self.pbg.update_bars(bars)
    else:
        self._process_bars(bars)
    ```
  - 替换为：
    ```python
    if self.bar_pipeline:
        self.bar_pipeline.handle_bars(bars)
    else:
        self._process_bars(bars)
    ```
  - 保留 `self.last_bars.update(bars)` 和换月检查、补漏检查、自动保存逻辑不变
  - **Validates: Requirements 1.1, 3.2**

- [x] 2.5 重构 `on_tick` 方法
  - 文件：`src/strategy/strategy_entry.py`，`on_tick` 方法
  - 当前代码：
    ```python
    def on_tick(self, tick: TickData) -> None:
        if self.pbg:
            self.pbg.update_tick(tick)
    ```
  - 替换为：
    ```python
    def on_tick(self, tick: TickData) -> None:
        if self.bar_pipeline:
            self.bar_pipeline.handle_tick(tick)
    ```
  - 无 BarPipeline 时 `on_tick` 不做任何K线相关处理（与当前行为一致）
  - **Validates: Requirements 1.3, 3.3**

- [x] 2.6 移除 `on_window_bars` 方法
  - 文件：`src/strategy/strategy_entry.py`
  - 完整删除 `on_window_bars` 方法（约第 489-492 行）：
    ```python
    # 删除整个方法
    def on_window_bars(self, bars: Dict[str, BarData]) -> None:
        """合成K线回调 — 直接编排领域逻辑"""
        self.logger.debug(f"on_window_bars received: {list(bars.keys())}")
        self._process_bars(bars)
    ```
  - 该回调职责已由 BarPipeline 内部的 `_on_window_bars` 承担
  - **Validates: Requirements 3.4**

- [x] 2.7 清理无用导入
  - 文件：`src/strategy/strategy_entry.py`
  - 如果 `PortfolioBarGenerator` 不再被直接使用，移除其导入语句：
    ```python
    # 如果存在，删除：
    from vnpy_portfoliostrategy.utility import PortfolioBarGenerator
    ```
  - 确认 `Interval` 导入是否仍需要（`on_init` 中 interval_map 仍使用），如不需要也一并移除
  - **Validates: Requirements 3.4, 3.5**

## 任务 3：历史数据回放兼容

- [x] 3.1 重构实盘 warmup 回放回调
  - 文件：`src/strategy/strategy_entry.py`，`on_init` 方法，warmup 部分
  - 当前代码（约第 388-393 行）：
    ```python
    ok = self.history_repo.replay_bars_from_database(
        vt_symbols=vt_symbols,
        days=self.warmup_days,
        on_bars_callback=self.on_bars   # ← 当前直接传 on_bars
    )
    ```
  - 修改逻辑：当有 BarPipeline 时，warmup 回放也需要经过 BarPipeline 合成：
    ```python
    warmup_callback = self.on_bars  # 走 on_bars → 内部会判断 bar_pipeline
    ok = self.history_repo.replay_bars_from_database(
        vt_symbols=vt_symbols,
        days=self.warmup_days,
        on_bars_callback=warmup_callback,
    )
    ```
  - 注意：由于 `on_bars` 内部已经根据 `self.bar_pipeline` 做了分支判断，所以回调仍然传 `self.on_bars` 即可，无需额外修改。但需要确认 warmup 期间 `self.bar_pipeline` 已经创建（步骤5在步骤6之前执行，已满足）
  - **Validates: Requirements 5.1, 5.2**

- [x] 3.2 确认回测模式兼容性
  - 文件：`src/strategy/strategy_entry.py`，`on_init` 方法，回测 warmup 部分
  - 当前回测 warmup 使用 `self.load_bars(self.warmup_days)`，该方法内部会调用 `on_bars`
  - 确认 `load_bars` → `on_bars` → `bar_pipeline.handle_bars` 或 `_process_bars` 的链路在回测模式下正常工作
  - 无需代码修改，仅需验证
  - **Validates: Requirements 5.3**

- [x] 3.3 添加 warmup 过程中的 BarPipeline 异常处理
  - 文件：`src/strategy/strategy_entry.py`，`on_init` 方法
  - 在实盘 warmup 的 try-except 块中，确保 BarPipeline 处理数据失败时能被捕获：
    ```python
    try:
        ok = self.history_repo.replay_bars_from_database(
            vt_symbols=vt_symbols,
            days=self.warmup_days,
            on_bars_callback=self.on_bars,
        )
        if not ok:
            self.logger.error("实盘 warmup 失败: MySQL 中未能回放到有效 K 线")
            raise RuntimeError("live warmup failed")
    except Exception:
        self.logger.error("实盘 warmup 执行失败（可能是 BarPipeline 处理异常）", exc_info=True)
        raise
    ```
  - 当前代码已有 try-except-raise 结构，确认异常能正确传播即可；如需要可增强日志信息
  - **Validates: Requirements 5.4**

## 任务 4：单元测试

- [x] 4.1 编写 BarPipeline 单元测试
  - 文件：`tests/strategy/infrastructure/bar_pipeline/__init__.py`（创建空包文件）
  - 文件：`tests/strategy/infrastructure/bar_pipeline/test_bar_pipeline.py`
  - 测试用例：
    1. **构造函数参数验证**：验证 BarPipeline 创建时正确接收 `bar_callback`、`window`、`interval` 参数，内部 `_pbg` 属性为 `PortfolioBarGenerator` 实例
    2. **handle_tick 委托**：mock `PortfolioBarGenerator`，调用 `handle_tick(tick)`，断言 `_pbg.update_tick(tick)` 被调用一次且参数正确
    3. **handle_bars 委托**：mock `PortfolioBarGenerator`，调用 `handle_bars(bars)`，断言 `_pbg.update_bars(bars)` 被调用一次且参数正确
    4. **PBG 回调链路**：模拟 PBG 合成完成后触发 `_on_window_bars`，断言 `bar_callback` 被调用且接收到正确的 bars 数据
  - 使用 `unittest.mock.patch` 或 `unittest.mock.MagicMock` mock PBG
  - **Validates: Requirements 2.2, 2.3, 2.4, 2.5**

- [x] 4.2 编写 StrategyEntry 重构后的单元测试
  - 文件：`tests/strategy/test_strategy_entry_bar_pipeline.py`
  - 测试用例：
    1. **参数隔离**：断言 `StrategyEntry.parameters` 列表中不包含 `"bar_window"` 和 `"bar_interval"`
    2. **无 bar_window 时直通**：构造 setting 中无 `bar_window`（或为 0）的 StrategyEntry，mock `_process_bars`，调用 `on_bars(bars)`，断言 `_process_bars` 被直接调用且参数为原始 bars
    3. **无 bar_window 时无管道实例**：断言 `self.bar_pipeline is None`
    4. **有 bar_window 时委托**：构造 setting 中 `bar_window=15` 的 StrategyEntry，mock BarPipeline，调用 `on_bars(bars)`，断言 `bar_pipeline.handle_bars(bars)` 被调用
    5. **有 bar_window 时 on_tick 委托**：mock BarPipeline，调用 `on_tick(tick)`，断言 `bar_pipeline.handle_tick(tick)` 被调用
    6. **无 bar_window 时 on_tick 无操作**：构造无 bar_window 的 StrategyEntry，调用 `on_tick(tick)`，断言无任何K线相关调用
    7. **on_window_bars 不存在**：断言 StrategyEntry 实例没有 `on_window_bars` 方法（或该方法已被移除）
  - 注意：StrategyEntry 依赖较重，需要 mock `StrategyEngine` 等外部依赖，参考现有测试的 mock 模式
  - **Validates: Requirements 1.1, 1.2, 1.3, 3.1, 3.2, 3.3, 3.4, 4.1**

## 任务 5：属性测试（Property-Based Testing）

- [x] 5.1 Property 1: 直通路径恒等传递
  - 文件：`tests/strategy/infrastructure/bar_pipeline/test_bar_pipeline_pbt.py`
  - Tag: `Feature: bar-generator-decoupling, Property 1: 直通路径恒等传递`
  - 使用 `hypothesis` 生成随机的 `Dict[str, BarData]`（包含 0~N 个 vt_symbol → BarData 映射）
  - 构造一个无 BarPipeline 的 StrategyEntry（mock 最小依赖），调用 `on_bars(bars)`
  - 断言 `_process_bars` 收到的参数与输入 bars 完全一致（`is` 同一对象或 `==` 相等）
  - 策略：自定义 `st_bar_data()` strategy 生成合法的 BarData 对象，`st_bars_dict()` 生成 `Dict[str, BarData]`
  - 至少 100 次迭代
  - **Validates: Requirements 1.1**

- [x] 5.2 Property 2: 直通路径忽略 tick
  - 文件：`tests/strategy/infrastructure/bar_pipeline/test_bar_pipeline_pbt.py`（同上文件）
  - Tag: `Feature: bar-generator-decoupling, Property 2: 直通路径忽略 tick`
  - 使用 `hypothesis` 生成随机的 `TickData`
  - 构造一个无 BarPipeline 的 StrategyEntry，mock `_process_bars` 和 `bar_pipeline`
  - 调用 `on_tick(tick)`，断言 `_process_bars` 未被调用，且无任何K线相关副作用
  - 至少 100 次迭代
  - **Validates: Requirements 1.3**

- [x] 5.3 Property 3: BarPipeline 创建条件
  - 文件：`tests/strategy/infrastructure/bar_pipeline/test_bar_pipeline_pbt.py`（同上文件）
  - Tag: `Feature: bar-generator-decoupling, Property 3: BarPipeline 创建条件`
  - 使用 `hypothesis` 生成随机的 setting 字典：
    - `bar_window` 从 `st.one_of(st.none(), st.integers())` 生成
    - `bar_interval` 从 `st.sampled_from(["MINUTE", "HOUR", "DAILY", "INVALID", ""])` 生成
  - 模拟 `on_init` 中的 BarPipeline 创建逻辑（可提取为独立函数测试）
  - 断言：
    - `bar_window` 为正整数 → `bar_pipeline` 为 `BarPipeline` 实例
    - `bar_window` 为 0、负数、None、不存在 → `bar_pipeline is None`
  - 至少 100 次迭代
  - **Validates: Requirements 3.1, 1.2**
