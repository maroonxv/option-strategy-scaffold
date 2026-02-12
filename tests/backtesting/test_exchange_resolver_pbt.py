"""
ExchangeResolver 属性测试

Feature: backtesting-restructure, Property 2: 交易所解析一致性
Validates: Requirements 3.1
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.backtesting.config import EXCHANGE_MAP
from src.backtesting.contract.exchange_resolver import ExchangeResolver


class TestExchangeResolverProperty:
    """Property 2: 交易所解析一致性

    *For any* EXCHANGE_MAP 中的品种代码，ExchangeResolver.resolve() 返回的交易所代码
    应与 EXCHANGE_MAP 中存储的值一致。

    **Validates: Requirements 3.1**
    """

    @given(product_code=st.sampled_from(sorted(EXCHANGE_MAP.keys())))
    @settings(max_examples=100)
    def test_resolve_matches_exchange_map(self, product_code: str):
        """ExchangeResolver.resolve() 应与 EXCHANGE_MAP 中的值一致。"""
        result = ExchangeResolver.resolve(product_code)
        expected = EXCHANGE_MAP[product_code]
        assert result == expected, (
            f"品种 {product_code}: resolve() 返回 {result}，"
            f"但 EXCHANGE_MAP 中为 {expected}"
        )
