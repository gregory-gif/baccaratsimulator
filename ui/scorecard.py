from nicegui import ui
from engine.strategy_rules import SessionState, BaccaratStrategist, PlayMode
from engine.tier_params import TIER_MAP

class Scorecard:
    def __init__(self, tier_level=1):
        # Initialize session with the requested Tier
        self.state = SessionState(tier=TIER_MAP[tier_level])
        self.current_decision = {'bet_amount': self.state.tier.base_unit, 'reason': "New Shoe", 'mode': PlayMode.ACTIVE}
        
        # UI Elements
        self.hud_bet_label = None
        self.hud_reason_label = None
        self.hud_mode_badge = None
        self.pnl_label = None
        self.shoe_progress = None
        self.shoe_label = None
        self.next_shoe_btn = None
        
        self.build_ui()
        self.refresh_hud()

    def process_result(self, won: bool):
        # Prevent betting if session is stopped
        if self.state.mode == PlayMode.STOPPED:
            ui.notify('Session Ended. Please reset.', type='warning')
            return

        bet_amt = self.current_decision['bet_amount']
        pnl_change = bet_amt if won else -bet_amt

        # Update Engine
        BaccaratStrategist.update_state_after_hand(self.state, won, pnl_change)
        
        # Get Next Prediction
        self.current_decision = BaccaratStrategist.get_next_decision(self.state, ytd_pnl=0.0)
        
        # Refresh Screen
        self.refresh_hud()

    def advance_shoe(self):
        """Moves from Shoe 1 -> 2 -> 3 -> End."""
        if self.state.current_shoe >= 3:
            ui.notify('Session Complete (3 Shoes Played)', type='positive')
            self.state.mode = PlayMode.STOPPED
            self.refresh_hud()
            return

        # Advance Shoe
        self.state.current_shoe += 1
        
        # Reset Shoe-Specific Counters
        self.state.hands_played_in_shoe = 0
        self.state.presses_this_shoe = 0
        self.state.consecutive_wins = 0
        self.state.consecutive_losses = 0
        self.state.penalty_cooldown = 0
        
        # Capture Snapshot for Shoe 3 Survival Logic
        if self.state.current_shoe == 3:
            self.state.shoe3_start_pnl = self.state.session_pnl
            ui.notify('Entering Shoe 3: Survival Rules Active', type='info')

        # Reset UI for new shoe
        self.current_decision = BaccaratStrategist.get_next_decision(self.state, ytd_pnl=0.0)
        self.refresh_hud()
        ui.notify(f'Started Shoe {self.state.current_shoe}', type='positive')

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
        color = "text-green-400" if pnl >= 0 else "text-red-400"
        self.pnl_label.set_text(f"€{pnl:+}")
        self.pnl_label.classes(replace=color)
        
        self.shoe_progress.set_value(self.state.hands_played_in_shoe / 80.0)
        self.shoe_label.set_text(f"{self.state.current_shoe} / 3")
        
        # Update Next Shoe Button State
        if self.state.current_shoe < 3 and mode != PlayMode.STOPPED:
             self.next_shoe_btn.enable()
             self.next_shoe_btn.set_text('Next Shoe')
        elif self.state.current_shoe == 3:
             self.next_shoe_btn.set_text('Finish Session')
        
        if mode == PlayMode.STOPPED:
             self.next_shoe_btn.disable()

    def build_ui(self):
        with ui.column().classes('w-full max-w-2xl mx-auto gap-6'):
            
            # --- UPPER HUD ---
            with ui.card().classes('w-full bg-slate-900 border border-slate-700 p-6 items-center text-center relative'):
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

                with ui.card().classes('bg-slate-800 p-3 items-center w-full'):
                    ui.label('HANDS').classes('text-xs text-slate-500')
                    self.shoe_progress = ui.linear_progress(value=0, show_value=False).props('color=blue track-color=grey-8').classes('w-full mt-2')

            # --- SESSION TOOLS ---
            with ui.expansion('Session Tools', icon='settings').classes('w-full bg-slate-800 text-slate-300'):
                with ui.row().classes('p-4 w-full justify-between'):
                    # The Reset Button now acts as Next Shoe
                    self.next_shoe_btn = ui.button('Next Shoe', on_click=self.advance_shoe, color='blue', icon='skip_next').props('outline')
                    ui.button('End Session', color='red', icon='logout').props('outline')
