from nicegui import ui
import plotly.graph_objects as go
import random
import asyncio
import traceback
import numpy as np
from engine.strategy_rules import SessionState, BaccaratStrategist, PlayMode, StrategyOverrides
from engine.tier_params import TIER_MAP, TierConfig, generate_tier_map, get_tier_for_ga
from utils.persistence import load_profile, save_profile

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
                press_depth=overrides.press_depth
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
                
                # Dynamic Ratchet Lock
                # Lock % of the Trigger Amount
                lock_pct = overrides.ratchet_lock_pct / 100.0
                lock_floor = trigger_profit_amount * lock_pct
                
                if ratchet_triggered and state.session_pnl <= lock_floor:
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

            # A. Luxury Tax
            tax_thresh = overrides.tax_threshold
            tax_rate = overrides.tax_rate / 100.0
            
            if use_tax and current_ga > tax_thresh:
                surplus = current_ga - tax_thresh
                tax = surplus * tax_rate
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
    
    # --- STRATEGY LIBRARY ---
    def load_saved_strategies():
        profile = load_profile()
        return profile.get('saved_strategies', {})

    def update_strategy_list():
        saved = load_saved_strategies()
        select_saved.options = list(saved.keys())
        select_saved.update()

    def save_current_strategy():
        name = input_name.value
        if not name:
            ui.notify('Please enter a name', type='warning')
            return
        
        profile = load_profile()
        if 'saved_strategies' not in profile:
            profile['saved_strategies'] = {}
            
        config = {
            'sim_num': slider_num_sims.value,
            'sim_years': slider_years.value,
            'sim_freq': slider_frequency.value,
            'eco_win': slider_contrib_win.value,
            'eco_loss': slider_contrib_loss.value,
            'eco_tax': switch_luxury_tax.value,
            'eco_hol': switch_holiday.value,
            'eco_tax_thresh': slider_tax_thresh.value,
            'eco_tax_rate': slider_tax_rate.value,
            'tac_safety': slider_safety.value,
            'tac_iron': slider_iron_gate.value,
            'tac_press': select_press.value,
            'tac_depth': slider_press_depth.value,
            'risk_stop': slider_stop_loss.value,
            'risk_prof': slider_profit.value,
            'risk_ratch': switch_ratchet.value,
            'risk_ratch_pct': slider_ratchet_lock.value,
            'gold_stat': select_status.value,
            'gold_earn': slider_earn_rate.value,
            'start_ga': slider_start_ga.value # NEW
        }
        
        profile['saved_strategies'][name] = config
        save_profile(profile)
        ui.notify(f'Saved: {name}', type='positive')
        update_strategy_list()
        input_name.value = ''

    def load_selected_strategy():
        name = select_saved.value
        if not name: return
        
        saved = load_saved_strategies()
        config = saved.get(name)
        if not config: return
        
        slider_num_sims.value = config.get('sim_num', 20)
        slider_years.value = config.get('sim_years', 10)
        slider_frequency.value = config.get('sim_freq', 9)
        slider_contrib_win.value = config.get('eco_win', 300)
        slider_contrib_loss.value = config.get('eco_loss', 200)
        switch_luxury_tax.value = config.get('eco_tax', True)
        slider_tax_thresh.value = config.get('eco_tax_thresh', 12500)
        slider_tax_rate.value = config.get('eco_tax_rate', 25)
        switch_holiday.value = config.get('eco_hol', True)
        slider_safety.value = config.get('tac_safety', 20)
        slider_iron_gate.value = config.get('tac_iron', 3)
        select_press.value = config.get('tac_press', 2)
        slider_press_depth.value = config.get('tac_depth', 3)
        slider_stop_loss.value = config.get('risk_stop', 8)
        slider_profit.value = config.get('risk_prof', 10)
        switch_ratchet.value = config.get('risk_ratch', False)
        slider_ratchet_lock.value = config.get('risk_ratch_pct', 50)
        select_status.value = config.get('gold_stat', 'Gold')
        slider_earn_rate.value = config.get('gold_earn', 10)
        slider_start_ga.value = config.get('start_ga', 1700) # NEW
        
        ui.notify(f'Loaded: {name}', type='info')

    def delete_selected_strategy():
        name = select_saved.value
        if not name: return
        
        profile = load_profile()
        if 'saved_strategies' in profile and name in profile['saved_strategies']:
            del profile['saved_strategies'][name]
            save_profile(profile)
            ui.notify(f'Deleted: {name}', type='negative')
            select_saved.value = None
            update_strategy_list()

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
            
            # --- CONFIG ---
            config = {
                'num_sims': int(slider_num_sims.value),
                'years': int(slider_years.value),
                'freq': int(slider_frequency.value),
                'contrib_win': int(slider_contrib_win.value),
                'contrib_loss': int(slider_contrib_loss.value),
                'status_target_name': select_status.value,
                'status_target_pts': SBM_TIERS[select_status.value],
                'earn_rate': float(slider_earn_rate.value),
                'use_ratchet': switch_ratchet.value,
                'use_tax': switch_luxury_tax.value,
                'use_holiday': switch_holiday.value,
                'safety': int(slider_safety.value),
                'start_ga': int(slider_start_ga.value), # NEW
                'press_depth': int(slider_press_depth.value),
                'ratchet_pct': int(slider_ratchet_lock.value),
                'tax_thresh': int(slider_tax_thresh.value),
                'tax_rate': int(slider_tax_rate.value),
                'press_limit_capped': True # Controlled by depth slider now
            }
            
            total_months = config['years'] * 12
            
            overrides = StrategyOverrides(
                iron_gate_limit=int(slider_iron_gate.value),
                stop_loss_units=int(slider_stop_loss.value),
                profit_lock_units=int(slider_profit.value),
                press_trigger_wins=int(select_press.value),
                press_depth=config['press_depth'],
                ratchet_lock_pct=config['ratchet_pct'],
                tax_threshold=config['tax_thresh'],
                tax_rate=config['tax_rate']
            )

            # Generate dynamic tiers based on safety factor
            # Use the user's Start GA directly
            start_ga = config['start_ga']
            
            all_results = []
            batch_size = 10
            for i in range(0, config['num_sims'], batch_size):
                count = min(batch_size, config['num_sims'] - i)
                
                def run_batch_careers():
                    batch_data = []
                    for _ in range(count):
                        res = SimulationWorker.run_full_career(
                            start_ga, total_months, config['freq'],
                            config['contrib_win'], config['contrib_loss'], overrides, 
                            config['use_ratchet'], config['use_tax'], config['use_holiday'], 
                            config['safety'], config['status_target_pts'], config['earn_rate']
                        )
                        batch_data.append(res)
                    return batch_data

                batch_res = await asyncio.to_thread(run_batch_careers)
                all_results.extend(batch_res)
                
                pct = len(all_results) / config['num_sims']
                progress.set_value(pct)
                label_stats.set_text(f"Simulating Universe {len(all_results)}/{config['num_sims']}")

            label_stats.set_text("Analyzing Data...")
            render_analysis(all_results, config, start_ga, overrides)
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

    def render_analysis(results, config, start_ga, overrides):
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
        avg_volume = np.mean([r['total_volume'] for r in results])
        
        gold_hits = [r['gold_year'] for r in results if r['gold_year'] != -1]
        gold_prob = (len(gold_hits) / len(results)) * 100
        avg_year_hit = np.mean(gold_hits) if gold_hits else 0
        
        total_months = config['years'] * 12
        insolvency_pct = (avg_insolvent / total_months) * 100
        active_pct = 100 - insolvency_pct
        avg_monthly_cost = (avg_contrib - avg_tax) / total_months
        net_life_result = avg_final_ga + avg_tax - (start_ga + avg_contrib)

        # SCOREBOARD
        survivor_count = len([r for r in results if r['final_ga'] >= 1500])
        score_survival = (survivor_count / len(results)) * 100
        
        if avg_monthly_cost <= 0:
            score_cost = 100
        else:
            score_cost = max(0, 100 - (avg_monthly_cost / 5))
            
        score_time = active_pct
        score_gold = gold_prob
        
        total_score = (score_gold * 0.30) + (score_survival * 0.30) + (score_cost * 0.20) + (score_time * 0.20)
        
        if total_score >= 90: grade, g_col = "A", "text-green-400"
        elif total_score >= 80: grade, g_col = "B", "text-blue-400"
        elif total_score >= 70: grade, g_col = "C", "text-yellow-400"
        elif total_score >= 60: grade, g_col = "D", "text-orange-400"
        else: grade, g_col = "F", "text-red-600"

        with scoreboard_container:
            scoreboard_container.clear()
            with ui.card().classes('w-full bg-slate-800 p-4 border-l-8').style(f'border-color: {"#ef4444" if grade=="F" else "#4ade80"}'):
                with ui.row().classes('w-full items-center justify-between'):
                    with ui.column():
                        ui.label('STRATEGY GRADE').classes('text-xs text-slate-400 font-bold tracking-widest')
                        ui.label(f"{grade}").classes(f'text-6xl font-black {g_col} leading-none')
                        ui.label(f"{total_score:.1f}% Score").classes(f'text-sm font-bold {g_col}')
                    
                    with ui.column().classes('items-center'):
                        ui.label('AVG ENDING BANKROLL').classes('text-[10px] text-slate-400 font-bold tracking-widest')
                        ui.label(f"€{avg_final_ga:,.0f}").classes('text-4xl font-black text-white leading-none')
                        pnl_color = 'text-green-400' if avg_final_ga >= start_ga else 'text-red-400'
                        pnl_prefix = '+' if avg_final_ga >= start_ga else ''
                        ui.label(f"{pnl_prefix}€{avg_final_ga - start_ga:,.0f}").classes(f'text-sm font-bold {pnl_color}')

                    with ui.grid(columns=4).classes('gap-x-8 gap-y-2'):
                        with ui.column().classes('items-center'):
                            ui.label('Gold Chase').classes('text-[10px] text-slate-500 uppercase')
                            ui.label(f"{score_gold:.0f}%").classes('text-lg font-bold text-yellow-400')
                        with ui.column().classes('items-center'):
                            ui.label('Survival').classes('text-[10px] text-slate-500 uppercase')
                            ui.label(f"{score_survival:.0f}%").classes('text-lg font-bold text-blue-400')
                        with ui.column().classes('items-center'):
                            ui.label('Cost Effic.').classes('text-[10px] text-slate-500 uppercase')
                            ui.label(f"{score_cost:.0f}%").classes('text-lg font-bold text-green-400')
                        with ui.column().classes('items-center'):
                            ui.label('Active Play').classes('text-[10px] text-slate-500 uppercase')
                            ui.label(f"{score_time:.0f}%").classes('text-lg font-bold text-purple-400')

        # CHART
        with chart_container:
            chart_container.clear()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=months + months[::-1], y=np.concatenate([max_band, min_band[::-1]]), fill='toself', fillcolor='rgba(128, 128, 128, 0.2)', line=dict(color='rgba(255,255,255,0)'), name='Best/Worst'))
            fig.add_trace(go.Scatter(x=months + months[::-1], y=np.concatenate([p75_band, p25_band[::-1]]), fill='toself', fillcolor='rgba(0, 255, 136, 0.3)', line=dict(color='rgba(255,255,255,0)'), name='Likely'))
            fig.add_trace(go.Scatter(x=months, y=mean_line, mode='lines', name='Average', line=dict(color='white', width=2)))
            
            fig.add_hline(y=1000, line_dash="dash", line_color="red", annotation_text="Insolvency")
            if config['use_holiday']: fig.add_hline(y=10000, line_dash="dash", line_color="yellow", annotation_text="Holiday")
            if config['use_tax']: fig.add_hline(y=12500, line_dash="dash", line_color="gold", annotation_text="Luxury Tax")

            fig.update_layout(title='Monte Carlo Confidence Bands', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#94a3b8'), margin=dict(l=20, r=20, t=40, b=20), xaxis=dict(title='Months Passed', gridcolor='#334155'), yaxis=dict(title='Game Account (€)', gridcolor='#334155'), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            ui.plotly(fig).classes('w-full h-96')

        # METRICS
        with stats_container:
            stats_container.clear()
            with ui.grid(columns=3).classes('w-full gap-4'):
                with ui.card().classes('bg-slate-900 border-l-4 border-yellow-500 p-4'):
                    ui.label(f"{config['status_target_name'].upper()} PROB").classes('text-xs text-slate-500')
                    g_color = 'text-green-400' if gold_prob > 80 else 'text-yellow-400'
                    if gold_prob < 50: g_color = 'text-red-400'
                    ui.label(f"{gold_prob:.1f}%").classes(f'text-3xl font-black {g_color}')
                    if gold_prob > 0:
                        ui.label(f"Hit Year {avg_year_hit:.1f}").classes('text-xs text-slate-400')

                with ui.card().classes('bg-slate-900 border-l-4 border-blue-500 p-4'):
                    ui.label('AVG FINAL GA').classes('text-xs text-slate-500')
                    color = 'text-green-400' if avg_final_ga >= start_ga else 'text-red-400'
                    ui.label(f"€{avg_final_ga:,.0f}").classes(f'text-2xl font-bold {color}')
                
                with ui.card().classes('bg-slate-900 border-l-4 border-red-500 p-4'):
                    ui.label('MONTHLY COST').classes('text-xs text-slate-500')
                    if avg_monthly_cost <= 0:
                        ui.label(f"+€{abs(avg_monthly_cost):.0f}").classes('text-2xl font-bold text-green-400')
                    else:
                        ui.label(f"€{avg_monthly_cost:.0f}").classes('text-2xl font-bold text-red-400')

        with report_container:
            report_container.clear()
            try:
                lines = []
                lines.append(f"MONTE CARLO REPORT ({len(results)} Universes)")
                lines.append(f"STRATEGY GRADE: {grade} ({total_score:.1f}%)")
                lines.append("-" * 40)
                
                tgt_name = config.get('status_target_name', 'N/A')
                tgt_pts = config.get('status_target_pts', 0)
                
                s_ga = f"€{start_ga:,.0f}"
                f_ga = f"€{avg_final_ga:,.0f}"
                n_res = f"€{net_life_result:,.0f}"
                t_cost = f"€{avg_monthly_cost:,.0f}"
                act_play = f"{active_pct:.1f}%"
                ins_mo = f"{avg_insolvent:.1f}"
                g_prob = f"{gold_prob:.1f}%"
                
                st_iron = overrides.iron_gate_limit
                st_press = overrides.press_trigger_wins
                
                depth = overrides.press_depth
                st_depth = "Unlimited" if depth == 0 else f"{depth} steps"
                
                st_stop = overrides.stop_loss_units
                st_prof = overrides.profit_lock_units
                st_safe = config.get('safety', 0)
                
                st_ratch = f"ON ({config['ratchet_pct']}%)" if config.get('use_ratchet') else "OFF"
                st_win = config.get('contrib_win', 0)
                st_loss = config.get('contrib_loss', 0)
                
                t_thr = config['tax_thresh']
                t_rate = config['tax_rate']
                st_tax = f"ON (>€{t_thr} @ {t_rate}%)" if config.get('use_tax') else "OFF"
                st_hol = "ON" if config.get('use_holiday') else "OFF"

                lines.append(f"Target: {tgt_name} ({tgt_pts:,.0f} pts)")
                lines.append(f"Start GA: {s_ga} | Final GA: {f_ga}")
                lines.append(f"Net Life Result: {n_res} (Avg)")
                lines.append(f"True Cost: {t_cost}/month")
                lines.append(f"Active Play: {act_play} ({ins_mo} months insolvent)")
                lines.append(f"Gold Prob: {g_prob}")
                
                lines.append("-" * 20 + " INPUTS " + "-" * 20)
                lines.append(f"Iron Gate: {st_iron} Losses")
                lines.append(f"Press Logic: {st_press} wins (Depth: {st_depth})")
                lines.append(f"Stop/Target: {st_stop}u / {st_prof}u")
                lines.append(f"Ratchet: {st_ratch}")
                lines.append(f"Safety Buffer: {st_safe}x")
                lines.append(f"Contrib: Win=€{st_win}, Loss=€{st_loss}")
                lines.append(f"Tax: {st_tax}")
                lines.append(f"Holiday: {st_hol}")
                
                report_text = "\n".join(lines)
            except Exception as e:
                report_text = f"Report Error: {str(e)}"
                print(traceback.format_exc())

            with ui.expansion('AI Analysis Data', icon='analytics').classes('w-full bg-slate-800 text-slate-400 mb-4'):
                ui.button('COPY', on_click=lambda: ui.run_javascript(f'navigator.clipboard.writeText(`{report_text}`)')).props('flat dense icon=content_copy color=white').classes('absolute top-2 right-12 z-10')
                ui.html(f'<pre style="white-space: pre-wrap; font-family: monospace; color: #94a3b8; font-size: 0.75rem;">{report_text}</pre>', sanitize=False)

    # --- LAYOUT ---
    with ui.column().classes('w-full max-w-4xl mx-auto gap-6 p-4'):
        ui.label('RESEARCH LAB: MY MONTE-CARLO').classes('text-2xl font-light text-slate-300')
        
        with ui.card().classes('w-full bg-slate-900 p-6 gap-4'):
            
            # LIBRARY
            with ui.expansion('STRATEGY LIBRARY (Load/Save)', icon='save').classes('w-full bg-slate-800 text-slate-300 mb-4'):
                with ui.column().classes('w-full gap-4'):
                    with ui.row().classes('w-full items-center gap-4'):
                        input_name = ui.input('Save Name').props('dark').classes('flex-grow')
                        ui.button('SAVE', on_click=save_current_strategy).props('icon=save color=green')
                    
                    with ui.row().classes('w-full items-center gap-4'):
                        select_saved = ui.select([], label='Saved Strategies').props('dark').classes('flex-grow')
                        ui.button('LOAD', on_click=load_selected_strategy).props('icon=file_upload color=blue')
                        ui.button('DELETE', on_click=delete_selected_strategy).props('icon=delete color=red')
                    
                    update_strategy_list()

            ui.separator().classes('bg-slate-700')
            
            # SIMULATION ROW
            with ui.row().classes('w-full gap-4 items-start'):
                with ui.column().classes('flex-grow'):
                    ui.label('SIMULATION').classes('font-bold text-white mb-2')
                    
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Universes').classes('text-xs text-slate-400')
                        lbl_num_sims = ui.label()
                    slider_num_sims = ui.slider(min=10, max=100, value=20).props('color=cyan')
                    lbl_num_sims.bind_text_from(slider_num_sims, 'value', lambda v: f'{v}')
                    lbl_num_sims.set_text('20') 
                    
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Duration (Years)').classes('text-xs text-slate-400')
                        lbl_years = ui.label()
                    slider_years = ui.slider(min=1, max=10, value=10).props('color=blue')
                    lbl_years.bind_text_from(slider_years, 'value', lambda v: f'{v}')
                    lbl_years.set_text('10') 
                    
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Freq (Sess/Yr)').classes('text-xs text-slate-400')
                        lbl_frequency = ui.label()
                    slider_frequency = ui.slider(min=9, max=50, value=9).props('color=blue')
                    lbl_frequency.bind_text_from(slider_frequency, 'value', lambda v: f'{v}')
                    lbl_frequency.set_text('9') 

                with ui.column().classes('w-1/2'):
                    ui.label('LADDER PREVIEW').classes('font-bold text-white mb-2')
                    with ui.expansion('View Table', icon='list').classes('w-full bg-slate-800 text-slate-300'):
                        ladder_grid = ui.aggrid({
                            'columnDefs': [
                                {'headerName': 'Tier', 'field': 'tier', 'width': 70},
                                {'headerName': 'Bet', 'field': 'bet', 'width': 70},
                                {'headerName': 'Start GA', 'field': 'start', 'width': 100},
                            ],
                            'rowData': [],
                        }).classes('h-40 w-full theme-balham-dark')

            ui.separator().classes('bg-slate-700')

            # ECOSYSTEM ROW
            ui.label('ECOSYSTEM').classes('font-bold text-green-400')
            with ui.row().classes('w-full gap-8'):
                with ui.column().classes('flex-grow'):
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Contrib (Win)').classes('text-xs text-green-400')
                        lbl_contrib_win = ui.label()
                    slider_contrib_win = ui.slider(min=0, max=1000, value=300).props('color=green')
                    lbl_contrib_win.bind_text_from(slider_contrib_win, 'value', lambda v: f'€{v}')
                    lbl_contrib_win.set_text('€300')
                
                with ui.column().classes('flex-grow'):
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Contrib (Loss)').classes('text-xs text-orange-400')
                        lbl_contrib_loss = ui.label()
                    slider_contrib_loss = ui.slider(min=0, max=1000, value=200).props('color=orange')
                    lbl_contrib_loss.bind_text_from(slider_contrib_loss, 'value', lambda v: f'€{v}')
                    lbl_contrib_loss.set_text('€200')
                
                with ui.column():
                    switch_luxury_tax = ui.switch('Tax').props('color=gold')
                    switch_luxury_tax.value = True
                    switch_holiday = ui.switch('Holiday').props('color=blue')
                    switch_holiday.value = True
                    
                    # Tax Settings Expandable
                    with ui.expansion('Settings', icon='tune').classes('bg-slate-800 text-xs'):
                         with ui.column().classes('p-2'):
                             ui.label('Tax Threshold')
                             slider_tax_thresh = ui.slider(min=5000, max=50000, step=500, value=12500).props('color=gold')
                             ui.label().bind_text_from(slider_tax_thresh, 'value', lambda v: f'€{v}')
                             ui.label('Tax Rate %')
                             slider_tax_rate = ui.slider(min=5, max=50, step=5, value=25).props('color=gold')
                             ui.label().bind_text_from(slider_tax_rate, 'value', lambda v: f'{v}%')

            ui.separator().classes('bg-slate-700')

            # STRATEGY & RISK ROW
            with ui.grid(columns=2).classes('w-full gap-8'):
                with ui.column():
                    ui.label('TACTICS').classes('font-bold text-purple-400')
                    
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Safety Buffer').classes('text-xs text-orange-400')
                        lbl_safety = ui.label()
                    slider_safety = ui.slider(min=10, max=60, value=20, on_change=update_ladder_preview).props('color=orange')
                    lbl_safety.bind_text_from(slider_safety, 'value', lambda v: f'{v}x')
                    lbl_safety.set_text('20x')
                    
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Iron Gate Limit').classes('text-xs text-purple-400')
                        lbl_iron = ui.label()
                    slider_iron_gate = ui.slider(min=2, max=6, value=3).props('color=purple')
                    lbl_iron.bind_text_from(slider_iron_gate, 'value', lambda v: f'{v} Losses')
                    lbl_iron.set_text('3 Losses')
                    
                    select_press = ui.select({0: 'Flat', 1: 'Press 1-Win', 2: 'Press 2-Wins'}, value=2, label='Press Logic').classes('w-full')
                    
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Press Depth (0=Inf)').classes('text-xs text-red-400')
                        lbl_depth = ui.label()
                    slider_press_depth = ui.slider(min=0, max=5, value=3).props('color=red')
                    lbl_depth.bind_text_from(slider_press_depth, 'value', lambda v: 'Unlimited' if v==0 else f'{v} Steps')
                    lbl_depth.set_text('3 Steps')

                with ui.column():
                    ui.label('RISK & REWARD').classes('font-bold text-red-400')
                    
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Stop Loss').classes('text-xs text-red-400')
                        lbl_stop = ui.label()
                    slider_stop_loss = ui.slider(min=5, max=30, value=8).props('color=red')
                    lbl_stop.bind_text_from(slider_stop_loss, 'value', lambda v: f'{v} Units')
                    lbl_stop.set_text('8 Units')
                    
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Target').classes('text-xs text-green-400')
                        lbl_profit = ui.label()
                    slider_profit = ui.slider(min=3, max=20, value=10).props('color=green')
                    lbl_profit.bind_text_from(slider_profit, 'value', lambda v: f'{v} Units')
                    lbl_profit.set_text('10 Units')
                    
                    with ui.row().classes('items-center justify-between'):
                         switch_ratchet = ui.switch('Ratchet').props('color=gold')
                         with ui.column():
                             ui.label('Lock %').classes('text-xs text-yellow-400')
                             slider_ratchet_lock = ui.slider(min=10, max=90, step=10, value=50).props('color=gold')
                             ui.label().bind_text_from(slider_ratchet_lock, 'value', lambda v: f'{v}%')

                    ui.label('Status Target').classes('text-xs text-yellow-400 mt-2')
                    select_status = ui.select(list(SBM_TIERS.keys()), value='Gold').classes('w-full')
                    
                    with ui.row().classes('w-full justify-between'):
                        ui.label('Earn Rate').classes('text-xs text-yellow-400')
                        lbl_earn = ui.label()
                    slider_earn_rate = ui.slider(min=1, max=20, value=10).props('color=yellow')
                    lbl_earn.bind_text_from(slider_earn_rate, 'value', lambda v: f'{v} pts/€100')
                    lbl_earn.set_text('10 pts/€100')

            ui.separator().classes('bg-slate-700')
            
            # Run
            with ui.row().classes('w-full items-center justify-between'):
                with ui.column():
                     # Replaced Select Tier with Slider Start GA
                     with ui.row().classes('w-full justify-between'):
                        ui.label('Starting Capital').classes('text-xs text-green-400')
                        lbl_start_ga = ui.label()
                     slider_start_ga = ui.slider(min=1000, max=3000, step=100, value=1700).props('color=green')
                     lbl_start_ga.bind_text_from(slider_start_ga, 'value', lambda v: f'€{v}')
                     lbl_start_ga.set_text('€1700')
                
                btn_sim = ui.button('RUN STATUS SIM', on_click=run_sim).props('icon=verified color=yellow text-color=black size=lg')
        
        label_stats = ui.label('Ready...').classes('text-sm text-slate-500')
        progress = ui.linear_progress().props('color=green').classes('mt-0')
        progress.set_visibility(False)

        # Place Scoreboard at the top of results
        scoreboard_container = ui.column().classes('w-full mb-4')
        stats_container = ui.column().classes('w-full')
        chart_container = ui.card().classes('w-full bg-slate-900 p-4')
        report_container = ui.column().classes('w-full')
        
        update_ladder_preview()
