# 应用层重构方案 (VolatilityTrade)

## 1. 重构目标
当前 `src/strategy/application/volatility_trade.py` 承担了过多职责，包括生命周期管理、编排、事件转换、风控规则维护以及部分基础设施数据清洗。
本重构旨在遵循 **DDD (领域驱动设计)** 与 **整洁架构** 原则，将非应用层职责剥离，使 `VolatilityTrade` 回归纯粹的 **Application Service (编排者)** 角色。

---

## 2. 持久化方法重构 (`dump_state` / `load_state`)

### 现状问题
- **Schema 泄露**：应用层手动构建包含 `version`, `active_contracts`, `position_aggregate` 等字段的大字典。应用层了解了太多关于“如何存储”的细节。
- **职责不清**：虽然 `StateRepository` 负责了写入文件的原子性，但“保存什么数据”的逻辑依然耦合在应用层。

### 重构方案
- **保留方法**：继续保留 `dump_state` 和 `load_state` 作为生命周期管理的 **触发点 (Trigger)**。
- **改变实现**：
    - 应用层仅作为协调者，调用聚合根或服务的 `to_snapshot()` / `from_snapshot()` 方法。
    - 消除手动构建字典的代码。
    - 示例目标代码：
      ```python
      def dump_state(self, file_path: str):
          snapshot = {
              "target_aggregate": self.target_aggregate.to_snapshot(),
              "position_aggregate": self.position_aggregate.to_snapshot(),
              "metadata": {"saved_at": datetime.now(), "version": 2}
          }
          self.state_repository.save(file_path, snapshot)
      ```

---

## 3. 私有方法重构 (职责剥离)

### A. 建议移出应用层的方法

| 方法名 | 当前问题 | 建议去向 | 详细说明 |
| :--- | :--- | :--- | :--- |
| **`_get_option_contracts`** | 包含大量 Pandas 操作、正则解析、硬编码映射 (IF->IO)。属于**基础设施/数据清洗**逻辑。 | **Infrastructure**: `src/strategy/infrastructure/parsing/contract_helper.py` | 封装为 `ContractHelper.get_option_chain(all_contracts, underlying_symbol)`，应用层负责传入全量合约列表。 |
| **`_is_contract_of_product`** | 简单的字符串匹配工具。 | **Infrastructure**: `src/strategy/infrastructure/parsing/contract_helper.py` | 封装为 `ContractHelper.is_contract_of_product(symbol, product_code)`。 |
| **`_ensure_daily_open_limit_state`** | 维护每日开仓限额状态。属于**风控领域业务规则**。 | **Domain**: `PositionAggregate` | 聚合根应维护其内部的不变性 (Invariants)。风控限额是开仓行为的约束，理应与持仓状态同在。 |
| **`_update_open_limits_from_trade`** | 同上。 | **Domain**: `PositionAggregate` | 实现为 `record_open_usage(vt_symbol, volume)`。 |
| **`_get_reserved_open_volume`** | 同上。 | **Domain**: `PositionAggregate` | 内部风控检查逻辑，无需暴露给应用层，只需暴露 `check_open_limit`。 |

### B. 应当保留在应用层的方法

| 方法名 | 理由 |
| :--- | :--- |
| **`_check_and_execute_open`** | 核心编排逻辑 (Doer)：串联信号、选合约、风控、下单。 |
| **`_check_and_execute_close`** | 核心编排逻辑。 |
| **`_select_option`** | 编排逻辑，调用 `OptionSelectorService`。 |
| **`_publish_domain_events`** | **ACL (防腐层)** 职责：将内部领域事件转换为外部 (VnPy) 事件。 |
| **`_create_alert_from_event`** | 同上，对象转换逻辑。 |

---

## 4. 状态管理重构 (风控状态下沉)

### 现状
应用层直接持有业务状态：
```python
self.daily_open_count_map: Dict[str, int] = {}
self.global_daily_open_count: int = 0
self.last_trading_date = ...
```
这导致应用层变成了“贫血模型”的宿主，业务逻辑泄露。且 `daily_open_count` 与 `position` 分离，破坏了数据的高内聚性。

### 方案：移入 `PositionAggregate`
`PositionAggregate` 将成为一个自包含的“账户/风控单元”，负责管理持仓及相关的风控计数。

**新增接口示例**：
- `check_open_limit(self, vt_symbol: str, volume: int) -> bool`: 检查是否允许开仓。
- `record_open_usage(self, vt_symbol: str, volume: int) -> None`: 记录已使用的开仓额度。
- `on_new_trading_day(self, date: date) -> None`: 重置每日计数器。

---

## 5. 公有方法职责界定

| 方法类型 | 方法名 | 职责说明 |
| :--- | :--- | :--- |
| **生命周期** | `__init__` | 依赖注入组装。 |
| **生命周期** | `dump_state` / `load_state` | 状态恢复与保存的入口。 |
| **业务入口** | `handle_bar_update` | 核心业务驱动入口。 |
| **业务入口** | `handle_order_update` 等 | 交易回报处理入口。 |
| **运维/任务** | `handle_universe_validation` | 定时任务入口，调用领域服务进行合约检查。 |
| **运维/任务** | `resubscribe_active_contracts` | 灾难恢复逻辑。 |

---

## 6. ContractHelper 设计细节 (Infrastructure)

### 设计目标
- **无状态转换器 (Data Adapter)**：屏蔽“VnPy 合约对象如何存储”、“期权代码规则是什么”、“Pandas 如何构建”等细节。

### 接口定义
```python
class ContractHelper:
    @staticmethod
    def get_option_chain(all_contracts, underlying_symbol) -> pd.DataFrame:
        """
        获取指定标的的期权链
        Args:
            all_contracts: 市场全部合约信息，由应用层 VolatilityTrade 传入。
            underlying_vt_symbol: 单个标的 VT 代码 (如 "IF2401.CFFEX")
        Returns:
            pd.DataFrame: 清洗后的期权链数据
        """
        pass

    @staticmethod
    def is_contract_of_product(symbol: str, product_code: str) -> bool:
        """判断合约是否属于指定品种 (正则匹配)"""
        pass
```

### 职责边界
- **Input**: 原始的全市场数据 (通过 `all_contracts` 参数传入)。
- **Process**: 解析标的代码 -> 过滤期权 -> 提取关键要素 (行权价/到期日/最新报价)。
- **Output**: 干净的 `pd.DataFrame`，供应用层直接使用。

---

## 7. 重构路线图 (Roadmap)

1.  **Phase 1: 风控状态下沉 (High Priority)**
    - 目标：消除应用层对 `daily_open_count_map` 的直接访问。
    - 行动：
        - 在 `PositionAggregate` 中实现限额管理逻辑。
        - 将 `_ensure_daily_open_limit_state`, `_update_open_limits_from_trade`, `_get_reserved_open_volume` 逻辑移入聚合根。
        - 更新 `VolatilityTrade` 调用聚合根的新接口。

2.  **Phase 2: 基础设施逻辑剥离 (Medium Priority)**
    - 目标：应用层不包含任何 Pandas 操作和正则解析。
    - 行动：
        - 创建 `src/strategy/infrastructure/parsing/contract_helper.py`。
        - 提取 `_get_option_contracts` 为 `ContractHelper.get_option_chain`。应用层先获取 `all_contracts` 再调用。
        - 提取 `_is_contract_of_product` 为 `ContractHelper.is_contract_of_product`。

3.  **Phase 3: 持久化逻辑优化 (Low Priority)**
    - 目标：应用层仅作为快照搬运工。
    - 行动：
        - 改造 `dump_state` / `load_state`，使用聚合根的快照方法。
