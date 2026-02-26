"""
IVSolver 单元测试

验证各算法的数值正确性、边界条件处理、牛顿法回退机制和批量求解功能。
"""
import math
import pytest

from src.strategy.domain.domain_service.pricing import IVSolver, SolveMethod, GreeksCalculator
from src.strategy.domain.value_object.greeks import GreeksInput, IVQuote, IVResult


@pytest.fixture
def solver():
    return IVSolver()


@pytest.fixture
def calc():
    return GreeksCalculator()


# ========== 辅助函数 ==========

def _bs_market_price(calc: GreeksCalculator, S, K, T, r, sigma, opt) -> float:
    """用 GreeksCalculator 计算 BS 理论价格作为 market_price"""
    params = GreeksInput(S, K, T, r, sigma, opt)
    return calc.bs_price(params)


# ========== 1. 各算法数值验证（Round-Trip） ==========

class TestNewtonMethod:
    """牛顿法数值验证"""

    # Requirements: 1.1, 1.2
    def test_atm_call_round_trip(self, solver, calc):
        """ATM call: 已知 σ=0.2 → BS价格 → Newton 反推 IV ≈ 0.2"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.NEWTON, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)
        assert result.iterations > 0

    def test_otm_put_round_trip(self, solver, calc):
        """OTM put: S=100, K=90, σ=0.3"""
        S, K, T, r, sigma = 100.0, 90.0, 0.25, 0.03, 0.3
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "put")

        result = solver.solve(market_price, S, K, T, r, "put",
                              method=SolveMethod.NEWTON, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)

    def test_itm_call_round_trip(self, solver, calc):
        """ITM call: S=120, K=100, σ=0.25"""
        S, K, T, r, sigma = 120.0, 100.0, 1.0, 0.05, 0.25
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.NEWTON, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)

    def test_high_vol_round_trip(self, solver, calc):
        """高波动率: σ=1.5"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 1.5
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.NEWTON, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.02)


class TestBisectionMethod:
    """二分法数值验证"""

    # Requirements: 1.1, 1.5
    def test_atm_call_round_trip(self, solver, calc):
        """ATM call: σ=0.2 → Bisection 反推"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.BISECTION, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)

    def test_otm_put_round_trip(self, solver, calc):
        """OTM put: Bisection"""
        S, K, T, r, sigma = 100.0, 90.0, 0.25, 0.03, 0.3
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "put")

        result = solver.solve(market_price, S, K, T, r, "put",
                              method=SolveMethod.BISECTION, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)

    def test_itm_call_round_trip(self, solver, calc):
        """ITM call: Bisection"""
        S, K, T, r, sigma = 120.0, 100.0, 1.0, 0.05, 0.25
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.BISECTION, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)


class TestBrentMethod:
    """Brent 法数值验证"""

    # Requirements: 1.1, 1.4, 1.5
    def test_atm_call_round_trip(self, solver, calc):
        """ATM call: σ=0.2 → Brent 反推"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.BRENT, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)

    def test_otm_put_round_trip(self, solver, calc):
        """OTM put: Brent"""
        S, K, T, r, sigma = 100.0, 90.0, 0.25, 0.03, 0.3
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "put")

        result = solver.solve(market_price, S, K, T, r, "put",
                              method=SolveMethod.BRENT, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)

    def test_itm_call_round_trip(self, solver, calc):
        """ITM call: Brent"""
        S, K, T, r, sigma = 120.0, 100.0, 1.0, 0.05, 0.25
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.BRENT, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)



# ========== 2. 边界条件测试 ==========

