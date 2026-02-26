"""
BlackScholesPricer 领域服务（向后兼容代理模块）

实际实现已移至 pricing/pricers/bs_pricer.py。
本模块保留以兼容现有导入路径。
"""
from .pricers.bs_pricer import BlackScholesPricer  # noqa: F401

__all__ = ["BlackScholesPricer"]
