from nicegui import ui
from engine.strategy_rules import SessionState, BaccaratStrategist, PlayMode, SniperState
from engine.tier_params import TIER_MAP

class Scorecard:
    def __init__(self, tier_level=1):
        # Initialize session with the requested Tier (Default Tier 1)
        self.state = SessionState(tier=TIER_MAP[tier_level])
        self.current_decision = {'bet_amount': self.state.tier.base_unit, 'reason': "New Shoe", 'mode': PlayMode.ACTIVE}
        
        # UI Elements (Refs for updating)
        self.hud_bet_label = None
        self.hud_reason_label = None
        self.hud_mode_badge = None
        self.pnl_label = None
        self.shoe_progress = None
        
        self.build_ui()
        self.refresh_hud()

    def process_result(self, won: bool):
        """
        1. Calculate amount won/lost based on the DECISION we just played.
        2. Update the Engine State.
        3. Get the NEXT decision.
        4. Refresh UI.
        """
        # Calculate PnL for the hand just played
        bet_amt = self.current_decision['bet_amount']
        
        # Banker Win = +0.95 * Bet (Standard Commission) or +1.0 for calculation simplicity? 
        # Master prompt implies "Punto Banco", usually 0.95 on Banker. 
        # For simplicity in "Units", we often track gross wins, but let's be precise:
        # If we bet 100 on Banker and Win: +95 (or +100 if No Commission variant).
        # Let's assume standard 1:1 payout for Unit tracking simplicity unless specified.
        # *Correction*: Master Prompt uses "Units" (Base/Press). Let's stick to raw amounts.
        
        if won:
            pnl_change = bet_amt # Treating as 1:1 for clean unit tracking
        else:
            pnl_change = -bet_amt

        # Update Engine
        BaccaratStrategist.update_state_after_hand(self.state, won, pnl_change)
        
        # Get Next Prediction
        # (Pass 0.0 for YTD PnL for now, we will link that later)
        self.current_decision = BaccaratStrategist.get_next_decision(self.state, ytd_pnl=0.0)
        
        # Refresh Screen
        self.refresh_hud()

    def refresh_hud(self):
        """Updates all visual elements based on new state."""
        # 1. Update Decision HUD
        decision = self.current_decision
        self.hud_bet_label.set_text(f"€{decision['bet_amount']}")
        self.hud_reason_label.set_text(decision['reason'])
        
        # 2. Update Mode Badge
        mode = self.state.mode
        if mode == PlayMode.WATCHER:
            self.hud_mode_badge.props('color=red icon=visibility label="IRON GATE: WATCHING"')
        elif mode == PlayMode.STOPPED:
            self.hud_mode_badge.props('color=grey icon=stop label="SESSION ENDED"')
        elif decision['bet_amount'] > self.state.tier.base_unit:
            self.hud_mode_badge.props('color=orange icon=local_fire_department label="SNIPER: FIRE"')
        else:
            self.hud_mode_badge.props('color=green icon=verified_user label="SNIPER: ACTIVE"')

        # 3. Update Stats
        pnl = self.state.session_pnl
        color = "text-green-400" if pnl >= 0 else "text-red-400"
        self.pnl_label.set_text(f"€{pnl:+}")
        self.pnl_label.classes(replace=color)
        
        self.shoe_progress.set_value(self.state.hands_played_in_shoe / 80.0) # Approx 80 hands/shoe

    def build_ui(self):
        with ui.column().classes('w-full max-w-2xl mx-auto gap-6'):
            
            # --- UPPER HUD: The "Call to Action" ---
            with ui.card().classes('w-full bg-slate-900 border border-slate-700 p-6 items-center text-center relative'):
                ui.label('NEXT BET').classes('text-slate-500 text-xs font-bold tracking-widest mb-1')
                
                # The Big Number
                self.hud_bet_label = ui.label('€50').classes('text-6xl font-black text-white mb-2')
                
                # The Reasoning
                self.hud_reason_label = ui.label('Waiting for Trigger').classes('text-slate-400 italic text-sm mb-4')
                
                # The Status Badge
                self.hud_mode_badge = ui.chip('ACTIVE', icon='verified_user').props('color=green text-color=white')

            # --- CONTROLS: The "Stick" ---
            with ui.row().classes('w-full gap-4'):
                # WIN BUTTON
                with ui.button(on_click=lambda: self.process_result(True)).classes('flex-1 h-24 text-2xl font-bold bg-green-600 hover:bg-green-500 shadow-lg'):
                    with ui.column().classes('items-center'):
                        ui.label('WIN').classes('leading-none')
                        ui.label('Banker').classes('text-xs font-normal opacity-80')

                # LOSS BUTTON
                with ui.button(on_click=lambda: self.process_result(False)).classes('flex-1 h-24 text-2xl font-bold bg-red-600 hover:bg-red-500 shadow-lg'):
                    with ui.column().classes('items-center'):
                        ui.label('LOSS').classes('leading-none')
                        ui.label('Player/Tie').classes('text-xs font-normal opacity-80')

            # --- STATS ROW ---
            with ui.grid(columns=3).classes('w-full gap-4'):
                # Shoe Tracker
                with ui.card().classes('bg-slate-800 p-3 items-center'):
                    ui.label('SHOE').classes('text-xs text-slate-500')
                    ui.label('1 / 3').classes('text-xl font-bold text-white') # Dynamic later
                
                # PnL Tracker
                with ui.card().classes('bg-slate-800 p-3 items-center'):
                    ui.label('SESSION PnL').classes('text-xs text-slate-500')
                    self.pnl_label = ui.label('€0').classes('text-xl font-bold text-white')

                # Hand Tracker
                with ui.card().classes('bg-slate-800 p-3 items-center w-full'):
                    ui.label('HANDS').classes('text-xs text-slate-500')
                    self.shoe_progress = ui.linear_progress(value=0, show_value=False).props('color=blue track-color=grey-8').classes('w-full mt-2')

            # --- RESET / ADMIN ---
            with ui.expansion('Session Tools', icon='settings').classes('w-full bg-slate-800 text-slate-300'):
                with ui.row().classes('p-4'):
                    ui.button('Reset Shoe', color='warning', outline=True, icon='restart_alt')
                    ui.button('End Session', color='red', outline=True, icon='logout')

def show_scorecard():
    # Helper to clear content and show this view
    # In a full app, we'd use a router, but for now we clear the main container
    # This requires 'layout.content_container' to be accessible or passed.
    # For simplicity in this step, we just instantiate it.
    Scorecard()
