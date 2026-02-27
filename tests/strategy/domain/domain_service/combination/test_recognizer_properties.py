"""
Property 4: Recognizer 表驱动行为等价性 - 属性测试

Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

*For any* 持仓列表和合约映射，表驱动重构后的 CombinationRecognizer 应返回与重构前完全相同的
CombinationType 结果。特别地：空列表返回 CUSTOM，合约缺失返回 CUSTOM，匹配规则按
IRON_CONDOR → STRADDLE → STRANGLE → VERTICAL_SPREAD → CALENDAR_SPREAD 优先级执行。

**Validates: Requirements 2.3, 2.4, 2.5, 2.6**

测试策略：
- Generate position structures for each combination type
- Verify recognition results match expected types
- Test edge cases: empty list returns CUSTOM, missing contracts return CUSTOM
- Verify priority order is respected
"""
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.strategy.domain.domain_service.combination.combination_recognizer import (
    CombinationRecognizer,
)
from src.strategy.domain.entity.position import Position
from src.strategy.domain.value_object.combination import CombinationType
from src.strategy.domain.value_object.market.option_contract import OptionContract


# ---------------------------------------------------------------------------
# 基础策略
# ---------------------------------------------------------------------------

_underlying = st.sampled_from(["m2509.DCE", "cu2506.SHFE", "i2509.DCE", "SR509.CZCE"])
_expiry = st.sampled_from(["20250901", "20251001", "20251101", "20251201"])
_strike = st.floats(
    min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False
)
_direction = st.sampled_from(["long", "short"])


def _make_position(vt_symbol: str, underlying: str, direction: str = "short") -> Position:
    """创建一个最小化的 Position 实例。"""
    return Position(
        vt_symbol=vt_symbol,
        underlying_vt_symbol=underlying,
        signal="test",
        volume=1,
        target_volume=1,
        direction=direction,
    )


def _make_contract(
    vt_symbol: str,
    underlying: str,
    option_type: str,
    strike_price: float,
    expiry_date: str,
) -> OptionContract:
    """创建一个最小化的 OptionContract 实例。"""
    return OptionContract(
        vt_symbol=vt_symbol,
        underlying_symbol=underlying,
        option_type=option_type,
        strike_price=strike_price,
        expiry_date=expiry_date,
        diff1=0.0,
        bid_price=1.0,
        bid_volume=10,
        ask_price=1.5,
        ask_volume=10,
        days_to_expiry=30,
    )


# ---------------------------------------------------------------------------
# 生成器：为每种组合类型生成有效的 (positions, contracts) 对
# ---------------------------------------------------------------------------


@st.composite
def straddle_inputs(draw):
    """
    STRADDLE: 2 positions, 同标的, 同到期日, 同行权价, 一 Call 一 Put
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)
    strike = draw(_strike)
    dir1 = draw(_direction)
    dir2 = draw(_direction)

    sym_c = f"{underlying}-C-{strike}-{expiry}"
    sym_p = f"{underlying}-P-{strike}-{expiry}"

    positions = [
        _make_position(sym_c, underlying, dir1),
        _make_position(sym_p, underlying, dir2),
    ]
    contracts = {
        sym_c: _make_contract(sym_c, underlying, "call", strike, expiry),
        sym_p: _make_contract(sym_p, underlying, "put", strike, expiry),
    }
    return positions, contracts


@st.composite
def strangle_inputs(draw):
    """
    STRANGLE: 2 positions, 同标的, 同到期日, 不同行权价, 一 Call 一 Put
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)
    strike1 = draw(_strike)
    strike2 = draw(_strike)
    assume(strike1 != strike2)
    dir1 = draw(_direction)
    dir2 = draw(_direction)

    sym_c = f"{underlying}-C-{strike1}-{expiry}"
    sym_p = f"{underlying}-P-{strike2}-{expiry}"

    positions = [
        _make_position(sym_c, underlying, dir1),
        _make_position(sym_p, underlying, dir2),
    ]
    contracts = {
        sym_c: _make_contract(sym_c, underlying, "call", strike1, expiry),
        sym_p: _make_contract(sym_p, underlying, "put", strike2, expiry),
    }
    return positions, contracts


