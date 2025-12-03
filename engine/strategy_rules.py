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
    STOPPED = auto() # Session Stop Loss/Profit Lock hit

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
    penalty_cooldown: int = 0  # Hands to wait after re-entry
    
    # Shield State
    shoe1_tripwire_triggered: bool = False # If triggered, force Tier 1 rules
    gold_churn_active: bool = False
    shoe3_start_pnl: float = 0.0 # Snapshot of PnL at start of Shoe 3
    
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
        if state.mode == PlayMode.STOPPED:
             return {'bet_amount': 0, 'reason': "SESSION STOPPED", 'mode': PlayMode.STOPPED}

        # A. Stop Loss (Hard Floor)
        if state.session_pnl <= state.tier.stop_loss:
            return {'bet_amount': 0, 'reason': "STOP LOSS HIT", 'mode': PlayMode.STOPPED}
        
        # B. Shoe 3 Survival Mode (Trailing Stop)
        if state.current_shoe == 3:
            # 5 Units calculation:
            five_units = state.tier.base_unit * 5
            
            # If we started Shoe 3 with a lead, we protect it.
            if state.shoe3_start_pnl >= five_units:
                # Trailing Stop: If we drop to +1 unit (Base Unit)
                if state.session_pnl <= state.tier.base_unit:
                     return {'bet_amount': 0, 'reason': "SHOE 3 TRAILING STOP HIT (+1 Unit)", 'mode': PlayMode.STOPPED}

        # C. Profit Lock / Gold Churn
        if state.session_pnl >= state.tier.profit_lock:
             return {'bet_amount': 0, 'reason': "PROFIT LOCK SECURED", 'mode': PlayMode.STOPPED}

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
            # Force Tier 1 rules (Flat 50)
            return {'bet_amount': 50, 'reason': "TRIPWIRE: Flat €50", 'mode': PlayMode.ACTIVE}

        # B. Shoe 3 Survival Mode (Flat Betting Only)
        if state.current_shoe == 3:
            five_units = state.tier.base_unit * 5
            if state.shoe3_start_pnl >= five_units:
                 # "Flat bets only"
                 return {'bet_amount': current_base, 'reason': "SHOE 3 SURVIVAL: Flat Bet", 'mode': PlayMode.ACTIVE}

        # C. Penalty Box / Cooling Off Period
        if state.penalty_cooldown > 0:
            return {'bet_amount': current_base, 'reason': f"RE-ENTRY ({state.penalty_cooldown} left)", 'mode': PlayMode.ACTIVE}

        # D. Sniper Engine Logic
        # WAIT -> TRIGGER -> FIRE -> RESET
        
        # Check Press Limits
        can_press = state.presses_this_shoe < state.tier.max_presses_per_shoe
        
        bet = current_base
        reason = "SNIPER: Base"

        # Logic: If 2 wins, NEXT bet is Press.
        if state.consecutive_wins >= 2 and can_press:
            bet = current_press
            reason = "SNIPER: FIRE (Press)"
        
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
                state.consecutive_wins = 0 
                state.consecutive_losses = 0
                state.penalty_cooldown = 3 # PENALTY: No pressing for 3 hands
            return 

        if won:
            state.consecutive_wins += 1
            state.consecutive_losses = 0
            
            # Decrement re-entry penalty if active
            if state.penalty_cooldown > 0:
                state.penalty_cooldown -= 1
            
            # Track Presses (heuristic: if amount won > base unit, it was a press)
            if amount_won > state.tier.base_unit:
                state.presses_this_shoe += 1
            
        else:
            state.consecutive_losses += 1
            state.consecutive_wins = 0
            
            # Check Iron Gate Trigger
            limit = 3 if state.tier.level <= 2 else 2
            if state.consecutive_losses >= limit:
                state.mode = PlayMode.WATCHER
                state.sniper_state = SniperState.RESET
                return

        # 4.1 A) Shoe 1 Tripwire Check
        if state.current_shoe == 1 and not state.shoe1_tripwire_triggered:
            if state.session_pnl < (state.tier.stop_loss * 0.5):
                state.shoe1_tripwire_triggered = True
