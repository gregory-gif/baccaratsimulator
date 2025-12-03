from dataclasses import dataclass
from typing import List

@dataclass
class YearState:
    ga_start: float      # GA0
    contributions: float # C
    play_pnl: float      # Net result from play
    luxury_tax: float    # LT
    
    @property
    def current_ga(self) -> float:
        return self.ga_start + self.contributions + self.play_pnl - self.luxury_tax

    @property
    def ytd_pnl(self) -> float:
        return self.play_pnl - self.luxury_tax

def calculate_luxury_tax(ga: float, current_lt: float) -> float:
    """
    6. LUXURY TAX
    If GA > 12,500 -> Withdraw 25% of surplus.
    """
    threshold = 12500
    if ga > threshold:
        surplus = ga - threshold
        tax = surplus * 0.25
        return tax
    return 0.0

def check_insolvency(ga: float) -> bool:
    """
    4.2 FINANCIAL DEFENSE
    Trigger: GA < 1,000 -> STOP YEAR.
    """
    return ga < 1000
