"""
VolSurfaceBuilder 属性测试和单元测试

使用 hypothesis 验证波动率曲面构建、插值、微笑提取和期限结构提取。
"""
import json
import pytest
from hypothesis import given, strategies as st, settings, assume

from src.strategy.domain.domain_service.pricing.volatility.vol_surface_builder import VolSurfaceBuilder
from src.strategy.domain.value_object.vol_surface import (
    VolQuote, VolQueryResult, VolSmile, TermStructure, VolSurfaceSnapshot,
)


# ========== 生成器 ==========

def build_grid_quotes(
    strikes: list[float], expiries: list[float], vol_range: tuple[float, float] = (0.1, 1.0)
):
    """构建完整网格报价的策略"""
    return st.lists(
        st.floats(min_value=vol_range[0], max_value=vol_range[1], allow_nan=False, allow_infinity=False),
        min_size=len(strikes) * len(expiries),
        max_size=len(strikes) * len(expiries),
    ).map(lambda vols: [
        VolQuote(strike=strikes[i % len(strikes)],
                 time_to_expiry=expiries[i // len(strikes)],
                 implied_vol=vols[i])
        for i in range(len(strikes) * len(expiries))
    ])


@st.composite
def vol_surface_st(draw):
    """生成有效的波动率曲面 (NxM 网格)"""
    n_exp = draw(st.integers(min_value=2, max_value=8))
    n_stk = draw(st.integers(min_value=2, max_value=10))

    raw_expiries = draw(st.lists(
        st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
        min_size=n_exp, max_size=n_exp,
    ))
    raw_strikes = draw(st.lists(
        st.floats(min_value=1000.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        min_size=n_stk, max_size=n_stk,
    ))

    expiries = sorted(set(round(e, 4) for e in raw_expiries))
    strikes = sorted(set(round(s, 2) for s in raw_strikes))

    assume(len(expiries) >= 2 and len(strikes) >= 2)

    quotes = []
    for exp in expiries:
        for stk in strikes:
            vol = draw(st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False))
            quotes.append(VolQuote(strike=stk, time_to_expiry=exp, implied_vol=vol))

    return quotes, strikes, expiries


class TestVolSurfaceBuildProperty:
    """Property 10: 波动率曲面构建正确性"""

    # Feature: advanced-order-hedging-volsurface, Property 10: 波动率曲面构建正确性
    # Validates: Requirements 8.1
    @settings(max_examples=100)
    @given(data=vol_surface_st())
    def test_property10_build_surface_correctness(self, data):
        """Property 10: strikes/expiries 升序, matrix 维度正确, 网格点值匹配"""
        quotes, expected_strikes, expected_expiries = data
        builder = VolSurfaceBuilder()
        snapshot = builder.build_surface(quotes)

        # strikes 升序
        assert snapshot.strikes == sorted(snapshot.strikes)
        # expiries 升序
        assert snapshot.expiries == sorted(snapshot.expiries)
        # matrix 维度
        assert len(snapshot.vol_matrix) == len(snapshot.expiries)
        for row in snapshot.vol_matrix:
            assert len(row) == len(snapshot.strikes)

        # 网格点值匹配输入
        lookup = {(q.time_to_expiry, q.strike): q.implied_vol for q in quotes}
        for ei, exp in enumerate(snapshot.expiries):
            for si, stk in enumerate(snapshot.strikes):
                if (exp, stk) in lookup:
                    assert abs(snapshot.vol_matrix[ei][si] - lookup[(exp, stk)]) < 1e-10


class TestVolSurfaceInterpolationProperty:
    """Property 11: 波动率曲面插值有界性"""

    # Feature: advanced-order-hedging-volsurface, Property 11: 波动率曲面插值有界性
    # Validates: Requirements 8.2
    @settings(max_examples=100)
    @given(data=vol_surface_st(), t_frac=st.floats(min_value=0.0, max_value=1.0), s_frac=st.floats(min_value=0.0, max_value=1.0))
    def test_property11_interpolation_bounded(self, data, t_frac, s_frac):
        """Property 11: 插值结果在四个角点的 min/max 之间"""
        quotes, strikes, expiries = data
        builder = VolSurfaceBuilder()
        snapshot = builder.build_surface(quotes)

        # 在网格范围内选一个查询点
        s_min, s_max = snapshot.strikes[0], snapshot.strikes[-1]
        e_min, e_max = snapshot.expiries[0], snapshot.expiries[-1]
        query_strike = s_min + (s_max - s_min) * s_frac
        query_expiry = e_min + (e_max - e_min) * t_frac

        result = builder.query_vol(snapshot, query_strike, query_expiry)
        assert result.success is True

        # 找到四个角点
        import bisect
        si = bisect.bisect_right(snapshot.strikes, query_strike) - 1
        si = max(0, min(si, len(snapshot.strikes) - 2))
        ei = bisect.bisect_right(snapshot.expiries, query_expiry) - 1
        ei = max(0, min(ei, len(snapshot.expiries) - 2))

        corners = [
            snapshot.vol_matrix[ei][si],
            snapshot.vol_matrix[ei][si + 1],
            snapshot.vol_matrix[ei + 1][si],
            snapshot.vol_matrix[ei + 1][si + 1],
        ]
        lo, hi = min(corners), max(corners)
        assert lo - 1e-9 <= result.implied_vol <= hi + 1e-9


class TestVolSmileExtractionProperty:
    """Property 13: 波动率微笑提取正确性与排序"""

    # Feature: advanced-order-hedging-volsurface, Property 13: 波动率微笑提取正确性与排序
    # Validates: Requirements 9.1, 9.2, 9.3
    @settings(max_examples=100)
    @given(data=vol_surface_st(), t_frac=st.floats(min_value=0.0, max_value=1.0))
    def test_property13_smile_extraction(self, data, t_frac):
        """Property 13: strikes 升序, 网格点匹配, 插值有界"""
        quotes, strikes, expiries = data
        builder = VolSurfaceBuilder()
        snapshot = builder.build_surface(quotes)

        e_min, e_max = snapshot.expiries[0], snapshot.expiries[-1]
        target_expiry = e_min + (e_max - e_min) * t_frac

        smile = builder.extract_smile(snapshot, target_expiry)

        # strikes 升序
        assert smile.strikes == sorted(smile.strikes)
        assert smile.strikes == snapshot.strikes

        # 当 target 匹配网格点时，vols 匹配对应行
        if target_expiry in snapshot.expiries:
            ei = snapshot.expiries.index(target_expiry)
            for si, vol in enumerate(smile.vols):
                assert abs(vol - snapshot.vol_matrix[ei][si]) < 1e-9

        # 当 target 在两个网格点之间时，每个 vol 有界
        import bisect
        ei = bisect.bisect_right(snapshot.expiries, target_expiry) - 1
        ei = max(0, min(ei, len(snapshot.expiries) - 2))
        for si in range(len(snapshot.strikes)):
            lo = min(snapshot.vol_matrix[ei][si], snapshot.vol_matrix[ei + 1][si])
            hi = max(snapshot.vol_matrix[ei][si], snapshot.vol_matrix[ei + 1][si])
            assert lo - 1e-9 <= smile.vols[si] <= hi + 1e-9


class TestTermStructureExtractionProperty:
    """Property 14: 期限结构提取正确性与排序"""

    # Feature: advanced-order-hedging-volsurface, Property 14: 期限结构提取正确性与排序
    # Validates: Requirements 10.1, 10.2, 10.3
    @settings(max_examples=100)
    @given(data=vol_surface_st(), s_frac=st.floats(min_value=0.0, max_value=1.0))
    def test_property14_term_structure_extraction(self, data, s_frac):
        """Property 14: expiries 升序, 网格点匹配, 插值有界"""
        quotes, strikes, expiries = data
        builder = VolSurfaceBuilder()
        snapshot = builder.build_surface(quotes)

        s_min, s_max = snapshot.strikes[0], snapshot.strikes[-1]
        target_strike = s_min + (s_max - s_min) * s_frac

        ts = builder.extract_term_structure(snapshot, target_strike)

        # expiries 升序
        assert ts.expiries == sorted(ts.expiries)
        assert ts.expiries == snapshot.expiries

        # 当 target 匹配网格点时，vols 匹配对应列
        if target_strike in snapshot.strikes:
            si = snapshot.strikes.index(target_strike)
            for ei, vol in enumerate(ts.vols):
                assert abs(vol - snapshot.vol_matrix[ei][si]) < 1e-9

        # 当 target 在两个网格点之间时，每个 vol 有界
        import bisect
        si = bisect.bisect_right(snapshot.strikes, target_strike) - 1
        si = max(0, min(si, len(snapshot.strikes) - 2))
        for ei in range(len(snapshot.expiries)):
            lo = min(snapshot.vol_matrix[ei][si], snapshot.vol_matrix[ei][si + 1])
            hi = max(snapshot.vol_matrix[ei][si], snapshot.vol_matrix[ei][si + 1])
            assert lo - 1e-9 <= ts.vols[ei] <= hi + 1e-9


class TestVolSurfaceSerializationProperty:
    """Property 12: 波动率曲面序列化 Round-Trip"""

    # Feature: advanced-order-hedging-volsurface, Property 12: 波动率曲面序列化 Round-Trip
    # Validates: Requirements 8.4, 8.5
    @settings(max_examples=100)
    @given(data=vol_surface_st())
    def test_property12_serialization_roundtrip(self, data):
        """Property 12: to_dict -> from_dict round-trip"""
        quotes, strikes, expiries = data
        builder = VolSurfaceBuilder()
        snapshot = builder.build_surface(quotes)

        d = snapshot.to_dict()
        json_str = json.dumps(d)
        restored = VolSurfaceSnapshot.from_dict(json.loads(json_str))

        assert restored.strikes == snapshot.strikes
        assert restored.expiries == snapshot.expiries
        assert len(restored.vol_matrix) == len(snapshot.vol_matrix)
        for orig_row, rest_row in zip(snapshot.vol_matrix, restored.vol_matrix):
            assert len(rest_row) == len(orig_row)
            for o, r in zip(orig_row, rest_row):
                assert abs(o - r) < 1e-10


# ========== 单元测试 ==========

class TestVolSurfaceBuilderUnit:
    """VolSurfaceBuilder 单元测试"""

    def _make_quotes(self):
        """构建 2x2 网格报价"""
        return [
            VolQuote(strike=3000.0, time_to_expiry=0.25, implied_vol=0.20),
            VolQuote(strike=4000.0, time_to_expiry=0.25, implied_vol=0.25),
            VolQuote(strike=3000.0, time_to_expiry=0.50, implied_vol=0.22),
            VolQuote(strike=4000.0, time_to_expiry=0.50, implied_vol=0.28),
        ]

    def test_out_of_range_strike(self):
        """边界查询: 行权价超出范围"""
        builder = VolSurfaceBuilder()
        snapshot = builder.build_surface(self._make_quotes())
        result = builder.query_vol(snapshot, 2000.0, 0.30)
        assert result.success is False
        assert "超出范围" in result.error_message

    def test_out_of_range_expiry(self):
        """边界查询: 到期时间超出范围"""
        builder = VolSurfaceBuilder()
        snapshot = builder.build_surface(self._make_quotes())
        result = builder.query_vol(snapshot, 3500.0, 1.0)
        assert result.success is False
        assert "超出范围" in result.error_message

    def test_insufficient_strikes(self):
        """报价不足: < 2 strikes"""
        builder = VolSurfaceBuilder()
        quotes = [
            VolQuote(strike=3000.0, time_to_expiry=0.25, implied_vol=0.20),
            VolQuote(strike=3000.0, time_to_expiry=0.50, implied_vol=0.22),
        ]
        with pytest.raises(ValueError, match="报价不足"):
            builder.build_surface(quotes)

    def test_insufficient_expiries(self):
        """报价不足: < 2 expiries"""
        builder = VolSurfaceBuilder()
        quotes = [
            VolQuote(strike=3000.0, time_to_expiry=0.25, implied_vol=0.20),
            VolQuote(strike=4000.0, time_to_expiry=0.25, implied_vol=0.25),
        ]
        with pytest.raises(ValueError, match="报价不足"):
            builder.build_surface(quotes)

    def test_filter_invalid_vol(self):
        """无效报价过滤: implied_vol <= 0"""
        builder = VolSurfaceBuilder()
        quotes = self._make_quotes() + [
            VolQuote(strike=5000.0, time_to_expiry=0.25, implied_vol=-0.1),
            VolQuote(strike=5000.0, time_to_expiry=0.50, implied_vol=0.0),
        ]
        snapshot = builder.build_surface(quotes)
        # 无效报价被过滤，只有 2 个 strikes
        assert len(snapshot.strikes) == 2

    def test_query_at_grid_point(self):
        """网格点查询精确匹配"""
        builder = VolSurfaceBuilder()
        snapshot = builder.build_surface(self._make_quotes())
        result = builder.query_vol(snapshot, 3000.0, 0.25)
        assert result.success is True
        assert abs(result.implied_vol - 0.20) < 1e-10
