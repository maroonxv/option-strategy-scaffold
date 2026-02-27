"""
calculate_open_volume / calculate_close_volume 编排逻辑与边界条件单元测试

覆盖:
- 前置风控检查保留（最大持仓、日限额、重复合约）
- compute_sizing 拒绝 → calculate_open_volume 返回 None
- Greek 值为零维度不参与最小值计算
- 配置默认值
- calculate_close_volume 保持不变
- Happy path
"""
import pytest

from src.strategy.domain.domain_service.risk.position_sizing_service import PositionSizingService
from src.strategy.domain.value_object.config.position_sizing_config import PositionSizingConfig
from src.strategy.domain.value_object.order_instruction import OrderInstruction, Direction, Offset
from src.strategy.domain.value_object.greeks import GreeksResult
from src.strategy.domain.value_object.risk import PortfolioGreeks, RiskThresholds
from src.strategy.domain.entity.position import Position


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _greeks(delta=-0.3, gamma=0.05, vega=0.15):
    return GreeksResult(delta=delta, gamma=gamma, vega=vega, theta=-0.02, success=True)


def _portfolio(total_delta=0.0, total_gamma=0.0, total_vega=0.0):
    return PortfolioGreeks(
        total_delta=total_delta, total_gamma=total_gamma,
        total_theta=0.0, total_vega=total_vega,
    )


def _thresholds(delta_limit=100.0, gamma_limit=50.0, vega_limit=200.0):
    return RiskThresholds(
        portfolio_delta_limit=delta_limit,
        portfolio_gamma_limit=gamma_limit,
        portfolio_vega_limit=vega_limit,
    )


def _active_position(vt_symbol="OPT-A.SSE", volume=1):
    """创建一个活跃持仓"""
    return Position(
        vt_symbol=vt_symbol,
        underlying_vt_symbol="ETF.SSE",
        signal="sell_put",
        volume=volume,
        direction="short",
    )


# 通用开仓参数（充足资金、宽松阈值）
_OPEN_KWARGS = dict(
    account_balance=500_000.0,
    total_equity=1_000_000.0,
    used_margin=100_000.0,
    signal="sell_put",
    vt_symbol="OPT-X.SSE",
    contract_price=200.0,
    underlying_price=4000.0,
    strike_price=3800.0,
    option_type="put",
    multiplier=10.0,
    greeks=_greeks(),
    portfolio_greeks=_portfolio(),
    risk_thresholds=_thresholds(),
    current_positions=[],
    current_daily_open_count=0,
    current_contract_open_count=0,
)


# ===========================================================================
# 1. Pre-check retention tests (calculate_open_volume)
# ===========================================================================

class TestPreCheckRetention:
    """前置风控检查保留验证"""

    def test_returns_none_when_max_positions_reached(self):
        svc = PositionSizingService(config=PositionSizingConfig(max_positions=2))
        positions = [_active_position(f"OPT-{i}.SSE") for i in range(2)]
        result = svc.calculate_open_volume(**{**_OPEN_KWARGS, "current_positions": positions})
        assert result is None

    def test_returns_none_when_global_daily_limit_exceeded(self):
        svc = PositionSizingService(config=PositionSizingConfig(global_daily_limit=5))
        result = svc.calculate_open_volume(**{**_OPEN_KWARGS, "current_daily_open_count": 5})
        assert result is None

    def test_returns_none_when_contract_daily_limit_exceeded(self):
        svc = PositionSizingService(config=PositionSizingConfig(contract_daily_limit=2))
        result = svc.calculate_open_volume(**{**_OPEN_KWARGS, "current_contract_open_count": 2})
        assert result is None

    def test_returns_none_when_duplicate_contract_in_active_positions(self):
        svc = PositionSizingService()
        dup = _active_position(vt_symbol="OPT-X.SSE")  # same as _OPEN_KWARGS vt_symbol
        result = svc.calculate_open_volume(**{**_OPEN_KWARGS, "current_positions": [dup]})
        assert result is None


# ===========================================================================
# 2. compute_sizing rejection → calculate_open_volume returns None
# ===========================================================================

class TestComputeSizingRejectionPropagation:
    """compute_sizing 拒绝时 calculate_open_volume 返回 None"""

    def test_returns_none_when_margin_le_zero(self):
        """contract_price=0, underlying_price=0 → 保证金 <= 0"""
        svc = PositionSizingService()
        result = svc.calculate_open_volume(**{
            **_OPEN_KWARGS,
            "contract_price": 0.0,
            "underlying_price": 0.0,
            "strike_price": 0.0,
        })
        assert result is None

    def test_returns_none_when_insufficient_funds(self):
        """极小 account_balance → 资金不足"""
        svc = PositionSizingService()
        result = svc.calculate_open_volume(**{**_OPEN_KWARGS, "account_balance": 1.0})
        assert result is None

    def test_returns_none_when_margin_usage_exceeded(self):
        """used_margin 过高 → 使用率超限"""
        svc = PositionSizingService(config=PositionSizingConfig(margin_usage_limit=0.6))
        result = svc.calculate_open_volume(**{
            **_OPEN_KWARGS,
            "total_equity": 100_000.0,
            "used_margin": 90_000.0,
        })
        assert result is None

    def test_returns_none_when_greeks_limit_exceeded(self):
        """Greeks 超限"""
        svc = PositionSizingService()
        result = svc.calculate_open_volume(**{
            **_OPEN_KWARGS,
            "greeks": _greeks(delta=-5.0),
            "portfolio_greeks": _portfolio(total_delta=99.0),
            "risk_thresholds": _thresholds(delta_limit=100.0),
        })
        assert result is None


