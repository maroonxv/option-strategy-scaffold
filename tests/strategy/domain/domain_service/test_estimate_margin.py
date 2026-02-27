"""estimate_margin 单元测试"""
import pytest
from src.strategy.domain.domain_service.risk.position_sizing_service import PositionSizingService
from src.strategy.domain.value_object.config.position_sizing_config import PositionSizingConfig


@pytest.fixture
def service():
    return PositionSizingService(config=PositionSizingConfig(margin_ratio=0.12, min_margin_ratio=0.07))


class TestEstimateMargin:
    """验证 estimate_margin 保证金估算公式 (Requirements 1.1)"""

    def test_put_otm(self, service: PositionSizingService):
        """OTM put: 行权价 < 标的价格，虚值额 = 0"""
        # strike=3.0 < underlying=4.0 → OTM put, out_of_money = 0
        result = service.estimate_margin(
            contract_price=0.5, underlying_price=4.0,
            strike_price=3.0, option_type="put", multiplier=10000,
        )
        premium = 0.5 * 10000  # 5000
        # max(4*10000*0.12 - 0, 4*10000*0.07) = max(4800, 2800) = 4800
        expected = premium + 4800
        assert result == pytest.approx(expected)

    def test_put_itm(self, service: PositionSizingService):
        """ITM put: 行权价 > 标的价格，虚值额 > 0"""
        # strike=5.0 > underlying=4.0 → ITM put, out_of_money = (5-4)*10000 = 10000
        result = service.estimate_margin(
            contract_price=1.2, underlying_price=4.0,
            strike_price=5.0, option_type="put", multiplier=10000,
        )
        premium = 1.2 * 10000  # 12000
        # max(4*10000*0.12 - 10000, 4*10000*0.07) = max(4800-10000, 2800) = max(-5200, 2800) = 2800
        expected = premium + 2800
        assert result == pytest.approx(expected)

    def test_call_otm(self, service: PositionSizingService):
        """OTM call: 标的价格 < 行权价，虚值额 = 0"""
        # underlying=3.0 < strike=4.0 → OTM call, out_of_money = 0
        result = service.estimate_margin(
            contract_price=0.3, underlying_price=3.0,
            strike_price=4.0, option_type="call", multiplier=10000,
        )
        premium = 0.3 * 10000  # 3000
        # max(3*10000*0.12 - 0, 3*10000*0.07) = max(3600, 2100) = 3600
        expected = premium + 3600
        assert result == pytest.approx(expected)

    def test_call_itm(self, service: PositionSizingService):
        """ITM call: 标的价格 > 行权价，虚值额 > 0"""
        # underlying=5.0 > strike=4.0 → ITM call, out_of_money = (5-4)*10000 = 10000
        result = service.estimate_margin(
            contract_price=1.5, underlying_price=5.0,
            strike_price=4.0, option_type="call", multiplier=10000,
        )
        premium = 1.5 * 10000  # 15000
        # max(5*10000*0.12 - 10000, 5*10000*0.07) = max(6000-10000, 3500) = max(-4000, 3500) = 3500
        expected = premium + 3500
        assert result == pytest.approx(expected)

    def test_atm_put(self, service: PositionSizingService):
        """ATM put: 行权价 == 标的价格，虚值额 = 0"""
        result = service.estimate_margin(
            contract_price=0.8, underlying_price=4.0,
            strike_price=4.0, option_type="put", multiplier=10000,
        )
        premium = 0.8 * 10000
        expected = premium + max(4 * 10000 * 0.12, 4 * 10000 * 0.07)
        assert result == pytest.approx(expected)

    def test_atm_call(self, service: PositionSizingService):
        """ATM call: 行权价 == 标的价格，虚值额 = 0"""
        result = service.estimate_margin(
            contract_price=0.8, underlying_price=4.0,
            strike_price=4.0, option_type="call", multiplier=10000,
        )
        premium = 0.8 * 10000
        expected = premium + max(4 * 10000 * 0.12, 4 * 10000 * 0.07)
        assert result == pytest.approx(expected)

    def test_min_margin_ratio_floor(self, service: PositionSizingService):
        """当 margin_ratio 项被虚值额抵消到低于 min_margin_ratio 项时，取 min_margin_ratio"""
        # Deep ITM put: strike=10, underlying=4 → out_of_money = 6*10000 = 60000
        result = service.estimate_margin(
            contract_price=6.5, underlying_price=4.0,
            strike_price=10.0, option_type="put", multiplier=10000,
        )
        premium = 6.5 * 10000  # 65000
        # max(4*10000*0.12 - 60000, 4*10000*0.07) = max(4800-60000, 2800) = 2800
        expected = premium + 2800
        assert result == pytest.approx(expected)
