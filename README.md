# 期权量化交易策略框架

## 一、项目简介

这是一个基于 VnPy 的期权量化交易策略框架，采用领域驱动设计（DDD）架构，提供了完整的策略开发骨架。框架支持多周期运行、Docker 容器化部署、实盘/回测/模拟交易等多种模式。

### 核心特性

*   **领域驱动设计**：清晰的分层架构（Domain / Infrastructure），领域逻辑完全独立于 VnPy，可单独测试和复用
*   **多周期支持**：可同时运行多个不同时间周期的策略实例（15分钟/30分钟/60分钟等），通过 BarPipeline 从 1 分钟线合成任意周期 K 线
*   **Greeks 风控体系**：内置 Black-Scholes Greeks 计算器，支持单持仓和组合级别的 Delta/Gamma/Vega 风控阈值
*   **波动率曲面**：从市场期权报价构建波动率曲面，支持双线性插值查询、微笑提取和期限结构提取
*   **动态对冲引擎**：Delta 对冲引擎和 Gamma Scalping 引擎，可配置对冲阈值和再平衡频率
*   **高级订单执行**：智能订单执行器（超时/重试/滑点管理）、冰山单、TWAP 分时拆单
*   **状态持久化**：JSON 序列化 + 迁移链机制，支持自动保存（60 秒间隔）、损坏检测、状态恢复
*   **进程守护**：父子进程架构，异常自动重启（指数退避），交易时段感知（非交易时间自动停止）
*   **监控面板**：Flask + SocketIO 实时 Web 面板，展示持仓、Greeks、盈亏、事件
*   **飞书通知**：交易信号、风控告警等事件实时推送到飞书群
*   **多模式运行**：实盘交易、模拟交易（Paper Trading）、历史回测
*   **灵活配置**：YAML 配置文件，支持全局默认 + 周期差异化覆盖


### 技术栈

*   **交易框架**：VnPy 4.2.0 + vnpy_portfoliostrategy
*   **CTP 网关**：vnpy_ctp 6.7.11（期货）、vnpy_sopt 3.7.1（期权）
*   **数据库**：MySQL 8.0（vnpy_mysql）
*   **容器化**：Docker + Docker Compose
*   **监控面板**：Flask + Flask-SocketIO
*   **技术指标**：TA-Lib
*   **数据源**：Tushare、AKShare
*   **测试框架**：pytest + Hypothesis（属性测试）

### 适用场景

*   期货期权套利策略
*   波动率交易策略
*   技术指标驱动的期权卖方策略
*   多品种、多周期的组合策略
*   需要 Greeks 风控和动态对冲的期权组合管理

---

## 二、项目结构

```
├── config/                            # 配置文件
│   ├── strategy_config.yaml           # 全局策略配置（参数、风控、对冲、订单执行）
│   ├── general/
│   │   ├── trading_target.yaml        # 交易品种列表
│   │   └── data_recorder_setting.json # 数据录制配置
│   └── timeframe/
│       └── 15m.yaml                   # 周期差异化配置（可添加 30m.yaml 等）
├── scripts/                           # 启动脚本
│   ├── run.bat                        # 实盘策略启动（守护进程模式）
│   ├── run_paper.bat                  # 模拟交易启动
│   ├── run_backtesting.bat            # 回测启动
│   ├── run_dashboard.bat              # 监控面板启动
│   └── run_datarecorder.bat           # 数据录制启动
├── deploy/                            # Docker 部署
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── init_data/                     # 数据库初始化 SQL
├── src/
│   ├── strategy/                      # 策略核心（DDD 架构）
│   │   ├── strategy_entry.py          # VnPy 策略入口 + 应用层编排
│   │   ├── domain/                    # 领域层（纯业务逻辑）
│   │   └── infrastructure/            # 基础设施层（VnPy 适配、持久化、监控）
│   ├── main/                          # 进程管理与启动
│   │   ├── main.py                    # 主入口（standalone / daemon 模式）
│   │   ├── process/                   # 父子进程、数据录制进程
│   │   ├── bootstrap/                 # 引擎工厂、数据库工厂
│   │   ├── config/                    # 配置加载、网关管理
│   │   └── utils/                     # 日志、信号处理
│   ├── backtesting/                   # 回测系统
│   │   ├── runner.py                  # 回测执行器
│   │   ├── cli.py                     # 回测命令行接口
│   │   ├── config.py                  # 回测配置与品种规格
│   │   ├── contract/                  # 合约注册、交易所映射、到期计算
│   │   └── discovery/                 # 合约代码生成、期权发现
│   └── web/                           # 监控面板
│       ├── app.py                     # Flask 应用（路由 + WebSocket）
│       ├── reader.py                  # MySQL 快照读取器
│       ├── templates/                 # HTML 模板
│       └── static/                    # 前端 JS
└── tests/                             # 测试
```


