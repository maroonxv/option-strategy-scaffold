# 功能设计文档：期货合约动态管理 (Check and Update Future Contract)

## 1. 需求背景

策略需要实现全自动的“主力合约”切换，以适应长期运行。根据用户的最新指示，**完全抛弃基于持仓量（Open Interest）的判断逻辑**，改为基于**到期日**的刚性规则。

### 1.1 核心规则 (The 7-Day Rule)
对于任意期货品种（如 `rb`）：
1.  **识别候选合约**：获取该品种所有可用合约，按合约代码（隐含时间顺序）排序。
2.  **定位当月合约**：排序后的第一个合约（即最近到期的合约）。
3.  **判断逻辑**：
    *   如果 **(当月合约到期日 - 当前日期) > 7天**：交易 **当月合约**。
    *   如果 **(当月合约到期日 - 当前日期) <= 7天**：交易 **次月合约**（排序后的第二个合约）。

### 1.2 目标
*   **启动时**：读取 `trading_target.yaml`，根据上述规则自动选择并订阅合约。
*   **盘中**：每日检查一次（如收盘前），若满足换月条件，自动切换标的。

## 2. 架构设计 (DDD)

本设计遵循现有的 DDD 分层架构，引入新的领域服务来封装合约选择逻辑，并在应用层进行流程编排。

### 2.1 领域层 (Domain Layer)

#### 2.1.1 `FutureSelectionService` (新增领域服务)
*   **职责**：纯粹的计算与规则判断逻辑。输入一堆合约和当前时间，输出“应该交易哪一个”。
*   **位置**：`src/strategy/domain/domain_service/future_selection_service.py`
*   **核心接口**：
    ```python
    class FutureSelectionService:
        def select_dominant_contract(
            self, 
            contracts: List[ContractData], 
            current_date: datetime
        ) -> Optional[ContractData]:
            """
            根据规则选择主力合约
            规则:
            1. 筛选出该品种的所有合约
            2. 按合约代码/到期日排序
            3. 检查当月合约到期日
               - 若 > 7天: 返回当月
               - 若 <= 7天: 返回次月
            """
            pass
    ```

    作为参考，以下是vnpy的ContractData类：
    @dataclass
    class ContractData(BaseData):
        """
        Contract data contains basic information about each contract traded.
        """

        symbol: str
        exchange: Exchange
        name: str
        product: Product
        size: float
        pricetick: float

        min_volume: float = 1                   # minimum order volume
        max_volume: float | None = None         # maximum order volume
        stop_supported: bool = False            # whether server supports stop order
        net_position: bool = False              # whether gateway uses net position volume
        history_data: bool = False              # whether gateway provides bar history data

        option_strike: float | None = None
        option_underlying: str | None = None     # vt_symbol of underlying contract
        option_type: OptionType | None = None
        option_listed: Datetime | None = None
        option_expiry: Datetime | None = None
        option_portfolio: str | None = None
        option_index: str | None = None          # for identifying options with same strike price

        def __post_init__(self) -> None:
            """"""
            self.vt_symbol: str = f"{self.symbol}.{self.exchange.value}"

#### 2.1.2 `TargetInstrumentAggregate` (标的聚合根增强)
*   **职责**：统一管理所有标的的状态，包括“当前正在交易哪个合约”。
*   **位置**：`src/strategy/domain/aggregate/target_instrument_aggregate.py`
*   **增强**：
    *   新增方法 `get_active_contract(product_code: str) -> Optional[str]`: 获取某品种当前的主力合约代码。
    *   新增方法 `set_active_contract(product_code: str, vt_symbol: str)`: 更新某品种的主力合约。
    *   新增方法 `get_all_active_contracts() -> List[str]`: 获取所有正在交易的合约列表。
*   **状态管理**：替代应用层原本打算维护的 `_active_contracts` 字典。

#### 2.1.3 `IMarketDataGateway` (复用接口)
*   **职责**：提供全市场合约查询能力。
*   **位置**：`src/strategy/domain/demand_interface/market_data_interface.py`
*   **接口保持**：使用现有的 `get_all_contracts()`。

### 2.2 基础设施层 (Infrastructure Layer)

