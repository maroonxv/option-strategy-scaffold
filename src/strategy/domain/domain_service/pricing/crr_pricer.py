"""
CRRPricer 领域服务（向后兼容代理模块）

实际实现已移至 pricing/pricers/crr_pricer.py。
本模块保留以兼容现有导入路径。
"""
from .pricers.crr_pricer import CRRPricer  # noqa: F401

__all__ = ["CRRPricer"]
