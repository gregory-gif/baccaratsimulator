from dataclasses import dataclass
from typing import Dict

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
    
    Standard Doctrine (High Risk): Factor 20 (e.g. €2000 for €100 bets = 5% risk)
    Conservative (Pro): Factor 40 (e.g. €4000 for €100 bets = 2.5% risk)
    """
    
    # Base Units are fixed by Table Limits logic
    # Tier 1: €50, Tier 2: €100, Tier 3: €150, Tier 4: €200, Tier 5: €250
    specs = [
        (1, 50, 100),
        (2, 100, 150),
        (3, 150, 200),
        (4, 200, 300),
        (5, 250, 375)
    ]
    
    tier_map = {}
    
    # Hardcoded floor for Tier 1 to allow starting small
    # Standard: 1500. If we use factor, 50*20 = 1000.
    # We'll use the MAX of (1500, Base*Factor) for Tier 1 to respect Doctrine minimums.
    
    for i, (level, base, press) in enumerate(specs):
        if level == 1:
            start_ga = max(1500, base * safety_factor)
        else:
            start_ga = base * safety_factor
            
        # Stop Loss / Profit Lock Scaling (Maintain ~8-10 units ratios)
        # Stop Loss: ~10 units (or calculated relative)
        stop = -(base * 10) 
        profit = base * 6 # Doctrine 2.0 (+6 units)
        
        # Cap: ~3.5x Stop Loss
        cat_cap = stop * 3.5
        
        # Calculate End GA (Start of next tier - 1)
        if i < len(specs) - 1:
            next_base = specs[i+1][1]
            end_ga = (next_base * safety_factor) - 1
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

def get_tier_for_ga(ga: float, tier_map: Dict[int, TierConfig]) -> TierConfig:
    """Finds the correct tier in a generated map."""
    for tier_level, config in tier_map.items():
        if config.min_ga <= ga <= config.max_ga:
            return config
            
    # Fallback logic
    lowest_min = tier_map[1].min_ga
    if ga < lowest_min:
        return tier_map[1]
    return tier_map[5]
