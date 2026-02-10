# 构建策略模板仓库 (Template Repository) 计划

本设计文档详细描述了如何从当前的 `StockIndexVolatility` 项目中提取通用的量化策略框架，构建一个可复用的 Template Repository。目标是保留完善的基础设施和架构分层，使开发者能够仅关注核心策略逻辑（信号生成、选券逻辑）的实现。

## 1. 目标
创建一个基于 **DDD (领域驱动设计)** 架构的 VNPY 策略开发脚手架。
该脚手架应包含：
- **完整的生命周期管理**：多进程守护、配置加载、日志管理。
- **完善的基础设施**：VNPY 适配器、飞书告警、数据持久化。
- **Web 监控看板**：开箱即用的持仓、订单和信号监控界面。
- **清晰的代码分层**：Application Layer 负责流程编排，Domain Layer 负责业务逻辑。

## 2. 重构实施步骤

### 第一步：物理文件清理与结构调整
1.  **清理**: 删除 `data/` 运行时数据，删除 `.git/`。
2.  **保留**: `src/`, `config/`, `scripts/` 核心目录。

### 第二步：领域层重构 (Domain Refactoring) **[关键]**

我们将对 `src/strategy/domain` 下的文件进行严格分类，区分**核心框架 (Keep/Refactor)** 与 **策略实现 (Delete/Move)**。

| 模块 | 文件路径 | 动作 | 详细处理说明 |
| :--- | :--- | :--- | :--- |
| **Aggregate** | `position_aggregate.py` | **保留 (Keep)** | 框架核心。负责订单生命周期、持仓核对、多空反手逻辑。需确保不引用特定 SignalType。 |
| | `target_instrument_aggregate.py` | **重构 (Refactor)** | 重命名为 `InstrumentManager`。保留行情分发逻辑，**删除** `update_indicators` 中的具体计算代码，改为调用 `IIndicatorService`。详见下方方法清单。 |
| **Entity** | `order.py`, `position.py` | **保留 (Keep)** | 通用金融模型，直接复用。 |
| | `target_instrument.py` | **瘦身 (Refactor)** | **采用贫血模型**：只保留 `vt_symbol`, `kline_queue`, `add_bar()` 等基础成员。**删除**所有计算逻辑 (`update_macd`, `check_dullness` 等)。新增 `indicators: Dict[str, Any]` 字典，由 `IIndicatorService` 负责填充。 |
| **Service** | `signal_service.py` | **接口化 (Refactor)** | 定义 `ISignalService` 接口。仅强制实现开/平仓检查逻辑。 |
| | `indicator_service.py` | **接口化 (Refactor)** | 定义 `IIndicatorService` 接口。作为计算主导者，负责计算指标并将结果写入 `instrument.indicators`。 |
| | `future_selection_service.py` | **基类化 (Refactor)** | 重构为 `BaseFutureSelector` 基类，内置主力合约与期限筛选逻辑。 |
| | `option_selector_service.py` | **保留并增强 (Keep)** | 保留现有逻辑，增加对 CALL/PUT 类型选择的支持。 |
| | `position_sizing_service.py` | **接口化 (Refactor)** | 重构为 `IPositionSizingService`，集成仓位限制与持仓检查逻辑。 |
| | `calculation_service/*.py` | **删除 (Delete)** | 移至示例策略包。 |
| **ValueObject** | `order_instruction.py` | **保留 (Keep)** | 将内部的 `signal` 字段类型修改为 `str` 以支持自定义。 |
| | `signal_type.py` | **废弃 (Delete/Refactor)** | 废弃枚举限制。建议用户使用字符串常量定义信号（如 `"long_trend_break"`)，框架只负责透传。 |
| | `*_value.py`, `*_state.py` | **删除 (Delete)** | 删除所有特定指标的值对象 (`MacdValue`, `DivergenceState` 等)。 |
| **Interfaces** | `demand_interface/*.py` | **保留 (Keep)** | 基础设施防腐层接口 (`Account`, `MarketData`, `TradeExecution`)，完全保留。 |

### 关键重构设计说明
#### InstrumentManager (原 TargetInstrumentAggregate) 重构详情
该类重构后将彻底转变为“标的容器”与“主力合约名录”，不再持有任何指标计算相关的业务知识。

