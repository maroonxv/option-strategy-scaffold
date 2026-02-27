"""
main.py - 策略运行主入口

支持运行模式:
1. standalone: 单进程直接运行 (开发调试用)
2. daemon: 父子进程分离运行 (生产环境推荐)

命令行参数:
    --mode: 运行模式 (standalone/daemon)
    --config: 配置文件路径
    --log-level: 日志级别
"""
import argparse
import sys
import logging
from pathlib import Path
from typing import Optional

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.main.utils.logging_setup import setup_logging
from src.main.config.config_loader import ConfigLoader
from src.main.utils.signal_handler import register_shutdown_signals


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数
    
    Returns:
        解析后的参数命名空间
    """
    parser = argparse.ArgumentParser(
        description="商品波动率策略运行入口",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--mode",
        type=str,
        default="standalone",
        choices=["standalone", "daemon"],
        help="运行模式: standalone(单进程) / daemon(守护进程)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config/strategy_config.toml",
        help="策略配置文件路径"
    )

    parser.add_argument(
        "--override-config",
        type=str,
        help="覆盖配置文件路径 (可选, 用于合并时间窗口等差异化配置)"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别"
    )
    
    parser.add_argument(
        "--log-dir",
        type=str,
        default="data/logs",
        help="日志目录"
    )
    
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="无界面模式运行"
    )

    parser.add_argument(
        "--paper",
        action="store_true",
        help="启用模拟交易模式"
    )
    
    return parser.parse_args()


def run_standalone(args: argparse.Namespace) -> None:
    """
    单进程直接运行模式
    
    适用于开发调试环境，所有组件在同一进程内运行。
    
    Args:
        args: 命令行参数
    """
    from src.main.process.child_process import ChildProcess
    
    # 确保配置文件路径是绝对路径
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
        
    child = ChildProcess(
        config_path=str(config_path),
        override_config_path=args.override_config,
        log_level=args.log_level,
        log_dir=args.log_dir,
        paper_trading=args.paper
    )
    
    # 注册信号处理器，确保 Ctrl+C 时能调用 child.shutdown()
    def shutdown_handler(signum, frame):
        logging.info(f"接收到退出信号 ({signum})，正在停止策略...")
        child.running = False
    
    register_shutdown_signals(shutdown_handler)
    
    try:
        child.run()
    except KeyboardInterrupt:
        logging.info("接收到 KeyboardInterrupt，正在停止...")
        child.shutdown()
    except Exception as e:
        logging.error(f"策略运行异常: {e}", exc_info=True)
        child.shutdown()
        sys.exit(1)


def run_daemon(args: argparse.Namespace) -> None:
    """
    守护进程模式运行
    
    父进程作为守护进程监控子进程，子进程异常退出时自动重启。
    
    Args:
        args: 命令行参数
    """
    from src.main.process.parent_process import ParentProcess
    
    # 确保配置文件路径是绝对路径
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
        
    parent = ParentProcess(
        config_path=str(config_path),
        override_config_path=args.override_config,
        log_level=args.log_level,
        log_dir=args.log_dir,
        log_name=getattr(args, "log_name", "strategy.log")
    )
    # 注意：守护进程模式目前不支持模拟交易参数传递
    # 如果需要，ParentProcess 也需要更新。假设模拟交易使用独立模式。
    
    # 注册信号处理器
    def shutdown_handler(signum, frame):
        logging.info(f"父进程接收到退出信号 ({signum})，正在停止...")
        parent.graceful_shutdown()
        sys.exit(0)
    
    register_shutdown_signals(shutdown_handler)
    
    try:
        parent.run()
    except KeyboardInterrupt:
        logging.info("父进程接收到 KeyboardInterrupt，正在停止...")
        parent.graceful_shutdown()


def main() -> None:
    """主函数"""
    args = parse_args()
    
    # 确定日志文件名和目录
    log_name = "strategy.log"
    if args.override_config:
        path = Path(args.override_config)
        timeframe = path.stem  # 例如 "config/timeframe/15m.toml" 中的 "15m"
        
        # 如果提供了覆盖配置，且看起来像时间窗口配置
        # 将日志目录修改为对应的子目录: data/logs/15m
        base_log_dir = Path(args.log_dir)
        if base_log_dir.name != timeframe:
            args.log_dir = str(base_log_dir / timeframe)
            
        # 设置日志文件名: strategy_15m.log
        log_name = f"strategy_{timeframe}.log"
    
    # 将 log_name 注入 args，供 run_daemon 使用
    args.log_name = log_name
    
    setup_logging(args.log_level, args.log_dir, args.log_name)
    
    logger = logging.getLogger(__name__)
    
    if args.mode == "standalone":
        run_standalone(args)
    else:
        run_daemon(args)


if __name__ == "__main__":
    main()
