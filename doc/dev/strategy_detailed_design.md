# 商品波动率策略 - DDD 完整设计方案

## 一、分层架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│  Interface Layer (接口层)                                        │
│  strategy_entry.py                               │
│  职责: VnPy回调入口 (on_init, on_bars, on_order等)               │
├─────────────────────────────────────────────────────────────────┤
│  Application Layer (应用层)                                      │
│  volatility_trade.py                                            │
│  职责: 编排两个聚合根, 处理领域事件, 协调业务流程                 │
├─────────────────────────────────────────────────────────────────┤
│  Domain Layer (领域层)                                           │
│  ┌────────────────────────┐  ┌────────────────────────┐         │
│  │ TargetInstrumentAgg    │  │ PositionAggregate      │         │
│  │ (只读, 行情状态)        │  │ (读写, 持仓生命周期)   │         │
│  │ 纯数据容器, 无计算逻辑  │  │ 纯状态管理, 发出事件   │         │
│  └────────────────────────┘  └────────────────────────┘         │
│  + Entity: TargetInstrument, Position                           │
│  + Value Object: SignalType, MACDValue, TDValue                 │
│  + Domain Service: IndicatorService, SignalService,             │
│                    PositionSizingService, OptionSelectorService   │
│  + Domain Event: ManualCloseDetectedEvent, ...                  │
├─────────────────────────────────────────────────────────────────┤
│  Infrastructure Layer (基础设施层)                               │
│  通过网关适配器与 VnPy Engine 交互，并用 EventEngine 发送通知     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、VnPy 事件驱动架构集成

### 2.1 VnPy EventEngine 核心机制

参考 VnPy 源码 (`vnpy/event/engine.py`)：

```
EventEngine 核心 API:
├── put(event: Event)         # 发布事件到队列
├── register(type, handler)   # 注册事件处理器
└── unregister(type, handler) # 注销事件处理器

Event 结构:
├── type: str                 # 事件类型 (如 "eOrder.", "eTrade.")
└── data: Any                 # 事件数据
```

### 2.2 自定义策略事件类型

位置: `src/strategy/domain/event/event_types.py`

```
# 策略领域事件类型定义
EVENT_STRATEGY_ALERT = "eStrategyAlert."    # 飞书告警事件
EVENT_STRATEGY_LOG = "eStrategyLog."        # 策略日志事件

# 事件数据结构
@dataclass
class StrategyAlertData:
    """策略告警数据"""
    strategy_name: str
    alert_type: str           # "manual_open", "manual_close", "order_rejected", etc.
    message: str
    timestamp: datetime
    vt_symbol: str = ""
    volume: float = 0
    extra: dict = field(default_factory=dict)
```

### 2.3 飞书通知 - 基于 EventEngine 的事件驱动实现

**设计原则**: 不使用适配器，直接利用 VnPy 的 EventEngine

**流程图**:
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 聚合根      │    │ 应用层      │    │ EventEngine │    │ 飞书Handler │
│ (产生事件)  │───►│ (转换事件)  │───►│ (分发事件)  │───►│ (发送告警)  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
     领域事件           put(Event)         dispatch        feishu.send()
```

**实现方式**:

```
# src/strategy/infrastructure/reporting/feishu_handler.py
class FeishuEventHandler:
    """飞书事件处理器 - 注册到 VnPy EventEngine"""
    
    def __init__(self, webhook_url: str, strategy_name: str):
        self.webhook_url = webhook_url
        self.strategy_name = strategy_name
    
    def handle_alert_event(self, event: Event):
        """处理策略告警事件"""
        data: StrategyAlertData = event.data
        
        # 只处理本策略的事件
        if data.strategy_name != self.strategy_name:
            return
        
        message = self._format_message(data)
        self._send_feishu(message)
    
    def _format_message(self, data: StrategyAlertData) -> str:
        """格式化飞书消息"""
        templates = {
            "manual_open": f"⚠️ 检测到手动开仓 {data.vt_symbol} {data.volume}手，程序不会自动平仓",
            "manual_close": f"📝 检测到手动平仓 {data.vt_symbol} {data.volume}手，已自动匹配",
            "order_cancelled": f"❌ 平仓订单被撤单: {data.message}",
            "order_rejected": f"🚫 平仓订单被拒单: {data.message}",
            "open_signal": f"📈 开仓信号触发: {data.message}",
            "close_signal": f"📉 平仓信号触发: {data.message}",
        }
        return templates.get(data.alert_type, data.message)
    
    def _send_feishu(self, message: str):
        """发送飞书消息"""
        import requests
        payload = {
            "msg_type": "text",
            "content": {"text": f"[{self.strategy_name}] {message}"}
        }
        requests.post(self.webhook_url, json=payload, timeout=5)


# 在接口层注册 (strategy_entry.py)
def on_init(self):
    # 创建飞书处理器
    self.feishu_handler = FeishuEventHandler(
        webhook_url=self.feishu_webhook,
        strategy_name=self.strategy_name
    )
    
    # 注册到 VnPy EventEngine
    self.strategy_engine.event_engine.register(
        EVENT_STRATEGY_ALERT, 
        self.feishu_handler.handle_alert_event
    )
