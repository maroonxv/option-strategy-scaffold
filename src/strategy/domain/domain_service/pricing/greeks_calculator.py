"""
GreeksCalculator 领域服务（向后兼容代理模块）

实际实现已移至 pricing/iv/greeks_calculator.py。
本模块保留以兼容现有导入路径。
"""
from .iv.greeks_calculator import GreeksCalculator  # noqa: F401

__all__ = ["GreeksCalculator"]
