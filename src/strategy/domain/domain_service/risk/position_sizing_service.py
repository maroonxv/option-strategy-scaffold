"""

PositionSizingService - 计算【考虑了当日开仓限额、品种开仓限额后的真实开仓数量与平仓数量】

"""

import math

from typing import List, Optional, Tuple


from ...value_object.order_instruction import OrderInstruction, Direction, Offset

from ...value_object.greeks import GreeksResult

from ...value_object.risk import PortfolioGreeks, RiskThresholds

from ...value_object.sizing import SizingResult

from ...entity.position import Position



class PositionSizingService:

    """

    仓位管理服务。负责计算开仓数量、检查风控限制并生成交易指令。

    """
    

    # 默认配置

    DEFAULT_MAX_POSITIONS = 5           # 最大持仓数量
    

    def __init__(
        self,

        max_positions: int = 5,

        global_daily_limit: int = 50,

        contract_daily_limit: int = 2,

        margin_ratio: float = 0.12,

        min_margin_ratio: float = 0.07,

        margin_usage_limit: float = 0.6,

        max_volume_per_order: int = 10,

    ):

        """

        初始化
        

        参数:

            max_positions: 最大持仓数量

            global_daily_limit: 全局日开仓限制

            contract_daily_limit: 单合约日开仓限制

            margin_ratio: 保证金比例（默认 0.12）

            min_margin_ratio: 最低保证金比例（默认 0.07）

            margin_usage_limit: 保证金使用率上限（默认 0.6）

            max_volume_per_order: 单笔最大手数（默认 10）

        """

        self.max_positions = max_positions

        self.global_daily_limit = global_daily_limit

        self.contract_daily_limit = contract_daily_limit

        self.margin_ratio = margin_ratio

        self.min_margin_ratio = min_margin_ratio

        self.margin_usage_limit = margin_usage_limit

        self.max_volume_per_order = max_volume_per_order


    def estimate_margin(
        self,
        contract_price: float,

        underlying_price: float,

        strike_price: float,

        option_type: str,
        multiplier: float,

    ) -> float:

        """

        估算单手卖出期权保证金。


        公式：权利金 × 合约乘数 + max(标的价格 × 合约乘数 × margin_ratio - 虚值额,

                                        标的价格 × 合约乘数 × min_margin_ratio)


        虚值额：

          - put: max(行权价 - 标的价格, 0) × 合约乘数

          - call: max(标的价格 - 行权价, 0) × 合约乘数

        """

        if option_type == "put":

            out_of_money = max(strike_price - underlying_price, 0) * multiplier
        else:

            out_of_money = max(underlying_price - strike_price, 0) * multiplier


        premium = contract_price * multiplier

        margin = premium + max(

            underlying_price * multiplier * self.margin_ratio - out_of_money,

            underlying_price * multiplier * self.min_margin_ratio,

        )
        return margin


    def _calc_margin_volume(

        self, available_funds: float, margin_per_lot: float

    ) -> int:

        """保证金维度：可用资金 / 单手保证金"""

        if margin_per_lot <= 0:

            return 0

        return math.floor(available_funds / margin_per_lot)


    def _calc_usage_volume(

        self, total_equity: float, used_margin: float, margin_per_lot: float

    ) -> int:

        """使用率维度：(总权益 × margin_usage_limit - 已用保证金) / 单手保证金"""

        if margin_per_lot <= 0:

            return 0

        available = total_equity * self.margin_usage_limit - used_margin

        if available <= 0:

            return 0

        return math.floor(available / margin_per_lot)


    def _calc_greeks_volume(
        self,

        greeks: GreeksResult,
        multiplier: float,

        portfolio_greeks: PortfolioGreeks,

        risk_thresholds: RiskThresholds,

    ) -> Tuple[int, float, float, float]:

        """Greeks 维度：返回 (允许手数, delta_budget, gamma_budget, vega_budget)"""

        delta_budget = risk_thresholds.portfolio_delta_limit - abs(portfolio_greeks.total_delta)

        gamma_budget = risk_thresholds.portfolio_gamma_limit - abs(portfolio_greeks.total_gamma)

        vega_budget = risk_thresholds.portfolio_vega_limit - abs(portfolio_greeks.total_vega)


        dimensions = [

            (greeks.delta, delta_budget),

            (greeks.gamma, gamma_budget),

            (greeks.vega, vega_budget),

        ]


        min_volume = 999999

        for greek_val, budget in dimensions:

            per_lot = abs(greek_val * multiplier)

            if per_lot == 0:
                continue

            vol = math.floor(budget / per_lot)

            min_volume = min(min_volume, vol)


        return (min_volume, delta_budget, gamma_budget, vega_budget)


    def compute_sizing(
        self,

        account_balance: float,

        total_equity: float,
        used_margin: float,
        contract_price: float,

        underlying_price: float,

        strike_price: float,

        option_type: str,
        multiplier: float,

        greeks: GreeksResult,

        portfolio_greeks: PortfolioGreeks,

        risk_thresholds: RiskThresholds,

    ) -> SizingResult:

        """纯计算方法：综合三维度计算最终手数，返回 SizingResult"""


        def _rejected(

            reject_reason: str,

            margin_volume: int = 0,

            usage_volume: int = 0,

            greeks_volume: int = 0,

            delta_budget: float = 0.0,

            gamma_budget: float = 0.0,

            vega_budget: float = 0.0,

        ) -> SizingResult:

            return SizingResult(

                final_volume=0,

                margin_volume=margin_volume,

                usage_volume=usage_volume,

                greeks_volume=greeks_volume,

                delta_budget=delta_budget,

                gamma_budget=gamma_budget,

                vega_budget=vega_budget,

                passed=False,

                reject_reason=reject_reason,

            )


        # 1. 估算单手保证金

        margin_per_lot = self.estimate_margin(

            contract_price, underlying_price, strike_price, option_type, multiplier

        )

        if margin_per_lot <= 0:

            return _rejected("保证金估算异常")


        # 2. 保证金维度

        margin_volume = self._calc_margin_volume(account_balance, margin_per_lot)

        if margin_volume < 1:

            return _rejected("可用资金不足", margin_volume=margin_volume)


        # 3. 使用率维度

        usage_volume = self._calc_usage_volume(total_equity, used_margin, margin_per_lot)

        if usage_volume < 1:

            return _rejected("保证金使用率超限", margin_volume=margin_volume, usage_volume=usage_volume)


        # 4. Greeks 维度

        greeks_volume, delta_budget, gamma_budget, vega_budget = self._calc_greeks_volume(

            greeks, multiplier, portfolio_greeks, risk_thresholds

        )

        if greeks_volume < 1:

            # 确定具体超限维度

            bottlenecks = []

            delta_per_lot = abs(greeks.delta * multiplier)

            gamma_per_lot = abs(greeks.gamma * multiplier)

            vega_per_lot = abs(greeks.vega * multiplier)

            if delta_per_lot > 0 and math.floor(delta_budget / delta_per_lot) < 1:

                bottlenecks.append("Delta")

            if gamma_per_lot > 0 and math.floor(gamma_budget / gamma_per_lot) < 1:

                bottlenecks.append("Gamma")

            if vega_per_lot > 0 and math.floor(vega_budget / vega_per_lot) < 1:

                bottlenecks.append("Vega")

            dimension_str = "/".join(bottlenecks) if bottlenecks else "Delta"

            return _rejected(

                f"Greeks 超限: {dimension_str}",

                margin_volume=margin_volume,

                usage_volume=usage_volume,

                greeks_volume=greeks_volume,

                delta_budget=delta_budget,

                gamma_budget=gamma_budget,

                vega_budget=vega_budget,

            )


        # 5. 取三维度最小值

        final_volume = min(margin_volume, usage_volume, greeks_volume)


        # 6. 综合手数不足

        if final_volume < 1:

            return _rejected(

                "综合计算手数不足",

                margin_volume=margin_volume,

                usage_volume=usage_volume,

                greeks_volume=greeks_volume,

                delta_budget=delta_budget,

                gamma_budget=gamma_budget,

                vega_budget=vega_budget,

            )


        # 7. Clamp 到 [1, max_volume_per_order]

        final_volume = min(max(final_volume, 1), self.max_volume_per_order)


        return SizingResult(

            final_volume=final_volume,

            margin_volume=margin_volume,

            usage_volume=usage_volume,

            greeks_volume=greeks_volume,

            delta_budget=delta_budget,

            gamma_budget=gamma_budget,

            vega_budget=vega_budget,

            passed=True,

        )



    def calculate_open_volume(
        self,

        account_balance: float,

        total_equity: float,
        used_margin: float,
        signal: str,

        vt_symbol: str,
        contract_price: float,

        underlying_price: float,

        strike_price: float,

        option_type: str,
        multiplier: float,

        greeks: GreeksResult,

        portfolio_greeks: PortfolioGreeks,

        risk_thresholds: RiskThresholds,

        current_positions: List[Position],

        current_daily_open_count: int = 0,

        current_contract_open_count: int = 0,

    ) -> Optional[OrderInstruction]:

        """

        生成开仓指令（动态仓位计算版本）


        流程:

        1. 风控前置检查（最大持仓、全局日限额、单合约日限额、重复合约）

        2. 调用 compute_sizing 综合三维度计算最终手数

        3. SizingResult.passed 为 False 时返回 None

        4. SizingResult.passed 为 True 时使用 final_volume 生成 OrderInstruction


        参数:

            account_balance: 可用资金

            total_equity: 账户总权益

            used_margin: 已用保证金

            signal: 信号类型

            vt_symbol: 合约代码

            contract_price: 合约价格（期权权利金）

            underlying_price: 标的价格

            strike_price: 行权价

            option_type: "call" | "put"

            multiplier: 合约乘数

            greeks: 单手 Greeks

            portfolio_greeks: 当前组合 Greeks

            risk_thresholds: Greeks 阈值

            current_positions: 当前持仓列表

            current_daily_open_count: 当前全局已开仓数（含预留）

            current_contract_open_count: 当前合约已开仓数（含预留）


        Returns:

            OrderInstruction（包含交易指令）或 None（不交易）

        """

        # 1. 检查是否超过最大持仓限制

        active_positions = [p for p in current_positions if p.is_active]

        if len(active_positions) >= self.max_positions:

            return None


        # 2. 风控检查: 每日开仓限额

        if current_daily_open_count + 1 > self.global_daily_limit:

            return None

        if current_contract_open_count + 1 > self.contract_daily_limit:

            return None


        # 3. 检查是否已有同一合约的持仓

        for pos in active_positions:

            if pos.vt_symbol == vt_symbol:

                return None


        # 4. 调用 compute_sizing 综合计算

        sizing_result = self.compute_sizing(

            account_balance=account_balance,

            total_equity=total_equity,

            used_margin=used_margin,

            contract_price=contract_price,

            underlying_price=underlying_price,

            strike_price=strike_price,

            option_type=option_type,

            multiplier=multiplier,

            greeks=greeks,

            portfolio_greeks=portfolio_greeks,

            risk_thresholds=risk_thresholds,

        )


        if not sizing_result.passed:

            return None


        # 5. 生成指令：卖权策略 - 卖出开仓 (Short Open)

        return OrderInstruction(

            vt_symbol=vt_symbol,

            direction=Direction.SHORT,

            offset=Offset.OPEN,

            volume=sizing_result.final_volume,

            price=contract_price,

            signal=signal,

        )

    

    def calculate_close_volume(
        self,

        position: Position,
        close_price: float,

        signal: str = ""

    ) -> Optional[OrderInstruction]:

        """

        生成平仓指令
        

        参数:

            position: 要平仓的持仓

            close_price: 平仓价格

            signal: 触发平仓的信号类型
            

        Returns:

            OrderInstruction (包含交易指令) 或 None

        """

        if not position.is_active or position.volume <= 0:

            return None
        

        # 卖权策略: 买入平仓 (Long Close)

        return OrderInstruction(

            vt_symbol=position.vt_symbol,

            direction=Direction.LONG,

            offset=Offset.CLOSE,

            volume=position.volume,

            price=close_price,

            signal=signal

        )

