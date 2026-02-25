"""
gateway.py - 网关管理器

职责:
1. 加载网关配置
2. 管理网关连接状态
3. 支持多网关 (CTP, 仿真等)
4. 提供网关状态查询接口
"""
import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

from vnpy.trader.engine import MainEngine


class GatewayStatus(Enum):
    """网关状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class GatewayState:
    """网关状态信息"""
    name: str
    status: GatewayStatus = GatewayStatus.DISCONNECTED
    error_message: str = ""
    connected_time: Optional[float] = None
    contract_count: int = 0


class GatewayManager:
    """
    网关管理器
    
    统一管理交易网关的配置、连接和状态。
    
    支持的网关类型:
    - CTP: 期货 CTP 柜台
    
    Attributes:
        main_engine: VnPy 主引擎
    """
    
    # 支持的网关类型映射
    GATEWAY_CLASS_MAP: Dict[str, type] = {
        "ctp": None,  # 动态导入
    }
    
    def __init__(
        self,
        main_engine: MainEngine
    ) -> None:
        """
        初始化网关管理器
        
        Args:
            main_engine: VnPy 主引擎
        """
        self.main_engine = main_engine
        
        self.logger = logging.getLogger(__name__)
        
        # 网关配置
        self.configs: Dict[str, Dict[str, Any]] = {}
        
        # 网关状态
        self.states: Dict[str, GatewayState] = {}
        
        # 加载网关类
        self._load_gateway_classes()
    
    def _load_gateway_classes(self) -> None:
        """动态加载网关类"""
        from vnpy_ctp import CtpGateway
        self.GATEWAY_CLASS_MAP["ctp"] = CtpGateway
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """
        设置网关配置
        
        Args:
            config: 网关配置字典 (e.g. {"ctp": {...}})
        """
        self.configs = config
        
        # 初始化状态
        for gateway_name in self.configs.keys():
            self.states[gateway_name] = GatewayState(name=gateway_name)
        
        self.logger.info(f"已设置网关配置: {list(self.configs.keys())}")
    
    def add_gateways(self) -> None:
        """添加所有配置的网关到主引擎"""
        for gateway_name in self.configs.keys():
            gateway_class = self.GATEWAY_CLASS_MAP.get(gateway_name)
            
            if gateway_class is None:
                self.logger.warning(f"不支持的网关类型: {gateway_name}")
                continue
            
            # 添加网关
            self.main_engine.add_gateway(gateway_class)
            self.logger.info(f"已添加网关: {gateway_name}")
    
    def connect_all(self) -> None:
        """连接所有网关"""
        for gateway_name, config in self.configs.items():
            self.connect_gateway(gateway_name, config)
    
    def connect_gateway(
        self,
        gateway_name: str,
        config: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        连接指定网关
        
        Args:
            gateway_name: 网关名称
            config: 连接配置，如果为 None 则使用已加载的配置
        """
        setting = config or self.configs.get(gateway_name, {})
        
        if not setting:
            raise ValueError(f"网关 {gateway_name} 配置为空")
        
        # 更新状态
        if gateway_name in self.states:
            self.states[gateway_name].status = GatewayStatus.CONNECTING
        else:
             self.states[gateway_name] = GatewayState(name=gateway_name, status=GatewayStatus.CONNECTING)
        
        try:
            # 转换为 VnPy 网关名称 (大写)
            vnpy_gateway_name = gateway_name.upper()
            
            self.main_engine.connect(setting, vnpy_gateway_name)
            self.logger.info(f"网关 {gateway_name} 连接请求已发送")
            
        except Exception as e:
            if gateway_name in self.states:
                self.states[gateway_name].status = GatewayStatus.ERROR
                self.states[gateway_name].error_message = str(e)
            raise
    
    def disconnect_all(self) -> None:
        """断开所有网关连接"""
        if self.main_engine:
            self.main_engine.close()
            
            for state in self.states.values():
                state.status = GatewayStatus.DISCONNECTED
    
    def wait_for_connection(
        self,
        timeout: float = 60.0,
        check_interval: float = 1.0
    ) -> bool:
        """
        等待所有网关连接成功
        
        通过检查合约数据来判断连接是否成功。
        
        Args:
            timeout: 超时时间（秒）
            check_interval: 检查间隔（秒）
            
        Returns:
            True 如果所有网关连接成功
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            contracts = self.main_engine.get_all_contracts()
            
            if contracts:
                # 更新状态
                for gateway_name, state in self.states.items():
                    # 简单判断：如果有合约数据，且该网关在配置中，认为已连接
                    # 严谨判断需要检查合约的 gateway_name
                    
                    gateway_contracts = [
                        c for c in contracts
                        if c.gateway_name.lower() == gateway_name
                    ]
                    
                    if gateway_contracts:
                        state.status = GatewayStatus.CONNECTED
                        state.connected_time = time.time()
                        state.contract_count = len(gateway_contracts)
                
                if self.is_all_connected():
                    return True
            
            time.sleep(check_interval)
        
        return False
    
    def get_status(self) -> Dict[str, GatewayState]:
        """
        获取所有网关状态
        
        Returns:
            网关状态字典
        """
        return self.states.copy()
    
    def is_all_connected(self) -> bool:
        """
        检查是否所有网关都已连接
        
        Returns:
            True 如果所有网关都已连接
        """
        if not self.states:
            return False
            
        return all(
            state.status == GatewayStatus.CONNECTED
            for state in self.states.values()
        )
    
    def get_connected_gateways(self) -> List[str]:
        """
        获取已连接的网关列表
        
        Returns:
            已连接的网关名称列表
        """
        return [
            name for name, state in self.states.items()
            if state.status == GatewayStatus.CONNECTED
        ]
