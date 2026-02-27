"""
VolSurfaceBuilder - 波动率曲面构建器

从市场期权报价构建波动率曲面，支持双线性插值查询、微笑提取和期限结构提取。
"""
import bisect
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ....value_object.pricing.vol_surface import (
    VolQuote, VolQueryResult, VolSmile, TermStructure, VolSurfaceSnapshot,
)


class VolSurfaceBuilder:
    """波动率曲面构建器"""

    def build_surface(self, quotes: List[VolQuote]) -> VolSurfaceSnapshot:
        """从报价列表构建波动率曲面，过滤 implied_vol <= 0 的报价"""
        valid = [q for q in quotes if q.implied_vol > 0]

        strikes = sorted(set(q.strike for q in valid))
        expiries = sorted(set(q.time_to_expiry for q in valid))

        if len(strikes) < 2 or len(expiries) < 2:
            raise ValueError(
                f"报价不足以构建曲面: {len(strikes)} strikes, {len(expiries)} expiries (需要至少各 2 个)"
            )

        # 构建查找表
        lookup: Dict[Tuple[float, float], float] = {}
        for q in valid:
            lookup[(q.time_to_expiry, q.strike)] = q.implied_vol

        # 构建矩阵 [expiry_idx][strike_idx]
        vol_matrix: List[List[float]] = []
        for exp in expiries:
            row: List[float] = []
            for stk in strikes:
                row.append(lookup.get((exp, stk), 0.0))
            vol_matrix.append(row)

        return VolSurfaceSnapshot(
            strikes=strikes,
            expiries=expiries,
            vol_matrix=vol_matrix,
            timestamp=datetime.now(),
        )

    def query_vol(
        self, snapshot: VolSurfaceSnapshot, strike: float, time_to_expiry: float
    ) -> VolQueryResult:
        """双线性插值查询隐含波动率"""
        strikes = snapshot.strikes
        expiries = snapshot.expiries
        matrix = snapshot.vol_matrix

        if not strikes or not expiries:
            return VolQueryResult(success=False, error_message="曲面为空")

        # 检查范围 (带浮点容差)
        eps = 1e-9
        if strike < strikes[0] - eps or strike > strikes[-1] + eps:
            return VolQueryResult(
                success=False,
                error_message=f"行权价 {strike} 超出范围 [{strikes[0]}, {strikes[-1]}]",
            )
        if time_to_expiry < expiries[0] - eps or time_to_expiry > expiries[-1] + eps:
            return VolQueryResult(
                success=False,
                error_message=f"到期时间 {time_to_expiry} 超出范围 [{expiries[0]}, {expiries[-1]}]",
            )
        # 钳位到范围内
        strike = max(strikes[0], min(strike, strikes[-1]))
        time_to_expiry = max(expiries[0], min(time_to_expiry, expiries[-1]))

        # 找到包围的索引
        si = bisect.bisect_right(strikes, strike) - 1
        si = min(si, len(strikes) - 2)
        ei = bisect.bisect_right(expiries, time_to_expiry) - 1
        ei = min(ei, len(expiries) - 2)

        s0, s1 = strikes[si], strikes[si + 1]
        e0, e1 = expiries[ei], expiries[ei + 1]

        # 双线性插值
        if s1 == s0:
            ts = 0.0
        else:
            ts = (strike - s0) / (s1 - s0)
        if e1 == e0:
            te = 0.0
        else:
            te = (time_to_expiry - e0) / (e1 - e0)

        v00 = matrix[ei][si]
        v01 = matrix[ei][si + 1]
        v10 = matrix[ei + 1][si]
        v11 = matrix[ei + 1][si + 1]

        vol = v00 * (1 - ts) * (1 - te) + v01 * ts * (1 - te) + v10 * (1 - ts) * te + v11 * ts * te

        return VolQueryResult(implied_vol=vol, success=True)

    def extract_smile(
        self, snapshot: VolSurfaceSnapshot, time_to_expiry: float
    ) -> VolSmile:
        """提取指定到期时间的波动率微笑，支持插值"""
        vols: List[float] = []
        for strike in snapshot.strikes:
            result = self.query_vol(snapshot, strike, time_to_expiry)
            vols.append(result.implied_vol if result.success else 0.0)

        return VolSmile(
            time_to_expiry=time_to_expiry,
            strikes=list(snapshot.strikes),
            vols=vols,
        )

    def extract_term_structure(
        self, snapshot: VolSurfaceSnapshot, strike: float
    ) -> TermStructure:
        """提取指定行权价的期限结构，支持插值"""
        vols: List[float] = []
        for exp in snapshot.expiries:
            result = self.query_vol(snapshot, strike, exp)
            vols.append(result.implied_vol if result.success else 0.0)

        return TermStructure(
            strike=strike,
            expiries=list(snapshot.expiries),
            vols=vols,
        )
