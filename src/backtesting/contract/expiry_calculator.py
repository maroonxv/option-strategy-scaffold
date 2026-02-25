"""
到期日计算器

根据交易所规则计算合约到期日，支持手动配置优先和 chinese_calendar 节假日排除。
"""

import calendar
import logging
from datetime import date, timedelta
from typing import List

from src.backtesting.config import MANUAL_EXPIRY_CONFIG
from src.backtesting.contract.exchange_resolver import ExchangeResolver

import chinese_calendar

logger = logging.getLogger(__name__)


class ExpiryCalculator:
    """到期日计算器，根据交易所规则计算合约到期日。"""

    @staticmethod
    def get_trading_days(year: int, month: int) -> List[date]:
        """获取指定月份的交易日列表（排除周末和法定节假日）。"""
        num_days = calendar.monthrange(year, month)[1]
        days = []
        for day in range(1, num_days + 1):
            d = date(year, month, day)
            if d.weekday() >= 5:
                continue
            if chinese_calendar.is_holiday(d):
                    continue
            days.append(d)
        return days

    @classmethod
    def calculate(cls, product_code: str, year: int, month: int) -> date:
        """根据交易所规则计算到期日。优先使用手动配置。"""
        # 1. 检查手动配置
        contract_suffix = f"{str(year)[-2:]}{month:02d}"
        symbol_key = f"{product_code}{contract_suffix}"
        if symbol_key in MANUAL_EXPIRY_CONFIG:
            return MANUAL_EXPIRY_CONFIG[symbol_key]

        # 2. 解析交易所
        try:
            exchange = ExchangeResolver.resolve(product_code)
        except ValueError:
            return date(year, month, 15)

        # 3. 计算交割月前一个月
        if month == 1:
            pre_year = year - 1
            pre_month = 12
        else:
            pre_year = year
            pre_month = month - 1

        try:
            if exchange == "CFFEX":
                return cls._calc_cffex(year, month)
            elif exchange == "DCE":
                return cls._calc_dce(pre_year, pre_month)
            elif exchange == "CZCE":
                return cls._calc_czce(pre_year, pre_month)
            elif exchange in ("SHFE", "INE"):
                return cls._calc_shfe_ine(pre_year, pre_month)
        except Exception as e:
            logger.error(f"计算到期日失败 {product_code}: {e}")
            return date(year, month, 15)

        return date(year, month, 15)

    @classmethod
    def _calc_cffex(cls, year: int, month: int) -> date:
        """中金所：合约月份的第三个周五。"""
        c_days = calendar.monthcalendar(year, month)
        fridays = [week[4] for week in c_days if week[4] != 0]
        if len(fridays) >= 3:
            expiry = date(year, month, fridays[2])
            while chinese_calendar.is_holiday(expiry):
                    expiry += timedelta(days=1)
            return expiry
        return date(year, month, 15)

    @classmethod
    def _calc_dce(cls, pre_year: int, pre_month: int) -> date:
        """大商所：交割月前一个月的第 12 个交易日。"""
        trading_days = cls.get_trading_days(pre_year, pre_month)
        if len(trading_days) >= 12:
            return trading_days[11]
        return trading_days[-1] if trading_days else date(pre_year, pre_month, 28)

    @classmethod
    def _calc_czce(cls, pre_year: int, pre_month: int) -> date:
        """郑商所：交割月前一个月的第 15 个交易日。"""
        trading_days = cls.get_trading_days(pre_year, pre_month)
        if len(trading_days) >= 15:
            return trading_days[14]
        return trading_days[-1] if trading_days else date(pre_year, pre_month, 28)

    @classmethod
    def _calc_shfe_ine(cls, pre_year: int, pre_month: int) -> date:
        """上期所/能源中心：交割月前一个月的倒数第 5 个交易日。"""
        trading_days = cls.get_trading_days(pre_year, pre_month)
        if len(trading_days) >= 5:
            return trading_days[-5]
        return trading_days[0] if trading_days else date(pre_year, pre_month, 1)
