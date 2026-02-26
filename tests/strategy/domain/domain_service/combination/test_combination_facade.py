"""
CombinationFacade 单元测试

验证 Facade 子服务异常传播：当子服务抛出异常时 evaluate 不静默吞没。

_Requirements: 6.4_
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.strategy.domain.domain_service.combination.combination_facade import (
    CombinationFacade,
)
from src.strategy.domain.domain_service.combination.combination_greeks_calculator import (
    CombinationGreeksCalculator,
)
from src.strategy.domain.domain_service.combination.combination_pnl_calculator import (
    CombinationPnLCalculator,
)
from src.strategy.domain.domain_service.combination.combination_risk_checker import (
    CombinationRiskChecker,
)
from src.strategy.domain.entity.combination import Combination
from src.strategy.domain.value_object.combination import (
    CombinationGreeks,
    CombinationPnL,
    CombinationRiskConfig,
    CombinationStatus,
    CombinationType,
    Leg,
)
from src.strategy.domain.value_object.greeks import GreeksResult
from src.strategy.domain.value_object.risk import RiskCheckResult


def _make_combination() -> Combination:
    """构建一个简单的测试 Combination。"""
    return Combination(
        combination_id="test-facade",
        combination_type=CombinationType.CUSTOM,
        underlying_vt_symbol="TEST.UND",
        legs=[
            Leg(
                vt_symbol="OPT1.TEST",
                option_type="call",
                strike_price=3000.0,
                expiry_date="20250901",
                direction="long",
                volume=1,
                open_price=100.0,
            ),
        ],
        status=CombinationStatus.ACTIVE,
        create_time=datetime(2025, 1, 1),
    )


class TestFacadeExceptionPropagation:
    """验证 Facade 子服务异常传播 - Requirements 6.4"""

    def _make_facade(self, greeks_calc=None, pnl_calc=None, risk_checker=None):
        """构建 Facade，允许注入 mock 子服务。"""
        greeks_calc = greeks_calc or MagicMock(spec=CombinationGreeksCalculator)
        pnl_calc = pnl_calc or MagicMock(spec=CombinationPnLCalculator)
        risk_checker = risk_checker or MagicMock(spec=CombinationRiskChecker)
        return CombinationFacade(greeks_calc, pnl_calc, risk_checker)

    def test_greeks_calculator_exception_propagates(self):
        """当 GreeksCalculator 抛出异常时，Facade 应传播该异常。"""
        greeks_calc = MagicMock(spec=CombinationGreeksCalculator)
        greeks_calc.calculate.side_effect = ValueError("Greeks 计算失败")

        facade = self._make_facade(greeks_calc=greeks_calc)
        combination = _make_combination()

        with pytest.raises(ValueError, match="Greeks 计算失败"):
            facade.evaluate(
                combination,
                greeks_map={"OPT1.TEST": GreeksResult()},
                current_prices={"OPT1.TEST": 110.0},
                multiplier=10.0,
            )

    def test_pnl_calculator_exception_propagates(self):
        """当 PnLCalculator 抛出异常时，Facade 应传播该异常。"""
        greeks_calc = MagicMock(spec=CombinationGreeksCalculator)
        greeks_calc.calculate.return_value = CombinationGreeks()

        pnl_calc = MagicMock(spec=CombinationPnLCalculator)
        pnl_calc.calculate.side_effect = RuntimeError("PnL 计算失败")

        facade = self._make_facade(greeks_calc=greeks_calc, pnl_calc=pnl_calc)
        combination = _make_combination()

        with pytest.raises(RuntimeError, match="PnL 计算失败"):
            facade.evaluate(
                combination,
                greeks_map={"OPT1.TEST": GreeksResult()},
                current_prices={"OPT1.TEST": 110.0},
                multiplier=10.0,
            )

    def test_risk_checker_exception_propagates(self):
        """当 RiskChecker 抛出异常时，Facade 应传播该异常。"""
        greeks_calc = MagicMock(spec=CombinationGreeksCalculator)
        greeks_calc.calculate.return_value = CombinationGreeks()

        pnl_calc = MagicMock(spec=CombinationPnLCalculator)
        pnl_calc.calculate.return_value = CombinationPnL(total_unrealized_pnl=0.0)

        risk_checker = MagicMock(spec=CombinationRiskChecker)
        risk_checker.check.side_effect = TypeError("风控检查失败")

        facade = self._make_facade(
            greeks_calc=greeks_calc, pnl_calc=pnl_calc, risk_checker=risk_checker
        )
        combination = _make_combination()

        with pytest.raises(TypeError, match="风控检查失败"):
            facade.evaluate(
                combination,
                greeks_map={"OPT1.TEST": GreeksResult()},
                current_prices={"OPT1.TEST": 110.0},
                multiplier=10.0,
            )

    def test_greeks_exception_prevents_pnl_and_risk(self):
        """当 GreeksCalculator 异常时，PnL 和 RiskChecker 不应被调用。"""
        greeks_calc = MagicMock(spec=CombinationGreeksCalculator)
        greeks_calc.calculate.side_effect = ValueError("Greeks 异常")

        pnl_calc = MagicMock(spec=CombinationPnLCalculator)
        risk_checker = MagicMock(spec=CombinationRiskChecker)

        facade = self._make_facade(
            greeks_calc=greeks_calc, pnl_calc=pnl_calc, risk_checker=risk_checker
        )
        combination = _make_combination()

        with pytest.raises(ValueError):
            facade.evaluate(
                combination,
                greeks_map={},
                current_prices={},
                multiplier=10.0,
            )

        pnl_calc.calculate.assert_not_called()
        risk_checker.check.assert_not_called()

    def test_pnl_exception_prevents_risk_check(self):
        """当 PnLCalculator 异常时，RiskChecker 不应被调用。"""
        greeks_calc = MagicMock(spec=CombinationGreeksCalculator)
        greeks_calc.calculate.return_value = CombinationGreeks()

        pnl_calc = MagicMock(spec=CombinationPnLCalculator)
        pnl_calc.calculate.side_effect = RuntimeError("PnL 异常")

        risk_checker = MagicMock(spec=CombinationRiskChecker)

        facade = self._make_facade(
            greeks_calc=greeks_calc, pnl_calc=pnl_calc, risk_checker=risk_checker
        )
        combination = _make_combination()

        with pytest.raises(RuntimeError):
            facade.evaluate(
                combination,
                greeks_map={},
                current_prices={},
                multiplier=10.0,
            )

        risk_checker.check.assert_not_called()
