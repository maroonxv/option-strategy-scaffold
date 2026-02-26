"""
BAWPricer 领域服务（向后兼容代理模块）

实际实现已移至 pricing/pricers/baw_pricer.py。
本模块保留以兼容现有导入路径。
"""
from .pricers.baw_pricer import BAWPricer  # noqa: F401

__all__ = ["BAWPricer"]