# ===========================================================================
# 3. Greek value zero dimension tests
# ===========================================================================

class TestGreekZeroDimension:
    """Greek 值为零的维度不参与最小值计算"""

    def test_zero_delta_not_in_min(self):
        svc = PositionSizingService()
        greeks = _greeks(delta=0.0, gamma=0.05, vega=0.15)
        vol, d_b, g_b, v_b = svc._calc_greeks_volume(
            greeks, 10.0, _portfolio(), _thresholds(),
        )
        # delta=0 → 不参与, 结果由 gamma 和 vega 决定
        gamma_vol = 50.0 / abs(0.05 * 10.0)   # 100
        vega_vol = 200.0 / abs(0.15 * 10.0)   # 133
        assert vol == int(min(gamma_vol, vega_vol))

    def test_zero_gamma_not_in_min(self):
        svc = PositionSizingService()
        greeks = _greeks(delta=-0.3, gamma=0.0, vega=0.15)
        vol, _, _, _ = svc._calc_greeks_volume(
            greeks, 10.0, _portfolio(), _thresholds(),
        )
        delta_vol = 100.0 / abs(-0.3 * 10.0)  # 33
        vega_vol = 200.0 / abs(0.15 * 10.0)   # 133
        assert vol == int(min(delta_vol, vega_vol))

    def test_zero_vega_not_in_min(self):
        svc = PositionSizingService()
        greeks = _greeks(delta=-0.3, gamma=0.05, vega=0.0)
        vol, _, _, _ = svc._calc_greeks_volume(
            greeks, 10.0, _portfolio(), _thresholds(),
        )
        delta_vol = 100.0 / abs(-0.3 * 10.0)  # 33
        gamma_vol = 50.0 / abs(0.05 * 10.0)   # 100
        assert vol == int(min(delta_vol, gamma_vol))

    def test_all_greeks_zero_returns_max(self):
        """所有 Greek 值为零 → 无限制 (999999)"""
        svc = PositionSizingService()
        greeks = _greeks(delta=0.0, gamma=0.0, vega=0.0)
        vol, _, _, _ = svc._calc_greeks_volume(
            greeks, 10.0, _portfolio(), _thresholds(),
        )
        assert vol == 999999


# ===========================================================================
# 4. Configuration defaults test
# ===========================================================================

class TestConfigurationDefaults:
    """验证 PositionSizingService 默认值匹配 spec"""

    def test_default_margin_ratio(self):
        svc = PositionSizingService()
        assert svc._config.margin_ratio == 0.12

    def test_default_min_margin_ratio(self):
        svc = PositionSizingService()
        assert svc._config.min_margin_ratio == 0.07

    def test_default_margin_usage_limit(self):
        svc = PositionSizingService()
        assert svc._config.margin_usage_limit == 0.6

    def test_default_max_volume_per_order(self):
        svc = PositionSizingService()
        assert svc._config.max_volume_per_order == 10


# ===========================================================================
# 5. calculate_close_volume unchanged tests
# ===========================================================================

class TestCalculateCloseVolume:
    """calculate_close_volume 保持不变验证"""

    def test_generates_buy_to_close_instruction(self):
        svc = PositionSizingService()
        pos = _active_position(volume=3)
        result = svc.calculate_close_volume(pos, close_price=150.0, signal="close_signal")
        assert result is not None
        assert result.direction == Direction.LONG
        assert result.offset == Offset.CLOSE
        assert result.volume == 3
        assert result.price == 150.0
        assert result.signal == "close_signal"

    def test_returns_none_for_inactive_position(self):
        svc = PositionSizingService()
        pos = _active_position(volume=2)
        pos.is_closed = True
        result = svc.calculate_close_volume(pos, close_price=100.0)
        assert result is None

    def test_returns_none_for_zero_volume_position(self):
        svc = PositionSizingService()
        pos = _active_position(volume=0)
        result = svc.calculate_close_volume(pos, close_price=100.0)
        assert result is None


# ===========================================================================
# 6. Happy path test
# ===========================================================================

class TestHappyPath:
    """calculate_open_volume 正常路径"""

    def test_returns_order_instruction_with_correct_volume(self):
        svc = PositionSizingService(config=PositionSizingConfig(max_volume_per_order=10))
        result = svc.calculate_open_volume(**_OPEN_KWARGS)
        assert result is not None
        assert isinstance(result, OrderInstruction)
        assert result.direction == Direction.SHORT
        assert result.offset == Offset.OPEN
        assert 1 <= result.volume <= 10
        assert result.vt_symbol == "OPT-X.SSE"
        assert result.price == 200.0
        assert result.signal == "sell_put"

    def test_volume_matches_compute_sizing(self):
        """final_volume 与 compute_sizing 结果一致"""
        svc = PositionSizingService()
        sizing = svc.compute_sizing(
            account_balance=500_000.0,
            total_equity=1_000_000.0,
            used_margin=100_000.0,
            contract_price=200.0,
            underlying_price=4000.0,
            strike_price=3800.0,
            option_type="put",
            multiplier=10.0,
            greeks=_greeks(),
            portfolio_greeks=_portfolio(),
            risk_thresholds=_thresholds(),
        )
        order = svc.calculate_open_volume(**_OPEN_KWARGS)
        assert order is not None
        assert order.volume == sizing.final_volume
