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
            # Annual Point Reset
            if m > 0 and m % 12 == 0:
                current_year_points = 0

            # A. Luxury Tax
            if use_tax and current_ga > 12500:
                surplus = current_ga - 12500
                tax = surplus * 0.25
                current_ga -= tax
                m_tax += tax

            # B. Contribution
            should_contribute = True
            if use_holiday and current_ga >= 10000:
                should_contribute = False
            
            if should_contribute:
                amount = contrib_win if last_session_won else contrib_loss
                current_ga += amount
                m_contrib += amount
            else:
                m_holidays += 1
            
            # C. Play
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
                gold_hit_year = (m // 12) + 1
            
            trajectory.append(current_ga)
            
        return {
            'trajectory': trajectory,
            'final_ga': current_ga,
            'contrib': m_contrib,
            'tax': m_tax,
            'play_pnl': m_play_pnl,
            'holidays': m_holidays,
            'insolvent_months': m_insolvent_months,
            'total_volume': m_total_volume,
            'gold_year': gold_hit_year
        }

def show_simulator():
    running = False
    
    def update_ladder_preview():
        factor = slider_safety.value
        t_map = generate_tier_map(factor)
        rows = []
        for level, t in t_map.items():
            risk_pct = (t.base_unit / t.min_ga) * 100
            rows.append({
                'tier': f"Tier {level}",
                'bet': f"€{t.base_unit}",
                'start': f"€{t.min_ga:,.0f}",
                'risk': f"{risk_pct:.1f}%"
            })
        ladder_grid.options['rowData'] = rows
        ladder_grid.update()

    async def run_sim():
        nonlocal running
        if running: return
        
        try:
            running = True
            btn_sim.disable()
            progress.set_value(0)
            progress.set_visibility(True)
            label_stats.set_text("Initializing Multiverse...")
            
            num_sims = int(slider_num_sims.value)
            years = int(slider_years.value)
            sessions_per_year = int(slider_frequency.value)
            total_months = years * 12
            
            contrib_win = int(slider_contrib_win.value)
            contrib_loss = int(slider_contrib_loss.value)
            
            # Gold
            status_target = SBM_TIERS[select_status.value]
            earn_rate = float(slider_earn_rate.value)
            
            # Toggles
            use_ratchet = switch_ratchet.value
            use_tax = switch_luxury_tax.value
            use_holiday = switch_holiday.value
            safety_factor = int(slider_safety.value)
            
            overrides = StrategyOverrides(
                iron_gate_limit=int(slider_iron_gate.value),
                stop_loss_units=int(slider_stop_loss.value),
                profit_lock_units=int(slider_profit.value),
                press_trigger_wins=int(select_press.value),
                press_limit_capped=switch_capped.value
            )

            temp_map = generate_tier_map(safety_factor)
            tier_level = int(select_tier.value)
            start_ga = temp_map[tier_level].min_ga
            
            all_results = []
            batch_size = 10
            for i in range(0, num_sims, batch_size):
                count = min(batch_size, num_sims - i)
                
                def run_batch_careers():
                    batch_data = []
                    for _ in range(count):
                        res = SimulationWorker.run_full_career(
                            start_ga, total_months, sessions_per_year,
                            contrib_win, contrib_loss, overrides, use_ratchet,
                            use_tax, use_holiday, safety_factor, 
                            status_target, earn_rate
                        )
                        batch_data.append(res)
                    return batch_data

                batch_res = await asyncio.to_thread(run_batch_careers)
                all_results.extend(batch_res)
                
                pct = len(all_results) / num_sims
                progress.set_value(pct)
                label_stats.set_text(f"Simulating Universe {len(all_results)}/{num_sims}")

            label_stats.set_text("Analyzing Data...")
            render_analysis(all_results, years, start_ga, status_target)
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

    def render_analysis(results, years, start_ga, status_target):
        if not results: return
        
        trajectories = np.array([r['trajectory'] for r in results])
        months = list(range(trajectories.shape[1]))
        
        min_band = np.min(trajectories, axis=0)
        max_band = np.max(trajectories, axis=0)
        p25_band = np.percentile(trajectories, 25, axis=0)
        p75_band = np.percentile(trajectories, 75, axis=0)
        mean_line = np.mean(trajectories, axis=0)
        
        avg_final_ga = np.mean([r['final_ga'] for r in results])
        avg_contrib = np.mean([r['contrib'] for r in results])
        avg_tax = np.mean([r['tax'] for r in results])
        avg_pnl = np.mean([r['play_pnl'] for r in results])
        avg_holidays = np.mean([r['holidays'] for r in results])
        avg_insolvent = np.mean([r['insolvent_months'] for r in results])
        
        gold_hits = [r['gold_year'] for r in results if r['gold_year'] != -1]
        gold_prob = (len(gold_hits) / len(results)) * 100
        avg_year_hit = np.mean(gold_hits) if gold_hits else 0
        
        total_months = years * 12
        insolvency_pct = (avg_insolvent / total_months) * 100
        active_pct = 100 - insolvency_pct
        avg_monthly_cost = (avg_contrib - avg_tax) / total_months
        net_life_result = avg_final_ga + avg_tax - (start_ga + avg_contrib)

        with chart_container:
            chart_container.clear()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=months + months[::-1], y=np.concatenate([max_band, min_band[::-1]]), fill='toself', fillcolor='rgba(128, 128, 128, 0.2)', line=dict(color='rgba(255,255,255,0)'), name='Best/Worst'))
            fig.add_trace(go.Scatter(x=months + months[::-1], y=np.concatenate([p75_band, p25_band[::-1]]), fill='toself', fillcolor='rgba(0, 255, 136, 0.3)', line=dict(color='rgba(255,255,255,0)'), name='Likely'))
            fig.add_trace(go.Scatter(x=months, y=mean_line, mode='lines', name='Average', line=dict(color='white', width=2)))
            
            fig.add_hline(y=1000, line_dash="dash", line_color="red", annotation_text="Insolvency")
            if switch_holiday.value: fig.add_hline(y=10000, line_dash="dash", line_color="yellow", annotation_text="Holiday")
            if switch_luxury_tax.value: fig.add_hline(y=12500, line_dash="dash", line_color="gold", annotation_text="Luxury Tax")

            fig.update_layout(title='Monte Carlo Confidence Bands', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#94a3b8'), margin=dict(l=20, r=20, t=40, b=20), xaxis=dict(title='Months Passed', gridcolor='#334155'), yaxis=dict(title='Game Account (€)', gridcolor='#334155'), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            ui.plotly(fig).classes('w-full h-96')

        with stats_container:
            stats_container.clear()
            with ui.grid(columns=3).classes('w-full gap-4'):
                with ui.card().classes('bg-slate-900 border-l-4 border-yellow-500 p-4'):
                    ui.label(f'{select_status.value.upper()} PROBABILITY').classes('text-xs text-slate-500')
                    g_color = 'text-green-400' if gold_prob > 80 else 'text-yellow-400'
                    if gold_prob < 50: g_color = 'text-red-400'
                    ui.label(f"{gold_prob:.1f}%").classes(f'text-3xl font-black {g_color}')
                    if gold_prob > 0:
                        ui.label(f"Secured in Year {avg_year_hit:.1f}").classes('text-xs text-slate-400')
                    else:
                        ui.label("Missed").classes('text-xs text-slate-500')

                with ui.card().classes('bg-slate-900 border-l-4 border-blue-500 p-4'):
                    ui.label('AVG FINAL GA').classes('text-xs text-slate-500')
                    color = 'text-green-400' if avg_final_ga >= start_ga else 'text-red-400'
                    ui.label(f"€{avg_final_ga:,.0f}").classes(f'text-2xl font-bold {color}')
                
                with ui.card().classes('bg-slate-900 border-l-4 border-red-500 p-4'):
                    ui.label('AVG MONTHLY COST').classes('text-xs text-slate-500')
                    if avg_monthly_cost <= 0:
                        ui.label(f"+€{abs(avg_monthly_cost):.0f}").classes('text-2xl font-bold text-green-400')
                    else:
                        ui.label(f"€{avg_monthly_cost:.0f}").classes('text-2xl font-bold text-red-400')

        with report_container:
            report_container.clear()
            report_text = (
                f"MONTE CARLO REPORT ({len(results)} Universes)\n"
                f"----------------------------------------\n"
                f"Status Target: {select_status.value}\n"
                f"Start GA: €{start_ga:.0f} | Final GA: €{avg_final_ga:.0f}\n"
                f"Net Life Result: €{net_life_result:.0f} (Avg)\n"
                f"True Cost: €{avg_monthly_cost:.0f}/month\n"
                f"Active Play: {active_pct:.1f}%\n"
                f"Tax On: {switch_luxury_tax.value} | Holiday On: {switch_holiday.value}\n"
            )
            with ui.expansion('AI Analysis Data', icon='analytics').classes('w-full bg-slate-800 text-slate-400 mb-4'):
                ui.textarea(value=report_text).props('readonly autogrow input-class="font-mono text-xs"').classes('w-full')

    # --- LAYOUT ---
    with ui.column().classes('w-full max-w-4xl mx-auto gap-6 p-4'):
        ui.label('RESEARCH LAB: MY MONTE-CARLO').classes('text-2xl font-light text-slate-300')
        
        with ui.card().classes('w-full bg-slate-900 p-6 gap-4'):
            
            # Row 1: The Unified Ladder
            with ui.expansion('Tier Ladder Preview (Live)', icon='list').classes('w-full bg-slate-800 text-slate-300'):
                ladder_grid = ui.aggrid({
                    'columnDefs':
