from nicegui import ui
from engine.strategy_rules import SessionState, BaccaratStrategist, PlayMode
from engine.tier_params import get_tier_for_ga
from utils.persistence import load_profile, log_session_result

class Scorecard:
    def __init__(self):
        # 1. LOAD PERSISTENCE
        # -------------------
        self.profile = load_profile()
        self.start_ga = self.profile['ga']
        
        # 2. AUTO-CALCULATE TIER (Unified Ladder)
        # ---------------------------------------
        # We always play the tier matching our Total Game Account (GA)
        self.tier_config = get_tier_for_ga(self.start_ga)
        
        # Initialize Session
        self.state = SessionState(tier=self.tier_config)
        self.current_decision = BaccaratStrategist.get_next_decision(self.state, ytd_pnl=self.profile['ytd_pnl'])
        
        # UI Refs
        self.hud_bet_label = None
        self.hud_reason_label = None
        self.hud_mode_badge = None
        self.pnl_label = None
        self.ga_label = None  # New: Shows Total Bankroll
        self.shoe_progress = None
        self.shoe_label = None
        self.next_shoe_btn = None
        self.end_session_btn = None
        
        self.build_ui()
        self.refresh_hud()

    def process_result(self, won: bool):
        if self.state.mode == PlayMode.STOPPED:
            ui.notify('Session Ended. Please save and exit.', type='warning')
            return

        bet_amt = self.current_decision['bet_amount']
        pnl_change = bet_amt if won else -bet_amt

        # Update Engine
        BaccaratStrategist.update_state_after_hand(self.state, won, pnl_change)
        
        # Get Next Prediction
        self.current_decision = BaccaratStrategist.get_next_decision(self.state, ytd_pnl=self.profile['ytd_pnl'])
        
        # Refresh Screen
        self.refresh_hud()

    def advance_shoe(self):
        """Moves from Shoe 1 -> 2 -> 3 -> End."""
        if self.state.current_shoe >= 3:
            self.end_session()
            return

        # Advance Shoe
        self.state.current_shoe += 1
        
        # Reset Shoe-Specific Counters (but keep PnL)
        self.state.hands_played_in_shoe = 0
        self.state.presses_this_shoe = 0
        self.state.consecutive_wins = 0
        self.state.consecutive_losses = 0
        self.state.penalty_cooldown = 0
        
        # Capture Snapshot for Shoe 3 Survival Logic
        if self.state.current_shoe == 3:
            self.state.shoe3_start_pnl = self.state.session_pnl
            ui.notify('Entering Shoe 3: Survival Rules Active', type='info')

        # Get fresh decision for new shoe
        self.current_decision = BaccaratStrategist.get_next_decision(self.state, ytd_pnl=self.profile['ytd_pnl'])
        self.refresh_hud()
        ui.notify(f'Started Shoe {self.state.current_shoe}', type='positive')

    def end_session(self):
        """Saves data to disk and locks the UI."""
        if self.state.mode == PlayMode.STOPPED and self.end_session_btn.text == 'Saved':
            return # Already saved

        # Calculate final numbers
        final_ga = self.start_ga + self.state.session_pnl
        
        # Save to Persistence
        log_session_result(self.start_ga, final_ga, self.state.current_shoe)
        
        # Update State
        self.state.mode = PlayMode.STOPPED
        self.profile['ga'] = final_ga # Update local ref for display
        
        # Visual Confirmation
        ui.notify(f'SESSION SAVED. New GA: €{final_ga}', type='positive', close_button=True, timeout=None)
        self.end_session_btn.set_text('Saved')
        self.end_session_btn.disable()
        self.next_shoe_btn.disable()
        self.refresh_hud()

    def refresh_hud(self):
        """Updates all visual elements."""
        decision = self.current_decision
        
        # 1. Update Decision HUD
        self.hud_bet_label.set_text(f"€{decision['bet_amount']}")
        self.hud_reason_label.set_text(decision['reason'])
        
        # 2. Update Mode Badge
        mode = self.state.mode
        if mode == PlayMode.WATCHER:
            self.hud_mode_badge.props('color=red icon=visibility label="IRON GATE: WATCHING"')
        elif mode == PlayMode.STOPPED:
            self.hud_mode_badge.props('color=grey icon=stop label="SESSION ENDED"')
            self.hud_bet_label.set_text("STOP")
        elif decision['bet_amount'] > self.state.tier.base_unit:
            self.hud_mode_badge.props('color=orange icon=local_fire_department label="SNIPER: FIRE"')
        else:
            self.hud_mode_badge.props('color=green icon=verified_user label="SNIPER: ACTIVE"')

        # 3. Update Stats
        pnl = self.state.session_pnl
        current_ga = self.start_ga + pnl
        
        color = "text-green-400" if pnl >= 0 else "text-red-400"
        self.pnl_label.set_text(f"€{pnl:+}")
        self.pnl_label.classes(replace=color)
        
        self.ga_label.set_text(f"GA: €{current_ga:,.0f}")
        
        self.shoe_progress.set_value(self.state.hands_played_in_shoe / 80.0)
        self.shoe_label.set_text(f"{self.state.current_shoe} / 3")
        
        # Button States
        if self.state.current_shoe < 3 and mode != PlayMode.STOPPED:
             self.next_shoe_btn.enable()
             self.next_shoe_btn.set_text('Next Shoe')
        elif self.state.current_shoe == 3 and mode != PlayMode.STOPPED:
             self.next_shoe_btn.set_text('Finish Shoe 3')
        
        if mode == PlayMode.STOPPED:
             self.next_shoe_btn.disable()

    def build_ui(self):
        with ui.column().classes('w-full max-w-2xl mx-auto gap-6'):
            
            # --- UPPER HUD ---
            with ui.card().classes('w-full bg-slate-900 border border-slate-700 p-6 items-center text-center relative'):
                # Tier Badge
                ui.chip(f'TIER {self.tier_config.level}', icon='layers').classes('absolute top-4 right-4').props('color=slate-700')
                
                ui.label('NEXT BET').classes('text-slate-500 text-xs font-bold tracking-widest mb-1')
                self.hud_bet_label = ui.label('€50').classes('text-6xl font-black text-white mb-2')
                self.hud_reason_label = ui.label('Waiting for Trigger').classes('text-slate-400 italic text-sm mb-4')
                self.hud_mode_badge = ui.chip('ACTIVE', icon='verified_user').props('color=green text-color=white')

            # --- CONTROLS ---
            with ui.row().classes('w-full gap-4'):
                with ui.button(on_click=lambda: self.process_result(True)).classes('flex-1 h-24 text-2xl font-bold bg-green-600 hover:bg-green-500 shadow-lg'):
                    with ui.column().classes('items-center'):
                        ui.label('WIN').classes('leading-none')
                        ui.label('Banker').classes('text-xs font-normal opacity-80')

                with ui.button(on_click=lambda: self.process_result(False)).classes('flex-1 h-24 text-2xl font-bold bg-red-600 hover:bg-red-500 shadow-lg'):
                    with ui.column().classes('items-center'):
                        ui.label('LOSS').classes('leading-none')
                        ui.label('Player/Tie').classes('text-xs font-normal opacity-80')

            # --- STATS ROW ---
            with ui.grid(columns=3).classes('w-full gap-4'):
                with ui.card().classes('bg-slate-800 p-3 items-center'):
                    ui.label('SHOE').classes('text-xs text-slate-500')
                    self.shoe_label = ui.label('1 / 3').classes('text-xl font-bold text-white')
                
                with ui.card().classes('bg-slate-800 p-3 items-center'):
                    ui.label('SESSION PnL').classes('text-xs text-slate-500')
                    self.pnl_label = ui.label('€0').classes('text-xl font-bold text-white')

                with ui.card().classes('bg-slate-800 p-3 items-center'):
                    ui.label('TOTAL GA').classes('text-xs text-slate-500')
                    self.ga_label = ui.label('€1,700').classes('text-xl font-bold text-blue-400')

            with ui.card().classes('bg-slate-800 p-2 items-center w-full'):
                 self.shoe_progress = ui.linear_progress(value=0, show_value=False).props('color=blue track-color=grey-8').classes('w-full')

            # --- SESSION TOOLS ---
            with ui.expansion('Session Tools', icon='settings').classes('w-full bg-slate-800 text-slate-300'):
                with ui.row().classes('p-4 w-full justify-between'):
                    self.next_shoe_btn = ui.button('Next Shoe', on_click=self.advance_shoe, color='blue', icon='skip_next').props('outline')
                    self.end_session_btn = ui.button('End & Save', on_click=self.end_session, color='red', icon='save').props('outline')

def show_scorecard():
    # Helper to clear content and show this view
    Scorecard()