```

---

## 三、核心设计原则

### 3.1 `on_` 前缀函数仅存在于接口层

| 层级 | 函数命名规范 | 示例 |
|-----|-------------|------|
| 接口层 | `on_*` (VnPy回调) | `on_init`, `on_bars`, `on_order`, `on_trade_event` |
| 应用层 | `handle_*` | `handle_bar_update`, `handle_order_update` |
| 聚合根 | `update_*` 或 动词短语 | `update_bar`, `add_position`, `match_manual_close` |
| 领域服务 | `calculate_*` 或 `check_*` | `calculate_macd`, `check_open_signal` |

### 3.2 聚合根保持纯净 - 计算逻辑委托给领域服务

**TargetInstrumentAggregate 职责边界**:

```
聚合根职责 (纯数据管理):
├── 管理 instruments 字典
├── 追加 K线数据到 DataFrame  
├── 存储指标计算结果
└── 提供查询接口

领域服务职责 (计算逻辑):
├── IndicatorService: 计算 MACD, TD 序列
├── SignalService: 判断钝化、背离、开/平仓信号
└── 返回计算结果，不修改状态
```

---

## 四、领域模型详细设计

### 4.0 领域对象概览

| 类型 | 名称 | 职责 |
|---|---|---|
| **Entity** | `TargetInstrument` | 标的聚合根，管理行情和指标状态 |
| **Entity** | `Position` | 策略持仓实体，追踪持仓盈亏与生命周期 |
| **Entity** | `Order` | 订单实体，追踪委托状态 |
| **ValueObject** | `SignalType` | 信号类型枚举 |
| **ValueObject** | `MACDValue` | MACD 指标快照 |
| **ValueObject** | `TDValue` | TD 序列快照 |
| **ValueObject** | `EMAState` | 均线状态快照 |
| **ValueObject** | `DullnessState` | 钝化状态 (业务逻辑状态) |
| **ValueObject** | `DivergenceState` | 背离状态 (业务逻辑状态) |
| **ValueObject** | `OrderInstruction` | 交易指令 (决策结果) |

### 4.1 Value Objects (值对象定义)

位置: `src/strategy/domain/value_object/`

```python
@dataclass(frozen=True)
class MACDValue:
    dif: float
    dea: float
    macd_bar: float

@dataclass(frozen=True)
class TDValue:
    td_count: int
    td_setup: int
    has_buy_8_9: bool
    has_sell_8_9: bool

@dataclass(frozen=True)
class EMAState:
    fast_ema: float
    slow_ema: float
    trend_status: str  # 'up', 'down', 'neutral'

@dataclass(frozen=True)
class DullnessState:
    """钝化状态 (MACD)"""
    is_top_active: bool = False
    is_bottom_active: bool = False
    start_time: Optional[datetime] = None
    start_price: float = 0.0
    start_diff: float = 0.0
    # 失效标记
    is_top_invalidated: bool = False
    is_bottom_invalidated: bool = False

@dataclass(frozen=True)
class DivergenceState:
    """背离状态 (MACD)"""
    is_top_confirmed: bool = False
    is_bottom_confirmed: bool = False
    confirm_time: Optional[datetime] = None
    confirm_price: float = 0.0
    confirm_diff: float = 0.0

@dataclass(frozen=True)
class OrderInstruction:
    """交易指令"""
    direction: Direction
    offset: Offset
    volume: int
    price: float
```

### 4.2 Entities (实体定义)

#### 4.2.1 TargetInstrument (标的实体 - 聚合根)

位置: `src/strategy/domain/aggregate/target_instrument_aggregate.py`

职责:
1.  **数据仓库**: `bars` DataFrame 存储完整的历史 K 线及指标序列 (MACD, TD 等)，作为计算依据。
2.  **状态快照**: 存储当前时刻的指标状态 (Value Objects)，作为决策依据。
3.  **一致性**: 保证所有状态在同一时间点对齐。

```python
class TargetInstrument:
    """标的实体"""
    
    def __init__(self, vt_symbol: str, ...):
        # 核心数据源: 包含 open, high, low, close, dif, dea, macd, td_count 等列
        self.bars: pd.DataFrame = pd.DataFrame()
        
        # 状态快照 (决策用)
        self.macd_value: Optional[MACDValue] = None
        self.td_value: Optional[TDValue] = None
        self.ema_state: Optional[EMAState] = None
        self.dullness_state: DullnessState = DullnessState()
        self.divergence_state: DivergenceState = DivergenceState()

    def update_indicators(self, 
                          macd_value: MACDValue, 
                          td_value: TDValue,
                          ema_state: EMAState,
                          dullness_state: DullnessState,
                          divergence_state: DivergenceState):
        """
        全量更新指标状态 (原子操作)
        """
        self.macd_value = macd_value
        self.td_value = td_value
        self.ema_state = ema_state
        self.dullness_state = dullness_state
        self.divergence_state = divergence_state
        
    def append_bar(self, bar: pd.Series):
        """追加新的K线数据"""
        # ... logic to append to self.bars ...
```

#### 4.2.2 Position (持仓实体)

位置: `src/strategy/domain/entity/position.py`

职责:
1.  **策略视角持仓**: 追踪策略发起的持仓，而不仅仅是账户层面的持仓。
2.  **信号关联**: 记录该持仓是基于哪个信号开仓的 (SignalType)，用于后续平仓逻辑判断。

```python
class Position:
    """持仓实体"""
    def __init__(self, vt_symbol: str, volume: int, direction: Direction, signal_type: SignalType):
        self.vt_symbol = vt_symbol
        self.volume = volume
        self.direction = direction
        self.signal_type = signal_type  # 关键: 记录开仓信号
        self.open_price = 0.0
        self.open_time = None
