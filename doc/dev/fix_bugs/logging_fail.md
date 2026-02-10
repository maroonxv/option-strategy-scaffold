# 日志丢失问题分析与修复方案

## 1. 问题描述
在运行策略或行情录制时，`data/logs` 目录下的日志文件中只包含了主程序 (`__main__`) 的 INFO 级别日志（如“策略初始化...”），而策略内部的业务日志（如 `SignalService` 的信号计算过程、`OptionSelector` 的筛选过程）完全丢失。

## 2. 根源分析

这个问题是由 **Python Logging 模块的配置方式** 与 **Windows 文件系统特性** 共同导致的。

### 2.1 冲突的日志配置
系统中有两处代码尝试控制日志文件：

1.  **主进程 (`src/main/main.py` 或 `run_recorder.py`)**:
    *   调用 `setup_logging` 初始化 Root Logger。
    *   创建 `TimedRotatingFileHandler` 打开日志文件 (e.g., `strategy.log`)。
    *   此时文件被主进程持有。

2.  **策略层 (`StrategyEntry`)**:
    *   初始化时调用 `setup_strategy_logger`。
    *   **再次**创建一个新的 `RotatingFileHandler` 尝试写入**同一个日志文件**。
    *   默认设置了 `propagate=False`，切断了与 Root Logger 的联系。

### 2.2 Windows 文件锁 (File Locking)
在 Linux/Unix 系统上，多个文件句柄同时写入同一个文件通常是可以工作的（虽然可能会日志交错）。但在 **Windows** 系统上，当主进程已经以写入模式打开文件后，策略进程再次尝试以写入模式打开同一个文件，会因为文件被锁定而失败，或者产生不可预知的写入阻塞。

### 2.3 结果
*   策略的 Handler 无法正确写入文件。
*   由于 `propagate=False`，策略的日志也没有传递给主程序的 Handler。
*   最终导致策略日志“凭空消失”。

## 3. 解决方案：统一日志通道 (One Logger to Rule Them All)

遵循 Python 日志最佳实践：**“应用配置日志，库只记录日志”**。策略模块应被视为“库”，不应主动管理文件资源。

### 3.1 修复逻辑
修改 `src/strategy/infrastructure/logging/logging_utils.py` 中的 `setup_strategy_logger` 函数：

1.  **环境检测**：在初始化策略 Logger 前，检查 Root Logger 是否已经绑定了 Handlers。
2.  **复用通道**：
    *   如果 Root Logger **已配置**（说明是在主程序运行中）：
        *   策略 Logger **不创建**任何 Handler。
        *   设置 `logger.propagate = True`。
        *   让日志自动“冒泡”到 Root Logger，由主程序统一写入文件和控制台。
    *   如果 Root Logger **未配置**（说明是在单元测试或独立调试）：
        *   保持原有逻辑，创建独立的 Console/File Handler。

### 3.2 代码变更
```python
def setup_strategy_logger(name: str, log_file: str = "strategy.log") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # 允许产生 DEBUG 日志
    
    # --- 新增逻辑: 检测主程序配置 ---
    root_logger = logging.getLogger()
    if root_logger.handlers:
        # 主程序已接管日志，策略直接复用
        logger.propagate = True
        if logger.hasHandlers():
            logger.handlers.clear()
        return logger
    # -------------------------------
    
    # ... (原有独立 Handler 创建逻辑) ...
```

## 4. 运行时注意

修复后，策略的日志将流向主程序的 Handler。由于策略调试日志（如信号计算）通常是 `DEBUG` 级别，而主程序默认运行在 `INFO` 级别。

**为了查看策略细节，必须在启动时指定日志级别：**

```bash
# 启动录制
python src/main/run_recorder.py --log-level DEBUG

# 或启动策略
python src/main/main.py --config config/timeframe/15m.yaml --log-level DEBUG
```

如果不加 `--log-level DEBUG`，主程序的过滤器会拦截掉策略的详细日志，依然只能看到 INFO 信息。