---

## 三、架构设计

本项目采用 Pragmatic DDD 架构：`StrategyEntry` 同时充当 VnPy 接口层和应用层，直接编排领域逻辑；领域层完全独立于 VnPy，可单独测试。

### 1. 策略入口层（`strategy_entry.py`）

VnPy `StrategyTemplate` 的实现，负责：
*   接收 VnPy 回调（`on_init`、`on_bars`、`on_tick`、`on_trade`、`on_order` 等）
*   编排领域服务调用流程
*   依赖注入：在 `on_init` 中初始化所有领域服务和基础设施组件
*   Warmup 逻辑：回测模式直接加载历史 Bar；实盘模式从 MySQL 回放 + 状态恢复
*   合约宇宙管理：自动选择主力合约、每日 14:50 检查换月

### 2. 领域层（`domain/`）

#### 聚合根（状态管理）
| 模块 | 职责 |
|------|------|
| `InstrumentManager` | 管理各品种的活跃合约、K 线数据、指标缓存 |
| `PositionAggregate` | 跟踪所有持仓、订单、成交，检测手动干预 |

#### 领域服务（业务逻辑）
| 模块 | 职责 |
|------|------|
| `SignalService` | 交易信号判断（开仓/平仓条件），模板类，需根据策略实现 |
| `IndicatorService` | 技术指标计算（MACD、TD 序列、EMA 等），模板类 |
| `OptionSelectorService` | 期权合约筛选（虚值档位、流动性过滤） |
| `PositionSizingService` | 仓位计算与风控（最大持仓、资金比例） |
| `BaseFutureSelector` | 期货主力合约选择与到期过滤 |
| `GreeksCalculator` | Black-Scholes Greeks 计算（Delta/Gamma/Vega/Theta） |
| `PortfolioRiskAggregator` | 组合级 Greeks 聚合与风控阈值检查 |
| `VolSurfaceBuilder` | 波动率曲面构建（双线性插值、微笑提取、期限结构） |
| `SmartOrderExecutor` | 智能订单执行（超时撤单、自适应滑点、重试） |
| `DeltaHedgingService` | Delta 对冲服务（目标 Delta、对冲带宽） |
| `GammaScalpingService` | Gamma Scalping 再平衡服务 |
| `AdvancedOrderScheduler` | 高级订单调度（冰山单、TWAP 分时拆单） |

#### 实体
| 模块 | 职责 |
|------|------|
| `Position` | 单个持仓记录（合约、方向、数量、盈亏） |
| `Order` | 订单跟踪（状态、成交、撤单） |
| `TargetInstrument` | 行情数据容器（K 线、Tick、指标） |

#### 值对象
`GreeksResult`、`OrderInstruction`、`OptionContract`、`RiskThresholds`、`VolSurface`、`HedgingConfig`、`AdvancedOrder`、`AccountSnapshot`、`PositionSnapshot`、`ContractParams`、`QuoteRequest`、`SignalType` 等。

#### 领域事件
`ManualCloseDetectedEvent`、`ManualOpenDetectedEvent`、`RiskLimitExceededEvent`、`GreeksRiskBreachEvent`、`OrderTimeoutEvent`、`OrderRetryExhaustedEvent`