| 方法名 | 处理动作 | 备注 |
| :--- | :--- | :--- |
| `__init__` | **保留** | 初始化标的字典与活跃合约映射。 |
| `set_active_contract` | **保留** | 框架功能：设置品种当前活跃/主力合约。 |
| `get_active_contract` | **保留** | 框架功能：获取品种活跃合约。 |
| `get_all_active_contracts` | **保留** | 框架功能：获取所有活跃合约列表。 |
| `get_instrument` | **保留** | 核心查询接口。 |
| `get_or_create_instrument` | **保留** | 核心工厂接口。 |
| `update_bar` | **保留** | 纯数据更新：调用 `instrument.append_bar`。 |
| **`update_indicators`** | **删除** | **关键改动**：废弃具体参数透传逻辑。指标将由 `IIndicatorService` 直接写入实体的 `indicators` 字典。 |
| `get_bar_history` | **保留** | 代理接口：获取 K 线 DataFrame。 |
| `get_latest_price` | **保留** | 代理接口：获取最新收盘价。 |
| `get_all_symbols` | **保留** | 辅助工具：获取所有已添加标的。 |
| `has_instrument` | **保留** | 辅助工具：检查标的是否存在。 |
| `has_enough_data` | **保留** | 代理接口：检查数据量是否满足计算窗口。 |
| `clear` | **保留** | 数据清理：回测重置或系统重开时使用。 |
| `__repr__` | **保留** | 调试打印。 |



#### 1. Entity 模式选择：贫血模型 + 强力 Service
经过权衡，框架决定采用 **“贫血模型 (Anemic Domain Model)”** 作为默认实践。
*   **TargetInstrument (Entity)**: 退化为纯粹的**数据容器**。
    *   允许用户继承（为了类型提示和自定义方法）。
    *   但是，框架默认不强求继承。如果用户没定义子类，就用基类 + indicators 字典。
    *   **保留**: 基础属性 (`vt_symbol`, `exchange`) 和 K线队列维护逻辑 (`add_bar`)。
    *   **新增**: `indicators: Dict[str, Any]` 字典。这是一个开放的动态容器，用于存放所有技术指标。
    *   **删除**: 所有具体的指标计算和状态判断方法 (`update_macd`, `check_dullness`)。
*   **IIndicatorService (Service)**: 升级为指标计算的**主导者**。
    *   它从 Entity 读取 Bar 数据，调用计算库（如 TALib），然后将结果直接写入 Entity 的 `indicators` 字典中。
    *   **优势**: 这种分离使得 Entity 极其稳定，增加新指标只需修改 Service，无需修改 Entity 结构，完美符合开闭原则。

#### 2. 信号机制：完全字符串化 (String-based Signals)
为了适应复杂多变的量化策略，框架废弃了严格的 `SignalType` 枚举。
*   **自定义**: 用户可以使用任意**字符串**来定义信号（例如 `"long_macd_golden_cross"`, `"sell_cover_stop_loss"`）。
*   **docstring**： docstring 里面指导用户按照类似（SELL_CALL_DIVERGENCE_TD9 ="sell_call_divergence_td9"     # 顶钝化 +高8/9）这样的规范去定义信号类别
*   **透传**: 框架层（Application & Infrastructure）对信号内容不做解析，只负责在日志、消息推送和数据库中**原样记录**。
*   **规范**: 建议用户采用 `ACTION_REASON_DETAIL` 的命名规范，以便于后续的数据分析。

### 核心接口与服务定义 (Core SPI & Services)

为了支持策略的多态性并降低重复开发成本，框架定义了以下核心组件。

#### 1. `ISignalService` (信号生成)
策略开发者只需专注于开仓和平仓条件的判断。
```python
class ISignalService(ABC):
    @abstractmethod
    def check_open_signal(self, instrument: TargetInstrument) -> Optional[OrderInstruction]:
        """
        [由开发者实现] 检查开仓信号。
        提示：在此方法内部可以调用自定义的辅助检查，如 self.check_macd() 或 self.check_volatility()。
        """
        pass

    @abstractmethod
    def check_close_signal(self, instrument: TargetInstrument, position: Position) -> Optional[OrderInstruction]:
        """
        [由开发者实现] 检查平仓信号。
        """
        pass
```

