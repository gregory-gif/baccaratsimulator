from nicegui import ui
import plotly.graph_objects as go
import random
import asyncio
import traceback
from engine.strategy_rules import SessionState, BaccaratStrategist, PlayMode, StrategyOverrides
from engine.tier_params import TIER_MAP, TierConfig, get_tier_for_ga

class SimulationWorker:
    """Runs the strategy logic."""
    @staticmethod
    def run_session(tier: TierConfig, overrides: StrategyOverrides, shoes_to_play=3):
        # Pass the overrides to the session state
        state = SessionState(tier=tier, overrides=overrides)
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
            
            if rnd < 0.4586: # Banker Win
                won = True
                pnl_change = decision['bet_amount'] * 0.95 
            elif rnd < (0.4586 + 0.4462): # Player Win
                won = False
                pnl_change = -decision['bet_amount']
            else: 
                is_tie = True
                pnl_change = 0

            if not is_tie:
                BaccaratStrategist.update_state_after_hand(state, won, pnl_change)
                history.append(state.session_pnl)
            else:
                state.hands_played_in_shoe += 1

            if state.hands_played_in_shoe >= 80:
                state.current_shoe += 1
                state.hands_played_in_shoe = 0
                state.presses_this_shoe = 0
                if state.current_shoe == 3:
                    state.shoe3_start_pnl = state.session_pnl

        return state.session_pnl, history

    @staticmethod
    def run_career_step(current_ga: float, overrides: StrategyOverrides):
        """Runs ONE session based on current wealth (Career Mode)."""
        tier = get_tier_for_ga(current_ga)
        pnl, _ = SimulationWorker.run_session(tier, overrides)
        return pnl

