from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional
from .tier_params import TierConfig

class SniperState(Enum):
    WAIT = auto()
    TRIGGER = auto()
    FIRE = auto()
    RESET = auto()

class PlayMode(Enum):
    ACTIVE = auto()
    WATCHER = auto()
    PENALTY = auto()
    STOPPED = auto()

@dataclass
class StrategyOverrides:
    """Allows the Simulator to inject custom rules."""
    iron_gate_limit: int = 3
    stop_loss_units: int = 10
    profit_lock_units: int = 6
    press_trigger_wins: int = 2 
    press_limit_capped: bool = True # <--- THIS IS THE CRITICAL MISSING VARIABLE

@dataclass
class SessionState:
    tier: TierConfig
    overrides: Optional[StrategyOverrides] = None
    
    current_shoe: int = 1
    hands_played_in_shoe: int = 0
    presses_this_shoe: int = 0
    session_pnl: float = 0.0
    shoe_pnls: dict[int, float] = None
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    sniper_state: SniperState = SniperState.WAIT
    mode: PlayMode = PlayMode.ACTIVE
    iron_gate_active: bool = False
    penalty_cooldown: int = 0
    shoe1_tripwire_triggered: bool = False
    gold_churn_active: bool = False
    shoe3_start_pnl: float = 0.0
    
    def __post_init__(self):
        if self.shoe_pnls is None:
            self.shoe_pnls = {1: 0.0, 2: 0.0, 3: 0.0}

class BaccaratStrategist:
    @staticmethod
    def get_next_decision(state: SessionState, ytd_pnl: float) -> dict:
        if state.mode == PlayMode.STOPPED:
             return {'bet_amount': 0, 'reason': "SESSION STOPPED", 'mode': PlayMode.STOPPED}

        # LIMITS
        if state.overrides:
            stop_limit = state.tier.base_unit * -state.overrides.stop_loss_units
            profit_limit = state.tier.base_unit * state.overrides.profit_lock_units
        else:
            stop_limit = state.tier.stop_loss
            profit_limit = state.tier.profit_lock

        # 1. STOP CONDITIONS
        if state.session_pnl <= stop_limit:
            return {'bet_amount': 0, 'reason': "STOP LOSS HIT", 'mode': PlayMode.STOPPED}
        
        if state.session_pnl >= profit_limit:
             return {'bet_amount': 0, 'reason': "PROFIT LOCK SECURED", 'mode': PlayMode.STOPPED}
        
        # Shoe 3 Trailing Stop
        if state.current_shoe == 3:
            five_units = state.tier.base_unit * 5
            if state.shoe3_start_pnl >= five_units:
                if state.session_pnl <= state.tier.base_unit:
                     return {'bet_amount': 0, 'reason': "SHOE 3 TRAILING STOP", 'mode': PlayMode.STOPPED}

        # 2. WATCHER MODE
        if state.mode == PlayMode.WATCHER:
            return {'bet_amount': 0, 'reason': "IRON GATE: Watching", 'mode': PlayMode.WATCHER}

        # 3. BETTING LOGIC
        current_base = state.tier.base_unit
        current_press = state.tier.press_unit
        
        if not state.overrides and state.shoe1_tripwire_triggered:
            return {'bet_amount': 50, 'reason': "TRIPWIRE: Flat €50", 'mode': PlayMode.ACTIVE}

        if state.penalty_cooldown > 0:
            return {'bet_amount': current_base, 'reason': f"RE-ENTRY ({state.penalty_cooldown})", 'mode': PlayMode.ACTIVE}

        # Sniper Logic
        default_max_press = 2 if state.tier.level == 1 else (3 if state.tier.level == 2 else 5)
        
        # Override logic
        if state.overrides:
            # Use the variable safely
            is_capped = getattr(state.overrides, 'press_limit_capped', True)
            if is_capped:
                max_press = default_max_press
            else:
                max_press = 999 
        else:
            max_press = default_max_press

        can_press = state.presses_this_shoe < max_press
        
        bet = current_base
        reason = "Base Bet"
        trigger_wins = state.overrides.press_trigger_wins if state.overrides else 2
        
        if trigger_wins > 0 and state.consecutive_wins >= trigger_wins and can_press:
            bet = current_press
            reason = "Press Bet"
        
        return {'bet_amount': bet, 'reason': reason, 'mode': PlayMode.ACTIVE}

    @staticmethod
    def update_state_after_hand(state: SessionState, won: bool, amount_won: float):
        state.session_pnl += amount_won
        state.shoe_pnls[state.current_shoe] += amount_won
        state.hands_played_in_shoe += 1
        
        if state.mode == PlayMode.WATCHER:
            if won:
                state.mode = PlayMode.ACTIVE
                state.consecutive_wins = 0 
                state.consecutive_losses = 0
                state.penalty_cooldown = 3
            return 

        if won:
            state.consecutive_wins += 1
            state.consecutive_losses = 0
            if state.penalty_cooldown > 0:
                state.penalty_cooldown -= 1
            if amount_won > state.tier.base_unit:
                state.presses_this_shoe += 1
            
        else:
            state.consecutive_losses += 1
            state.consecutive_wins = 0
            
            limit = state.overrides.iron_gate_limit if state.overrides else 3
            if state.consecutive_losses >= limit:
                state.mode = PlayMode.WATCHER
                state.sniper_state = SniperState.RESET
                return

        if not state.overrides and state.current_shoe == 1 and not state.shoe1_tripwire_triggered:
            if state.session_pnl < (state.tier.stop_loss * 0.5):
                state.shoe1_tripwire_triggered = True
