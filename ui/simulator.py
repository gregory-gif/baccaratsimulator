from nicegui import ui
import plotly.graph_objects as go
import random
import asyncio
import traceback
from engine.strategy_rules import SessionState, BaccaratStrategist, PlayMode
from engine.tier_params import TIER_MAP, TierConfig, get_tier_for_ga

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
            is_tie = False
            
            # PROBABILITY MATRIX (Standard Punto Banco)
            if rnd < 0.4586: # Banker Win
                won = True
                pnl_change = decision['bet_amount'] * 0.95 # Commission
            elif rnd < (0.4586 + 0.4462): # Player Win
                won = False
                pnl_change = -decision['bet_amount']
            else: 
                is_tie = True
                pnl_change = 0

            # Update Engine
            if not is_tie:
                BaccaratStrategist.update_state_after_hand(state, won, pnl_change)
                history.append(state.session_pnl)
            else:
                state.hands_played_in_shoe += 1

            # Advance shoe logic
            if state.hands_played_in_shoe >= 80:
                state.current_shoe += 1
                state.hands_played_in_shoe = 0
                state.presses_this_shoe = 0
                if state.current_shoe == 3:
                    state.shoe3_start_pnl = state.session_pnl

        return state.session_pnl, history

    @staticmethod
    def run_batch_independent(tier: TierConfig, count: int):
        """Runs sessions that RESET every time (Stress Test)."""
        results = []
        for _ in range(count):
            pnl, _ = SimulationWorker.run_session(tier)
            results.append(pnl)
        return results

    @staticmethod
    def run_career_step(current_ga: float):
        """Runs ONE session based on current wealth (Career Mode)."""
        # 1. Determine Tier based on current Bankroll
        tier = get_tier_for_ga(current_ga)
        
        # 2. Run Session
        pnl, _ = SimulationWorker.run_session(tier)
        
        # 3. Return result
        return pnl

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
            
            if not slider_sessions.value:
                raise ValueError("Invalid settings")

            n_sessions = int(slider_sessions.value)
            is_career = switch_career.value
            
            # Initial Bankroll Setup
            tier_level = int(select_tier.value)
            # If independent, we use the selected Tier.
            # If Career, we start at the Min GA of that Tier.
            start_tier = TIER_MAP[tier_level]
            current_career_ga = start_tier.min_ga 
            if current_career_ga < 1700: current_career_ga = 1700 # Default floor
            
            # Execution Loop
            chunk_size = 50 
            
            for i in range(0, n_sessions, chunk_size):
                remaining = n_sessions - len(results)
                current_batch_size = min(chunk_size, remaining)
                if current_batch_size <= 0: break

                if is_career:
                    # CAREER MODE: Must run sequentially
                    # We run this chunk in a thread, but the chunk itself is a loop
                    def run_career_chunk(start_ga, count):
                        chunk_pnls = []
                        local_ga = start_ga
                        for _ in range(count):
                            if local_ga < 1000: # Insolvency Check
                                break 
                            pnl = SimulationWorker.run_career_step(local_ga)
                            local_ga += pnl
                            chunk_pnls.append(pnl)
                        return chunk_pnls, local_ga

                    # Await the thread
                    batch_results, new_ga = await asyncio.to_thread(run_career_chunk, current_career_ga, current_batch_size)
                    current_career_ga = new_ga
                    results.extend(batch_results)
                    
                    # If we went bust, stop early
                    if current_career_ga < 1000:
                        ui.notify(f"BANKRUPT! Career ended at session {len(results)}", type='negative')
                        break
                        
                else:
                    # INDEPENDENT MODE: Run parallel logic
                    batch_results = await asyncio.to_thread(SimulationWorker.run_batch_independent, start_tier, current_batch_size)
                    results.extend(batch_results)

                # Update UI
                current_pct = len(results) / n_sessions
                progress.set_value(current_pct)
                label_stats.set_text(f"Simulating... {len(results)}/{n_sessions}")

            # Finalize
            label_stats.set_text("Rendering Charts...")
            render_results(results, start_tier, is_career)
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

    def render_results(data, tier, is_career):
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
                    label = 'CAREER TOTAL' if is_career else 'TOTAL PnL'
                    ui.label(label).classes('text-xs text-slate-500')
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
            title = 'Career PnL Trajectory' if is_career else 'Session PnL Distribution'
            
            if is_career:
                # For Career, we plot the Equity Curve (Cumulative PnL)
                cumulative = []
                curr = 0
                for val in data:
                    curr += val
                    cumulative.append(curr)
                    
                fig = go.Figure(data=[go.Scatter(y=cumulative, mode='lines', line=dict(color='#00ff88', width=2))])
                fig.update_layout(xaxis=dict(title='Sessions Played'), yaxis=dict(title='Total Bankroll Growth (€)'))
            else:
                # For Independent, we plot the Histogram
                fig = go.Figure(data=[go.Histogram(x=data, nbinsx=30, marker_color='#00ff88')])
                fig.update_layout(xaxis=dict(title='Profit/Loss (€)'), yaxis=dict(title='Count'))
                fig.add_vline(x=tier.stop_loss, line_dash="dash", line_color="red", annotation_text="Stop")
                fig.add_vline(x=tier.profit_lock, line_dash="dash", line_color="green", annotation_text="Target")

            fig.update_layout(
                title=title,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94a3b8'),
                margin=dict(l=20, r=20, t=40, b=20),
                xaxis=dict(gridcolor='#334155'),
                yaxis=dict(gridcolor='#334155')
            )
            ui.plotly(fig).classes('w-full h-80')

    # --- LAYOUT ---
    with ui.column().classes('w-full max-w-4xl mx-auto gap-6 p-4'):
        ui.label('MONTE CARLO LAB').classes('text-2xl font-light text-slate-300')
        
        with ui.card().classes('w-full bg-slate-900 p-4'):
            # Top Row: Controls
            with ui.row().classes('w-full items-center gap-4'):
                slider_sessions = ui.slider(min=10, max=1000, value=100).props('label-always color=blue').classes('flex-grow')
                select_tier = ui.select({1: 'Tier 1', 2: 'Tier 2', 3: 'Tier 3', 4: 'Tier 4', 5: 'Tier 5'}, value=1).classes('w-32')
            
            # Second Row: Mode Switch & Button
            with ui.row().classes('w-full items-center justify-between mt-4'):
                switch_career = ui.switch('CAREER MODE (Compounding)').props('color=purple')
                btn_sim = ui.button('RUN SIMULATION', on_click=run_sim).props('icon=play_arrow color=green')
            
            label_stats = ui.label('Ready to test strategy...').classes('text-sm text-slate-500 mt-2')
            progress = ui.linear_progress().props('color=blue').classes('mt-2')
            progress.set_visibility(False)

        stats_container = ui.column().classes('w-full')
        chart_container = ui.card().classes('w-full bg-slate-900 p-4')