### 3. 基础设施层（`infrastructure/`）

#### 网关适配器（VnPy 接口封装）
| 模块 | 职责 |
|------|------|
| `VnpyMarketDataGateway` | 行情订阅、合约查询 |
| `VnpyAccountGateway` | 账户余额、持仓查询 |
| `VnpyTradeExecutionGateway` | 下单、撤单、成交跟踪 |
| `VnpyOrderGateway` | 订单状态查询 |
| `VnpyQuoteGateway` | 报价请求 |
| `VnpyEventGateway` | 事件注册/注销 |
| `VnpyConnectionGateway` | 网关连接管理 |

#### 持久化
| 模块 | 职责 |
|------|------|
| `StateRepository` | 策略状态存取（JSON 序列化） |
| `HistoryDataRepository` | 从 MySQL 回放历史 K 线（Warmup 用） |
| `AutoSaveService` | 定时自动保存（60 秒间隔） |
| `JsonSerializer` | 序列化/反序列化 + 迁移链 |
| `MigrationChain` | 状态版本迁移 |

#### 其他
| 模块 | 职责 |
|------|------|
| `BarPipeline` | K 线合成管道（1 分钟 → 任意周期） |
| `StrategyMonitor` | 策略快照写入 MySQL（供面板读取） |
| `FeishuEventHandler` | 飞书 Webhook 通知 |
| `ContractHelper` | 合约代码解析工具 |


---

## 四、进程管理

### 运行模式

| 模式 | 说明 | 启动方式 |
|------|------|----------|
| `daemon` | 父子进程分离，生产环境推荐 | `scripts/run.bat` |
| `standalone` | 单进程直接运行，开发调试用 | `--mode standalone` |
| `paper` | 模拟交易模式 | `scripts/run_paper.bat` |

### 父子进程架构

```
ParentProcess（守护进程）
├── 监控子进程健康状态
├── 异常退出自动重启（指数退避：5s → 10s → 20s → ... → 300s）
├── 连续运行 1 小时后重置重启计数
├── 交易时段感知（非交易时间停止子进程）
└── 信号处理（优雅退出）

ChildProcess（工作进程）
├── 初始化 VnPy 引擎（EventEngine → MainEngine → StrategyEngine）
├── 加载 CTP 网关并连接
├── 加载并启动策略
└── 处理交易事件
```

### 回测系统

回测系统独立于实盘运行，通过 CLI 启动：

```powershell
scripts\run_backtesting.bat
```

回测流程：
1. 加载策略配置 → 2. 从 `trading_target.yaml` 获取品种列表 → 3. 生成近期合约代码 → 4. 从数据库发现关联期权合约 → 5. 注册合约到 `ContractRegistry` → 6. 初始化 VnPy `BacktestingEngine` → 7. 运行回测并输出结果

### 数据录制

独立进程录制行情数据到 MySQL：

```powershell
scripts\run_datarecorder.bat
```

---

## 五、回测系统

### 模块组成

| 模块 | 职责 |
|------|------|
| `BacktestRunner` | 编排完整回测流程 |
| `BacktestCLI` | 命令行接口，解析参数并调用 Runner |
| `BacktestConfig` | 回测配置（日期范围、品种规格等） |
| `SymbolGenerator` | 根据品种代码生成近期合约代码（如 IF → IF2601、IF2603） |
| `OptionDiscoveryService` | 从数据库查找期货合约关联的期权合约 |
| `ContractRegistry` | 合约元数据管理（合约乘数、最小变动价、交易所） |
| `ContractFactory` | 创建 VnPy `ContractData` 对象 |
| `ExchangeResolver` | 品种代码 → 交易所映射 |
| `ExpiryCalculator` | 合约到期日计算 |

### 使用方式

```powershell
# 使用默认配置运行回测
python -m src.backtesting.cli

# 回测日志自动保存到 data/backtesting/ 目录
```

---

## 六、监控面板

### 功能