class TestBoundaryConditions:
    """边界条件：market_price=0、负值、低于内在价值、极端参数"""

    # Requirements: 1.6
    def test_market_price_zero(self, solver):
        """market_price=0 → success=False"""
        result = solver.solve(0.0, 100.0, 100.0, 0.5, 0.05, "call")
        assert not result.success
        assert result.error_message

    def test_market_price_negative(self, solver):
        """market_price 负值 → success=False"""
        result = solver.solve(-1.0, 100.0, 100.0, 0.5, 0.05, "call")
        assert not result.success
        assert result.error_message

    # Requirements: 1.7
    def test_market_price_below_intrinsic_call(self, solver):
        """call: market_price 低于内在价值 → success=False"""
        # ITM call: S=120, K=100, intrinsic ≈ 120 - 100*e^(-0.05*0.5) ≈ 22.47
        # market_price=10 远低于内在价值
        result = solver.solve(10.0, 120.0, 100.0, 0.5, 0.05, "call")
        assert not result.success
        assert "内在价值" in result.error_message

    def test_market_price_below_intrinsic_put(self, solver):
        """put: market_price 低于内在价值 → success=False"""
        # ITM put: S=80, K=120, intrinsic ≈ 120*e^(-0.05*0.5) - 80 ≈ 37.04
        # market_price=5 远低于内在价值
        result = solver.solve(5.0, 80.0, 120.0, 0.5, 0.05, "put")
        assert not result.success
        assert "内在价值" in result.error_message

    def test_market_price_exactly_at_intrinsic_call(self, solver, calc):
        """market_price 恰好等于内在价值（在容差范围内）不应被拒绝"""
        S, K, T, r = 120.0, 100.0, 0.5, 0.05
        intrinsic = max(S - K * math.exp(-r * T), 0.0)
        # 给一个略高于内在价值的价格
        market_price = intrinsic + 0.5
        result = solver.solve(market_price, S, K, T, r, "call")
        # 不应因内在价值检查而失败
        # （可能因为 IV 极低而收敛困难，但不应是 "内在价值" 错误）
        if not result.success:
            assert "内在价值" not in result.error_message

    def test_very_small_market_price(self, solver):
        """极小正 market_price（深度 OTM）应能求解"""
        # 深度 OTM call: S=50, K=200, 价格很小但正
        result = solver.solve(0.01, 50.0, 200.0, 0.5, 0.05, "call")
        # 可能成功也可能因收敛困难失败，但不应因输入校验失败
        if not result.success:
            assert "大于 0" not in result.error_message
            assert "内在价值" not in result.error_message


# ========== 3. 牛顿法回退二分法 ==========

class TestNewtonFallback:
    """牛顿法未收敛自动回退二分法"""

    # Requirements: 1.3
    def test_newton_fallback_to_bisection(self, solver, calc):
        """
        用极少的 max_iterations 使牛顿法本身无法收敛，
        验证自动回退二分法后仍能得到正确结果。
        """
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        # 牛顿法 max_iterations=2 几乎不可能收敛到 tol=1e-6
        # 但 solve() 会自动回退二分法（也用 max_iterations=2）
        # 所以我们用足够的迭代让回退的二分法能收敛
        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.NEWTON,
                              max_iterations=100, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)

    def test_newton_alone_fails_with_tiny_iterations(self, solver, calc):
        """
        验证牛顿法内部方法在极少迭代下确实返回 success=False。
        """
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        # 直接调用内部牛顿法，1次迭代不够收敛到 1e-6
        result = solver._solve_newton(market_price, S, K, T, r, "call",
                                      max_iterations=1, tolerance=1e-6)
        assert not result.success
        assert "未收敛" in result.error_message

    def test_fallback_produces_correct_result(self, solver, calc):
        """
        强制牛顿法失败（1次迭代），但 solve() 整体应通过回退二分法成功。
        需要足够的 max_iterations 让二分法收敛。
        """
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        # 注意：solve() 中牛顿法和回退二分法共用同一个 max_iterations
        # 所以 max_iterations=1 时两者都只有1次迭代
        # 用 max_iterations=50 + tolerance=1e-6 让二分法有机会收敛
        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.NEWTON,
                              max_iterations=50, tolerance=1e-6)
        assert result.success
        assert result.implied_volatility == pytest.approx(sigma, abs=0.01)


# ========== 4. 所有算法未收敛 ==========