```

#### 4.2.3 Order (订单实体)

位置: `src/strategy/domain/entity/order.py`

职责:
1.  **委托追踪**: 记录订单的生命周期状态 (提交、成交、撤单)。
2.  **关联**: 关联到具体的策略操作。

```python
class Order:
    """订单实体"""
    def __init__(self, vt_orderid: str, vt_symbol: str, direction: Direction, offset: Offset, volume: int):
        self.vt_orderid = vt_orderid
        self.vt_symbol = vt_symbol
        self.direction = direction
        self.offset = offset
        self.volume = volume
        self.status = Status.SUBMITTING
        self.traded = 0
```

### 4.3 IndicatorService (指标计算领域服务)

位置: `src/strategy/domain/domain_service/indicator_service.py`

职责: **协调**各项指标的计算，并生成状态快照。它作为应用层和底层计算逻辑(Calculator)之间的桥梁。

设计模式: **Facade (外观模式)** + **Stateless Service**

> [!NOTE]
> `IndicatorService` 统一调配以下底层计算服务 (MacdCalculator, TdCalculator, EmaCalculator)，对外提供统一接口 `calculate_all`。

```python
class IndicatorService:
    """
    指标服务 (无状态)
    协调 MacdCalculator, TdCalculator 等完成计算
    """
    
    def calculate_all(self, instrument: TargetInstrument) -> IndicatorResultDTO:
        # ... (同上) ...
        pass
```

### 4.2.1 MacdCalculatorService (底层计算服务)

位置: `src/strategy/domain/domain_service/calculation_service/macd_calculation_service.py`

职责: 负责 MACD 相关的纯数学计算。

```python
class MacdCalculatorService:
    """MACD计算服务 (无状态, 纯静态方法)"""

    @staticmethod
    def compute(bars: pd.DataFrame, fast_period=12, slow_period=26, signal_period=9):
        """
        计算并向 DataFrame 追加/更新 dif, dea, macd 列
        """
        # 使用 ta-lib 或 pandas 矢量化计算
        # 注意: 增量计算逻辑以提高性能
        pass
        
    @staticmethod
    def detect_peak(bars: pd.DataFrame) -> List[MACDPeakInfo]:
        """
        检测红绿柱峰值
        """
        pass
```

### 4.2.2 TdCalculatorService (底层计算服务)

位置: `src/strategy/domain/domain_service/calculation_service/td_calculation_service.py`

职责: 负责 TD 序列相关的纯数学计算。

```python
class TdCalculatorService:
    """TD序列计算服务"""

    @staticmethod
    def compute(bars: pd.DataFrame):
        """
        计算并向 DataFrame 追加/更新 td_count, td_setup 列
        """
        pass
```

### 4.2.3 EmaCalculatorService (底层计算服务)

位置: `src/strategy/domain/domain_service/calculation_service/ema_calculation_service.py`

职责: 负责 EMA 均线计算。

```python
class EmaCalculatorService:
    """EMA计算服务"""
    
    @staticmethod
    def compute(bars: pd.DataFrame, period_fast=5, period_slow=20):
        """
        计算并向 DataFrame 追加/更新 ema_fast, ema_slow 列
        """
        pass
```

### 4.3 SignalService (信号判断领域服务)

位置: `src/strategy/domain/domain_service/signal_service.py`

职责: 纯业务规则判断。根据当前的指标状态 (Dullness, Divergence, TD) 判断是否触发开平仓信号。

```python
class SignalService:
    """信号判断领域服务 (无状态, 纯函数)"""
    
    @staticmethod
    def check_open_signal(instrument: TargetInstrument) -> Optional[SignalType]:
        """
        检查开仓信号
        
        卖沽开仓:
        - 底钝化 + 低8/9 => SELL_PUT_DIVERGENCE_TD9
        - 底背离确认 => SELL_PUT_DIVERGENCE_CONFIRM
        
        卖购开仓:
        - 顶钝化 + 高8/9 => SELL_CALL_DIVERGENCE_TD9
        - 顶背离确认 => SELL_CALL_DIVERGENCE_CONFIRM
        """
        dullness = instrument.dullness_state
        divergence = instrument.divergence_state
        td = instrument.td_value
        
        # 卖沽信号
        if dullness.is_bottom_active and td.has_buy_8_9:
            return SignalType.SELL_PUT_DIVERGENCE_TD9
        
        if divergence.is_bottom_confirmed:
            return SignalType.SELL_PUT_DIVERGENCE_CONFIRM
        
        # 卖购信号
        if dullness.is_top_active and td.has_sell_8_9:
            return SignalType.SELL_CALL_DIVERGENCE_TD9
        
        if divergence.is_top_confirmed:
            return SignalType.SELL_CALL_DIVERGENCE_CONFIRM
        
        return None
    
    @staticmethod
    def check_close_signal(position: Position, 
                          instrument: TargetInstrument) -> Optional[SignalType]:
        """
        检查平仓信号 (根据持仓的开仓信号类型)
        
        返回: 匹配的平仓信号，或 None
        """
        dullness = instrument.dullness_state
        divergence = instrument.divergence_state
        td = instrument.td_value
        
        open_signal = position.signal_type
        valid_close_signals = SignalType.get_valid_close_signals(open_signal)
        
        # 止盈信号
        if open_signal in [SignalType.SELL_PUT_DIVERGENCE_TD9, SignalType.SELL_PUT_DIVERGENCE_CONFIRM]:
            # 卖沽持仓的止盈: 高8/9, 顶背离
            if td.has_sell_8_9 and SignalType.CLOSE_PUT_TD_HIGH9 in valid_close_signals:
                return SignalType.CLOSE_PUT_TD_HIGH9
            if divergence.is_top_confirmed and SignalType.CLOSE_PUT_TOP_DIVERGENCE in valid_close_signals:
                return SignalType.CLOSE_PUT_TOP_DIVERGENCE
        
        if open_signal in [SignalType.SELL_CALL_DIVERGENCE_TD9, SignalType.SELL_CALL_DIVERGENCE_CONFIRM]:
            # 卖购持仓的止盈: 低8/9, 底背离
            if td.has_buy_8_9 and SignalType.CLOSE_CALL_TD_LOW9 in valid_close_signals:
                return SignalType.CLOSE_CALL_TD_LOW9
            if divergence.is_bottom_confirmed and SignalType.CLOSE_CALL_BOTTOM_DIVERGENCE in valid_close_signals:
                return SignalType.CLOSE_CALL_BOTTOM_DIVERGENCE
        
        # 止损信号 (钝化失效)
        if dullness.is_bottom_invalidated and SignalType.CLOSE_PUT_FLATTENING_INVALID in valid_close_signals:
            return SignalType.CLOSE_PUT_FLATTENING_INVALID
        
        if dullness.is_top_invalidated and SignalType.CLOSE_CALL_FLATTENING_INVALID in valid_close_signals:
            return SignalType.CLOSE_CALL_FLATTENING_INVALID
        
        return None