#### 2.2.1 `VnpyMarketDataGateway` (实现增强)
*   **位置**：`src/strategy/infrastructure/gateway/vnpy_market_data_gateway.py`
*   **实现**：
    *   `get_all_contracts()`: 确保能从 `main_engine` 获取并返回所有合约对象。
    *   *注*：不再需要 `get_contract_open_interest` 或临时订阅逻辑。

### 2.3 应用层 (Application Layer)

#### 2.3.1 `VolatilityTrade` (应用服务)
*   **位置**：`src/strategy/application/volatility_trade.py`
*   **新增方法**：
    *   `handle_universe_initialization(target_products: List[str])`: 启动时调用，执行初始选合约逻辑。
    *   `handle_universe_rollover_check(current_time: datetime)`: 盘中调用，检查是否换月。
*   **流程编排**：
    1.  调用 Gateway 获取全市场合约列表。
    2.  对于每个品种，筛选出候选合约列表。
    3.  调用 `FutureSelectionService`，传入合约列表和当前时间。
    4.  确定主力后，调用 `TargetInstrumentAggregate.set_active_contract(product, vt_symbol)` 更新当前交易的主力合约状态，并订阅新合约（退订旧合约）。

### 2.4 接口层 (Interface Layer)

#### 2.4.1 `StrategyEntry` (策略入口)
*   **位置**：`src/strategy/strategy_entry.py`
*   **改动**：
    *   **`on_start`**: 
        1.  调用 `ConfigLoader.load_target_products()` 读取品种列表。
        2.  调用 `app_service.handle_universe_initialization()`。
    *   **`on_bars`**: 
        *   在收到 K 线推送时，检查当前时间。
        *   **定时检查**：若时间为 **14:50** (收盘前)，且当天尚未检查过，则调用 `app_service.handle_universe_rollover_check()` 执行换月检查。
        *   引入 `self.rollover_check_done` 标志位防止重复触发。

### 2.5 工具类 (Utils)

#### 2.5.1 `ConfigLoader` (配置加载器)
*   **位置**：`src/main/utils/config_loader.py`
*   **改动**：
    *   新增静态方法 `load_target_products(path: str = "config/general/trading_target.yaml") -> List[str]`: 专门用于加载品种列表。

#### 2.5.2 `ContractUtils` (新增日期解析工具)
*   **位置**：`src/main/utils/contract_utils.py`
*   **职责**：
    *   `get_expiry_from_symbol(symbol: str) -> date`: 解析合约代码（如 `rb2501`）获取到期日。

---

## 3. 详细实现计划

### 步骤 1: 工具类实现
1.  在 `ConfigLoader` 中添加 `load_target_products` 方法。
2.  创建 `ContractUtils` 类，实现 `get_expiry_from_symbol` 方法，支持常见期货代码格式解析。

### 步骤 2: 领域模型增强
1.  创建 `FutureSelectionService`：实现“排序 + 7天规则”逻辑。
2.  修改 `TargetInstrumentAggregate`：增加对 active contracts 的状态管理。

### 步骤 3: 应用层编排 (`VolatilityTrade`)
实现 `handle_universe_initialization` 和 `handle_universe_rollover_check`，串联获取合约、调用服务、更新状态、管理订阅的流程。

### 步骤 4: 策略入口接入 (`StrategyEntry`)
在 `on_start` 中调用初始化逻辑，在 `on_bars` 或定时器中调用检查逻辑。

---

## 4. 关键代码片段预览

### 4.1 ConfigLoader (增强)

```python
    @staticmethod
    def load_target_products(path: str = "config/general/trading_target.yaml") -> List[str]:
        """
        加载交易目标品种列表
        
        Args:
            path: 配置文件路径
            
        Returns:
            品种代码列表 (e.g. ['rb', 'm'])
        """
        # 处理相对路径，确保基于项目根目录
        if not os.path.isabs(path):
             # 获取项目根目录逻辑
             pass
        return ConfigLoader.load_yaml(path)
```

### 4.2 ContractUtils (新增)

