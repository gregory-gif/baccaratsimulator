from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class TierConfig:
    level: int
    min_ga: int
    max_ga: int
    base_unit: int
    press_unit: int
    stop_loss: int
    profit_lock: int
    max_presses_per_shoe: int
    catastrophic_cap: int  # YTD Loss Limit

# 3. THE UNIFIED LADDER & 4.2 CATASTROPHIC CAP
# Note: Tier 0 is for the first session logic if needed, but primarily we map 1-5.
TIER_MAP = {
    1: TierConfig(
        level=1, min_ga=1500, max_ga=1999, 
        base_unit=50, press_unit=100, 
        stop_loss=-400, profit_lock=500, 
        max_presses_per_shoe=2, catastrophic_cap=-1400
    ),
    2: TierConfig(
        level=2, min_ga=2000, max_ga=2999, 
        base_unit=100, press_unit=150, 
        stop_loss=-800, profit_lock=1000, 
        max_presses_per_shoe=3, catastrophic_cap=-2800
    ),
    3: TierConfig(
        level=3, min_ga=3000, max_ga=4999, 
        base_unit=150, press_unit=200, 
        stop_loss=-1200, profit_lock=1500, 
        max_presses_per_shoe=5, catastrophic_cap=-4200
    ),
    4: TierConfig(
        level=4, min_ga=5000, max_ga=7499, 
        base_unit=200, press_unit=300, 
        stop_loss=-1600, profit_lock=2000, 
        max_presses_per_shoe=5, catastrophic_cap=-5600
    ),
    5: TierConfig(
        level=5, min_ga=7500, max_ga=999999, 
        base_unit=250, press_unit=375, 
        stop_loss=-2000, profit_lock=2500, 
        max_presses_per_shoe=5, catastrophic_cap=-7000
    ),
}

def get_tier_for_ga(ga: float) -> TierConfig:
    """
    Returns the TierConfig based on the current Game Account (GA).
    Falls back to Tier 1 if GA is below 1500 (Insolvency checks handled elsewhere).
    """
    for tier_level, config in TIER_MAP.items():
        if config.min_ga <= ga <= config.max_ga:
            return config
    
    # Fallback for low bankroll (handled by Insolvency Floor usually) or extremely high
    if ga < 1500:
        return TIER_MAP[1]
    return TIER_MAP[5]

def get_churn_bet_size(tier_level: int) -> int:
    """
    4.1 C: Gold Churn - Churn at one Tier lower than current Play Tier.
    """
    if tier_level <= 2:
        return 50
    return 100