```

### 4.4 PositionSizingService (仓位管理领域服务)

位置: `src/strategy/domain/domain_service/position_sizing_service.py`

职责: 负责计算交易数量和风控检查。它是"决策者"的核心组件。

```python
class PositionSizingService:
    """仓位管理领域服务 (无状态)"""
    
    @staticmethod
    def make_open_decision(account_balance: float,
                          signal_type: SignalType,
                          contract_price: float,
                          current_positions: List[Position]) -> Optional[OrderInstruction]:
        """
        生成开仓决策
        
        参数:
            account_balance: 可用资金
            signal_type: 信号类型
            contract_price: 合约价格
            current_positions: 当前持仓列表 (用于检查最大持仓限制)
            
        返回:
            OrderInstruction (包含交易指令) 或 None (不交易)
        """
        # 1. 检查是否超过最大持仓限制
        if len(current_positions) >= MAX_POSITIONS:
            return None
            
        # 2. 资金管理规则 (例如: 每次使用 10% 资金)
        target_amount = account_balance * 0.1
        volume = int(target_amount / (contract_price * CONTRACT_MULTIPLIER))
        
        if volume <= 0:
            return None
            
        # 3. 生成指令
        return OrderInstruction(
            direction=Direction.SHORT, # 卖权策略通常是 Short
            offset=Offset.OPEN,
            volume=volume,
            price=contract_price
        )
```

### 4.6 OptionSelectorService (期权选择领域服务)

位置: `src/strategy/domain/domain_service/option_selector_service.py`

职责: 负责从全市场合约中筛选出符合策略要求的虚值期权合约。

设计原则:
- **虚值选择**: 根据 Diff1 指标 (行权价与标的价格的偏离度) 排序，选择虚值程度合适的档位 (如虚四档)。
- **流动性过滤**: 过滤买一价过低或买一量不足的合约。
- **生命周期过滤**: 过滤即将到期或剩余时间过长的合约。

```python
class OptionSelectorService:
    """虚N档期权选择服务"""
    
    def __init__(self, strike_level: int = 4):
        """
        初始化
        strike_level: 虚值档位，本策略默认使用虚四档 (Out-of-the-Money 4 Strikes)
        """
        self.strike_level = strike_level
    
    def select_option(self,
                           group: DataFrame,
                           strike_level: Optional[int] = None,
                           min_trading_days: int = 1,
                           max_trading_days: int = 50) -> DataFrame:
        """
        选择目标期权
        
        流程:
        1. filter_candidates: 过滤不符合流动性要求的合约
        2. select_otm_strike: 按 diff1 排序，选择虚值第 N 档 (CALL 选大, PUT 选小)
        3. apply_trading_days_window: 过滤到期日不合适的合约
        
        返回: 包含目标合约信息的 DataFrame
        """
        # ... 具体实现参考源码 ...
        pass
```

### 4.7 Domain Events (领域事件设计)

位置: `src/strategy/domain/event/`

职责: 明确系统内的关键业务状态变更，用于解耦业务逻辑和副作用 (如通知、日志)。

#### 4.7.1 ManualCloseDetectedEvent (手动平仓侦测)

- **触发时机**: `PositionAggregate` 检测到持仓量减少，且该减少并非由策略发出的订单触发。
- **用途**: 修正策略内部持仓状态，避免逻辑错乱；触发飞书告警通知交易员。

```python
@dataclass
class ManualCloseDetectedEvent(DomainEvent):
    vt_symbol: str
    volume: float
    timestamp: datetime = field(default_factory=datetime.now)