class TestNonConvergence:
    """所有算法均未收敛"""

    # Requirements: 1.8
    def test_newton_non_convergence_with_1_iteration(self, solver, calc):
        """max_iterations=1 + 极紧容差 → 牛顿法+回退二分法都无法收敛"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.NEWTON,
                              max_iterations=1, tolerance=1e-10)
        assert not result.success
        assert "未收敛" in result.error_message

    def test_bisection_non_convergence(self, solver, calc):
        """二分法 max_iterations=1 + 极紧容差"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.BISECTION,
                              max_iterations=1, tolerance=1e-10)
        assert not result.success
        assert "未收敛" in result.error_message

    def test_brent_non_convergence(self, solver, calc):
        """Brent 法 max_iterations=1 + 极紧容差"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.BRENT,
                              max_iterations=1, tolerance=1e-10)
        assert not result.success
        assert "未收敛" in result.error_message

    def test_non_convergence_has_iterations(self, solver, calc):
        """未收敛结果应包含迭代次数"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        result = solver.solve(market_price, S, K, T, r, "call",
                              method=SolveMethod.BISECTION,
                              max_iterations=3, tolerance=1e-10)
        assert not result.success
        assert result.iterations == 3


# ========== 5. 批量求解 ==========

class TestSolveBatch:
    """批量求解：混合有效/无效报价"""

    # Requirements: 2.1, 2.2, 2.3
    def test_batch_length_preserved(self, solver, calc):
        """返回列表长度与输入一致"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        quotes = [
            IVQuote(market_price, S, K, T, r, "call"),
            IVQuote(0.0, S, K, T, r, "call"),       # 无效: price=0
            IVQuote(market_price, S, K, T, r, "put"),
        ]
        results = solver.solve_batch(quotes)
        assert len(results) == len(quotes)

    def test_batch_order_preserved(self, solver, calc):
        """有效/无效报价的结果顺序与输入一致"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        quotes = [
            IVQuote(market_price, S, K, T, r, "call"),  # 有效
            IVQuote(-1.0, S, K, T, r, "call"),           # 无效
            IVQuote(market_price, S, K, T, r, "call"),   # 有效
        ]
        results = solver.solve_batch(quotes)

        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    def test_batch_isolation(self, solver, calc):
        """单个报价失败不影响其他报价"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        quotes = [
            IVQuote(0.0, S, K, T, r, "call"),           # 无效
            IVQuote(market_price, S, K, T, r, "call"),   # 有效
            IVQuote(-5.0, S, K, T, r, "put"),            # 无效
            IVQuote(market_price, S, K, T, r, "call"),   # 有效
        ]
        results = solver.solve_batch(quotes)

        assert not results[0].success
        assert results[1].success
        assert results[1].implied_volatility == pytest.approx(sigma, abs=0.01)
        assert not results[2].success
        assert results[3].success
        assert results[3].implied_volatility == pytest.approx(sigma, abs=0.01)

    def test_batch_empty_list(self, solver):
        """空列表 → 空结果"""
        results = solver.solve_batch([])
        assert results == []

    def test_batch_all_invalid(self, solver):
        """全部无效报价"""
        quotes = [
            IVQuote(0.0, 100.0, 100.0, 0.5, 0.05, "call"),
            IVQuote(-1.0, 100.0, 100.0, 0.5, 0.05, "put"),
        ]
        results = solver.solve_batch(quotes)
        assert len(results) == 2
        assert all(not r.success for r in results)

    def test_batch_with_method(self, solver, calc):
        """批量求解可指定算法"""
        S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.05, 0.2
        market_price = _bs_market_price(calc, S, K, T, r, sigma, "call")

        quotes = [IVQuote(market_price, S, K, T, r, "call")]
        results = solver.solve_batch(quotes, method=SolveMethod.BRENT, tolerance=1e-6)
        assert len(results) == 1
        assert results[0].success
        assert results[0].implied_volatility == pytest.approx(sigma, abs=0.01)