*   策略列表总览（`/`）
*   单策略详情页（`/dashboard/<variant>`）
*   实时数据 API（`/api/data/<variant>`、`/api/events/<variant>`、`/api/bars`）
*   WebSocket 实时推送（Flask-SocketIO）

### 数据流

```
StrategyEntry → StrategyMonitor → MySQL (monitor_signal_snapshot / strategy_state)
                                      ↓
                              Web Dashboard (Flask)
                                      ↓
                              浏览器 (WebSocket 实时更新)
```

### 启动

```powershell
scripts\run_dashboard.bat
# 自动打开浏览器访问 http://localhost:5007
```

---

## 七、运行配置指南

### 1. 环境变量（`.env`）

复制 `.env.example` 为 `.env` 并填写：

```ini
# CTP 网关
CTP_USERNAME=your_username
CTP_PASSWORD=your_password
CTP_BROKER_ID=your_broker_id
CTP_TD_SERVER=your_td_server
CTP_MD_SERVER=your_md_server
CTP_PRODUCT_NAME=your_product_name
CTP_AUTH_CODE=your_auth_code

# 数据库
VNPY_DATABASE_DRIVER=mysql
VNPY_DATABASE_DATABASE=volatility_strategy
VNPY_DATABASE_HOST=localhost
VNPY_DATABASE_PORT=3306
VNPY_DATABASE_USER=root
VNPY_DATABASE_PASSWORD=your_password

# 飞书通知
FEISHU_WEBHOOK_URL=your_feishu_webhook_url
```

### 2. 策略配置（`config/strategy_config.yaml`）

此文件定义全局默认参数，所有周期的策略进程都会加载：

```yaml
strategies:
  - class_name: "StrategyEntry"
    setting:
      max_positions: 5          # 最大持仓合约数
      position_ratio: 0.1       # 单次开仓资金比例
      strike_level: 4           # 虚值档位
      bar_window: 1             # K线合成窗口
      bar_interval: "MINUTE"    # K线基础周期

runtime:
  max_restart_count: 10         # 最大重启次数
  restart_delay: 5.0            # 重启间隔（秒）
  trading_periods:              # 交易时段
    - start: "08:40"
      end: "11:30"
    - start: "13:00"
      end: "15:30"

greeks_risk:                    # Greeks 风控
  risk_free_rate: 0.02
  position_limits:              # 单持仓阈值
    delta: 0.8
    gamma: 0.1
    vega: 50.0
  portfolio_limits:             # 组合阈值
    delta: 5.0
    gamma: 1.0
    vega: 500.0

order_execution:                # 订单执行
  timeout_seconds: 30
  max_retries: 3
  slippage_ticks: 2

hedging:                        # 动态对冲
  delta_hedging:
    target_delta: 0.0
    hedging_band: 0.5
  gamma_scalping:
    rebalance_threshold: 0.3

advanced_orders:                # 高级订单
  default_iceberg_batch_size: 5
  default_twap_slices: 10
  default_time_window_seconds: 300
```

### 3. 交易标的（`config/general/trading_target.yaml`）

```yaml
- IF  # 沪深300股指期货
- IM  # 中证1000股指期货
```

### 4. 多周期差异化配置（`config/timeframe/*.yaml`）

`scripts/run.bat` 自动扫描该目录下所有 `.yaml` 文件，为每个文件启动独立策略进程。

启用新周期：创建对应文件即可（如 `30m.yaml`）。停用：删除文件。

```yaml
# config/timeframe/15m.yaml
strategies:
  - strategy_name: "volatility_strategy_15m"
    setting:
      bar_window: 15
      bar_interval: "MINUTE"
```


---

## 八、Docker 部署指南

### 1. 部署架构

采用"统一镜像，多服务编排"架构，所有服务共享同一个 Docker 镜像：
*   **`mysql-db`**: 数据库服务 (MySQL 8.0)
*   **`dashboard`**: 监控面板服务 (端口 5007)
*   **`strategy-15m`**: 15分钟周期策略服务（示例）
*   可按需添加更多周期服务

### 2. 快速开始

#### 步骤 1: 准备数据
将数据库备份文件 `init.sql` 放入 `deploy/init_data/` 目录（首次启动时自动执行初始化）。

