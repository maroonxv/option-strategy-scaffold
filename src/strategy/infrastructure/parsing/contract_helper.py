from datetime import date
from typing import Any, List, Optional, Callable, Iterator, Dict
import pandas as pd
import re

class ContractHelper:
    """
    合约工具类 (Infrastructure Layer)
    
    职责:
    1. 屏蔽 VnPy 合约对象的存储细节
    2. 提供纯函数的合约筛选与解析逻辑
    3. 数据适配: 将合约列表转换为 Pandas DataFrame
    """

    @staticmethod
    def get_option_chain(all_contracts: List[Any], underlying_vt_symbol: str, log_func: Optional[Callable] = None) -> pd.DataFrame:
        """
        获取指定标的期货的期权链
        
        Args:
            all_contracts: 市场全部合约列表 (VnPy ContractData 对象列表)
            underlying_vt_symbol: 标的期货 VT 代码 (e.g. "IF2501.CFFEX")
            log_func: 日志回调函数 (Optional)
            
        Returns:
            pd.DataFrame: 清洗后的期权链数据
        """
        option_data = []
        for info in ContractHelper._iter_option_contract_infos(
            all_contracts=all_contracts,
            underlying_vt_symbol=underlying_vt_symbol,
            log_func=log_func,
        ):
            option_data.append(
                {
                    "vt_symbol": info["vt_symbol"],
                    "symbol": info["contract_symbol"],
                    "underlying_symbol": info["contract_underlying"] or info["underlying_symbol"],
                    "option_type": info["option_type"],
                    "strike_price": info["strike_price"],
                    "expiry_date": info["expiry_date"],
                }
            )

        return pd.DataFrame(option_data)

    @staticmethod
    def _iter_option_contract_infos(
        all_contracts: List[Any],
        underlying_vt_symbol: str,
        log_func: Optional[Callable] = None,
    ) -> Iterator[Dict[str, Any]]:
        FUTURE_OPTION_MAP = {
            "IF": "IO",
            "IM": "MO",
            "IH": "HO",
        }

        if not underlying_vt_symbol:
            return

        try:
            if "." in underlying_vt_symbol:
                symbol, exchange_str = underlying_vt_symbol.split(".")
            else:
                symbol = underlying_vt_symbol
                exchange_str = ""

            match = re.match(r"^([a-zA-Z]+)(\d+)", symbol)
            if not match:
                return

            product_code = match.group(1).upper()
            contract_suffix = match.group(2)

            if product_code in FUTURE_OPTION_MAP:
                option_product_code = FUTURE_OPTION_MAP[product_code]
                target_prefix = f"{option_product_code}{contract_suffix}"
            else:
                target_prefix = symbol

        except ValueError:
            return

        def _infer_option_type_from_symbol(text: str) -> Optional[str]:
            if not text:
                return None
            base = text.split(".")[0]
            m = re.search(r"-(C|P)-", base, flags=re.IGNORECASE)
            if m:
                return "call" if m.group(1).upper() == "C" else "put"
            m = re.search(r"([CPcp])[-]?[0-9]+(?:\.[0-9]+)?$", base)
            if m:
                return "call" if m.group(1).upper() == "C" else "put"
            return None

        for contract in all_contracts:
            if not hasattr(contract, "option_type") and not hasattr(contract, "option_strike"):
                continue

            contract_symbol = getattr(contract, "symbol", "") or ""
            is_potential = contract_symbol.startswith(target_prefix)

            contract_exchange = getattr(contract, "exchange", None)
            exchange_val = getattr(contract_exchange, "value", str(contract_exchange)) if contract_exchange else ""
            if exchange_val and "Exchange." in exchange_val:
                try:
                    exchange_val = exchange_val.split(".")[-1]
                except IndexError:
                    pass

            if exchange_str and exchange_val != exchange_str:
                # if is_potential and log_func:
                #     log_func(
                #         f"[调试-HELPER] 检查 {contract.vt_symbol} | 前缀匹配: 是 | 原始交易所: {contract_exchange} | "
                #         f"清洗后值: '{exchange_val}' | 目标交易所: '{exchange_str}'"
                #     )
                #     log_func(f"[调试-HELPER] -> 已跳过，因交易所不匹配: '{exchange_val}' != '{exchange_str}'")
                continue

            contract_underlying = getattr(contract, "underlying_symbol", None) or getattr(contract, "option_underlying", None)

            should_include = False
            if contract_underlying:
                underlying_text = str(contract_underlying)
                underlying_symbol_only = underlying_text.split(".")[0] if "." in underlying_text else underlying_text
                if underlying_symbol_only.upper() == symbol.upper() or underlying_text.upper() == underlying_vt_symbol.upper():
                    should_include = True

            if not should_include and contract_symbol.startswith(target_prefix):
                should_include = True
                # if is_potential and log_func:
                #     log_func(
                #         f"[调试-HELPER] 检查 {contract.vt_symbol} | 前缀匹配: 是 | 原始交易所: {contract_exchange} | "
                #         f"清洗后值: '{exchange_val}' | 目标交易所: '{exchange_str}'"
                #     )
                #     log_func(f"[调试-HELPER] -> 已纳入! 标的字段: {contract_underlying}")

            if not should_include:
                continue

            strike_price = getattr(contract, "option_strike", 0)
            if not strike_price:
                m = re.search(r"([CPcp])[-]?([0-9]+(?:\.[0-9]+)?)$", contract_symbol)
                if m:
                    strike_price = float(m.group(2))

            raw_option_type = getattr(contract, "option_type", None)
            option_type_value = getattr(raw_option_type, "value", raw_option_type)
            option_type_str = str(option_type_value).lower()

            if option_type_value == 1 or option_type_str in ("call", "c", "optiontype.call"):
                option_type_text = "call"
            elif option_type_value == 2 or option_type_str in ("put", "p", "optiontype.put"):
                option_type_text = "put"
            else:
                option_type_text = _infer_option_type_from_symbol(contract_symbol) or _infer_option_type_from_symbol(
                    getattr(contract, "vt_symbol", "") or ""
                )
                if option_type_text is None:
                    continue

            # if is_potential and log_func:
            #     log_func(
            #         f"[调试-HELPER] 解析 {contract.vt_symbol} | 行权价: {strike_price} | "
            #         f"类型原始值: {raw_option_type} ({option_type_value}) | 映射类型: {option_type_text}"
            #     )

            yield {
                "vt_symbol": contract.vt_symbol,
                "contract_symbol": contract_symbol,
                "contract_underlying": contract_underlying,
                "underlying_symbol": symbol,
                "option_type": option_type_text,
                "strike_price": strike_price,
                "expiry_date": str(getattr(contract, "option_expiry", "")),
            }

    @staticmethod
    def get_option_vt_symbols(
        all_contracts: List[Any],
        underlying_vt_symbol: str,
        log_func: Optional[Callable] = None
    ) -> List[str]:
        return [
            info["vt_symbol"]
            for info in ContractHelper._iter_option_contract_infos(
                all_contracts=all_contracts,
                underlying_vt_symbol=underlying_vt_symbol,
                log_func=log_func,
            )
        ]

    @staticmethod
    def is_contract_of_product(contract: Any, product_code: str) -> bool:
        """
        判断合约是否属于指定品种
        """
        symbol = getattr(contract, "symbol", "")
        match = re.match(r"^([a-zA-Z]+)", symbol)
        if match:
            return match.group(1).lower() == product_code.lower()
        return False

    @staticmethod
    def get_expiry_from_symbol(symbol: str) -> Optional[date]:
        """
        从合约代码解析到期日
        示例: rb2501 -> 2025-01-15 (估算)
             SA501 -> 2025-01-15 (估算)
        """
        match = re.search(r"(\d{3,4})$", symbol)
        if not match:
            return None

        digits = match.group(1)
        current_year = date.today().year

        if len(digits) == 4:
            year_suffix = int(digits[:2])
            month = int(digits[2:])
            year = 2000 + year_suffix
        elif len(digits) == 3:
            year_suffix = int(digits[0])
            month = int(digits[1:])
            year = (current_year // 10) * 10 + year_suffix
            if year < current_year - 1:
                year += 10
        else:
            return None

        try:
            return date(year, month, 15)
        except ValueError:
            return None
