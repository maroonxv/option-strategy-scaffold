# 使用 vnpy_paperaccount 进行本地模拟交易方案

## 1. 目标
集成 `vnpy_paperaccount` 模块，替代目前简陋的“日志拦截式”模拟交易。实现真实的**本地撮合**功能，能够根据实时行情模拟订单的成交、持仓变化和资金盈亏，从而更准确地验证策略逻辑。

## 2. 现状分析
目前项目中的 `--paper` 模式仅是在 `VnpyTradeExecutionGateway` 中拦截了下单请求并打印日志（参见 `src/strategy/infrastructure/gateway/vnpy_trade_execution_gateway.py`）。
*   **缺点**：无法模拟成交回报、无法更新持仓状态、无法测试平仓逻辑（因为没持仓）。
*   **需求**：需要一个本地仿真网关，接收 CTP 行情，但在本地维护账户和撮合订单。

## 3. 架构设计

### 3.1 核心组件
*   **PaperAccountApp**: VnPy 官方提供的本地模拟交易模块。它会注册一个 `PaperGateway`。
*   **CTP Gateway**: 仅作为**行情源** (Market Data Provider)，不用于交易。
*   **PaperGateway**: 作为**交易网关** (Trade Execution Provider)，负责接收策略订单并进行本地撮合。

### 3.2 数据流向
1.  **行情**: CTP Server -> `CtpGateway` -> `MainEngine` -> `Strategy` & `PaperAccountApp`
2.  **交易**: `Strategy` -> `PaperGateway` -> `PaperAccountApp` (本地撮合) -> `Strategy` (OnTrade/OnOrder)

## 4. 实施步骤

### 4.1 依赖安装
确保环境中已安装 `vnpy_paperaccount`。
```bash
pip install vnpy_paperaccount
```

### 4.2 修改 `src/main/child_process.py`

需要在初始化引擎时加载 `PaperAccountApp`，并根据配置决定是否启用。

**伪代码：**

```python
# src/main/child_process.py

def _init_engines(self) -> None:
    # ... 原有代码 ...
    self.main_engine = MainEngine(self.event_engine)
    
    # [新增] 加载 PaperAccountApp
    # 注意：必须在添加 Gateway 之前加载 App，因为 App 可能会注册 Gateway
    if self.paper_trading:
        try:
            from vnpy_paperaccount import PaperAccountApp
            self.main_engine.add_app(PaperAccountApp)
            self.logger.info("已加载 PaperAccountApp (本地模拟交易)")
        except ImportError:
            self.logger.error("未安装 vnpy_paperaccount，无法启用高级模拟交易！")

    # ... 原有 Gateway 初始化 ...
    self.gateway_manager = GatewayManager(self.main_engine)
    # 注意：这里需要修改 GatewayManager 的逻辑，稍后说明
```

### 4.3 修改 `src/main/gateway.py`

`GatewayManager` 需要支持根据模式选择加载哪些网关。
*   **实盘模式**: 加载 CTP Gateway (用于行情和交易)。
*   **模拟模式**: 加载 CTP Gateway (仅用于行情) + Paper Gateway (用于交易)。
*   **注意**: `vnpy_paperaccount` 会自动注册一个名为 `PAPER` 的网关。我们需要确保策略连接到这个 `PAPER` 网关，而不是 `CTP` 网关进行交易。

**伪代码：**

```python
# src/main/gateway.py

class GatewayManager:
    def connect_all(self, use_paper_trading=False):
        """
        连接网关
        Args:
            use_paper_trading: 是否启用模拟交易
        """
        # 1. 连接 CTP (作为行情源)
        # 即使是模拟交易，也需要 CTP 的行情
        self.connect_gateway("ctp") 
        
        # 2. 连接 Paper Gateway (作为交易柜台)
        if use_paper_trading:
            # Paper Gateway 不需要外部配置，直接连接即可
            # VnPy 的 PaperAccountApp 会自动注册 "PAPER" 网关
            if self.main_engine.get_gateway("PAPER"):
                self.main_engine.connect({}, "PAPER")
                self.logger.info("已连接 PAPER 网关 (本地撮合)")
            else:
                self.logger.error("PAPER 网关未找到，请检查 PaperAccountApp 是否加载")
```

