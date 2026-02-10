# 期权量化交易策略框架

## 一、项目简介

这是一个基于 VnPy 的期权量化交易策略框架，采用领域驱动设计（DDD）架构，提供了完整的策略开发骨架。框架支持多周期运行、Docker 容器化部署、实盘/回测/模拟交易等多种模式。

### 核心特性

*   **领域驱动设计**：清晰的分层架构（Domain/Application/Infrastructure），便于扩展和维护
*   **多周期支持**：可同时运行多个不同时间周期的策略实例（15分钟/30分钟/60分钟等）
*   **灵活配置**：支持 YAML 配置文件，无需修改代码即可调整策略参数
*   **容器化部署**：提供完整的 Docker 部署方案，一键启动所有服务
*   **状态持久化**：支持策略状态保存与恢复，重启后自动恢复运行状态
*   **监控面板**：内置 Web 监控面板，实时查看策略运行状态
*   **多模式运行**：支持实盘交易、模拟交易、历史回测

### 技术栈

*   **交易框架**：VnPy 4.2.0
*   **数据库**：MySQL 8.0
*   **容器化**：Docker + Docker Compose
*   **监控面板**：Flask + SocketIO
*   **技术指标**：TA-Lib

### 适用场景

本框架适用于基于技术指标的期权交易策略开发，特别是：
*   期货期权套利策略
*   波动率交易策略
*   技术指标驱动的期权卖方策略
*   多品种、多周期的组合策略

---

## 二、Docker 部署指南

本项目推荐使用 Docker 进行容器化部署，以实现环境隔离、一键启动和数据持久化。

### 1. 部署架构
我们采用"统一镜像，多服务编排"的架构，所有服务共享同一个 Docker 镜像：
*   **`mysql-db`**: 数据库服务 (MySQL 8.0)，负责存储行情与交易记录。
*   **`dashboard`**: 监控面板服务，提供 Web 界面查看策略状态 (端口 5007)。
*   **`strategy-15m`**: 15分钟周期策略服务 (示例)。
*   *(可选)*: 如需更多周期 (如 1h)，可直接复制 strategy 服务块并修改配置。

### 2. 快速开始

#### 步骤 1: 准备数据
首次部署前，请联系项目开发人员获取最新的数据库备份文件 `init.sql`（包含基础配置和历史行情数据）。

**操作**：将获取到的 `init.sql` 文件放入项目的 `deploy/init_data/` 目录下。
*(Docker 容器首次启动时会自动检测并执行该目录下的 SQL 文件进行初始化)*

> **注意**：`init.sql` 已被 git 忽略，请务必手动获取并放置。

#### 步骤 2: 启动服务
进入 `deploy` 目录并启动所有服务：

```powershell
cd deploy
docker-compose up -d --build
```

