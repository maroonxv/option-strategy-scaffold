"""PricingEngineConfig 配置值对象"""

from dataclasses import dataclass

from ..pricing import PricingModel


@dataclass(frozen=True)
class PricingEngineConfig:
    """定价引擎配置"""

    american_model: PricingModel = PricingModel.BAW  # 美式期权定价模型
    crr_steps: int = 100  # CRR 二叉树步数
