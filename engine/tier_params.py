from dataclasses import dataclass

@dataclass
class TierConfig:
    level: int
    min_ga: float
    max_ga: float
    base_unit: float
    press_unit: float
    stop_loss: float
    profit_lock: float
    catastrophic_cap: float

# --- BETTING ENGINE MODES ---
# 1. STANDARD: Safe, Exponential Growth
# 2. FORTRESS: Aggressive 100 start (2000 threshold)
# 3. TITAN: High Roller Hysteresis (150/250 push)

def generate_tier_map(safety_factor: int = 25, mode: str = 'Standard') -> dict:
    tiers = {}
    
    # --- MODE: TITAN (Updated Hysteresis Logic) ---
    if mode == 'Titan':
        # Tier 1: Defense (Below €2,000) -> Bet €50
        tiers[1] = TierConfig(
            level=1, min_ga=0, max_ga=2000,
            base_unit=50.0, press_unit=50.0,
            stop_loss=-(50.0*10), profit_lock=50.0*6, catastrophic_cap=-(50.0*20)
        )
        # Tier 2: The Floor (Between €2,000 and €5,000) -> Bet €100 / Press €150
        tiers[2] = TierConfig(
            level=2, min_ga=2000, max_ga=float('inf'),
            base_unit=100.0, press_unit=150.0, # Custom Press
            stop_loss=-(100.0*10), profit_lock=100.0*6, catastrophic_cap=-(100.0*20)
        )
        # Tier 3: The Ceiling (Above €5,000) -> Bet €150 / Press €250
        tiers[3] = TierConfig(
            level=3, min_ga=5000, max_ga=float('inf'),
            base_unit=150.0, press_unit=250.0, # Custom Press
            stop_loss=-(150.0*10), profit_lock=150.0*6, catastrophic_cap=-(150.0*20)
        )
        return tiers

    # --- MODE: FORTRESS (Protected Berserker) ---
    if mode == 'Fortress':
        tiers[1] = TierConfig(
            level=1, min_ga=0, max_ga=2000,
            base_unit=50.0, press_unit=50.0,
            stop_loss=-(50.0*10), profit_lock=50.0*6, catastrophic_cap=-(50.0*20)
        )
        tiers[2] = TierConfig(
            level=2, min_ga=2000, max_ga=float('inf'),
            base_unit=100.0, press_unit=100.0,
            stop_loss=-(100.0*10), profit_lock=100.0*6, catastrophic_cap=-(100.0*20)
        )
        return tiers

    # --- MODE: STANDARD (Exponential) ---
    BASE_BET_T1 = 50.0
    multipliers = [1, 2, 4, 10, 20, 40] 
    for i, mult in enumerate(multipliers):
        level = i + 1
        base = BASE_BET_T1 * mult
        min_ga = base * safety_factor
        max_ga = (BASE_BET_T1 * multipliers[i+1] * safety_factor) if i < len(multipliers)-1 else float('inf')
        
        tiers[level] = TierConfig(
            level=level, min_ga=min_ga, max_ga=max_ga,
            base_unit=base, press_unit=base,
            stop_loss=-(base*10), profit_lock=base*6, catastrophic_cap=-(base*20)
        )
    return tiers

def get_tier_for_ga(current_ga: float, tier_map: dict = None, active_level: int = 1, mode: str = 'Standard') -> TierConfig:
    """
    Selects Tier with Hysteresis (Memory).
    """
    if tier_map is None:
        tier_map = generate_tier_map()

    # --- TITAN HYSTERESIS LOGIC (UPDATED) ---
    if mode == 'Titan':
        # 1. UPGRADE CHECK
        if active_level < 3:
            if current_ga >= 5000: return tier_map[3] # Cross 5k -> Tier 3
            if current_ga >= 2000: return tier_map[2] # Cross 2k -> Tier 2
            return tier_map[1] # Else Tier 1

        # 2. DOWNGRADE CHECK (Tightened Safety)
        if active_level == 3:
            if current_ga < 4500: return tier_map[2] # Crash 4.5k -> Drop to 2 (Was 3500)
            return tier_map[3] # Stay at 3 (Buffer Zone)
            
        return tier_map[active_level] # Fallback

    # --- FORTRESS LOGIC ---
    if mode == 'Fortress':
        if current_ga >= 2000: return tier_map[2]
        return tier_map[1]

    # --- STANDARD LOGIC ---
    selected_tier = tier_map[min(tier_map.keys())]
    for level in sorted(tier_map.keys()):
        t = tier_map[level]
        if current_ga >= t.min_ga:
            selected_tier = t
        else:
            break
    return selected_tier