#### 2. `BaseFutureSelector` (标的筛选基类)
提供常用的期货标的筛选工具，避免重复造轮子。
*   **`select_dominant_contract(contracts)`**: 自动根据成交量（Volume）筛选出全市场持仓/成交最大的主力合约。
*   **`filter_by_maturity(contracts, mode)`**: 根据月份（当月/次月）筛选合约，复用现有成熟逻辑。

#### 3. `OptionSelectorService` (期权选择服务)
在给定的一堆同标的期权中，根据流动性和行权价选择特定合约。
*   **`select_option(underlying, option_type, strike_preference)`**:
    *   `option_type`: `CALL` 或 `PUT`。
    *   `strike_preference`: `ATM`, `OTM1`, `OTM2` 等。
    *   内置逻辑：自动处理剩余交易日过滤、成交量排序等。

#### 4. `IPositionSizingService` (仓位计算与风控)
负责将策略的“期望”转化为“实际可执行”的单量，并执行基础风控检查。
```python
class IPositionSizingService(ABC):
    @abstractmethod
    def calculate_open_volume(self, desired_volume: int, instrument: TargetInstrument, account: Account) -> int:
        """
        计算实际开仓手数。内部需包含：
        1. 检查是否超过该品种的最大持仓限制。
        2. 检查是否已有同一方向/合约的持仓（防止重复开仓）。
        3. 检查账户可用资金是否充足。
        """
        pass

    @abstractmethod
    def calculate_exit_volume(self, desired_volume: int, current_position: Position) -> int:
        """
        计算实际平仓手数。内部需包含：
        1. 检查理想平仓手数是否超出当前实际持仓数（防止超卖/超买）。
        """
        pass
```

#### 5. `IIndicatorService` (指标计算服务)
作为指标计算的引擎，负责维护 `TargetInstrument` 的状态。
```python
class IIndicatorService(ABC):
    @abstractmethod
    def calculate_bar(self, instrument: TargetInstrument, bar: BarData) -> None:
        """
        [由开发者实现] K线更新时的指标计算逻辑。
        指导：
        1. 建议在内部实现若干以 `calculate_` 开头的辅助方法（如 `calculate_macd`, `calculate_td`）。
        2. 计算结果必须存入 `instrument.indicators` 字典中，以便 SignalService 读取。
        """
        pass
```

### 第三步：应用层重构 (Application Refactoring)

`VolatilityTrade` 将重命名为 **`StrategyEngine`**，并从一个“具体的波动率交易员”进化为“通用的策略指挥官”。

#### 1. 方法级重构清单 (26个方法处理方案)

| 方法名 | 处理动作 | 说明 |
| :--- | :--- | :--- |
| `__init__` | **改造** | 移除硬编码的服务实例化，改为依赖注入 SPI 接口。删除特定的 MACD/钝化缓存。 |
| `_dump_snapshot` | **保留** | 仅微调：直接序列化 `TargetInstrument`（现已包含 indicators 字典）。 |
| `dump_state` / `load_state` | **改造** | 框架仅负责总体编排，具体的服务状态恢复需委托给各 Service 的接口方法。 |
| `resubscribe_active_contracts` | **保留** | 核心生命周期功能，直接复用。 |
| `handle_universe_validation` | **保留** | 核心标的补漏功能。微调：调用 `BaseFutureSelector` 筛选主力。 |
| `handle_universe_rollover_check` | **保留** | 核心换月检查逻辑。微调：调用 `BaseFutureSelector`。 |
| `_is_contract_of_product` | **保留** | 辅助方法。 |
| **`handle_bar_update`** | **彻底改造** | **重中之重**：删除所有 MACD、背离、钝化的具体逻辑。替换为标准的 SPI 调用流水线。 |
| `handle_bars` | **保留** | 批处理入口，直接复用。 |
| `handle_order_update` | **保留** | 透传订单状态至聚合根。 |
| `handle_trade_update` | **改造** | 除去更新持仓外，将风控计数的更新委托给 `sizing_service.on_trade_update(trade)`。 |
| `handle_position_update` | **保留** | 透传持仓状态。 |
| **`_check_and_execute_open`** | **彻底改造** | **移除具体的期权选择逻辑**。改为：`check_open_signal` -> `select_target` -> `sizing` -> `send_order`。 |
| **`_check_and_execute_close`** | **彻底改造** | 流程同开仓，逻辑简化。 |
| **`_select_option`** | **删除/移走** | 这是特定的期权策略逻辑，移至示例实现或具体的 `ContractSelector`。 |
| **`_get_option_contracts`** | **删除/移走** | 同上，属于特定策略的基础工具。 |
| `_publish_domain_events` | **保留** | 事件驱动通信机制。 |
| `_get_current_date` | **保留** | 辅助工具。 |
| **`_ensure_daily_open_limit_state`** | **删除/移走** | 属于特定风控逻辑，移入 `IPositionSizingService` 的具体实现中。 |
| **`_get_reserved_open_volume`** | **删除/移走** | 同上，移入 Sizing Service。 |
| **`_update_open_limits_from_trade`**| **删除/移走** | 同上，移入 Sizing Service。 |
| `_create_alert_from_event` | **保留** | 核心告警翻译逻辑。 |
| `_publish_alert` | **保留** | 核心告警发布逻辑。 |