```

#### 4.7.2 SignalGeneratedEvent (信号生成 - 隐式/显式可选)

- **触发时机**: `SignalService` 检测到开仓或平仓信号。
- **用途**: 记录信号产生的时间、依据 (如背离、钝化)，用于回测分析或实时通知。

#### 4.7.3 OrderInstructionGeneratedEvent (指令生成 - 隐式/显式可选)

- **触发时机**: `PositionSizingService` 生成了有效的交易指令。
- **用途**: 记录策略的“决策”结果，区别于最终的“执行”结果 (成交)。

---

### 4.8 PositionAggregate (持仓聚合根)

职责: 管理期权持仓的生命周期

```
class PositionAggregate:
    """持仓聚合根 (读写)"""
    
    # ========== 数据容器 ==========
    positions: Dict[vt_symbol, Position]
    pending_orders: Dict[vt_orderid, OrderInfo]
    managed_symbols: Set[str]
    
    # 领域事件队列
    domain_events: List[DomainEvent]
    
    # ========== 状态更新接口 ==========
    
    def update_from_order(self, order_data: OrderData):
        """
        根据订单更新持仓状态 (由应用层调用)
        
        注意: 不使用 on_ 前缀
        """
        vt_symbol = order_data.vt_symbol
        
        if order_data.offset == Offset.OPEN:
            self._handle_open_order(order_data)
        else:
            self._handle_close_order(order_data)
    
    def update_from_trade(self, trade_data: TradeData):
        """
        根据成交更新持仓 (由应用层调用)
        """
        if trade_data.vt_symbol not in self.managed_symbols:
            return
        
        position = self.positions.get(trade_data.vt_symbol)
        if not position:
            return
        
        if trade_data.offset == Offset.OPEN:
            position.volume += trade_data.volume
        else:
            position.volume -= trade_data.volume
            if position.volume <= 0:
                position.is_closed = True
                position.close_time = datetime.now()
    
    def update_from_position(self, position_data: PositionData):
        """
        根据持仓数据检测手动平仓 (由应用层调用)
        """
        if position_data.vt_symbol not in self.managed_symbols:
            return
        
        position = self.positions.get(position_data.vt_symbol)
        if not position:
            return
        
        if position_data.volume < position.volume:
            manual_volume = position.volume - position_data.volume
            position.volume = position_data.volume
            position.is_manually_closed = True
            
            if position.volume <= 0:
                position.is_closed = True
                position.close_time = datetime.now()
            
            self.domain_events.append(ManualCloseDetectedEvent(
                vt_symbol=position_data.vt_symbol,
                volume=manual_volume
            ))
    
    # ========== 持仓管理接口 ==========
    
    def create_position(self, option_vt_symbol: str, 
                       underlying_vt_symbol: str,
                       signal_type: SignalType, 
                       target_volume: float) -> Position:
        """创建新持仓"""
        position = Position(
            vt_symbol=option_vt_symbol,
            underlying_vt_symbol=underlying_vt_symbol,
            signal_type=signal_type,
            volume=0,
            target_volume=target_volume,
            create_time=datetime.now(),
            is_closed=False
        )
        self.positions[option_vt_symbol] = position
        self.managed_symbols.add(option_vt_symbol)
        return position
    
    def get_positions_by_underlying(self, underlying_vt_symbol: str) -> List[Position]:
        """获取某期货标的下的所有活跃持仓"""
        return [
            p for p in self.positions.values()
            if p.underlying_vt_symbol == underlying_vt_symbol 
            and not p.is_closed
            and p.volume > 0
        ]
    
    def has_pending_close(self, position: Position) -> bool:
        """检查是否有进行中的平仓订单"""
        for order in self.pending_orders.values():
            if order.vt_symbol == position.vt_symbol and order.offset != Offset.OPEN:
                if order.status in [Status.SUBMITTING, Status.NOTTRADED, Status.PARTTRADED]:
                    return True
        return False
    
    def pop_domain_events(self) -> List[DomainEvent]:
        """获取并清空领域事件"""
        events = self.domain_events.copy()
        self.domain_events.clear()
        return events
```

---

### 4. Demand Interface (需求方接口)

位置: `src/strategy/domain/demand_interface/`

#### 4.8.1 IMarketDataGateway / IAccountGateway / ITradeExecutionGateway

职责: 定义领域层对外部能力的需求（行情/资金/交易执行）。应用层依赖这些接口，基础设施层基于 VnPy 上下文实现。

```python
class IMarketDataGateway(ABC):
    @abstractmethod
    def subscribe(self, vt_symbol: str) -> None:
        pass

class IAccountGateway(ABC):
    @abstractmethod
    def get_balance(self) -> float:
        pass

class ITradeExecutionGateway(ABC):
    @abstractmethod
    def send_order(self, instruction: OrderInstruction) -> List[str]:
        pass