#### 步骤 3: 验证运行
*   **查看状态**: `docker-compose ps` 确保所有容器状态为 `Up`。
*   **访问面板**: 浏览器打开 [http://localhost:5007](http://localhost:5007)。
*   **查看日志**:
    ```powershell
    docker-compose logs -f strategy-15m  # 查看策略日志
    docker-compose logs -f dashboard     # 查看监控面板日志
    ```

### 3. 配置说明
*   **文件位置**: 所有 Docker 相关文件位于 `deploy/` 目录下。
*   **环境变量**: 修改 `deploy/.env` 文件可调整数据库密码等敏感信息。
*   **策略配置**: 宿主机的 `config/` 目录已挂载到容器内。修改本地配置文件后，**重启容器即可生效**，无需重新构建镜像。

---

## 三、运行配置指南

本策略的配置文件位于 `config/` 目录下，分为**基础策略配置**、**交易标的配置**和**多周期差异化配置**三部分。

### 1. 基础策略配置 (`config/strategy_config.yaml`)
此文件定义了策略的**全局默认参数**和**运行时环境**。所有时间周期的策略进程默认都会加载此配置，除非被差异化配置覆盖。

*   **策略参数 (`strategies.setting`)**：
    *   `max_positions`: 策略允许持有的最大合约数量（风控限制）。
    *   `strike_level`: 期权选合约时的虚值档位（OTM Level），例如 `4` 表示虚值四档。
    *   其他指标参数请根据策略需求自行添加。

*   **运行时参数 (`runtime`)**：
    *   `trading_periods`: **交易时段**。守护进程会根据此时段自动启动或停止交易子进程。请根据实际交易所时间调整（例如包含夜盘时段）。
    *   `max_restart_count`: 子进程允许的最大异常重启次数。

### 2. 交易标的配置 (`config/general/trading_target.yaml`)
此文件定义了策略需要监控和交易的**期货品种代码**。

*   **格式**：YAML 列表格式。
*   **示例**：
    ```yaml
    - IF  # 沪深300股指期货
    - IM  # 中证1000股指期货
    ```
    策略启动时会自动加载这些品种的主力合约，并监控其对应的期权链。

### 3. 多周期差异化配置 (`config/timeframe/*.yaml`)
本策略支持同时运行多个不同时间周期的实例（如 15分钟、30分钟、60分钟等）。
项目采用自动扫描机制，您只需在 `config/timeframe/` 目录下管理配置文件即可。

#### 3.1 启用新周期
只需在 `config/timeframe/` 目录下创建一个新的 `.yaml` 配置文件。
`scripts/run.bat` 启动脚本会自动扫描该目录下所有的 `.yaml` 文件，并为每个文件启动一个独立的策略进程。

**示例**：
如果您想运行 15 分钟和 30分钟两个周期的策略，只需确保目录下存在以下文件：
- `config/timeframe/15m.yaml`
- `config/timeframe/30m.yaml`

#### 3.2 配置文件格式
配置文件内容主要用于覆盖默认配置中的 `strategy_name` 和 `bar_window` 参数。
例如 `15m.yaml` 的内容可以是：
```yaml
strategies:
  - strategy_name: "volatility_strategy_15m"
    setting:
      bar_window: 15
      bar_interval: "MINUTE"
```

#### 3.3 停用周期
若要暂时停用某个周期的策略，直接把对应配置文件删除即可。

---

## 四、架构设计

本项目采用领域驱动设计（DDD）架构，代码结构清晰，职责分明。

### 1. 目录结构

```
src/strategy/
├── strategy_entry.py          # VnPy 策略入口（适配器层）
├── application/                        # 应用层
│   └── volatility_trade.py           # 策略执行协调器
├── domain/                            # 领域层
│   ├── aggregate/                     # 聚合根（状态管理）
│   │   ├── position_aggregate.py     # 持仓状态管理
│   │   └── target_instrument_aggregate.py  # 行情数据管理
│   ├── domain_service/                # 领域服务（业务逻辑）
│   │   ├── signal_service.py         # 交易信号判断
│   │   ├── indicator_service.py      # 技术指标计算
│   │   ├── option_selector_service.py # 期权合约选择
│   │   ├── position_sizing_service.py # 仓位管理
│   │   └── future_selection_service.py # 主力合约选择
│   └── interface/                     # 领域接口定义
└── infrastructure/                    # 基础设施层
    ├── gateway/                       # 交易网关适配
    ├── persistence/                   # 数据持久化
    ├── logging/                       # 日志管理
    └── reporting/                     # 报告与通知
```

### 2. 核心模块说明

#### 策略入口层
*   **`strategy_entry.py`**：VnPy 策略模板的实现，负责接收 VnPy 回调并转发给应用层

#### 应用层
*   **`volatility_trade.py`**：策略执行协调器，编排各个领域服务的调用流程

#### 领域层（核心业务逻辑）
*   **`signal_service.py`**：交易信号判断逻辑（开仓/平仓条件）
*   **`indicator_service.py`**：技术指标计算（MACD、TD序列、EMA等）
*   **`option_selector_service.py`**：期权合约筛选规则（虚值档位、流动性过滤）
*   **`position_sizing_service.py`**：仓位管理与风控（最大持仓、交易次数限制）
*   **`future_selection_service.py`**：期货主力合约选择与换月逻辑
*   **`position_aggregate.py`**：持仓状态管理（持仓记录、订单追踪）
*   **`target_instrument_aggregate.py`**：行情数据管理（K线数据、指标缓存）

#### 基础设施层
*   **`gateway/`**：交易网关适配器（VnPy 接口封装）
*   **`persistence/`**：数据持久化（MySQL、Pickle）
*   **`logging/`**：日志管理
*   **`reporting/`**：飞书通知等报告功能

### 3. 如何开发自己的策略

#### 步骤 1：实现信号逻辑
修改 `src/strategy/domain/domain_service/signal_service.py`，实现你的开仓和平仓条件判断。

#### 步骤 2：调整指标计算
如需使用其他技术指标，修改 `src/strategy/domain/domain_service/indicator_service.py`。

#### 步骤 3：配置策略参数
修改 `config/strategy_config.yaml` 和 `config/timeframe/*.yaml`，调整策略参数。

#### 步骤 4：测试与部署
*   **回测**：使用 VnPy 回测引擎进行历史数据测试
*   **模拟交易**：连接模拟账户进行实时测试
*   **实盘部署**：使用 Docker 部署到生产环境

---

## 五、开发指南

### 1. 本地开发环境搭建

#### 安装依赖
```powershell
pip install -r requirements.txt
```

#### 配置数据库
修改 `.env` 文件，配置 MySQL 连接信息。

#### 运行策略
```powershell
# 运行单个周期策略
python -m src.main.run_strategy --config config/timeframe/15m.yaml

# 运行回测
python -m src.main.run_backtesting

# 启动监控面板
python -m src.interface.dashboard
```

### 2. 添加新的技术指标

在 `src/strategy/domain/domain_service/indicator_service.py` 中添加新的指标计算方法：

```python
def calculate_your_indicator(self, bars: List[BarData]) -> float:
    """计算自定义指标"""
    # 实现你的指标计算逻辑
    pass
```

### 3. 自定义交易信号

修改 `src/strategy/domain/domain_service/signal_service.py`：

```python
def check_open_signal(self, instrument_data, current_bar) -> Optional[str]:
    """
    检查开仓信号
    
    Returns:
        "SELL_PUT" | "SELL_CALL" | None
    """
    # 实现你的开仓逻辑
    pass

def check_close_signal(self, position, instrument_data, current_bar) -> bool:
    """检查平仓信号"""
    # 实现你的平仓逻辑
    pass
```

### 4. 扩展期权选择规则

修改 `src/strategy/domain/domain_service/option_selector_service.py`，自定义合约筛选条件。

---

## 六、常见问题

### 1. 如何添加新的交易品种？
修改 `config/general/trading_target.yaml`，添加期货品种代码。

### 2. 如何调整策略参数？
修改 `config/strategy_config.yaml` 或对应周期的配置文件。

### 3. 如何查看策略日志？
*   **Docker 部署**：`docker-compose logs -f strategy-15m`
*   **本地运行**：查看 `data/logs/` 目录

### 4. 策略重启后如何恢复状态？
策略会自动从 `data/pickle/` 目录加载上次保存的状态，并从数据库回放最近的 K 线数据进行 warmup。

### 5. 如何接入飞书通知？
在 `config/strategy_config.yaml` 中配置 `feishu_webhook` 参数。

---

## 七、许可证

本项目仅供学习和研究使用。