```python
import re
from datetime import date

class ContractUtils:
    @staticmethod
    def get_expiry_from_symbol(symbol: str) -> Optional[date]:
        """
        从合约代码解析到期日
        示例: rb2501 -> 2025-01-15 (估算)
        """
        # 提取末尾数字
        match = re.search(r"(\d{3,4})$", symbol)
        if not match:
            return None
            
        digits = match.group(1)
        # 处理年份和月份
        if len(digits) == 3: # 如 A001 (很少见，假设是年1位月2位?) 或者其他格式，需根据交易所规则
             # 这里简化处理常见的 4位 (2501) 或 3位 (501)
             pass 
        
        year_suffix = int(digits[:-2])
        month = int(digits[-2:])
        
        year = 2000 + year_suffix # 假设2000年后
        
        # 默认设为该月中旬，或者1日，用于保守计算
        try:
            return date(year, month, 15)
        except ValueError:
            return None
```

### 4.3 FutureSelectionService (规则实现)

```python
class FutureSelectionService:
    def select_dominant_contract(
        self, 
        contracts: List[ContractData], 
        current_date: date
    ) -> Optional[ContractData]:
        
        # 1. 筛选与排序 (按 symbol 字母序，通常等同于时间序)
        sorted_contracts = sorted(contracts, key=lambda c: c.symbol)
        if not sorted_contracts:
            return None

        # 2. 定位当月合约 (第一个)
        current_month_contract = sorted_contracts[0]
        
        # 3. 解析到期日
        expiry_date = ContractUtils.get_expiry_from_symbol(current_month_contract.symbol)
        if not expiry_date:
            # 解析失败，保守策略：就做当月，或者报错
            return current_month_contract
            
        # 4. 7天规则判断
        days_to_expiry = (expiry_date - current_date).days
        
        if days_to_expiry > 7:
            return current_month_contract
        else:
            # 切换到次月
            if len(sorted_contracts) > 1:
                return sorted_contracts[1]
            else:
                return current_month_contract
```

### 4.4 TargetInstrumentAggregate (状态管理)

```python
class TargetInstrumentAggregate:
    def __init__(self):
        self._active_contracts: Dict[str, str] = {} # product -> vt_symbol
        
    def set_active_contract(self, product: str, vt_symbol: str):
        self._active_contracts[product] = vt_symbol
        
    def get_active_contract(self, product: str) -> Optional[str]:
        return self._active_contracts.get(product)
        
    def get_all_active_contracts(self) -> List[str]:
        return list(self._active_contracts.values())
```

### 4.5 VolatilityTrade (应用服务编排)

```python
def handle_universe_initialization(self, target_products: List[str]):
    all_contracts = self.market_gateway.get_all_contracts()
    current_date = datetime.now().date() # 或从外部传入
    
    for product in target_products:
        # 1. 筛选
        product_contracts = [c for c in all_contracts if self._is_contract_of_product(c, product)]
        
        # 2. 选择
        target_contract = self.future_selection_service.select_dominant_contract(product_contracts, current_date)
        
        if target_contract:
            # 3. 更新状态
            self.target_aggregate.set_active_contract(product, target_contract.vt_symbol)
            # 4. 订阅
            self.market_gateway.subscribe(target_contract.vt_symbol)

def handle_universe_rollover_check(self, current_time: datetime):
    # 逻辑类似 initialization，但增加了“是否变化”的判断
    # 若变化：unsubscribe old, subscribe new
    pass
```

### 4.6 StrategyEntry (策略入口实现)

```python
def on_bars(self, bars: Dict[str, BarData]):
    self.app_service.handle_bars(bars)
    
    # === 换月检查 ===
    # 取当前时间 (假设 bars 中有数据，取第一个 bar 的时间)
    if not bars:
        return
    
    current_dt = list(bars.values())[0].datetime
    
    # 每天 14:50 触发一次
    if current_dt.hour == 14 and current_dt.minute == 50:
        if not self.rollover_check_done:
            self.logger.info(f"触发每日换月检查: {current_dt}")
            self.app_service.handle_universe_rollover_check(current_dt)
            self.rollover_check_done = True
    else:
        # 非检查时间窗口，重置标志位
        self.rollover_check_done = False
```