@st.composite
def vertical_spread_inputs(draw):
    """
    VERTICAL_SPREAD: 2 positions, 同标的, 同到期日, 同期权类型, 不同行权价
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)
    opt_type = draw(st.sampled_from(["call", "put"]))
    strike1 = draw(_strike)
    strike2 = draw(_strike)
    assume(strike1 != strike2)
    dir1 = draw(_direction)
    dir2 = draw(_direction)

    sym1 = f"{underlying}-{opt_type}-{strike1}-{expiry}"
    sym2 = f"{underlying}-{opt_type}-{strike2}-{expiry}"

    positions = [
        _make_position(sym1, underlying, dir1),
        _make_position(sym2, underlying, dir2),
    ]
    contracts = {
        sym1: _make_contract(sym1, underlying, opt_type, strike1, expiry),
        sym2: _make_contract(sym2, underlying, opt_type, strike2, expiry),
    }
    return positions, contracts


@st.composite
def calendar_spread_inputs(draw):
    """
    CALENDAR_SPREAD: 2 positions, 同标的, 不同到期日, 同行权价, 同期权类型
    """
    underlying = draw(_underlying)
    expiry1 = draw(_expiry)
    expiry2 = draw(_expiry)
    assume(expiry1 != expiry2)
    opt_type = draw(st.sampled_from(["call", "put"]))
    strike = draw(_strike)
    dir1 = draw(_direction)
    dir2 = draw(_direction)

    sym1 = f"{underlying}-{opt_type}-{strike}-{expiry1}"
    sym2 = f"{underlying}-{opt_type}-{strike}-{expiry2}"

    positions = [
        _make_position(sym1, underlying, dir1),
        _make_position(sym2, underlying, dir2),
    ]
    contracts = {
        sym1: _make_contract(sym1, underlying, opt_type, strike, expiry1),
        sym2: _make_contract(sym2, underlying, opt_type, strike, expiry2),
    }
    return positions, contracts


@st.composite
def iron_condor_inputs(draw):
    """
    IRON_CONDOR: 4 positions, 同标的, 同到期日,
    2 Puts 不同行权价 + 2 Calls 不同行权价
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)

    put_strike1 = draw(_strike)
    put_strike2 = draw(_strike)
    assume(put_strike1 != put_strike2)

    call_strike1 = draw(_strike)
    call_strike2 = draw(_strike)
    assume(call_strike1 != call_strike2)

    sym_p1 = f"{underlying}-P-{put_strike1}-{expiry}"
    sym_p2 = f"{underlying}-P-{put_strike2}-{expiry}"
    sym_c1 = f"{underlying}-C-{call_strike1}-{expiry}"
    sym_c2 = f"{underlying}-C-{call_strike2}-{expiry}"

    positions = [
        _make_position(sym_p1, underlying, draw(_direction)),
        _make_position(sym_p2, underlying, draw(_direction)),
        _make_position(sym_c1, underlying, draw(_direction)),
        _make_position(sym_c2, underlying, draw(_direction)),
    ]
    contracts = {
        sym_p1: _make_contract(sym_p1, underlying, "put", put_strike1, expiry),
        sym_p2: _make_contract(sym_p2, underlying, "put", put_strike2, expiry),
        sym_c1: _make_contract(sym_c1, underlying, "call", call_strike1, expiry),
        sym_c2: _make_contract(sym_c2, underlying, "call", call_strike2, expiry),
    }
    return positions, contracts


@st.composite
def custom_inputs_non_matching_count(draw):
    """
    生成不匹配任何预定义类型的持仓结构（腿数不是 2 或 4）。
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)
    n = draw(st.sampled_from([1, 3, 5, 6]))

    positions = []
    contracts = {}
    for i in range(n):
        opt_type = draw(st.sampled_from(["call", "put"]))
        strike = draw(_strike)
        sym = f"{underlying}-{opt_type}-{strike}-{expiry}-{i}"
        positions.append(_make_position(sym, underlying, draw(_direction)))
        contracts[sym] = _make_contract(sym, underlying, opt_type, strike, expiry)

    return positions, contracts



@st.composite
def random_positions_and_contracts(draw):
    """
    生成随机的持仓和合约映射，用于测试表驱动逻辑的一般行为。
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)
    n = draw(st.integers(min_value=0, max_value=6))

    positions = []
    contracts = {}
    for i in range(n):
        opt_type = draw(st.sampled_from(["call", "put"]))
        strike = draw(_strike)
        sym = f"{underlying}-{opt_type}-{strike}-{expiry}-{i}"
        positions.append(_make_position(sym, underlying, draw(_direction)))
        contracts[sym] = _make_contract(sym, underlying, opt_type, strike, expiry)

    return positions, contracts