```

## 五、应用层设计

### 5.1 VolatilityTrade (应用层服务)

位置: `src/strategy/application/volatility_trade.py`

职责:
1. 编排两个聚合根的协作
2. 调用领域服务计算指标
3. 将领域事件转换为 VnPy Event
4. 协调开仓/平仓业务流程

```
class VolatilityTrade:
    """波动率策略应用服务"""
    
    def __init__(self, strategy_context: Any):
        """
        初始化应用服务
        
        Args:
            strategy_context: 接口层传入的策略实例 (StrategyTemplate)
                              用于获取 EventEngine 和作为 Gateway 的底层实现
        """
        # 1. 基础设施初始化
        # 将 strategy_context 传递给网关适配器，使其具备订阅/查询/下单能力
        self.market_gateway = VnpyMarketDataGateway(strategy_context)
        self.account_gateway = VnpyAccountGateway(strategy_context)
        self.exec_gateway = VnpyTradeExecutionGateway(strategy_context)
        
        # 获取 EventEngine 用于发布事件 (通过 strategy_engine)
        self.event_engine = strategy_context.strategy_engine.event_engine
        
        # 记录 strategy_name 用于日志/告警
        self.strategy_name = strategy_context.strategy_name
        
        # 2. 领域聚合根初始化
        self.target_aggregate = TargetInstrumentAggregate()
        self.position_aggregate = PositionAggregate()
        
        # 3. 状态缓存初始化
        self.ema_states: Dict[str, EMAState] = {}
        self.td_states: Dict[str, TDValue] = {}
        self.macd_history: Dict[str, List[MACDValue]] = {}
    
    # ========== 接口层调用的方法 ==========
    
    def handle_bar_update(self, bar_data: BarData):
        """
        处理K线更新 (由接口层的 on_window_bar 调用)
        
        编排流程:
        1. 更新聚合根数据
        2. 调用领域服务计算指标
        3. 调用领域服务检查信号
        4. 执行交易逻辑
        5. 处理领域事件
        """
        vt_symbol = bar_data.vt_symbol
        
        # 1. 更新行情数据
        self.target_aggregate.update_bar(bar_data)
        
        # 2. 计算指标 (调用领域服务)
        bars = self.target_aggregate.get_bar_history(vt_symbol, 50)
        
        macd_value, ema_state = IndicatorService.calculate_macd(
            bars, self.ema_states.get(vt_symbol)
        )
        self.ema_states[vt_symbol] = ema_state
        self.macd_history.setdefault(vt_symbol, []).append(macd_value)
        
        td_value, td_state = IndicatorService.calculate_td(
            bars, self.td_states.get(vt_symbol)
        )
        self.td_states[vt_symbol] = td_state
        
        # 3. 检查钝化/背离状态 (调用领域服务)
        instrument = self.target_aggregate.get_instrument(vt_symbol)
        
        dullness = SignalService.check_dullness(
            bars, self.macd_history[vt_symbol], instrument.dullness_state
        )
        divergence = SignalService.check_divergence(
            bars, self.macd_history[vt_symbol], dullness, instrument.divergence_state
        )
        
        # 4. 更新聚合根状态
        self.target_aggregate.update_indicators(
            vt_symbol, macd_value, td_value, dullness, divergence
        )
        
        # 5. 检查并执行交易
        self._check_and_execute_close(vt_symbol, dullness, divergence, td_value)
        self._check_and_execute_open(vt_symbol, dullness, divergence, td_value)
        
        # 6. 处理领域事件
        self._publish_domain_events()
    
    def handle_order_update(self, order_data: OrderData):
        """处理订单更新"""
        self.position_aggregate.update_from_order(order_data)
        self._publish_domain_events()
    
    def handle_trade_update(self, trade_data: TradeData):
        """处理成交更新"""
        self.position_aggregate.update_from_trade(trade_data)
        self._publish_domain_events()
    
    def handle_position_update(self, position_data: PositionData):
        """处理持仓更新"""
        self.position_aggregate.update_from_position(position_data)
        self._publish_domain_events()
    
    # ========== 私有方法 ==========
    
    def _check_and_execute_open(self, vt_symbol, dullness, divergence, td_value):
        """检查并执行开仓"""
        open_signal = SignalService.check_open_signal(dullness, divergence, td_value)
        if not open_signal:
            return
        
        # 选择期权合约
        option_contract = self._select_option(vt_symbol, open_signal)
        if not option_contract:
            return
        
        # 决策: 调用 PositionSizingService 生成指令 (Tell, Don't Ask)
        # PositionAggregate 负责提供当前持仓状态供决策参考
        instruction = PositionSizingService.make_open_decision(
            account_balance=self._get_balance(),
            signal_type=open_signal,
            contract_price=计算价格,
            current_positions=self.position_aggregate.get_active_positions()
        )
        
        if instruction:
            # 更新聚合根 (预先记录意图或创建占位持仓)
            self.position_aggregate.create_position(
                option_vt_symbol=option_contract.vt_symbol,
                underlying_vt_symbol=vt_symbol,
                signal_type=open_signal,
                target_volume=instruction.volume
            )
            
            # 执行: 调用 Gateway 下单 (Side Effect)
            # 使用 ITradeExecutionGateway 接口方法 send_order
            self.exec_gateway.send_order(instruction)
            
            # 发布事件
            self._publish_alert("open_signal", f"开仓信号: {open_signal.value}", vt_symbol, instruction.volume)
    
    def _check_and_execute_close(self, underlying_vt_symbol, dullness, divergence, td_value):
        """检查并执行平仓"""
        positions = self.position_aggregate.get_positions_by_underlying(underlying_vt_symbol)
        
        for position in positions:
            close_signal = SignalService.check_close_signal(
                position, dullness, divergence, td_value
            )
            if not close_signal:
                continue
            if self.position_aggregate.has_pending_close(position):
                continue
            
            # 下单
            # 构造平仓指令 (假设全平，卖权策略平仓为买入平仓)
            instruction = OrderInstruction(
                direction=Direction.LONG, 
                offset=Offset.CLOSE,
                volume=position.volume,
                price=0 # TODO: 获取当前盘口价格
            )
            self.exec_gateway.send_order(instruction)
            
            # 发布事件
            self._publish_alert("close_signal", f"平仓信号: {close_signal.value}", 
                              position.vt_symbol, position.volume)
    
    def _publish_domain_events(self):
        """将领域事件转换为 VnPy Event 并发布"""
        events = self.position_aggregate.pop_domain_events()
        
        for domain_event in events:
            if isinstance(domain_event, ManualCloseDetectedEvent):
                alert_data = StrategyAlertData(
                    strategy_name=self.strategy_name,
                    alert_type="manual_close",
                    message=f"检测到手动平仓",
                    timestamp=datetime.now(),
                    vt_symbol=domain_event.vt_symbol,
                    volume=domain_event.volume
                )
            elif isinstance(domain_event, ManualOpenDetectedEvent):
                alert_data = StrategyAlertData(
                    strategy_name=self.strategy_name,
                    alert_type="manual_open",
                    message=f"检测到手动开仓",
                    timestamp=datetime.now(),
                    vt_symbol=domain_event.vt_symbol,
                    volume=domain_event.volume
                )
            # ... 其他事件类型
            
            vnpy_event = Event(type=EVENT_STRATEGY_ALERT, data=alert_data)
            self.event_engine.put(vnpy_event)
    
    def _publish_alert(self, alert_type: str, message: str, vt_symbol: str = "", volume: float = 0):
        """发布告警事件"""
        alert_data = StrategyAlertData(
            strategy_name=self.strategy_name,
            alert_type=alert_type,
            message=message,
            timestamp=datetime.now(),
            vt_symbol=vt_symbol,
            volume=volume
        )
        event = Event(type=EVENT_STRATEGY_ALERT, data=alert_data)
        self.event_engine.put(event)
    
    def _select_option(self, underlying_vt_symbol: str, signal_type: SignalType):
        """选择期权合约 (虚值四档)"""
        # 根据 signal_type 判断认沽/认购
        # 调用 main_engine.get_all_contracts() 筛选
        # 返回虚值四档合约
        ...
