"""
FeishuEventHandler - 飞书事件处理器

订阅 VnPy 的事件引擎，处理策略告警事件并发送飞书消息。

设计原则:
- 通过 EventEngine.register() 订阅事件
- 处理 StrategyAlertData 类型的事件
- 发送格式化的飞书消息
"""
from typing import Any, Optional
from datetime import datetime
import json

from ...domain.event.event_types import StrategyAlertData, EVENT_STRATEGY_ALERT
from ..logging.logging_utils import setup_strategy_logger


class FeishuEventHandler:
    """
    飞书事件处理器
    
    职责:
    - 注册到 VnPy EventEngine
    - 处理策略告警事件
    - 格式化并发送飞书消息
    
    使用方式:
    在接口层 on_init 中创建并注册:
    ```
    self.feishu_handler = FeishuEventHandler(webhook_url, strategy_name)
    self.strategy_engine.event_engine.register(
        EVENT_STRATEGY_ALERT,
        self.feishu_handler.handle_alert_event
    )
    ```
    """
    
    # 消息模板
    MESSAGE_TEMPLATES = {
        "manual_open": "⚠️ 检测到手动开仓 {vt_symbol} {volume}手，程序不会自动平仓",
        "manual_close": "📝 检测到手动平仓 {vt_symbol} {volume}手，已自动匹配",
        "order_cancelled": "❌ 平仓订单被撤单: {message}",
        "order_rejected": "🚫 平仓订单被拒单: {message}",
        "open_signal": "📈 开仓信号触发: {message}",
        "close_signal": "📉 平仓信号触发: {message}",
        "position_opened": "✅ 开仓成功: {vt_symbol} {volume}手",
        "position_closed": "✅ 平仓成功: {vt_symbol} {volume}手",
        "error": "🔴 策略错误: {message}",
        "warning": "🟡 策略警告: {message}",
        "info": "ℹ️ {message}",
    }
    
    def __init__(
        self,
        webhook_url: str,
        strategy_name: str,
        enabled: bool = True
    ) -> None:
        """
        初始化飞书处理器
        
        Args:
            webhook_url: 飞书群机器人 Webhook URL
            strategy_name: 策略名称 (用于过滤和标识)
            enabled: 是否启用发送
        """
        self.webhook_url = webhook_url
        self.strategy_name = strategy_name
        self.enabled = enabled
        
        # 初始化日志
        # 复用策略的日志配置
        self.logger = setup_strategy_logger(strategy_name, "strategy.log")

        # 发送限流 (避免频繁发送)
        self._last_send_time: Optional[datetime] = None
        self._min_interval_seconds = 5
    
    def handle_alert_event(self, event: Any) -> None:
        """
        处理策略告警事件
        
        事件处理器方法，由 EventEngine 调用。
        
        Args:
            event: VnPy Event 对象 (event.data 为 StrategyAlertData)
        """
        if not self.enabled:
            return
        
        try:
            data: StrategyAlertData = event.data
            
            # 只处理本策略的事件
            if data.strategy_name != self.strategy_name:
                return
            
            # 格式化消息
            message = self._format_message(data)
            
            # 发送飞书
            self._send_feishu(message)
            
        except Exception as e:
            # 避免日志循环，这里只简单打印
            self.logger.error(f"[飞书处理] 处理事件失败: {e}")
    
    def _format_message(self, data: StrategyAlertData) -> str:
        """
        格式化飞书消息
        
        Args:
            data: 策略告警数据
            
        Returns:
            格式化后的消息字符串
        """
        template = self.MESSAGE_TEMPLATES.get(data.alert_type, "{message}")
        
        try:
            message = template.format(
                vt_symbol=data.vt_symbol,
                volume=data.volume,
                message=data.message,
                **data.extra
            )
        except KeyError:
            # 模板参数不匹配，使用原始消息
            message = data.message
        
        return message
    
    def _send_feishu(self, message: str) -> bool:
        """
        发送飞书消息
        
        Args:
            message: 要发送的消息
            
        Returns:
            True 如果发送成功
        """
        # 限流检查
        now = datetime.now()
        if self._last_send_time:
            elapsed = (now - self._last_send_time).total_seconds()
            if elapsed < self._min_interval_seconds:
                return False
        
        import requests

        try:
            payload = {
                "msg_type": "text",
                "content": {
                    "text": f"[{self.strategy_name}] {message}"
                }
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=5
            )
            
            self._last_send_time = now
            
            return response.status_code == 200
            
        except Exception as e:
            self.logger.error(f"[飞书处理] 发送失败: {e}")
            return False
    

