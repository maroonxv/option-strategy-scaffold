"""
tests for src/backtesting/cli.py
CLI 参数解析和入口函数行为验证
"""

import argparse
from unittest.mock import patch, MagicMock

from src.backtesting.cli import main


class TestCliArgParsing:
    """验证 CLI 参数解析：所有参数默认 None，--no-chart 为 store_true。"""

    def _parse(self, argv: list[str]) -> argparse.Namespace:
        """辅助方法：模拟 sys.argv 调用 main 中的 parser。"""
        import src.backtesting.cli as cli_mod
        parser = argparse.ArgumentParser(description="运行组合策略回测")
        parser.add_argument("--config", type=str, default=None)
        parser.add_argument("--start", type=str, default=None)
        parser.add_argument("--end", type=str, default=None)
        parser.add_argument("--capital", type=int, default=None)
        parser.add_argument("--rate", type=float, default=None)
        parser.add_argument("--slippage", type=float, default=None)
        parser.add_argument("--size", type=int, default=None)
        parser.add_argument("--pricetick", type=float, default=None)
        parser.add_argument("--no-chart", action="store_true", default=None, dest="no_chart")
        return parser.parse_args(argv)

    def test_no_args_all_none(self):
        """Req 10.2: 未提供参数时所有值为 None（由 BacktestConfig 提供默认值）。"""
        args = self._parse([])
        assert args.config is None
        assert args.start is None
        assert args.end is None
        assert args.capital is None
        assert args.rate is None
        assert args.slippage is None
        assert args.size is None
        assert args.pricetick is None
        assert args.no_chart is None

    def test_all_args_provided(self):
        """Req 10.1: 支持所有参数。"""
        args = self._parse([
            "--config", "my.toml",
            "--start", "2025-01-01",
            "--end", "2025-06-30",
            "--capital", "500000",
            "--rate", "0.0001",
            "--slippage", "0.5",
            "--size", "100",
            "--pricetick", "0.1",
            "--no-chart",
        ])
        assert args.config == "my.toml"
        assert args.start == "2025-01-01"
        assert args.end == "2025-06-30"
        assert args.capital == 500000
        assert args.rate == 0.0001
        assert args.slippage == 0.5
        assert args.size == 100
        assert args.pricetick == 0.1
        assert args.no_chart is True

    def test_partial_args(self):
        """部分参数提供，其余保持 None。"""
        args = self._parse(["--start", "2025-03-01", "--capital", "2000000"])
        assert args.start == "2025-03-01"
        assert args.capital == 2000000
        assert args.config is None
        assert args.end is None
        assert args.no_chart is None

    def test_no_chart_flag_absent_is_none(self):
        """--no-chart 未提供时为 None（非 False），让 BacktestConfig 保留默认值。"""
        args = self._parse([])
        assert args.no_chart is None

    def test_no_chart_flag_present_is_true(self):
        """--no-chart 提供时为 True。"""
        args = self._parse(["--no-chart"])
        assert args.no_chart is True


class TestCliMain:
    """验证 main() 函数的调用流程。"""

    def test_main_calls_full_pipeline(self):
        """Req 10.3: CLI 将参数传递给 BacktestConfig 并启动 BacktestRunner。"""
        fake_args = argparse.Namespace(
            config=None, start=None, end=None, capital=None,
            rate=None, slippage=None, size=None, pricetick=None,
            no_chart=None,
        )

        mock_config = MagicMock()
        mock_runner_instance = MagicMock()
        mock_factory_instance = MagicMock()

        # 构造 mock 模块，模拟 main() 内部的延迟 import
        mock_config_mod = MagicMock()
        mock_config_mod.BacktestConfig.from_args.return_value = mock_config

        mock_dotenv_mod = MagicMock()

        mock_db_mod = MagicMock()
        mock_db_mod.DatabaseFactory.get_instance.return_value = mock_factory_instance

        mock_runner_mod = MagicMock()
        mock_runner_mod.BacktestRunner.return_value = mock_runner_instance

        modules_patch = {
            "dotenv": mock_dotenv_mod,
            "src.main": MagicMock(),
            "src.main.bootstrap": MagicMock(),
            "src.main.bootstrap.database_factory": mock_db_mod,
            "src.backtesting.runner": mock_runner_mod,
        }

        with patch("argparse.ArgumentParser.parse_args", return_value=fake_args), \
             patch("src.backtesting.config.BacktestConfig.from_args", return_value=mock_config) as mock_from_args, \
             patch.dict("sys.modules", modules_patch):

            main()

            # 验证调用链
            mock_from_args.assert_called_once_with(fake_args)
            mock_dotenv_mod.load_dotenv.assert_called_once()
            mock_db_mod.DatabaseFactory.get_instance.assert_called_once()
            mock_factory_instance.initialize.assert_called_once_with(eager=True)
            mock_runner_mod.BacktestRunner.assert_called_once_with(mock_config)
            mock_runner_instance.run.assert_called_once()
