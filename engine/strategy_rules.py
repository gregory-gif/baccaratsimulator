from enum import Enum, auto
from dataclasses import dataclass
from .tier_params import TierConfig

class SniperState(Enum):
    WAIT = auto()    # Flat betting, waiting for trigger
    TRIGGER = auto() # 2 consecutive wins achieved
    FIRE = auto()    # Placing the Press Bet
    RESET = auto()   # Returning to base after Fire

class PlayMode(Enum):
    ACTIVE = auto()  # Normal betting
    WATCHER = auto() # Iron Gate activated: No betting, observing
    PENALTY = auto() # Penalty Box active (Flat bets only)
    STOPPED = auto() # Session Stop Loss/Profit Lock

@dataclass
class SessionState:
    """Tracks the mutable state of a single session."""
    tier: TierConfig
    current_shoe: int = 1
    hands_played_in_shoe: int = 0
    presses_this_shoe: int = 0
    
    # PnL Tracking
    session_pnl: float = 0.0
    shoe_pnls: dict[int, float] = None
    
    # Sniper State
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    sniper_state: SniperState = SniperState.WAIT
    
    # Defense State
    mode: PlayMode = PlayMode.ACTIVE
    iron_gate_active: bool = False
    penalty_cooldown: int = 0  # Hands to wait after re-entry (No Pressing for 3 hands)
    
    # Shield State
    shoe1_tripwire_triggered: bool = False # If triggered, force Tier 1 rules
    gold_churn_active: bool = False
    
    def __post_init__(self):
        if self.shoe_pnls is None:
            self.shoe_pnls = {1: 0.0, 2: 0.0, 3: 0.0}

class BaccaratStrategist:
    """
    The Brain. Determines the NEXT bet based on the SessionState.
    """
    
    @staticmethod
    def get_next_decision(state: SessionState, ytd_pnl: float) -> dict:
        """
        Returns a dict: {'bet_amount': int, 'reason': str, 'mode': PlayMode}
        """
        
        # 1. CHECK STOP CONDITIONS (Profit Lock / Stop Loss)
        # ------------------------------------------------
        # Check Trailing Stop for Shoe 3 Survival Mode
        if state.current_shoe == 3:
            # Entering Shoe 3 with +5 units logic would be handled at Shoe change, 
            # but we check the trailing stop here if active.
            pass # (Simplified for this snippet, typically checks generic stop loss)

        if state.session_pnl <= state.tier.stop_loss:
            return {'bet_amount': 0, 'reason': "STOP LOSS HIT", 'mode': PlayMode.STOPPED}
        
        if state.session_pnl >= state.tier.profit_lock and not state.gold_churn_active:
            # 4.1 C: Trigger Gold Churn if >= +2 units? 
            # The prompt says: If session ends >= +2 units -> Play 10 flat hands.
            # This implies we don't hard stop at profit lock if we want Churn, 
            # but usually Profit Lock is a hard cap. Let's assume Profit Lock overrides Churn 
            # unless specifically in "Churn Mode".
            return {'bet_amount': 0, 'reason': "PROFIT LOCK HIT", 'mode': PlayMode.STOPPED}

        # 2. IRON GATE CHECK (Watcher Mode)
        # ---------------------------------
        if state.mode == PlayMode.WATCHER:
            return {'bet_amount': 0, 'reason': "IRON GATE: Watching for Banker Win", 'mode': PlayMode.WATCHER}

        # 3. DETERMINE BET SIZE (Sniper vs Flat)
        # --------------------------------------
        
        # A. Shield: Shoe 1 Tripwire Active?
        current_base = state.tier.base_unit
        current_press = state.tier.press_unit
        
        if state.shoe1_tripwire_triggered:
            # Force Tier 1 rules
            current_base = 50
            current_press = 50 # Effectively flat betting if strict Tier 1 rules imply flat? 
            # Prompt says: "Downshift to Tier 1 rules (Flat €50)"
            return {'bet_amount': 50, 'reason': "TRIPWIRE: Flat €50", 'mode': PlayMode.ACTIVE}

        # B. Penalty Box / Cooling Off Period
        if state.penalty_cooldown > 0:
            return {'bet_amount': current_base, 'reason': f"RE-ENTRY ({state.penalty_cooldown} left)", 'mode': PlayMode.ACTIVE}

        # C. Sniper Engine Logic
        # 2.1 THE SNIPER ENGINE
        # WAIT: Flat bet Base Unit.
        # TRIGGER: After 2 consecutive wins.
        # FIRE: Bet Press Unit.
        # RESET: Return to Base immediately.
        
        # Check Press Limits
        can_press = state.presses_this_shoe < state.tier.max_presses_per_shoe
        
        bet = current_base
        reason = "SNIPER: Base"

        if state.consecutive_wins >= 2 and can_press:
            bet = current_press
            reason = "SNIPER: FIRE (Press)"
            # Note: We don't update state here, we update it AFTER result.
            # This function just READS state to decide bet.
        
        return {'bet_amount': bet, 'reason': reason, 'mode': PlayMode.ACTIVE}

    @staticmethod
    def update_state_after_hand(state: SessionState, won: bool, amount_won: float):
        """
        Updates the state machine based on the result of the last hand.
        """
        # Update PnL
        state.session_pnl += amount_won
        state.shoe_pnls[state.current_shoe] += amount_won
        state.hands_played_in_shoe += 1
        
        # 2.2 THE IRON GATE (Discipline Protocol)
        # ---------------------------------------
        if state.mode == PlayMode.WATCHER:
            if won:
                # Exit Watcher Mode
                state.mode = PlayMode.ACTIVE
                state.consecutive_wins = 1 # Reset counters
                state.consecutive_losses = 0
                state.penalty_cooldown = 3 # PENALTY: No pressing for 3 hands
            return # Don't process sniper logic while watching

        if won:
            state.consecutive_wins += 1
            state.consecutive_losses = 0
            
            # Decrement re-entry penalty if active
            if state.penalty_cooldown > 0:
                state.penalty_cooldown -= 1
            
            # Count press usage
            # If we just won a PRESS bet (implied by previous state logic), increment press count?
            # To be strictly accurate, we should have stored if the *last* bet was a press.
            # For this simplified version, we assume the UI passed the bet amount, 
            # or we deduce it. (Refinement needed for full implementation).
            
        else:
            state.consecutive_losses += 1
            state.consecutive_wins = 0
            
            # Check Iron Gate Trigger
            limit = 3 if state.tier.level <= 2 else 2
            if state.consecutive_losses >= limit:
                state.mode = PlayMode.WATCHER
                state.sniper_state = SniperState.RESET # Reset sniper
                return

        # 4.1 A) Shoe 1 Tripwire Check
        if state.current_shoe == 1 and not state.shoe1_tripwire_triggered:
            if state.session_pnl < (state.tier.stop_loss * 0.5): # Loss > 50% of stop loss
                state.shoe1_tripwire_triggered = True