### 第四步：策略入口改造 (Strategy Entry Point)

`StrategyEntry` 将重命名为 **`GenericStrategyAdapter`**。
它是连接 VnPy 引擎与 `StrategyEngine` 的胶水层。

#### 1. 核心设计原则
*   **去 UI 化**：不再维护 VnPy 的 `parameters` UI 列表，所有参数均通过 `setting` 字典传入。
*   **严格分层**：`GenericStrategyAdapter` 仅处理基础设施（日志、回测开关），策略逻辑全权委托给 `StrategyEngine`。
*   **依赖倒置**：通过 `ServiceBundle` 强类型对象传递依赖，确保 `StrategyEngine` 在所有服务装配完成后才被构建。

#### 2. 服务包定义 (ServiceBundle)
为了保证类型安全与命名一致性，定义标准服务包：

```python
@dataclass
class ServiceBundle:
    """
    领域服务包
    字段名严格对应 domain/domain_service 下的模块定义
    """
    indicator_service: IIndicatorService          # 指标计算接口
    signal_service: ISignalService                # 信号生成接口
    position_sizing_service: IPositionSizingService # 仓位与风控接口
    future_selection_service: BaseFutureSelector  # 标的/主力合约筛选 (负责 Underlying)
    option_selector_service: OptionSelectorService # 交易对象/期权筛选 (负责 Execution Target)
```

#### 3. 方法级重构清单

| 方法名 | 处理动作 | 说明 |
| :--- | :--- | :--- |
| `__init__` | **清理** | 移除所有策略特定的成员变量（如 `macd_fast`），只保留基础设施变量。 |
| **`on_init`** | **重构** | **核心流程**：<br>1. 初始化 Logger 与基础配置。<br>2. 调用 `setup_services()` 获取 `ServiceBundle`。<br>3. 实例化 `StrategyEngine` 并注入服务。 |
| **`setup_services`** | **新增** | **抽象方法 (Hook)**。子类必须实现。负责从 `self.setting` 读取参数，实例化并返回 `ServiceBundle`。 |
| `on_start` / `on_stop` | **保留** | 生命周期管理。 |
| `on_tick` / `on_bars` | **保留** | 行情数据清洗与转发。 |
| `on_order` / `on_trade` | **保留** | 交易回报透传。 |

#### 4. 代码结构示例

**GenericStrategyAdapter (Base):**
```python
class GenericStrategyAdapter(StrategyTemplate):
    def on_init(self):
        # 1. 基础设置
        self.setup_logger()
        
        # 2. [Hook] 用户装配零件
        # 用户子类在此处读取 self.setting 并实例化服务
        self.services = self.setup_services()
        
        # 3. [Core] 框架组装整机
        # 此时所有依赖已就绪
        self.strategy_engine = StrategyEngine(
            strategy_context=self,
            indicator_service=self.services.indicator_service,
            signal_service=self.services.signal_service,
            position_sizing_service=self.services.position_sizing_service,
            future_selection_service=self.services.future_selection_service,
            option_selector_service=self.services.option_selector_service
        )

    @abstractmethod
    def setup_services(self) -> ServiceBundle:
        """用户必须实现此方法以提供策略所需的服务组件"""
        pass
```

**UserStrategy (Implementation):**
```python
class MyDemoStrategy(GenericStrategyAdapter):
    def setup_services(self) -> ServiceBundle:
        # 从配置读取参数
        fast = self.setting.get("fast_window", 12)
        
        return ServiceBundle(
            indicator_service=MyMacd(fast),
            signal_service=MySignal(),
            position_sizing_service=FixedSizing(),
            future_selection_service=BaseFutureSelector(),
            option_selector_service=OptionSelectorService(strike_level=2)
        )
```