@st.composite
def positions_with_missing_contracts(draw):
    """
    生成持仓列表，但部分合约在 contracts 字典中缺失。
    """
    underlying = draw(_underlying)
    expiry = draw(_expiry)
    n = draw(st.integers(min_value=2, max_value=4))

    positions = []
    contracts = {}
    for i in range(n):
        opt_type = draw(st.sampled_from(["call", "put"]))
        strike = draw(_strike)
        sym = f"{underlying}-{opt_type}-{strike}-{expiry}-{i}"
        positions.append(_make_position(sym, underlying, draw(_direction)))
        # 只添加部分合约到 contracts
        if draw(st.booleans()):
            contracts[sym] = _make_contract(sym, underlying, opt_type, strike, expiry)

    # 确保至少有一个合约缺失
    if len(contracts) == len(positions):
        # 移除一个合约
        first_key = next(iter(contracts))
        del contracts[first_key]

    return positions, contracts


# ---------------------------------------------------------------------------
# Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性
# ---------------------------------------------------------------------------


class TestProperty4RecognizerTableDrivenBehavior:
    """
    Property 4: Recognizer 表驱动行为等价性

    *For any* 持仓列表和合约映射，表驱动重构后的 CombinationRecognizer 应返回与重构前
    完全相同的 CombinationType 结果。特别地：空列表返回 CUSTOM，合约缺失返回 CUSTOM，
    匹配规则按 IRON_CONDOR → STRADDLE → STRANGLE → VERTICAL_SPREAD → CALENDAR_SPREAD
    优先级执行。

    **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
    """

    def setup_method(self) -> None:
        self.recognizer = CombinationRecognizer()

    # --- 空列表返回 CUSTOM ---

    @given(contracts=st.dictionaries(st.text(), st.none()))
    @settings(max_examples=100)
    def test_empty_positions_returns_custom(self, contracts):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证空持仓列表返回 CUSTOM。

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        result = self.recognizer.recognize([], {})
        assert result == CombinationType.CUSTOM

    # --- 合约缺失返回 CUSTOM ---

    @given(data=positions_with_missing_contracts())
    @settings(max_examples=100)
    def test_missing_contracts_returns_custom(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证当 contracts 字典中缺少某个 Position 的合约信息时，返回 CUSTOM。

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result = self.recognizer.recognize(positions, contracts)
        assert result == CombinationType.CUSTOM

    # --- IRON_CONDOR 识别 ---

    @given(data=iron_condor_inputs())
    @settings(max_examples=100)
    def test_iron_condor_recognized(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证 IRON_CONDOR 结构被正确识别。
        IRON_CONDOR: 4 positions, 同标的, 同到期日, 2 Puts 不同行权价 + 2 Calls 不同行权价

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result = self.recognizer.recognize(positions, contracts)
        assert result == CombinationType.IRON_CONDOR

    # --- STRADDLE 识别 ---

    @given(data=straddle_inputs())
    @settings(max_examples=100)
    def test_straddle_recognized(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证 STRADDLE 结构被正确识别。
        STRADDLE: 2 positions, 同标的, 同到期日, 同行权价, 一 Call 一 Put

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result = self.recognizer.recognize(positions, contracts)
        assert result == CombinationType.STRADDLE

    # --- STRANGLE 识别 ---

    @given(data=strangle_inputs())
    @settings(max_examples=100)
    def test_strangle_recognized(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证 STRANGLE 结构被正确识别。
        STRANGLE: 2 positions, 同标的, 同到期日, 不同行权价, 一 Call 一 Put

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result = self.recognizer.recognize(positions, contracts)
        assert result == CombinationType.STRANGLE

    # --- VERTICAL_SPREAD 识别 ---

    @given(data=vertical_spread_inputs())
    @settings(max_examples=100)
    def test_vertical_spread_recognized(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证 VERTICAL_SPREAD 结构被正确识别。
        VERTICAL_SPREAD: 2 positions, 同标的, 同到期日, 同期权类型, 不同行权价

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result = self.recognizer.recognize(positions, contracts)
        assert result == CombinationType.VERTICAL_SPREAD

    # --- CALENDAR_SPREAD 识别 ---

    @given(data=calendar_spread_inputs())
    @settings(max_examples=100)
    def test_calendar_spread_recognized(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证 CALENDAR_SPREAD 结构被正确识别。
        CALENDAR_SPREAD: 2 positions, 同标的, 不同到期日, 同行权价, 同期权类型

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result = self.recognizer.recognize(positions, contracts)
        assert result == CombinationType.CALENDAR_SPREAD

    # --- 不匹配时返回 CUSTOM ---

    @given(data=custom_inputs_non_matching_count())
    @settings(max_examples=100)
    def test_non_matching_count_returns_custom(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证当持仓数量不是 2 或 4（即 1, 3, 5, 6）时，返回 CUSTOM。

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result = self.recognizer.recognize(positions, contracts)
        assert result == CombinationType.CUSTOM

    # --- 优先级测试：IRON_CONDOR 优先于其他类型 ---

    @given(data=iron_condor_inputs())
    @settings(max_examples=100)
    def test_priority_iron_condor_first(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证 IRON_CONDOR 在优先级列表中排第一。
        即使 4 腿结构可能满足其他条件，也应优先识别为 IRON_CONDOR。

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result = self.recognizer.recognize(positions, contracts)
        # IRON_CONDOR 应该被优先识别
        assert result == CombinationType.IRON_CONDOR

    # --- 优先级测试：STRADDLE 优先于 STRANGLE ---

    @given(data=straddle_inputs())
    @settings(max_examples=100)
    def test_priority_straddle_over_strangle(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证 STRADDLE 优先于 STRANGLE。
        STRADDLE 和 STRANGLE 都是 2 腿、一 Call 一 Put，但 STRADDLE 要求同行权价。
        当满足 STRADDLE 条件时，应识别为 STRADDLE 而非 STRANGLE。

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result = self.recognizer.recognize(positions, contracts)
        assert result == CombinationType.STRADDLE

    # --- 结果确定性：相同输入产生相同输出 ---

    @given(data=random_positions_and_contracts())
    @settings(max_examples=100)
    def test_recognition_is_deterministic(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证识别结果是确定性的：相同输入总是产生相同输出。

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result1 = self.recognizer.recognize(positions, contracts)
        result2 = self.recognizer.recognize(positions, contracts)
        assert result1 == result2

    # --- 结果总是有效的 CombinationType ---

    @given(data=random_positions_and_contracts())
    @settings(max_examples=100)
    def test_result_is_valid_combination_type(self, data):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证识别结果总是有效的 CombinationType 枚举值。

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        positions, contracts = data
        result = self.recognizer.recognize(positions, contracts)
        assert isinstance(result, CombinationType)
        assert result in list(CombinationType)

    # --- 表驱动规则覆盖所有预定义类型 ---

    def test_all_combination_types_covered(self):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证表驱动规则覆盖所有预定义组合类型（除 CUSTOM 外）。
        这是一个静态检查，确保规则列表完整。

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        from src.strategy.domain.domain_service.combination.combination_recognizer import (
            _RULES,
        )

        # 获取规则中覆盖的类型
        covered_types = {rule.combination_type for rule in _RULES}

        # 预期覆盖的类型（除 CUSTOM 外）
        expected_types = {
            CombinationType.IRON_CONDOR,
            CombinationType.STRADDLE,
            CombinationType.STRANGLE,
            CombinationType.VERTICAL_SPREAD,
            CombinationType.CALENDAR_SPREAD,
        }

        assert covered_types == expected_types

    # --- 规则优先级顺序正确 ---

    def test_rules_priority_order(self):
        """
        Feature: combination-service-optimization, Property 4: Recognizer 表驱动行为等价性

        验证规则列表按正确的优先级顺序排列：
        IRON_CONDOR → STRADDLE → STRANGLE → VERTICAL_SPREAD → CALENDAR_SPREAD

        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        from src.strategy.domain.domain_service.combination.combination_recognizer import (
            _RULES,
        )

        expected_order = [
            CombinationType.IRON_CONDOR,
            CombinationType.STRADDLE,
            CombinationType.STRANGLE,
            CombinationType.VERTICAL_SPREAD,
            CombinationType.CALENDAR_SPREAD,
        ]

        actual_order = [rule.combination_type for rule in _RULES]
        assert actual_order == expected_order
