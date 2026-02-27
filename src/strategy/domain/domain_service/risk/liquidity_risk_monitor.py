"""
LiquidityRiskMonitor - 持仓流动性监控服务

负责监控已持仓合约的流动性变化，基于成交量、价差、持仓量三个维度计算流动性评分。
"""

from typing import Dict, List

from ...entity.position import Position
from ...value_object.risk.risk import (
    LiquidityMonitorConfig,
    MarketData,
    LiquidityScore,
    LiquidityWarning,
)


class LiquidityRiskMonitor:
    """
    持仓流动性监控服务
    
    职责:
    1. 计算持仓合约的流动性评分（成交量、价差、持仓量三个维度）
    2. 监控流动性趋势变化（improving、stable、deteriorating）
    3. 检测流动性恶化并生成警告
    4. 仅针对已持仓合约进行评估
    """
    
    def __init__(self, config: LiquidityMonitorConfig) -> None:
        """
        初始化流动性监控器
        
        Args:
            config: 流动性监控配置对象
            
        Raises:
            ValueError: 如果权重总和不等于 1.0
        """
        self._config = config
        
        # 验证权重总和
        total_weight = (
            config.volume_weight + 
            config.spread_weight + 
            config.open_interest_weight
        )
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(
                f"权重总和必须等于 1.0，当前为 {total_weight:.6f}"
            )
    
    def calculate_liquidity_score(
        self,
        vt_symbol: str,
        current_data: MarketData,
        historical_data: List[MarketData]
    ) -> LiquidityScore:
        """
        计算流动性评分
        
        Args:
            vt_symbol: 合约代码
            current_data: 当前市场数据
            historical_data: 历史市场数据（用于趋势分析）
            
        Returns:
            LiquidityScore 包含综合评分和各维度评分
        """
        # 计算各维度评分
        volume_score = self._calculate_volume_score(
            current_data.volume, historical_data
        )
        spread_score = self._calculate_spread_score(
            current_data.bid_price, current_data.ask_price
        )
        oi_score = self._calculate_oi_score(
            current_data.open_interest, historical_data
        )
        
        # 计算综合评分（加权平均）
        overall_score = (
            volume_score * self._config.volume_weight +
            spread_score * self._config.spread_weight +
            oi_score * self._config.open_interest_weight
        )
        
        # 识别流动性趋势
        trend = self._identify_trend(
            current_data, historical_data, volume_score, spread_score, oi_score
        )
        
        return LiquidityScore(
            vt_symbol=vt_symbol,
            overall_score=overall_score,
            volume_score=volume_score,
            spread_score=spread_score,
            open_interest_score=oi_score,
            trend=trend
        )
    
    def monitor_positions(
        self,
        positions: List[Position],
        market_data: Dict[str, MarketData],
        historical_data: Dict[str, List[MarketData]]
    ) -> List[LiquidityWarning]:
        """
        监控所有持仓的流动性
        
        Args:
            positions: 活跃持仓列表
            market_data: 当前市场数据（合约代码 -> MarketData）
            historical_data: 历史市场数据（合约代码 -> List[MarketData]）
            
        Returns:
            流动性警告列表
        """
        warnings = []
        
        for position in positions:
            # 只监控活跃持仓
            if not position.is_active:
                continue
            
            vt_symbol = position.vt_symbol
            
            # 检查是否有市场数据
            if vt_symbol not in market_data:
                continue
            
            current_data = market_data[vt_symbol]
            hist_data = historical_data.get(vt_symbol, [])
            
            # 计算流动性评分
            score = self.calculate_liquidity_score(
                vt_symbol, current_data, hist_data
            )
            
            # 检查是否低于阈值
            if score.overall_score < self._config.liquidity_score_threshold:
                message = (
                    f"流动性恶化警告: {vt_symbol} 流动性评分 "
                    f"{score.overall_score:.3f} 低于阈值 "
                    f"{self._config.liquidity_score_threshold:.3f}，"
                    f"趋势: {score.trend}"
                )
                
                warnings.append(LiquidityWarning(
                    vt_symbol=vt_symbol,
                    current_score=score.overall_score,
                    threshold=self._config.liquidity_score_threshold,
                    trend=score.trend,
                    message=message
                ))
        
        return warnings
    
    def _calculate_volume_score(
        self,
        current_volume: float,
        historical_data: List[MarketData]
    ) -> float:
        """
        计算成交量评分
        
        评分逻辑:
        - 如果没有历史数据，使用简单归一化
        - 如果有历史数据，计算当前成交量相对于历史平均值的比例
        - 评分范围 [0, 1]，成交量越大评分越高
        
        Args:
            current_volume: 当前成交量
            historical_data: 历史市场数据
            
        Returns:
            成交量评分 [0, 1]
        """
        if not historical_data:
            # 没有历史数据，使用简单归一化
            # 假设成交量 > 1000 为良好流动性
            return min(current_volume / 1000.0, 1.0)
        
        # 计算历史平均成交量
        avg_volume = sum(d.volume for d in historical_data) / len(historical_data)
        
        if avg_volume <= 0:
            return 0.0
        
        # 当前成交量相对于历史平均值的比例
        ratio = current_volume / avg_volume
        
        # 归一化到 [0, 1]，比例 >= 1.0 时评分为 1.0
        return min(ratio, 1.0)
    
    def _calculate_spread_score(
        self,
        bid_price: float,
        ask_price: float
    ) -> float:
        """
        计算价差评分
        
        评分逻辑:
        - 价差越小，流动性越好，评分越高
        - 使用相对价差（价差 / 中间价）
        - 评分范围 [0, 1]
        
        Args:
            bid_price: 买价
            ask_price: 卖价
            
        Returns:
            价差评分 [0, 1]
        """
        if bid_price <= 0 or ask_price <= 0 or ask_price <= bid_price:
            return 0.0
        
        # 计算相对价差
        mid_price = (bid_price + ask_price) / 2.0
        spread = ask_price - bid_price
        relative_spread = spread / mid_price if mid_price > 0 else 1.0
        
        # 相对价差越小评分越高
        # 假设相对价差 < 0.01 (1%) 为良好流动性
        # 使用指数衰减函数: score = exp(-k * relative_spread)
        # 当 relative_spread = 0.01 时，score ≈ 0.9
        # k = -ln(0.9) / 0.01 ≈ 10.5
        import math
        k = 10.5
        score = math.exp(-k * relative_spread)
        
        return min(max(score, 0.0), 1.0)
    
    def _calculate_oi_score(
        self,
        current_oi: float,
        historical_data: List[MarketData]
    ) -> float:
        """
        计算持仓量评分
        
        评分逻辑:
        - 如果没有历史数据，使用简单归一化
        - 如果有历史数据，计算当前持仓量相对于历史平均值的比例
        - 评分范围 [0, 1]，持仓量越大评分越高
        
        Args:
            current_oi: 当前持仓量
            historical_data: 历史市场数据
            
        Returns:
            持仓量评分 [0, 1]
        """
        if not historical_data:
            # 没有历史数据，使用简单归一化
            # 假设持仓量 > 5000 为良好流动性
            return min(current_oi / 5000.0, 1.0)
        
        # 计算历史平均持仓量
        avg_oi = sum(d.open_interest for d in historical_data) / len(historical_data)
        
        if avg_oi <= 0:
            return 0.0
        
        # 当前持仓量相对于历史平均值的比例
        ratio = current_oi / avg_oi
        
        # 归一化到 [0, 1]，比例 >= 1.0 时评分为 1.0
        return min(ratio, 1.0)
    
    def _identify_trend(
        self,
        current_data: MarketData,
        historical_data: List[MarketData],
        volume_score: float,
        spread_score: float,
        oi_score: float
    ) -> str:
        """
        识别流动性趋势
        
        趋势判断逻辑:
        - improving: 成交量增加、价差缩小、持仓量增加
        - deteriorating: 成交量减少、价差扩大、持仓量减少
        - stable: 其他情况
        
        Args:
            current_data: 当前市场数据
            historical_data: 历史市场数据
            volume_score: 成交量评分
            spread_score: 价差评分
            oi_score: 持仓量评分
            
        Returns:
            流动性趋势 ("improving" | "stable" | "deteriorating")
        """
        if not historical_data or len(historical_data) < 2:
            return "stable"
        
        # 计算历史平均值
        avg_volume = sum(d.volume for d in historical_data) / len(historical_data)
        avg_oi = sum(d.open_interest for d in historical_data) / len(historical_data)
        
        # 计算历史平均价差
        avg_spread = 0.0
        valid_spread_count = 0
        for d in historical_data:
            if d.ask_price > d.bid_price and d.bid_price > 0:
                mid = (d.bid_price + d.ask_price) / 2.0
                if mid > 0:
                    avg_spread += (d.ask_price - d.bid_price) / mid
                    valid_spread_count += 1
        
        if valid_spread_count > 0:
            avg_spread /= valid_spread_count
        
        # 计算当前相对价差
        current_spread = 0.0
        if current_data.ask_price > current_data.bid_price and current_data.bid_price > 0:
            mid = (current_data.bid_price + current_data.ask_price) / 2.0
            if mid > 0:
                current_spread = (current_data.ask_price - current_data.bid_price) / mid
        
        # 判断趋势
        improving_signals = 0
        deteriorating_signals = 0
        
        # 成交量趋势
        if avg_volume > 0:
            if current_data.volume > avg_volume * 1.1:  # 增加 10% 以上
                improving_signals += 1
            elif current_data.volume < avg_volume * 0.9:  # 减少 10% 以上
                deteriorating_signals += 1
        
        # 价差趋势（价差缩小为改善）
        if avg_spread > 0:
            if current_spread < avg_spread * 0.9:  # 价差缩小 10% 以上
                improving_signals += 1
            elif current_spread > avg_spread * 1.1:  # 价差扩大 10% 以上
                deteriorating_signals += 1
        
        # 持仓量趋势
        if avg_oi > 0:
            if current_data.open_interest > avg_oi * 1.1:  # 增加 10% 以上
                improving_signals += 1
            elif current_data.open_interest < avg_oi * 0.9:  # 减少 10% 以上
                deteriorating_signals += 1
        
        # 综合判断
        if improving_signals >= 2:
            return "improving"
        elif deteriorating_signals >= 2:
            return "deteriorating"
        else:
            return "stable"