### 第五步：运行时环境改造 (Runtime/Main Refactoring)

`src/main` 是系统的“量化操作系统 (Quant OS)”，负责进程守护、网关连接与环境初始化。目标是使其完全通用化，能够加载任意符合 `GenericStrategyAdapter` 规范的策略。

#### 1. 进程入口与守护 (Keep)
*   `src/main/main.py`: 系统入口，保持原样。
*   `src/main/parent_process.py`: 守护进程。
    *   **处理**: 检查并移除任何硬编码的旧策略名称（如日志打印中的 `"StrategyEntry"`），改为通用描述。

#### 2. 策略执行环境 (Core Refactor)
*   **`src/main/child_process.py`**:
    *   **现状**: 硬编码引入了具体的策略类 `StrategyEntry`。
    *   **重构方案**: 解耦策略加载逻辑，采用**固定入口模式**。
        1.  约定：所有基于模板开发的策略，必须在 `src/strategy/__init__.py` (或指定入口模块) 中暴露一个名为 `StrategyEntry` 的类。
        2.  代码修改：
            ```python
            # child_process.py 修改前
            from src.strategy.strategy_entry import StrategyEntry
            engine.add_strategy(StrategyEntry, setting)
            
            # child_process.py 修改后
            from src.strategy import StrategyEntry # 动态指向用户的策略类
            engine.add_strategy(StrategyEntry, setting)
            ```

#### 3. 基础设施组件 (Keep)
*   `src/main/gateway.py`: VNPY 网关加载器，完全保留。
*   `src/main/run_recorder.py`: 数据录制进程，完全保留。

#### 4. 工具库 (Utils Refactor)
*   `src/main/utils/config_loader.py`:
    *   **增强**: 修改 `load_strategy_config`，使其返回完整的配置字典，**不进行字段过滤**。这样 `GenericStrategyAdapter` 才能无障碍地读取到用户自定义的参数。
*   `src/main/utils/log_handler.py`: 保留标准日志配置。
*   `src/main/utils/contract_utils.py`: 保留通用合约工具。

### 第六步：回测与配置适配
1.  修改 `run_backtesting.py` 以适配新的 `StrategyEntry` 加载方式。
2.  清理 `strategy_config.yaml`，分离通用配置与策略参数。

## 4. 目录结构预览 (Target Structure)

```text
├── config/
│   └── strategy_config.yaml      # 通用配置模板
├── src/
│   ├── main/                     # 进程管理与入口 (通用)
│   ├── backtesting/              # 回测套件 (通用)
│   ├── interface/                # Web 监控 (通用)
│   ├── strategy/
│   │   ├── application/
│   │   │   └── strategy_engine.py # [通用] 编排引擎 (原 volatility_trade.py)
│   │   ├── domain/
│   │   │   ├── aggregate/
│   │   │   │   ├── position_aggregate.py # [通用] 持仓管理
│   │   │   │   └── instrument_manager.py # [通用] 标的管理 (原 TargetInstrumentAggregate)
│   │   │   ├── entity/
│   │   │   │   ├── order.py
│   │   │   │   ├── position.py
│   │   │   │   └── target_instrument.py  # [通用] 标的基类 (瘦身版)
│   │   │   ├── interface/        # [SPI] 核心接口定义 (新增)
│   │   │   │   ├── signal_service.py
│   │   │   │   ├── indicator_service.py
│   │   │   │   └── contract_selector.py
│   │   │   └── impl/             # [示例] 策略实现 (用户修改区)
│   │   │       ├── demo_signal_service.py
│   │   │       └── demo_indicator_service.py
│   │   ├── infrastructure/       # [通用] 适配器
│   │   └── strategy_main.py      # [入口] 策略组装
├── scripts/                      # 启动脚本
└── requirements.txt
```

## 5. 开发者使用指南
1.  **定义数据**: 继承 `TargetInstrument` (可选) 或直接使用 `indicators` 字典存储策略状态。
2.  **实现指标**: 实现 `IIndicatorService`，计算技术指标并更新到标的对象中。
3.  **实现信号**: 实现 `ISignalService`，根据标的状态生成交易指令。
4.  **组装运行**: 在 `strategy_main.py` 中将上述服务注入 `StrategyEngine`。