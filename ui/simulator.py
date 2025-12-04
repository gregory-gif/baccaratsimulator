from nicegui import ui
import plotly.graph_objects as go
import random
import asyncio
import traceback
import numpy as np
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

    @staticmethod
    def run_full_career(start_ga, total_months, sessions_per_year, 
                        monthly_contribution, contrib_win, contrib_loss, 
                        overrides):
        """Simulates one complete career timeline."""
        trajectory = []
        current_ga = start_ga
        sessions_played_total = 0
        last_session_won = False
        
        # Metrics
        m_contrib = 0
        m_tax = 0
        m_play_pnl = 0
        m_holidays = 0
        m_insolvent_months = 0 # New: Track time spent in penalty box
        
        for m in range(total_months):
            # A. LUXURY TAX
            if current_ga > 12500:
                surplus = current_ga - 12500
                tax = surplus * 0.25
                current_ga -= tax
                m_tax += tax

            # B. ECOSYSTEM (Dynamic)
            if current_ga < 10000:
                amount = contrib_win if last_session_won else contrib_loss
                # If first month (no last session), assume loss (conservative start)
                current_ga += amount
                m_contrib += amount
            else:
                m_holidays += 1
            
            # C. PLAY CHECK
            # Rule: Resume play only if GA >= 1,500
            can_play = (current_ga >= 1500)
            
            if not can_play:
                m_insolvent_months += 1
            
            # D. PLAY EXECUTION
            expected_sessions = int((m + 1) * (sessions_per_year / 12))
            sessions_due = expected_sessions - sessions_played_total
            
            if can_play and sessions_due > 0:
                for _ in range(sessions_due):
                    pnl = SimulationWorker.run_session(current_ga, overrides)
                    current_ga += pnl
                    m_play_pnl += pnl
                    sessions_played_total += 1
                    last_session_won = (pnl > 0)
            
            trajectory.append(current_ga)
            
        return {
            'trajectory': trajectory,
            'final_ga': current_ga,
            'contrib': m_contrib,
            'tax': m_tax,
            'play_pnl': m_play_pnl,
            'holidays': m_holidays,
            'insolvent_months': m_insolvent_months
        }

