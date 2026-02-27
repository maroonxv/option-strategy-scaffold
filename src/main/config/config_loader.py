"""
config_loader.py - 配置加载器

支持:
1. TOML 配置文件 (策略配置)
2. 环境变量 (网关配置)
3. 配置验证
"""
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Python 3.11+ 内置 tomllib，之前版本使用 tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class ConfigLoader:
    """
    配置加载器
    
    - 策略配置: 从 YAML 文件加载
    - 网关配置: 从环境变量加载 (.env)
    """
    
    @staticmethod
    def load_toml(path: str) -> Dict[str, Any]:
        """加载 TOML 配置文件"""
        with open(path, "rb") as f:
            return tomllib.load(f)
    
    @staticmethod
    def load_yaml(path: str) -> Dict[str, Any]:
        """加载 YAML 配置文件（已弃用，保留用于向后兼容）"""
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    @staticmethod
    def load_gateway_config() -> Dict[str, Any]:
        """
        从环境变量加载网关配置
        
        需要:
            包含 CTP 配置的 .env 文件
        """
        # 显式定位项目根目录下的 .env
        # 从 src/main/config/config_loader.py 到项目根目录需要 4 级 parent
        env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
        else:
            # 回退到默认搜索
            load_dotenv()
        
        def get_env_any(*keys, default=""):
            for key in keys:
                val = os.getenv(key)
                if val:
                    return val
            return default

        # 加载并标准化地址
        td_addr = get_env_any("CTP_TD_ADDRESS", "CTP_TD_SERVER", "CTP_TD_URI")
        md_addr = get_env_any("CTP_MD_ADDRESS", "CTP_MD_SERVER", "CTP_MD_URI")
        
        if td_addr and not td_addr.startswith("tcp://"):
            td_addr = "tcp://" + td_addr
        if md_addr and not md_addr.startswith("tcp://"):
            md_addr = "tcp://" + md_addr

        config = {
            "ctp": {
                "用户名": get_env_any("CTP_USERID", "CTP_USERNAME"),
                "密码": get_env_any("CTP_PASSWORD"),
                "经纪商代码": get_env_any("CTP_BROKERID", "CTP_BROKER_ID"),
                "交易服务器": td_addr,
                "行情服务器": md_addr,
                "产品名称": get_env_any("CTP_PRODUCT_NAME", "CTP_APP_ID", "CTP_PRODUCT_INFO", default="simnow_client_test"),
                "授权编码": get_env_any("CTP_AUTH_CODE", default="0000000000000000"),
                "柜台环境": get_env_any("CTP_ENV", default="实盘")
            }
        }
        
        # 立即验证关键字段
        if not config["ctp"]["交易服务器"]:
            raise ValueError(f"CTP_TD_ADDRESS (or CTP_TD_SERVER) 未配置或为空! (.env path: {env_path})")
        if not config["ctp"]["行情服务器"]:
            # 如果行情服务器为空，尝试使用交易服务器（有些环境可能是同一个，或者用户忘了配）
            # 但通常不建议这样做，这里还是报错提示用户
            raise ValueError(f"CTP_MD_ADDRESS (or CTP_MD_SERVER) 未配置或为空! (.env path: {env_path})")
            
        return config
    
    @staticmethod
    def validate_gateway_config(config: Dict[str, Any]) -> bool:
        """
        验证网关配置
        
        Args:
            config: 网关配置字典
            
        Returns:
            True 如果配置有效
        """
        required_fields = [
            "用户名", "密码", "经纪商代码",
            "交易服务器", "行情服务器"
        ]
        
        for gateway_name, gateway_config in config.items():
            for field in required_fields:
                if field not in gateway_config:
                    raise ValueError(
                        f"网关 {gateway_name} 缺少必填字段: {field}"
                    )
        
        return True

    @staticmethod
    def validate_strategy_config(config: Dict[str, Any]) -> bool:
        """
        验证策略配置
        
        Args:
            config: 策略配置字典
            
        Returns:
            True 如果配置有效
        """
        strategies = config.get("strategies", [])
        
        if not strategies:
            raise ValueError("策略配置为空")
        
        for strategy in strategies:
            if "class_name" not in strategy:
                raise ValueError("策略缺少 class_name")
        return True

    @staticmethod
    def merge_strategy_config(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并策略配置
        
        将 override_config 中的策略配置合并到 base_config 中。
        假设两个配置都包含 'strategies' 列表，且列表长度为 1。
        
        Args:
            base_config: 基础配置
            override_config: 覆盖配置 (如时间窗口配置)
            
        Returns:
            合并后的新配置字典
        """
        if not override_config or "strategies" not in override_config:
            return base_config
            
        merged = base_config.copy()
        
        # 确保基础配置也有 strategies
        if "strategies" not in merged:
            merged["strategies"] = override_config["strategies"]
            return merged
            
        # 简单的合并逻辑：取第一个策略进行合并
        # 我们假设 run.bat 每次启动只针对一个策略/时间窗口
        base_strategy = merged["strategies"][0]
        override_strategy = override_config["strategies"][0]
        
        # 1. 覆盖 strategy_name (关键! 用于 pickle 文件名)
        if "strategy_name" in override_strategy:
            base_strategy["strategy_name"] = override_strategy["strategy_name"]
            
        # 2. 合并 setting
        if "setting" in override_strategy:
            if "setting" not in base_strategy:
                base_strategy["setting"] = {}
            
            # 更新 setting 中的字段 (如 bar_window)
            base_strategy["setting"].update(override_strategy["setting"])
            
        return merged
                
    @staticmethod
    def load_target_products(path: str = "config/general/trading_target.toml") -> list[str]:
        """
        加载交易目标品种列表
        
        Args:
            path: 配置文件路径
            
        Returns:
            品种代码列表 (e.g. ['rb', 'm'])
        """
        if not os.path.isabs(path):
            # 从 src/main/config/config_loader.py 到项目根目录需要 4 级 parent
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            path = str(project_root / path)
            
        if not os.path.exists(path):
            return []
        
        # 尝试 TOML 格式
        if path.endswith('.toml'):
            with open(path, "rb") as f:
                data = tomllib.load(f)
                return data.get("targets", [])
        
        # 向后兼容：尝试 YAML 格式
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)


    @staticmethod
    def load_hedging_config(config: dict) -> dict:
        """
        从策略配置中加载对冲配置

        Args:
            config: 完整策略配置字典

        Returns:
            包含 delta_hedging 和 gamma_scalping 配置的字典，缺失字段使用默认值
        """
        hedging = config.get("hedging", {})

        delta_defaults = {
            "target_delta": 0.0,
            "hedging_band": 0.5,
            "hedge_instrument_vt_symbol": "",
            "hedge_instrument_delta": 1.0,
            "hedge_instrument_multiplier": 10.0,
        }
        gamma_defaults = {
            "rebalance_threshold": 0.3,
            "hedge_instrument_vt_symbol": "",
            "hedge_instrument_delta": 1.0,
            "hedge_instrument_multiplier": 10.0,
        }

        delta_cfg = hedging.get("delta_hedging", {})
        gamma_cfg = hedging.get("gamma_scalping", {})

        return {
            "delta_hedging": {k: delta_cfg.get(k, v) for k, v in delta_defaults.items()},
            "gamma_scalping": {k: gamma_cfg.get(k, v) for k, v in gamma_defaults.items()},
        }

    @staticmethod
    def load_advanced_orders_config(config: dict) -> dict:
        """
        从策略配置中加载高级订单配置

        Args:
            config: 完整策略配置字典

        Returns:
            高级订单配置字典，缺失字段使用默认值
        """
        defaults = {
            "default_iceberg_batch_size": 5,
            "default_twap_slices": 10,
            "default_time_window_seconds": 300,
        }
        ao_cfg = config.get("advanced_orders", {})
        return {k: ao_cfg.get(k, v) for k, v in defaults.items()}

    @staticmethod
    def load_combination_risk_config(config: dict) -> "CombinationRiskConfig":
        """
        从策略配置中加载组合策略风控配置

        Args:
            config: 完整策略配置字典

        Returns:
            CombinationRiskConfig 实例，缺失字段使用默认值
            默认值: delta_limit=2.0, gamma_limit=0.5, vega_limit=200.0
        """
        from src.strategy.domain.value_object.combination.combination import CombinationRiskConfig

        combination_risk = config.get("combination_risk", {})

        return CombinationRiskConfig(
            delta_limit=combination_risk.get("delta_limit", 2.0),
            gamma_limit=combination_risk.get("gamma_limit", 0.5),
            vega_limit=combination_risk.get("vega_limit", 200.0),
        )

@staticmethod
def load_combination_risk_config(config: dict) -> "CombinationRiskConfig":
    """
    从策略配置中加载组合策略风控配置

    Args:
        config: 完整策略配置字典

    Returns:
        CombinationRiskConfig 实例，缺失字段使用默认值
        默认值: delta_limit=2.0, gamma_limit=0.5, vega_limit=200.0
    """
    from src.strategy.domain.value_object.combination.combination import CombinationRiskConfig

    combination_risk = config.get("combination_risk", {})

    return CombinationRiskConfig(
        delta_limit=combination_risk.get("delta_limit", 2.0),
        gamma_limit=combination_risk.get("gamma_limit", 0.5),
        vega_limit=combination_risk.get("vega_limit", 200.0),
    )