### 4.4 策略层的适配 (`StrategyEntry`)

VnPy 的 `StrategyTemplate` 默认会向所有连接的网关发单，或者需要指定 `gateway_name`。
在 `PaperAccountApp` 模式下，存在两个网关：`CTP` 和 `PAPER`。
*   策略需要知道向哪个网关发单。
*   通常 VnPy 的 `OmsEngine` 或策略基类会自动处理，但在多网关环境下，最好明确指定。

**策略配置调整**:
我们需要确保策略引用的 `vt_symbol` 使用正确的网关后缀，或者策略发单时指定网关。
*   **行情**: 来自 CTP，所以 `vt_symbol` 格式为 `rb2405.SHFE` (此时 gateway_name 通常是 CTP，但 `vt_symbol` 里的 exchange 后缀由 `ContractData` 决定，gateway 信息在 `ContractData.gateway_name`)。
*   **交易**: 发往 PAPER。

**关键点**: `vnpy_paperaccount` 的设计是——它会监听全市场的行情（来自 CTP），当收到发往 `PAPER` 网关的订单时，利用 CTP 的行情进行撮合。

**修改 `src/strategy/application/volatility_trade.py`**:
目前 `VnpyTradeExecutionGateway` 并没有指定网关名称。需要修改它，使其在模拟模式下，将订单发往 `PAPER` 网关。

```python
# src/strategy/infrastructure/gateway/vnpy_trade_execution_gateway.py

class VnpyTradeExecutionGateway:
    def send_order(self, instruction):
        # ...
        
        # [修改] 获取目标网关名称
        # 如果是模拟模式，且已加载 PaperAccount，则目标是 "PAPER"
        # 否则默认发给合约所属的网关 (CTP)
        target_gateway = "PAPER" if self.context.paper_trading else None 
        
        # 调用策略的下单接口
        # VnPy 的 buy/sell 方法通常不接受 gateway_name 参数，它们默认发给合约所属的网关。
        # 这是一个潜在问题：合约是 CTP 的，默认会发给 CTP。
        
        # 解决方案 A: 使用特定的 converter 将 CTP 合约转换为 PAPER 合约 (复杂)
        # 解决方案 B: (推荐) 拦截下单请求，直接调用 main_engine.send_order 并指定 gateway="PAPER"
        
        if self.context.paper_trading:
             # 构造 OrderRequest
             req = OrderRequest(
                 symbol=symbol,
                 exchange=exchange,
                 direction=direction,
                 type=OrderType.LIMIT,
                 volume=volume,
                 price=price,
                 offset=offset,
                 reference=f"{PROJECT_NAME}_PAPER"
             )
             # 强制发给 PAPER 网关
             vt_orderid = self.context.strategy_engine.main_engine.send_order(req, "PAPER")
             return [vt_orderid]
        else:
             # 原有逻辑，发给 CTP
             # ...
```

### 4.5 CTP 端口配置

CTP 的配置方式**保持不变**，依然使用 `.env` 文件配置 SimNow 或实盘账号。
因为 `vnpy_paperaccount` 依然依赖 CTP 提供实时行情数据来进行撮合。

```ini
# .env 示例
CTP_TD_ADDRESS=tcp://180.168.146.187:10101
CTP_MD_ADDRESS=tcp://180.168.146.187:10131
CTP_USERID=...
CTP_PASSWORD=...
CTP_BROKERID=9999
CTP_APP_ID=simnow_client_test
CTP_AUTH_CODE=0000000000000000
```

## 5. 总结

1.  **配置**: 保持 `.env` 配置 CTP 信息不变。
2.  **启动**: 加载 `PaperAccountApp`。
3.  **连接**: 同时连接 `CTP` (只看行情) 和 `PAPER` (只做交易)。
4.  **交易**: 策略端的 `ExecutionGateway` 需要识别模式，将订单强制路由到 `PAPER` 网关。

这样就能在不消耗真实/仿真账户资金的情况下，利用真实行情进行完整的策略闭环测试。