def show_simulator():
    results = []
    running = False
    
    async def run_sim():
        nonlocal running, results
        if running: return
        
        try:
            running = True
            btn_sim.disable()
            results = []
            
            progress.set_value(0)
            progress.set_visibility(True)
            label_stats.set_text("Initializing...")
            
            # 1. TIME SETTINGS
            years = int(slider_years.value)
            sessions_per_year = int(slider_frequency.value)
            total_sessions = years * sessions_per_year
            
            # 2. STRATEGY SETTINGS
            overrides = StrategyOverrides(
                iron_gate_limit=int(slider_iron_gate.value),
                stop_loss_units=int(slider_stop_loss.value),
                profit_lock_units=int(slider_profit.value),
                press_trigger_wins=int(select_press.value)
            )

            # 3. INITIAL STATE
            tier_level = int(select_tier.value)
            start_tier = TIER_MAP[tier_level]
            current_career_ga = start_tier.min_ga if start_tier.min_ga >= 1700 else 1700
            
            chunk_size = 50 
            
            for i in range(0, total_sessions, chunk_size):
                remaining = total_sessions - len(results)
                current_batch_size = min(chunk_size, remaining)
                if current_batch_size <= 0: break

                # Career Loop (Threaded)
                def run_career_chunk(start_ga, count, ovr):
                    chunk_pnls = []
                    local_ga = start_ga
                    for _ in range(count):
                        if local_ga < 1000: break 
                        pnl = SimulationWorker.run_career_step(local_ga, ovr)
                        local_ga += pnl
                        chunk_pnls.append(pnl)
                    return chunk_pnls, local_ga

                batch_results, new_ga = await asyncio.to_thread(run_career_chunk, current_career_ga, current_batch_size, overrides)
                current_career_ga = new_ga
                results.extend(batch_results)
                
                if current_career_ga < 1000:
                    ui.notify(f"BANKRUPT! Year {(len(results)/sessions_per_year):.1f}", type='negative')
                    break

                current_pct = len(results) / total_sessions
                progress.set_value(current_pct)
                label_stats.set_text(f"Simulating... Year {(len(results)/sessions_per_year):.1f}/{years}")

            label_stats.set_text("Rendering...")
            render_results(results, start_tier)
            label_stats.set_text(f"Simulation Complete: {len(results)} Sessions ({len(results)/sessions_per_year:.1f} Years)")

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
        total_pnl = sum(data)
        avg_pnl = total_pnl / len(data)
        wins = len([x for x in data if x > 0])
        win_rate = wins / len(data) * 100
        
        with stats_container:
            stats_container.clear()
            with ui.grid(columns=3).classes('w-full gap-4'):
                with ui.card().classes('bg-slate-900 border-l-4 border-blue-500 p-4'):
                    ui.label('CAREER PnL').classes('text-xs text-slate-500')
                    ui.label(f"€{total_pnl:,.0f}").classes('text-2xl font-bold text-white')
                
                with ui.card().classes('bg-slate-900 border-l-4 border-purple-500 p-4'):
                    ui.label('AVG SESSION').classes('text-xs text-slate-500')
                    color = 'text-green-400' if avg_pnl > 0 else 'text-red-400'
                    ui.label(f"€{avg_pnl:,.0f}").classes(f'text-2xl font-bold {color}')

                with ui.card().classes('bg-slate-900 border-l-4 border-yellow-500 p-4'):
                    ui.label('WIN RATE').classes('text-xs text-slate-500')
                    ui.label(f"{win_rate:.1f}%").classes('text-2xl font-bold text-yellow-400')

        with chart_container:
            chart_container.clear()
            cumulative = []
            curr = 0
            for val in data:
                curr += val
                cumulative.append(curr)
                
            fig = go.Figure(data=[go.Scatter(y=cumulative, mode='lines', line=dict(color='#00ff88', width=2))])
            fig.update_layout(
                title='Career PnL Trajectory',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94a3b8'),
                margin=dict(l=20, r=20, t=40, b=20),
                xaxis=dict(title='Sessions Played', gridcolor='#334155'),
                yaxis=dict(title='Total Bankroll Growth (€)', gridcolor='#334155')
            )
            ui.plotly(fig).classes('w-full h-80')

    # --- LAYOUT ---
    with ui.column().classes('w-full max-w-4xl mx-auto gap-6 p-4'):
        ui.label('RESEARCH LAB').classes('text-2xl font-light text-slate-300')
        
        # --- CONTROL PANEL ---
        with ui.card().classes('w-full bg-slate-900 p-6 gap-4'):
            
            # Row 1: Time Settings
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('schedule', color='blue').classes('text-2xl')
                ui.label('TIMELINE').classes('font-bold text-blue-400 w-24')
                slider_years = ui.slider(min=1, max=10, value=5).props('label-always label-value="Years" color=blue').classes('flex-grow')
                slider_frequency = ui.slider(min=9, max=100, value=9).props('label-always label-value="Sess/Yr" color=blue').classes('flex-grow')
            
            ui.separator().classes('bg-slate-700')

            # Row 2: Strategy Settings
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('tune', color='purple').classes('text-2xl')
                ui.label('STRATEGY').classes('font-bold text-purple-400 w-24')
                
                # Iron Gate Limit
                slider_iron_gate = ui.slider(min=2, max=5, value=3).props('label-always label-value="Iron Gate (Losses)" color=purple').classes('flex-grow')
                
                # Betting Logic
                select_press = ui.select({0: 'Flat Bet', 1: 'Press after 1 Win', 2: 'Press after 2 Wins'}, value=2, label='Betting Mode').classes('w-48')

            # Row 3: Risk Management
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('shield', color='red').classes('text-2xl')
                ui.label('RISK').classes('font-bold text-red-400 w-24')
                
                # Stop Loss / Profit
                slider_stop_loss = ui.slider(min=5, max=30, value=10).props('label-always label-value="Stop (Units)" color=red').classes('flex-grow')
                slider_profit = ui.slider(min=3, max=20, value=6).props('label-always label-value="Target (Units)" color=green').classes('flex-grow')

            ui.separator().classes('bg-slate-700')
            
            # Row 4: Action
            with ui.row().classes('w-full items-center justify-between'):
                select_tier = ui.select({1: 'Tier 1 Start', 2: 'Tier 2 Start', 3: 'Tier 3 Start'}, value=1, label="Starting Capital").classes('w-40')
                btn_sim = ui.button('RUN SIMULATION', on_click=run_sim).props('icon=play_arrow color=green size=lg')
        
        # --- OUTPUT ---
        label_stats = ui.label('Configure your strategy above...').classes('text-sm text-slate-500')
        progress = ui.linear_progress().props('color=blue').classes('mt-0')
        progress.set_visibility(False)

        stats_container = ui.column().classes('w-full')
        chart_container = ui.card().classes('w-full bg-slate-900 p-4')
