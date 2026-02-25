from datetime import date
from typing import List, Optional, Callable
from vnpy.trader.object import ContractData
from src.strategy.infrastructure.parsing.contract_helper import ContractHelper


class BaseFutureSelector:
    """
    Base class for future selection strategies.
    Provides common utilities for contract filtering and selection.
    """
    
    def select_dominant_contract(
        self, 
        contracts: List[ContractData], 
        current_date: date,
        log_func: Optional[Callable[[str], None]] = None
    ) -> Optional[ContractData]:
        """  
        Select the dominant contract.
        Default implementation selects the contract with the earliest expiry (nearest month).
        
        Args:
            contracts: List of available contracts
            current_date: Current date
            log_func: Logger function
            
        Returns:
            The selected dominant contract object
        """
        if not contracts:
            return None
            
        # 1. Sort by contract symbol (usually alphabetical order equals chronological order)
        sorted_contracts = sorted(contracts, key=lambda c: c.symbol)
        
        # 2. Default: Return the first contract (current month)
        return sorted_contracts[0]

    def filter_by_maturity(
        self, 
        contracts: List[ContractData], 
        current_date: date, 
        mode: str = "current_month"
    ) -> List[ContractData]:
        """
        Filter contracts by maturity.
        
        Args:
            contracts: List of available contracts
            current_date: Current date
            mode: "current_month" or "next_month"
            
        Returns:
            Filtered list of contracts
        """
        sorted_contracts = sorted(contracts, key=lambda c: c.symbol)
        if not sorted_contracts:
            return []
            
        if mode == "current_month":
            return [sorted_contracts[0]]
        elif mode == "next_month":
            if len(sorted_contracts) > 1:
                return [sorted_contracts[1]]
            else:
                return []
        return sorted_contracts