def show_simulator():
    running = False
    
    async def run_sim():
        nonlocal running
        if running: return
        
        try:
            running = True
            btn_sim.disable()
            
            progress.set_value(0)
            progress.set_visibility(True)
            label_stats.set_text("Initializing Multiverse...")
            
            # 1. SETTINGS
            num_sims = int(slider_num_sims.value)
            years = int(slider_years.value)
            sessions_per_year = int(slider_frequency.value)
            total_months = years * 12
            
            # Contributions
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
            
            # 2. BATCH EXECUTION
            all_results = []
            
            # Run in batches of 10 to keep UI responsive
            batch_size = 10
            for i in range(0, num_sims, batch_size):
                count = min(batch_size, num_sims - i)
                
                # Wrapper to run N careers
                def run_batch_careers():
                    batch_data = []
                    for _ in range(count):
                        res = SimulationWorker.run_full_career(
                            current_ga, total_months, sessions_per_year,
                            0, contrib_win, contrib_loss, overrides
                        )
                        batch_data.append(res)
                    return batch_data

                batch_res = await asyncio.to_thread(run_batch_careers)
                all_results.extend(batch_res)
                
                # Update UI
                pct = len(all_results) / num_sims
                progress.set_value(pct)
                label_stats.set_text(f"Simulating Universe {len(all_results)}/{num_sims}")

            label_stats.set_text("Analyzing Probabilities...")
            render_analysis(all_results, years, current_ga)
            label_stats.set_text("Analysis Complete")

        except Exception as e:
            error_msg = str(e)
            print(traceback.format_exc())
            ui.notify(f"Error: {error_msg}", type='negative', close_button=True)
            label_stats.set_text(f"Failed: {error_msg}")
            
        finally:
            running = False
            btn_sim.enable()
            progress.set_visibility(False)

    def render_analysis(results, years, start_ga):
        if not results: return
        
        # 1. PROCESS DATA FOR CHART
        # Extract trajectories: List of [Month0, Month1, ... MonthN]
        trajectories = np.array([r['trajectory'] for r in results])
        
        # Calculate Bands per month (Columns)
        months = list(range(trajectories.shape[1]))
        
        min_band = np.min(trajectories, axis=0)
        max_band = np.max(trajectories, axis=0)
        p25_band = np.percentile(trajectories, 25, axis=0)
        p75_band = np.percentile(trajectories, 75, axis=0)
        mean_line = np.mean(trajectories, axis=0)
        
        # 2. PROCESS ECONOMICS (Averages)
        avg_final_ga = np.mean([r['final_ga'] for r in results])
        avg_contrib = np.mean([r['contrib'] for r in results])
        avg_tax = np.mean([r['tax'] for r in results])
        avg_pnl = np.mean([r['play_pnl'] for r in results])
        avg_holidays = np.mean([r['holidays'] for r in results])
        
        # Insolvency Metrics
        avg_insolvent = np.mean([r['insolvent_months'] for r in results])
        
        total_months = years * 12
        insolvency_pct = (avg_insolvent / total_months) * 100
        active_pct = 100 - insolvency_pct
        
        avg_monthly_cost = (avg_contrib - avg_tax) / total_months
        net_life_result = avg_final_ga + avg_tax - (start_ga + avg_contrib)

        # 3. RENDER CHART
        with chart_container:
            chart_container.clear()
            fig = go.Figure()
            
            # A. Worst/Best Range (Gray)
            fig.add_trace(go.Scatter(
                x=months + months[::-1], # X then X reversed
                y=np.concatenate([max_band, min_band[::-1]]), # Upper then Lower reversed
                fill='toself',
                fillcolor='rgba(128, 128, 128, 0.2)',
                line=dict(color='rgba(255,255,255,0)'),
                name='Best/Worst Range'
            ))
            
            # B. Realistic Range (Green - P25 to P75)
            fig.add_trace(go.Scatter(
                x=months + months[::-1],
                y=np.concatenate([p75_band, p25_band[::-1]]),
                fill='toself',
                fillcolor='rgba(0, 255, 136, 0.3)',
                line=dict(color='rgba(255,255,255,0)'),
                name='Likely Outcome (50%)'
            ))
            
            # C. Mean Line (White)
            fig.add_trace(go.Scatter(
                x=months, y=mean_line,
                mode='lines',
                name='Average Path',
                line=dict(color='white', width=2)
            ))
            
            # Lines
            fig.add_hline(y=1000, line_dash="dash", line_color="red", annotation_text="Insolvency")
            fig.add_hline(y=12500, line_dash="dash", line_color="gold", annotation_text="Luxury Tax")

            fig.update_layout(
                title='Monte Carlo Confidence Bands',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94a3b8'),
                margin=dict(l=20, r=20, t=40, b=20),
                xaxis=dict(title='Months Passed', gridcolor='#334155'),
                yaxis=dict(title='Game Account (€)', gridcolor='#334155'),
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            ui.plotly(fig).classes('w-full h-96')

        # 4. RENDER METRICS
        with stats_container:
            stats_container.clear()
            with ui.grid(columns=3).classes('w-full gap-4'):
                with ui.card().classes('bg-slate-900 border-l-4 border-blue-500 p-4'):
                    ui.label('AVG FINAL GA').classes('text-xs text-slate-500')
                    color = 'text-green-400' if avg_final_ga >= start_ga else 'text-red-400'
                    ui.label(f"€{avg_final_ga:,.0f}").classes(f'text-2xl font-bold {color}')
                
                with ui.card().classes('bg-slate-900 border-l-4 border-purple-500 p-4'):
                    ui.label('ACTIVE PLAY TIME').classes('text-xs text-slate-500')
                    # Color logic: High uptime is good
                    color = 'text-green-400' if active_pct > 80 else 'text-yellow-400'
                    if active_pct < 50: color = 'text-red-400'
                    ui.label(f"{active_pct:.1f}%").classes(f'text-2xl font-bold {color}')
                    ui.label(f"{avg_insolvent:.1f} months insolvent").classes('text-xs text-slate-600')

                with ui.card().classes('bg-slate-900 border-l-4 border-yellow-500 p-4'):
                    ui.label('AVG MONTHLY COST').classes('text-xs text-slate-500')
                    if avg_monthly_cost <= 0:
                        ui.label(f"+€{abs(avg_monthly_cost):.0f}/mo").classes('text-2xl font-bold text-green-400')
                        ui.label('PROFIT').classes('text-xs text-green-600 font-bold')
                    else:
                        ui.label(f"€{avg_monthly_cost:.0f}/mo").classes('text-2xl font-bold text-red-400')

        # 5. REPORT
        with report_container:
            report_container.clear()
            
            report_text = (
                f"MONTE CARLO REPORT ({len(results)} Universes)\n"
                f"----------------------------------------\n"
                f"Settings: {years} Years @ {slider_frequency.value} Sess/Yr\n"
                f"Start GA: €{start_ga:.0f} | Avg Final GA: €{avg_final_ga:.0f}\n"
                f"Net Life Result: €{net_life_result:.0f} (Avg)\n"
                f"True Cost: €{avg_monthly_cost:.0f}/month\n"
                f"Casino Edge Impact: €{avg_pnl:.0f}\n"
                f"Active Play Time: {active_pct:.1f}%\n"
                f"Avg Insolvency: {avg_insolvent:.1f} months\n"
                f"Avg Tax Withdrawn: €{avg_tax:.0f}\n"
                f"Avg Contributed: €{avg_contrib:.0f}\n"
            )
            
            with ui.expansion('AI Analysis Data', icon='analytics').classes('w-full bg-slate-800 text-slate-400 mb-4'):
                ui.textarea(value=report_text).props('readonly autogrow input-class="font-mono text-xs"').classes('w-full')

    # --- LAYOUT ---
    with ui.column().classes('w-full max-w-4xl mx-auto gap-6 p-4'):
        ui.label('RESEARCH LAB: MULTIVERSE').classes('text-2xl font-light text-slate-300')
        
        with ui.card().classes('w-full bg-slate-900 p-6 gap-4'):
            
            # Row 1: Multiverse Settings
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('hub', color='white').classes('text-2xl')
                ui.label('SIMULATION').classes('font-bold text-white w-24')
                
                with ui.column().classes('flex-grow'):
                    slider_num_sims = ui.slider(min=10, max=100, value=20).props('color=white')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Universes (Count)')
                        ui.label().bind_text_from(slider_num_sims, 'value', lambda v: f'{v} Sims').classes('font-bold text-white')

                with ui.column().classes('flex-grow'):
                    slider_years = ui.slider(min=1, max=10, value=5).props('color=blue')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Duration')
                        ui.label().bind_text_from(slider_years, 'value', lambda v: f'{v} Years').classes('font-bold text-blue-400')

            ui.separator().classes('bg-slate-700')

            # Row 2: Ecosystem
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('savings', color='green').classes('text-2xl')
                ui.label('ECOSYSTEM').classes('font-bold text-green-400 w-24')
                
                with ui.column().classes('flex-grow'):
                    slider_contrib_win = ui.slider(min=0, max=1000, value=200).props('color=green')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Contrib (Win)')
                        ui.label().bind_text_from(slider_contrib_win, 'value', lambda v: f'€{v}').classes('font-bold text-green-400')

                with ui.column().classes('flex-grow'):
                    slider_contrib_loss = ui.slider(min=0, max=1000, value=100).props('color=orange')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Contrib (Loss)')
                        ui.label().bind_text_from(slider_contrib_loss, 'value', lambda v: f'€{v}').classes('font-bold text-orange-400')

            ui.separator().classes('bg-slate-700')

            # Row 3: Strategy
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('tune', color='purple').classes('text-2xl')
                ui.label('STRATEGY').classes('font-bold text-purple-400 w-24')
                
                with ui.column().classes('flex-grow'):
                    slider_iron_gate = ui.slider(min=2, max=6, value=3).props('color=purple')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Iron Gate')
                        ui.label().bind_text_from(slider_iron_gate, 'value', lambda v: f'{v} Losses').classes('font-bold text-purple-400')

                select_press = ui.select({0: 'Flat', 1: 'Press 1-Win', 2: 'Press 2-Wins'}, value=2).classes('w-32')

            # Row 4: Risk
            with ui.row().classes('w-full gap-4 items-center'):
                ui.icon('shield', color='red').classes('text-2xl')
                ui.label('RISK').classes('font-bold text-red-400 w-24')
                
                with ui.column().classes('flex-grow'):
                    slider_stop_loss = ui.slider(min=5, max=30, value=10).props('color=red')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Stop')
                        ui.label().bind_text_from(slider_stop_loss, 'value', lambda v: f'{v} Units').classes('font-bold text-red-400')

                with ui.column().classes('flex-grow'):
                    slider_profit = ui.slider(min=3, max=20, value=6).props('color=green')
                    with ui.row().classes('justify-between w-full'):
                        ui.label('Target')
                        ui.label().bind_text_from(slider_profit, 'value', lambda v: f'{v} Units').classes('font-bold text-green-400')

            ui.separator().classes('bg-slate-700')
            
            # Run Button
            with ui.row().classes('w-full items-center justify-between'):
                with ui.column():
                    select_tier = ui.select({1: 'Tier 1 Start', 2: 'Tier 2 Start'}, value=1).classes('w-40')
                    slider_frequency = ui.slider(min=9, max=50, value=9).props('color=blue').classes('w-40 hidden') # Hidden logic, kept for value
                
                btn_sim = ui.button('RUN MULTIVERSE SIM', on_click=run_sim).props('icon=hub color=white text-color=black size=lg')
        
        # Output
        label_stats = ui.label('Configure your strategy above...').classes('text-sm text-slate-500')
        progress = ui.linear_progress().props('color=white').classes('mt-0')
        progress.set_visibility(False)

        stats_container = ui.column().classes('w-full')
        chart_container = ui.card().classes('w-full bg-slate-900 p-4')
        report_container = ui.column().classes('w-full')
