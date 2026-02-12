"""
BacktestConfig 属性测试

Feature: backtesting-restructure
Property 8: 配置 CLI 覆盖优先级
Validates: Requirements 8.4
"""

import argparse

from hypothesis import given, settings
from hypothesis import strategies as st

from src.backtesting.config import BacktestConfig


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 为每个 CLI 字段生成 Optional 值：None 表示不覆盖，非 None 表示覆盖
_config_path_st = st.one_of(st.none(), st.text(min_size=1, max_size=50))
_date_st = st.one_of(st.none(), st.text(min_size=1, max_size=20))
_capital_st = st.one_of(st.none(), st.integers(min_value=1, max_value=10**9))
_rate_st = st.one_of(
    st.none(),
    st.floats(min_value=1e-8, max_value=0.01, allow_nan=False, allow_infinity=False),
)
_slippage_st = st.one_of(
    st.none(),
    st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
_size_st = st.one_of(st.none(), st.integers(min_value=1, max_value=10000))
_pricetick_st = st.one_of(
    st.none(),
    st.floats(min_value=0.001, max_value=100.0, allow_nan=False, allow_infinity=False),
)
_no_chart_st = st.one_of(st.none(), st.just(True))


# ---------------------------------------------------------------------------
# Property 8: 配置 CLI 覆盖优先级
# ---------------------------------------------------------------------------


class TestBacktestConfigCLIOverride:
    """Property 8: 配置 CLI 覆盖优先级

    *For any* BacktestConfig 默认值和命令行参数覆盖值，当 CLI 参数非 None 时，
    最终配置中该字段的值应等于 CLI 参数值；当 CLI 参数为 None 时，应保留默认值。

    **Validates: Requirements 8.4**
    """

    @given(
        config_val=_config_path_st,
        start_val=_date_st,
        end_val=_date_st,
        capital_val=_capital_st,
        rate_val=_rate_st,
        slippage_val=_slippage_st,
        size_val=_size_st,
        pricetick_val=_pricetick_st,
        no_chart_val=_no_chart_st,
    )
    @settings(max_examples=200)
    def test_cli_override_priority(
        self,
        config_val,
        start_val,
        end_val,
        capital_val,
        rate_val,
        slippage_val,
        size_val,
        pricetick_val,
        no_chart_val,
    ):
        """CLI 参数非 None 时覆盖默认值，为 None 时保留默认值。

        **Validates: Requirements 8.4**
        """
        args = argparse.Namespace(
            config=config_val,
            start=start_val,
            end=end_val,
            capital=capital_val,
            rate=rate_val,
            slippage=slippage_val,
            size=size_val,
            pricetick=pricetick_val,
            no_chart=no_chart_val,
        )

        cfg = BacktestConfig.from_args(args)
        default = BacktestConfig()

        # 字段映射: (args 属性, config 属性, 默认值, 是否反转)
        field_mappings = [
            ("config", "config_path", default.config_path, False),
            ("start", "start_date", default.start_date, False),
            ("end", "end_date", default.end_date, False),
            ("capital", "capital", default.capital, False),
            ("rate", "rate", default.rate, False),
            ("slippage", "slippage", default.slippage, False),
            ("size", "default_size", default.default_size, False),
            ("pricetick", "default_pricetick", default.default_pricetick, False),
        ]

        for args_attr, config_attr, default_val, _ in field_mappings:
            cli_val = getattr(args, args_attr)
            actual = getattr(cfg, config_attr)

            if cli_val is not None:
                assert actual == cli_val, (
                    f"CLI {args_attr}={cli_val!r} 应覆盖 {config_attr}，"
                    f"但实际值为 {actual!r}"
                )
            else:
                assert actual == default_val, (
                    f"CLI {args_attr}=None 时 {config_attr} 应保留默认值 "
                    f"{default_val!r}，但实际值为 {actual!r}"
                )

        # no_chart 特殊处理：反转逻辑
        if no_chart_val is not None:
            assert cfg.show_chart is (not no_chart_val), (
                f"CLI no_chart={no_chart_val!r} 时 show_chart 应为 "
                f"{not no_chart_val}，但实际值为 {cfg.show_chart!r}"
            )
        else:
            assert cfg.show_chart is default.show_chart, (
                f"CLI no_chart=None 时 show_chart 应保留默认值 "
                f"{default.show_chart!r}，但实际值为 {cfg.show_chart!r}"
            )
