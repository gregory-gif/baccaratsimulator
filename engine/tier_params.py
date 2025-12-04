from dataclasses import dataclass
from typing import Dict, Optional

@dataclass(frozen=True)
class TierConfig:
    level: int
    min_ga: int
    max_ga: int
    base_unit: int
    press_unit: int
    stop_loss: int
    profit_lock: int
    catastrophic_cap: int

def generate_tier_map(safety_factor: int = 20) -> Dict[int, TierConfig]:
    """
    Generates the Tier Ladder based on Risk Tolerance.
    safety_factor: How many Base Units you need to play this tier.
    Standard Doctrine = 20. Conservative = 40.
    """
    
    # Base Units: Tier 1=50, Tier 2=100, Tier 3=150, Tier 4=200, Tier 5=250
    specs = [
        (1, 50, 100),
        (2, 100, 150),
        (3, 150, 200),
        (4, 200, 300),
        (5, 250, 375)
    ]
    
    tier_map = {}
    
    for i, (level, base, press) in enumerate(specs):
        if level == 1:
            # Floor of 1500 or calculated risk, whichever is higher
            start_ga = max(1500, base * safety_factor)
        else:
            start_ga = base * safety_factor
            
        # Stop Loss: ~10 units | Profit: +6 units
        stop = -(base * 10) 
        profit = base * 6 
        
        # Cap: ~3.5x Stop Loss
        cat_cap = stop * 3.5
        
        # Calculate End GA (Start of next tier - 1)
        if i < len(specs) - 1:
            next_base = specs[i+1][1]
            # Ensure next tier start doesn't overlap weirdly if safety factor is low
            next_start = next_base * safety_factor
            end_ga = next_start - 1
        else:
            end_ga = 9999999
            
        tier_map[level] = TierConfig(
            level=level,
            min_ga=int(start_ga),
            max_ga=int(end_ga),
            base_unit=base,
            press_unit=press,
            stop_loss=stop,
            profit_lock=profit,
            catastrophic_cap=int(cat_cap)
        )
        
    return tier_map

# --- CRITICAL FIX: EXPORT DEFAULT MAP ---
# This prevents ImportError in other files that expect TIER_MAP to exist.
TIER_MAP = generate_tier_map(safety_factor=20)

def get_tier_for_ga(ga: float, tier_map: Optional[Dict[int, TierConfig]] = None) -> TierConfig:
    """
    Finds the correct tier.
    If tier_map is None, uses the default TIER_MAP (Standard Doctrine).
    """
    if tier_map is None:
        tier_map = TIER_MAP

    for tier_level, config in tier_map.items():
        if config.min_ga <= ga <= config.max_ga:
            return config
            
    # Fallback logic
    lowest_min = tier_map[1].min_ga
    if ga < lowest_min:
        return tier_map[1]
    return tier_map[5]

def get_churn_bet_size(tier_level: int) -> int:
    if tier_level <= 2:
        return 50
    return 100