```

### 5.2 交易执行模型 (The Decider/Doer Pattern)

**设计哲学**: 遵循 "Tell, Don't Ask" 原则，同时保持领域层纯净。

**核心矛盾**:
- **Tell, Don't Ask**: 业务逻辑（能不能开仓，开多少）应封装在领域对象内部。应用层不应询问状态后自己做决定。
- **Domain Purity**: 领域对象不能直接持有 `Gateway` 进行下单（副作用），否则难以测试且污染模型。

**解决方案 (Decider/Doer 模式)**:

1.  **The Decider (领域层)**:
    - 职责: 接收信号，结合当前持仓和资金，计算**交易意图 (OrderInstruction)**。
    - 特性: 纯逻辑，无副作用。
    - 实现: `PositionSizingService` 提供 `make_open_decision` 方法，返回 `OrderInstruction`。
    
2.  **The Doer (应用层)**:
    - 职责: 拿到 `OrderInstruction`，调用 `Gateway` 执行副作用。
    - 特性: 负责编排，不包含业务判断逻辑。
    - 实现: `VolatilityTrade` 调用 `self.exec_gateway.send_order(instruction)`。

**伪代码示例**:

```python
# 应用层 (Doer)
def on_bar(self):
    # 1. 获取信号
    signal = self.signal_service.check_signal(self.instrument)
    
    # 2. Tell: 调用仓位服务进行决策
    instruction = PositionSizingService.make_open_decision(
        account_balance=self.balance,
        signal_type=signal,
        contract_price=current_price,
        current_positions=self.position_aggregate.positions
    )
    
    # 3. Do: 如果产生了指令，去执行 (副作用)
    if instruction:
        self.exec_gateway.send_order(instruction)
```

**PositionSizingService**:
- 这是一个独立的无状态领域服务，专注于回答 "买多少" 和 "能不能买" 的问题。

---

## 六、基础设施层设计 (Infrastructure Layer)

**设计原则**:
采用 "Context Injection" 模式。网关适配器不直接持有 `MainEngine`，而是持有 `StrategyEntry` (作为 `strategy_context`)。
这使得我们可以直接调用 `PortfolioStrategy` 模板提供的 `buy`, `sell`, `short`, `cover` 方法，这些方法已经内置了对 `StrategyEngine` 的调用和复杂的订单路由逻辑（如锁仓/净仓处理、目标仓位管理）。

### 6.2 网关适配器实现

位置: `src/strategy/infrastructure/gateway/`

职责: 实现需求方接口，将订阅/查询/下单等调用适配到 VnPy 的引擎与策略模板方法。

**依赖关系说明**:
`StrategyEntry` (Interface) -> `VolatilityTrade` (Application) -> `Vnpy*Gateway` (Infrastructure)。
在 `StrategyEntry.on_init` 中，将 `self`（策略实例）传递给 `VolatilityTrade`，后者将其传递给各个网关适配器。

```python
# src/strategy/infrastructure/gateway/vnpy_trade_execution_gateway.py
class VnpyTradeExecutionGateway(ITradeExecutionGateway):
    def __init__(self, strategy_context: Any):
        self.context = strategy_context

    def send_order(self, instruction: OrderInstruction) -> List[str]:
        return self.context.buy/sell/short/cover(...)