> `init.sql` 已被 git 忽略，请联系开发人员获取。

#### 步骤 2: 启动服务
```powershell
cd deploy
docker-compose up -d --build
```

#### 步骤 3: 验证运行
```powershell
docker-compose ps                        # 查看容器状态
docker-compose logs -f strategy-15m      # 查看策略日志
docker-compose logs -f dashboard         # 查看面板日志
```
浏览器访问 [http://localhost:5007](http://localhost:5007) 查看监控面板。

### 3. 配置说明
*   **环境变量**：修改 `deploy/.env` 调整数据库密码等
*   **策略配置**：宿主机 `config/` 目录已挂载到容器内，修改后重启容器即可生效

---

## 九、本地开发指南

### 1. 环境搭建

```powershell
# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
copy .env.example .env
# 编辑 .env 填写 CTP 和数据库信息
```

### 2. 运行

```powershell
# 实盘交易（守护进程模式，自动扫描所有周期配置）
scripts\run.bat

# 模拟交易
scripts\run_paper.bat

# 回测
scripts\run_backtesting.bat

# 监控面板
scripts\run_dashboard.bat

# 数据录制
scripts\run_datarecorder.bat

# 单进程调试模式
python src\main\main.py --mode standalone --config config\strategy_config.yaml --override-config config\timeframe\15m.yaml
```

### 3. 命令行参数

```
python src\main\main.py [OPTIONS]

--mode              运行模式: standalone / daemon (默认 standalone)
--config            策略配置文件路径 (默认 config/strategy_config.yaml)
--override-config   覆盖配置文件路径 (用于周期差异化配置)
--log-level         日志级别: DEBUG / INFO / WARNING / ERROR (默认 INFO)
--log-dir           日志目录 (默认 data/logs)
--no-ui             无界面模式
--paper             模拟交易模式
```

### 4. 如何开发自己的策略

#### 步骤 1：实现信号逻辑
`IndicatorService` 和 `SignalService` 是模板类，需要根据策略需求实现：

```python
# src/strategy/domain/domain_service/indicator_service.py
class IndicatorService(IIndicatorService):
    def calculate_bar(self, instrument, bar):
        """在此实现你的指标计算逻辑（MACD、TD序列、EMA 等）"""
        pass
```

```python
# src/strategy/domain/domain_service/signal_service.py
class SignalService:
    def check_open_signal(self, instrument_data, current_bar):
        """返回 "SELL_PUT" | "SELL_CALL" | None"""
        pass

    def check_close_signal(self, position, instrument_data, current_bar):
        """返回 True/False"""
        pass
```

#### 步骤 2：调整配置参数
修改 `config/strategy_config.yaml` 中的策略参数、Greeks 风控阈值、对冲参数等。

#### 步骤 3：测试与部署
*   **回测**：`scripts\run_backtesting.bat`
*   **模拟交易**：`scripts\run_paper.bat`
*   **实盘部署**：Docker 部署或 `scripts\run.bat`

---

## 十、常见问题

### 如何添加新的交易品种？
修改 `config/general/trading_target.yaml`，添加期货品种代码。

### 如何调整 Greeks 风控阈值？
修改 `config/strategy_config.yaml` 中的 `greeks_risk` 部分。

### 如何配置动态对冲？
修改 `config/strategy_config.yaml` 中的 `hedging` 部分，设置 `target_delta`、`hedging_band`、`rebalance_threshold` 等参数。

### 策略重启后如何恢复状态？
策略会自动从持久化存储加载上次保存的状态（`StateRepository` + `AutoSaveService`），并从 MySQL 回放最近的 K 线数据进行 Warmup。

### 如何接入飞书通知？
在 `.env` 中配置 `FEISHU_WEBHOOK_URL`。

### 如何查看策略日志？
*   **Docker 部署**：`docker-compose logs -f strategy-15m`
*   **本地运行**：查看 `data/logs/` 目录

---

## 十一、许可证

本项目仅供学习和研究使用。