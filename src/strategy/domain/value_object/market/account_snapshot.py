"""
AccountSnapshot 值对象 - 账户快照

封装 vnpy AccountData 的关键字段，提供账户资金信息的不可变快照。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AccountSnapshot:
    """
    账户快照值对象
    
    封装 vnpy AccountData 的关键字段，用于策略层查询账户资金信息。
    
    Attributes:
        balance: 账户总资金 (权益)
        available: 可用资金
        frozen: 冻结资金 (保证金 + 冻结手续费)
        accountid: 账户ID (用于多账户场景)
    """
    balance: float
    available: float
    frozen: float = 0.0
    accountid: str = ""
    
    @property
    def used(self) -> float:
        """已使用资金 (总资金 - 可用)"""
        return max(0.0, self.balance - self.available)
    
    @property
    def usage_ratio(self) -> float:
        """资金使用率 (已使用 / 总资金)"""
        if self.balance <= 0:
            return 0.0
        return self.used / self.balance
    
    def __repr__(self) -> str:
        return (
            f"AccountSnapshot(balance={self.balance:.2f} "
            f"available={self.available:.2f} frozen={self.frozen:.2f})"
        )
