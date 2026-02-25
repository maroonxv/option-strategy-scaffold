"""
PositionSizingService - 计算【考虑了当日开仓限额、品种开仓限额后的真实开仓数量与平仓数量】
"""
import math
from typing import List, Optional

from ...value_object.order_instruction import OrderInstruction, Direction, Offset
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


    
    def calculate_open_volumn(
        self,
        account_balance: float,
        signal: str,
        vt_symbol: str,
        contract_price: float,
        current_positions: List[Position],
        current_daily_open_count: int = 0,
        current_contract_open_count: int = 0,
    ) -> Optional[OrderInstruction]:
        """
        生成开仓指令
        
        流程:
        1. 检查是否超过最大持仓限制
        2. 检查每日开仓限额
        3. 计算开仓数量 (目前策略固定为 1 手)
        4. 生成 OrderInstruction
        
        参数:
            account_balance: 可用资金
            signal: 信号类型
            vt_symbol: 合约代码
            contract_price: 合约价格 (期权权利金)
            current_positions: 当前持仓列表 (用于检查最大持仓限制)
            current_daily_open_count: 当前全局已开仓数 (含预留)
            current_contract_open_count: 当前合约已开仓数 (含预留)
            
        Returns:
            OrderInstruction (包含交易指令) 或 None (不交易)
        """
        # 1. 检查是否超过最大持仓限制
        active_positions = [p for p in current_positions if p.is_active]
        if len(active_positions) >= self.max_positions:
            return None
        
        # 2. 风控检查: 每日开仓限额
        # 预判开仓 1 手的情况
        if current_daily_open_count + 1 > self.global_daily_limit:
            return None
        if current_contract_open_count + 1 > self.contract_daily_limit:
            return None

        # 3. 检查是否已有同一合约的持仓
        for pos in active_positions:
            if pos.vt_symbol == vt_symbol:
                return None
        
        # 3. 资金管理规则计算
        # 奥卡姆剃刀原则：直接固定 1 手，移除所有复杂资金计算
        volume = 1
        
        if contract_price <= 0:
            return None
        
        # 4. 生成指令
        # 卖权策略: 卖出开仓 (Short Open)
        return OrderInstruction(
            vt_symbol=vt_symbol,
            direction=Direction.SHORT,
            offset=Offset.OPEN,
            volume=volume,
            price=contract_price,
            signal=signal
        )
    
    def calculate_close_volumn(
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