```

### 6.2 FeishuEventHandler (飞书通知处理器)

位置: `src/strategy/infrastructure/reporting/feishu_handler.py`

职责: 订阅 VnPy 的事件引擎，处理策略告警事件并发送飞书消息。

```python
class FeishuEventHandler:
    """飞书事件处理器 - 注册到 VnPy EventEngine"""
    
    def __init__(self, webhook_url: str, strategy_name: str):
        self.webhook_url = webhook_url
        self.strategy_name = strategy_name
    
    def handle_alert_event(self, event: Event):
        """处理策略告警事件"""
        data: StrategyAlertData = event.data
        
        # 只处理本策略的事件
        if data.strategy_name != self.strategy_name:
            return
        
        message = self._format_message(data)
        self._send_feishu(message)
    
    def _format_message(self, data: StrategyAlertData) -> str:
        """格式化飞书消息"""
        templates = {
            "manual_open": f"⚠️ 检测到手动开仓 {data.vt_symbol} {data.volume}手，程序不会自动平仓",
            "manual_close": f"📝 检测到手动平仓 {data.vt_symbol} {data.volume}手，已自动匹配",
            "order_cancelled": f"❌ 平仓订单被撤单: {data.message}",
            "order_rejected": f"🚫 平仓订单被拒单: {data.message}",
            "open_signal": f"📈 开仓信号触发: {data.message}",
            "close_signal": f"📉 平仓信号触发: {data.message}",
        }
        return templates.get(data.alert_type, data.message)
    
    def _send_feishu(self, message: str):
        """发送飞书消息"""
        import requests
        payload = {
            "msg_type": "text",
            "content": {"text": f"[{self.strategy_name}] {message}"}
        }
        try:
            requests.post(self.webhook_url, json=payload, timeout=5)
        except Exception as e:
            # 避免日志循环，这里只简单打印或忽略
            print(f"Feishu send failed: {e}")
```

### 6.3 实例传递路径 (Dependency Injection Path)

**核心原则**: `strategy` 实例 (即 VnPy 的接口对象) 从接口层传递到应用层，再由应用层传递给基础设施层。**不需要经过领域层 (Domain Layer)**。

传递路径如下:

1.  **Interface Layer (起点)**:
    - `StrategyEntry` (策略入口类) 在 `on_init` 中创建应用服务 `VolatilityTrade`。
    - 它将 `self` (即 `PortfolioStrategy` 实例) 传递给 `VolatilityTrade`。

2.  **Application Layer**:
    - `VolatilityTrade` (应用服务) 接收 `strategy_context` (即 `self`)。
    - 它负责创建基础设施层的网关适配器，并将 `strategy_context` 传递给它们。
    - *注意*: 应用层持有这些网关实例用于后续的订阅/查询/下单。

3.  **Infrastructure Layer (终点 - 脏活累活)**:
    - 网关适配器接收 `strategy_context`。
    - 交易执行通过 `strategy_context.buy/sell/short/cover`，行情与合约查询通过 `strategy_context.strategy_engine.main_engine`。

4.  **Domain Layer (纯净区)**:
    - `SignalService`, `PositionSizingService`, `TargetInstrument` 等对象**完全不知道** `strategy` 或 `engine` 的存在。
    - 它们只处理纯数据 (Entity, Value Object) 和业务逻辑。

```
StrategyEntry (Interface)
       │
       ▼ 1. 创建并传递 self
VolatilityTrade (Application) ────────┐
       │                              │
       ▼ 2. 创建并传递 self           │
Vnpy*Gateway (Infrastructure) <───┘
       │
       ▼ 3. 后续调用 (通过 Gateway 接口)
VolatilityTrade (Application)
       │
       ▼ 4. 调用纯逻辑方法
Domain Layer (SignalService, TargetInstrument...)
```

---

## 七、接口层设计 (Interface Layer / Adapter)

### 7.1 StrategyEntry (策略入口)

位置: `src/strategy/strategy_entry.py`

职责:
1.  **组装**: 在 `on_init` 中实例化 Application Layer (并将 `self` 传递给它)。
2.  **适配**: 将 VnPy 的 `on_bars`, `on_trade` 等回调转换为 Application Layer 的调用。

```python
class StrategyEntry(StrategyTemplate):
    
    def __init__(self, strategy_engine, strategy_name, vt_symbols, setting):
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)
        
        self.app_service = None
        # 网关由 app_service 内部管理
        
    def on_init(self):
        self.logger.info("策略初始化...")
        
        # 1. 初始化应用服务 (注入 self)
        # 依赖注入路径: Strategy(self) -> VolatilityTrade -> Vnpy*Gateway
        # 应用服务内部负责实例化 Gateway，从而保持接口层简洁
        self.app_service = VolatilityTrade(
            strategy_context=self,
            indicator_service=IndicatorService(),
            signal_service=SignalService(),
            # 可以在此注入 PositionSizingService
        )
        
        self.logger.info("应用服务组装完成")

    def on_bars(self, bars: Dict[str, BarData]):
        # 适配器模式: 转发给应用层
        if self.app_service:
            self.app_service.handle_bars(bars)
            
    def on_trade(self, trade: TradeData):
        if self.app_service:
            self.app_service.handle_trade_update(trade)
```

---

## 八、Todo List (开发计划)

---

## 九、重要设计约束

> [!IMPORTANT]
> **`on_` 前缀仅用于接口层**
> - 接口层: `on_init`, `on_bars`, `on_window_bar`, `on_start`, `on_stop`
> - 应用层: `handle_bar_update`, `handle_order_update`
> - 聚合根: `update_bar`, `update_from_order`, `update_indicators`

> [!IMPORTANT]
> **聚合根保持纯净**
> - TargetInstrumentAggregate: 只做数据存储和查询
> - 所有计算逻辑委托给 IndicatorService 和 SignalService
> - 应用层负责调用领域服务并更新聚合根

> [!IMPORTANT]
> **事件驱动飞书通知**
> - 聚合根产生领域事件 (DomainEvent)
> - 应用层转换为 VnPy Event 并 put() 到 EventEngine
> - FeishuEventHandler 通过 register() 订阅并处理

