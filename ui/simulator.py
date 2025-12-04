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
    def run_session(current_ga: float, overrides: StrategyOverrides):
        """Runs a single session and returns the PnL."""
        tier = get_tier_for_ga(current_ga)
        state = SessionState(tier=tier, overrides=overrides)
        state.current_shoe = 1
        
        while state.current_shoe <= 3 and state.mode != PlayMode.STOPPED:
            decision = BaccaratStrategist.get_next_decision(state, ytd_pnl=0.0)
            
            if decision['mode'] == PlayMode.STOPPED:
                break
                
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
            else:
                state.hands_played_in_shoe += 1

            if state.hands_played_in_shoe >= 80:
                state.current_shoe += 1
                state.hands_played_in_shoe = 0
                state.presses_this_shoe = 0
                if state.current_shoe == 3:
                    state.shoe3_start_pnl = state.session_pnl

        return state.session_pnl

def show_simulator():
    # UI STATE
    results = [] 
    running = False
    
    # Metrics Storage
    metric_contrib = 0
    metric_tax = 0
    metric_play_pnl = 0
    metric_holidays = 0
    
    async def run_sim():
        nonlocal running, results, metric_contrib, metric_tax, metric_play_pnl, metric_holidays
        if running: return
        
        try:
            running = True
            btn_sim.disable()
            results = [] 
            
            # Reset Metrics
            metric_contrib = 0
            metric_tax = 0
            metric_play_pnl = 0
            metric_holidays = 0
            
            progress.set_value(0)
            progress.set_visibility(True)
            label_stats.set_text("Initializing Ecosystem...")
            
            # 1. SETTINGS
            years = int(slider_years.value)
            sessions_per_year = int(slider_frequency.value)
            
            # Dynamic Contributions
            contrib_win = int(slider_contrib_win.value)
            contrib_loss = int(slider_contrib_loss.value)
            
            overrides = StrategyOverrides(
                iron_gate_limit=int(slider_iron_gate.value),
                stop_loss_units=int(slider_stop_loss.value),
                profit_lock_units=int(slider_profit.value),
                press_trigger_wins=int(select_press.value)
            )

            # Initial Capital
            tier_level = int(select_tier.value)
            start_tier = TIER_MAP[tier_level]
            current_ga = float(start_tier.min_ga if start_tier.min_ga >= 1700 else 1700)
            
            # 2. TIME LOOP
            total_months = years * 12
            sessions_played_total = 0
            
            # Track 'Last Session Result' to determine contribution
            # Default to False (Conservative start: assume base contribution)
            last_session_won = False 
            
            chunk_size = 6 
            
            for m in range(0, total_months, chunk_size):
                
                # Logic Wrapper for Threading
                def process_months_batch(start_ga, start_sessions, batch_months, start_last_won):
                    local_ga = start_ga
                    local_sessions = start_sessions
                    local_last_won = start_last_won
                    batch_history = []
                    
                    b_contrib = 0
                    b_tax = 0
                    b_play_pnl = 0
                    b_holidays = 0
                    
                    for month_idx in range(batch_months):
                        # A. LUXURY TAX (Before Contribution)
                        if local_ga > 12500:
                            surplus = local_ga - 12500
                            tax = surplus * 0.25
                            local_ga -= tax
                            b_tax += tax

                        # B. ECOSYSTEM: Dynamic Monthly Contribution
                        # Rule: Stop contributing if GA >= 10,000 (Holiday)
                        if local_ga < 10000:
                            # Apply Dynamic Rule:
                            amount = contrib_win if local_last_won else contrib_loss
                            local_ga += amount
                            b_contrib += amount
                        else:
                            b_holidays += 1
                        
                        # C. INSOLVENCY CHECK
                        can_play = True
                        if local_ga < 1500:
                            can_play = False
                        
                        # D. PLAY SESSIONS
                        expected_sessions = int((local_sessions + 1 + month_idx + m) * (sessions_per_year / 12))
                        sessions_due = expected_sessions - local_sessions
                        
                        if can_play and sessions_due > 0:
                            for _ in range(sessions_due):
                                pnl = SimulationWorker.run_session(local_ga, overrides)
                                local_ga += pnl
                                b_play_pnl += pnl
                                local_sessions += 1
                                # Update Win State for NEXT month's contribution
                                local_last_won = (pnl > 0)
                        
                        batch_history.append(local_ga)
                    
                    return batch_history, local_ga, local_sessions, b_contrib, b_tax, b_play_pnl, b_holidays, local_last_won

                # Run Batch
                remaining_months = min(chunk_size, total_months - m)
                batch_res = await asyncio.to_thread(
                    process_months_batch, current_ga, sessions_played_total, remaining_months, last_session_won
                )
                
                # Unpack Results
                batch_data, new_ga, new_sessions, b_con, b_tax, b_pnl, b_hol, new_last_won = batch_res
                
                # Update State
                current_ga = new_ga
                sessions_played_total = new_sessions
                last_session_won = new_last_won # Persistence for next batch
                results.extend(batch_data)
                
                # Update Metrics
                metric_contrib += b_con
                metric_tax += b_tax
                metric_play_pnl += b_pnl
                metric_holidays += b_hol
                
                # Update UI
                progress.set_value(len(results) / total_months)
                label_stats.set_text(f"Simulating Month {len(results)}/{total_months} (GA: €{current_ga:,.0f})")

            label_stats.set_text("Rendering Report...")
            render_results(results, years)
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

    def render_results(data, years):
        if not data: return
        
        final_ga = data[-1]
        start_ga = data[0]
        total_months = years * 12
        avg_monthly_cost = (metric_contrib - metric_tax) / total_months
        
        peak = max(data)

        # 1. MAIN STATS
        with stats_container:
            stats_container.clear()
            with ui.grid(columns=3).classes('w-full gap-4'):
                with ui.card().classes('bg-slate-900 border-l-4 border-blue-500 p-4'):
                    ui.label('FINAL BANKROLL').classes('text-xs text-slate-500')
                    color = 'text-green-400' if final_ga >= start_ga else 'text-red-400'
                    ui.label(f"€{final_ga:,.0f}").classes(f'text-2xl font-bold {color}')
                
                with ui.card().classes('bg-slate-900 border-l-4 border-purple-500 p-4'):
                    ui.label('PLAY PnL (Casino Only)').classes('text-xs text-slate-500')
                    color = 'text-green-400' if metric_play_pnl >= 0 else 'text-red-400'
                    ui.label(f"€{metric_play_pnl:,.0f}").classes(f'text-2xl font-bold {color}')

                with ui.card().classes('bg-slate-900 border-l-4 border-yellow-500 p-4'):
                    ui.label('TRUE MONTHLY COST').classes('text-xs text-slate-500')
                    if avg_monthly_cost <= 0:
                        ui.label(f"+€{abs(avg_monthly_cost):.0f}/mo").classes('text-2xl font-bold text-green-400')
                        ui.label('PROFITABLE').classes('text-xs text-green-600 font-bold')
                    else:
                        ui.label(f"€{avg_monthly_cost:.0f}/mo").classes('text-2xl font-bold text-red-400')

        # 2. ECONOMIC REPORT CARD
        with report_container:
            report_container.clear()
            with ui.card().classes('w-full bg-slate-800 p-4'):
                ui.label('ECOSYSTEM ECONOMIC REPORT').classes('text-slate-400 text-xs font-bold tracking-widest mb-4')
                
                with ui.grid(columns=2).classes('w-full gap-y-2 gap-x-8'):
                    ui.label('Total Contributed:').classes('text-slate-300')
                    ui.label(f"€{metric_contrib:,.0f}").classes('text-right text-white font-bold')
                    
                    ui.label('Luxury Tax Withdrawn:').classes('text-slate-300')
                    ui.label(f"€{metric_tax:,.0f}").classes('text-right text-yellow-400 font-bold')
                    
                    ui.label('Contribution Holidays:').classes('text-slate-300')
                    ui.label(f"{metric_holidays} months").classes('text-right text-blue-400 font-bold')
                    
                    ui.separator().classes('col-span-2 bg-slate-600 my-2')
                    
                    ui.label('NET LIFE RESULT:').classes('text-slate-200 font-bold')
                    net_life = final_ga + metric_tax - (start_ga + metric_contrib)
                    color = 'text-green-400' if net_life >= 0 else 'text-red-400'
                    ui.label(f"€{net_life:,.0f}").classes(f'text-right font-black text-xl {color}')

        # 3. CHART
        with chart_container:
            chart_container.clear()
            months = list(range(len(data)))
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=months, y=data, 
                mode='lines', 
                name='Bankroll',
                line=dict(color='#00ff88', width=2),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 136, 0.1)'
            ))
            
            fig.add_hline(y=1000, line_dash="dash", line_color="red", annotation_text="Insolvency")
            fig.add_hline(y=10000, line_dash="dash", line_color="yellow", annotation_text="Holiday Limit")
            fig.add_hline(y=12500, line_dash="dash", line_color="gold", annotation_text="Luxury Tax Threshold")

            fig.update_layout(
                title='Ecosystem Trajectory',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94a3b8'),
                margin=dict(l=20, r=20, t=40, b=20),
                xaxis=dict(title='Months Passed', gridcolor='#334155'),
                yaxis=dict(title='Total Game Account (€)', gridcolor='#334155')
            )
            ui.plotly(fig).classes('w-full h-80')

    # --- LAYOUT ---
    with ui.column().classes('w-full max-w-4xl mx-auto gap-6 p-4'):
        ui.label('RESEARCH LAB: ECOSYSTEM').classes('text-2xl font-light text-slate-300')
        
        with ui.card().classes('w-full bg-slate-900 p-6 gap-4'):
            
            # Row 1: Ecosystem
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('savings', color='green').classes('text-2xl')
                ui.label('ECOSYSTEM').classes('font-bold text-green-400 w-24')
                
                with ui.column().classes('flex-grow'):
                    # DYNAMIC CONTRIBUTIONS
                    slider_contrib_win = ui.slider(min=0, max=1000, value=200).props('color=green')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Contrib (Post-Win)')
                        ui.label().bind_text_from(slider_contrib_win, 'value', lambda v: f'€{v}/mo').classes('font-bold text-green-400')

                    slider_contrib_loss = ui.slider(min=0, max=1000, value=100).props('color=orange') # Orange for distinction
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Contrib (Post-Loss)')
                        ui.label().bind_text_from(slider_contrib_loss, 'value', lambda v: f'€{v}/mo').classes('font-bold text-orange-400')
                
                select_tier = ui.select({1: 'Tier 1 Start', 2: 'Tier 2 Start', 3: 'Tier 3 Start'}, value=1).classes('w-40')

            ui.separator().classes('bg-slate-700')

            # Row 2: Time
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('schedule', color='blue').classes('text-2xl')
                ui.label('TIMELINE').classes('font-bold text-blue-400 w-24')
                
                with ui.column().classes('flex-grow'):
                    slider_years = ui.slider(min=1, max=10, value=5).props('color=blue')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Duration')
                        ui.label().bind_text_from(slider_years, 'value', lambda v: f'{v} Years').classes('font-bold text-blue-400')

                with ui.column().classes('flex-grow'):
                    slider_frequency = ui.slider(min=9, max=50, value=9).props('color=blue')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Frequency')
                        ui.label().bind_text_from(slider_frequency, 'value', lambda v: f'{v} Sess/Yr').classes('font-bold text-blue-400')
            
            ui.separator().classes('bg-slate-700')

            # Row 3: Strategy Variables
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('tune', color='purple').classes('text-2xl')
                ui.label('STRATEGY').classes('font-bold text-purple-400 w-24')
                
                with ui.column().classes('flex-grow'):
                    slider_iron_gate = ui.slider(min=2, max=6, value=3).props('color=purple')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Iron Gate Limit')
                        ui.label().bind_text_from(slider_iron_gate, 'value', lambda v: f'{v} Losses').classes('font-bold text-purple-400')

                select_press = ui.select({0: 'Flat', 1: 'Press 1-Win', 2: 'Press 2-Wins'}, value=2).classes('w-40')

            # Row 4: Risk
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('shield', color='red').classes('text-2xl')
                ui.label('RISK').classes('font-bold text-red-400 w-24')
                
                with ui.column().classes('flex-grow'):
                    slider_stop_loss = ui.slider(min=5, max=30, value=10).props('color=red')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Stop Loss')
                        ui.label().bind_text_from(slider_stop_loss, 'value', lambda v: f'{v} Units').classes('font-bold text-red-400')

                with ui.column().classes('flex-grow'):
                    slider_profit = ui.slider(min=3, max=20, value=6).props('color=green')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Profit Target')
                        ui.label().bind_text_from(slider_profit, 'value', lambda v: f'{v} Units').classes('font-bold text-green-400')

            ui.separator().classes('bg-slate-700')
            
            # Run Button
            with ui.row().classes('w-full items-center justify-end'):
                btn_sim = ui.button('RUN SIMULATION', on_click=run_sim).props('icon=play_arrow color=green size=lg')
        
        # Output
        label_stats = ui.label('Configure your strategy above...').classes('text-sm text-slate-500')
        progress = ui.linear_progress().props('color=blue').classes('mt-0')
        progress.set_visibility(False)

        stats_container = ui.column().classes('w-full')
        report_container = ui.column().classes('w-full')
        chart_container = ui.card().classes('w-full bg-slate-900 p-4')
