from nicegui import ui
import plotly.graph_objects as go
import random
import asyncio
import traceback
import numpy as np
from engine.strategy_rules import SessionState, BaccaratStrategist, PlayMode, StrategyOverrides
from engine.tier_params import TIER_MAP, TierConfig, generate_tier_map, get_tier_for_ga

# SBM LOYALTY TIERS
SBM_TIERS = {
    'Silver': 5000,
    'Gold': 22500,
    'Platinum': 175000
}

class SimulationWorker:
    """Runs the strategy logic."""
    @staticmethod
    def run_session(current_ga: float, overrides: StrategyOverrides, tier_map: dict, use_ratchet: bool = False):
        tier = get_tier_for_ga(current_ga, tier_map)
        
        session_overrides = overrides
        trigger_profit_amount = 0
        ratchet_triggered = False
        
        if use_ratchet:
            trigger_profit_amount = overrides.profit_lock_units * tier.base_unit
            session_overrides = StrategyOverrides(
                iron_gate_limit=overrides.iron_gate_limit,
                stop_loss_units=overrides.stop_loss_units,
                profit_lock_units=1000, 
                press_trigger_wins=overrides.press_trigger_wins,
                press_limit_capped=overrides.press_limit_capped
            )
        
        state = SessionState(tier=tier, overrides=session_overrides)
        state.current_shoe = 1
        volume = 0 
        
        while state.current_shoe <= 3 and state.mode != PlayMode.STOPPED:
            decision = BaccaratStrategist.get_next_decision(state, ytd_pnl=0.0)
            
            if decision['mode'] == PlayMode.STOPPED:
                break
            
            bet = decision['bet_amount']
            volume += bet
            
            if use_ratchet:
                if not ratchet_triggered and state.session_pnl >= trigger_profit_amount:
                    ratchet_triggered = True
                if ratchet_triggered and state.session_pnl <= (trigger_profit_amount * 0.5):
                    break 

            rnd = random.random()
            won = False
            pnl_change = 0
            is_tie = False
            
            if rnd < 0.4586: 
                won = True
                pnl_change = bet * 0.95 
            elif rnd < (0.4586 + 0.4462): 
                won = False
                pnl_change = -bet
            else: 
                is_tie = True
                pnl_change = 0

            if not is_tie:
                BaccaratStrategist.update_state_after_hand(state, won, pnl_change)
            else:
                state.hands_played_in_shoe += 1

            if state.hands_played_in_shoe >= 80:
                state.current_shoe += 1
                state.hands_played_in_shoe = 0
                state.presses_this_shoe = 0
                if state.current_shoe == 3:
                    state.shoe3_start_pnl = state.session_pnl

        return state.session_pnl, volume

    @staticmethod
    def run_full_career(start_ga, total_months, sessions_per_year, 
                        contrib_win, contrib_loss, overrides, use_ratchet,
                        use_tax, use_holiday, safety_factor, 
                        target_points, earn_rate):
        
        tier_map = generate_tier_map(safety_factor)
        trajectory = []
        current_ga = start_ga
        sessions_played_total = 0
        last_session_won = False
        
        m_contrib = 0
        m_tax = 0
        m_play_pnl = 0
        m_holidays = 0
        m_insolvent_months = 0 
        m_total_volume = 0 
        
        gold_hit_year = -1
        current_year_points = 0
        
        for m in range(total_months):
            if m > 0 and m % 12 == 0:
                current_year_points = 0

            if use_tax and current_ga > 12500:
                surplus = current_ga - 12500
                tax = surplus * 0.25
                current_ga -= tax
                m_tax += tax

            should_contribute = True
            if use_holiday and current_ga >= 10000:
                should_contribute = False
            
            if should_contribute:
                amount = contrib_win if last_session_won else contrib_loss
                current_ga += amount
                m_contrib += amount
            else:
                m_holidays += 1
            
            can_play = (current_ga >= 1500)
            if not can_play:
                m_insolvent_months += 1
            
            expected_sessions = int((m + 1) * (sessions_per_year / 12))
            sessions_due = expected_sessions - sessions_played_total
            
            if can_play and sessions_due > 0:
                for _ in range(sessions_due):
                    pnl, vol = SimulationWorker.run_session(current_ga, overrides, tier_map, use_ratchet)
                    current_ga += pnl
                    m_play_pnl += pnl
                    sessions_played_total += 1
                    m_total_volume += vol
                    last_session_won = (pnl > 0)
                    
                    points = vol * (earn_rate / 100)
                    current_year_points += points
            
            if gold_hit_year == -1 and current_year_points >= target_points:
                gold_hit_
