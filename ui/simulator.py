from nicegui import ui
import plotly.graph_objects as go
import random
import asyncio
import traceback
from engine.strategy_rules import SessionState, BaccaratStrategist, PlayMode
from engine.tier_params import TIER_MAP, TierConfig

class SimulationWorker:
    """Runs the strategy logic."""
    @staticmethod
    def run_session(tier: TierConfig, shoes_to_play=3):
        state = SessionState(tier=tier)
        state.current_shoe = 1
        history = [] 
        
        while state.current_shoe <= shoes_to_play and state.mode != PlayMode.STOPPED:
            decision = BaccaratStrategist.get_next_decision(state, ytd_pnl=0.0)
            
            if decision['mode'] == PlayMode.STOPPED:
                break
                
            # Simulate Hand
            rnd = random.random()
            won = False
            pnl_change = 0
            
            # Bankers: 0.4586, Player: 0.4462, Tie: 0.0952
            if rnd < 0.4586: 
                won = True
                pnl_change = decision['bet_amount'] 
            elif rnd < (0.4586 + 0.4462): 
                won = False
                pnl_change = -decision['bet_amount']
            else: 
                # Tie - no change
                pnl_change = 0
                continue 

            if pnl_change != 0:
                BaccaratStrategist.update_state_after_hand(state, won, pnl_change)
                history.append(state.session_pnl)
                
            # Advance shoe logic (approx 80 hands)
            if state.hands_played_in_shoe >= 80:
                state.current_shoe += 1
                state.hands_played_in_shoe = 0
                state.presses_this_shoe = 0
                if state.current_shoe == 3:
                    state.shoe3_start_pnl = state.session_pnl

        return state.session_pnl, history

def show_simulator():
    # UI STATE
    results = []
    running = False
    
    async def run_sim():
        nonlocal running, results
        if running: return
        
        try:
            running = True
            btn_sim.disable()
            results = []
            
            # Reset UI
            progress.set_value(0)
            progress.set_visibility(True)
            label_stats.set_text("Initializing...")
            
            if not slider_sessions.value or not select_tier.value:
                raise ValueError("Invalid settings")

            n_sessions = int(slider_sessions.value)
            tier_level = int(select_tier.value)
            tier = TIER_MAP[tier_level]
            
            # Execution Strategy: Micro-Batches
            # We run small batches in the main thread, then YIELD to allow UI updates.
            # This is slower but much more stable on free cloud servers.
            batch_size = 5 
            
            for i in range(0, n_sessions, batch_size):
                # 1. Run a small batch of sessions
                # We calculate how many to run in this loop (usually 5, or less at the end)
                current_batch_count = min(batch_size, n_sessions - len(results))
                if current_batch_count <= 0: break
                
                for _ in range(current_batch_count):
                    pnl, _ = SimulationWorker.run_session(tier)
                    results.append(pnl)

                # 2. Force UI Update
                # We pause for 0.01 seconds. This lets the server send the
                # "Progress Bar: 10%" message to your browser.
                current_pct = len(results) / n_sessions
                progress.set_value(current_pct)
                label_stats.set_text(f"Simulating... {len(results)}/{n_sessions}")
                
                await asyncio.sleep(0.01) 
                
            # Finalize
            label_stats.set_text("Rendering Charts...")
            render_results(results, tier)
            label_stats.set_text("Simulation Complete")

        except Exception as e:
            error_msg = str(e)
            print(traceback.format_exc())
            ui.notify(f"Error: {error_msg}", type='negative', close_button=True)
            label_stats.set_text(f"Failed: {error_msg}")
            
        finally:
            running = False
            btn_sim.enable()
            progress.set_visibility(False)

    def render_results(data, tier):
        if not data: return
        
        # Calculate Stats
        total_pnl = sum(data)
        avg_pnl = total_pnl / len(data)
        wins = len([x for x in data if x > 0])
        win_rate = wins / len(data) * 100
        
        # Update Stats Cards
        stats_container.clear()
        with stats_container:
            with ui.grid(columns=3).classes('w-full gap-4'):
                with ui.card().classes('bg-slate-900 border-l-4 border-blue-500 p-4'):
                    ui.label('TOTAL PnL').classes('text-xs text-slate-500')
                    ui.label(f"€{total_pnl:,.0f}").classes('text-2xl font-bold text-white')
                
                with ui.card().classes('bg-slate-900 border-l-4 border-purple-500 p-4'):
                    ui.label('AVG SESSION').classes('text-xs text-slate-500')
                    color = 'text-green-400' if avg_pnl > 0 else 'text-red-400'
                    ui.label(f"€{avg_pnl:,.0f}").classes(f'text-2xl font-bold {color}')

                with ui.card().classes('bg-slate-900 border-l-4 border-yellow-500 p-4'):
                    ui.label('WIN RATE').classes('text-xs text-slate-500')
                    ui.label(f"{win_rate:.1f}%").classes('text-2xl font-bold text-yellow-400')

        # Update Chart
        chart_container.clear()
        with chart_container:
            fig = go.Figure(data=[go.Histogram(x=data, nbinsx=30, marker_color='#00ff88')])
            fig.update_layout(
                title='Session PnL Distribution',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94a3b8'),
                xaxis=dict(title='Profit/Loss (€)', gridcolor='#334155'),
                yaxis=dict(title='Count', gridcolor='#334155'),
                margin=dict(l=20, r=20, t=40, b=20)
            )
            fig.add_vline(x=tier.stop_loss, line_dash="dash", line_color="red", annotation_text="Stop Loss")
            fig.add_vline(x=tier.profit_lock, line_dash="dash", line_color="green", annotation_text="Target")
            ui.plotly(fig).classes('w-full h-80')

    # --- LAYOUT ---
    with ui.column().classes('w-full max-w-4xl mx-auto gap-6 p-4'):
        ui.label('MONTE CARLO LAB').classes('text-2xl font-light text-slate-300')
        
        with ui.card().classes('w-full bg-slate-900 p-4'):
            with ui.row().classes('w-full items-center gap-4'):
                slider_sessions = ui.slider(min=10, max=1000, value=100).props('label-always color=blue').classes('flex-grow')
                select_tier = ui.select({1: 'Tier 1', 2: 'Tier 2', 3: 'Tier 3', 4: 'Tier 4', 5: 'Tier 5'}, value=1).classes('w-32')
                btn_sim = ui.button('RUN SIMULATION', on_click=run_sim).props('icon=play_arrow color=green')
            
            label_stats = ui.label('Ready to test strategy...').classes('text-sm text-slate-500 mt-2')
            
            # The progress bar is defined here, but visibility is toggled by the button
            progress = ui.linear_progress().props('color=blue').classes('mt-2')
            progress.set_visibility(False)

        stats_container = ui.column().classes('w-full')
        chart_container = ui.card().classes('w-full bg-slate-900 p-4')
