# ... (Previous imports remain the same)

    # ... (Inside render_analysis function)
    
        # 3. REPORT (The "Bulletproof" Version)
        with report_container:
            report_container.clear()
            
            # We build the list of lines first to avoid f-string crashes
            r_lines = []
            r_lines.append(f"MONTE CARLO REPORT ({len(results)} Universes)")
            r_lines.append("-" * 30)
            
            # Safe Data Extraction
            t_name = str(config.get('status_target_name', 'Gold'))
            t_pts = config.get('status_target_pts', 22500)
            r_lines.append(f"Target: {t_name} ({t_pts:,.0f} pts)")
            
            r_lines.append(f"Start GA: €{start_ga:,.0f}")
            r_lines.append(f"Avg Final GA: €{avg_final_ga:,.0f}")
            r_lines.append(f"Net Life Result: €{net_life_result:,.0f}")
            r_lines.append(f"True Cost: €{avg_monthly_cost:,.0f}/month")
            r_lines.append(f"Gold Volume: €{avg_volume:,.0f}")
            
            # Format Percentages
            r_lines.append(f"Active Play: {active_pct:.1f}%")
            r_lines.append(f"Avg Insolvency: {avg_insolvent:.1f} months")
            
            # Settings
            r_lines.append("-" * 30)
            r_lines.append(f"Safety Buffer: {config.get('safety')}x")
            r_lines.append(f"Iron Gate: {overrides.iron_gate_limit} Losses")
            r_lines.append(f"Stop/Target: {overrides.stop_loss_units}u / {overrides.profit_lock_units}u")
            r_lines.append(f"Ratchet: {'ON' if config.get('use_ratchet') else 'OFF'}")
            r_lines.append(f"Tax/Holiday: {config.get('use_tax')}/{config.get('use_holiday')}")

            report_text = "\n".join(r_lines)
            
            with ui.expansion('AI Analysis Data', icon='analytics').classes('w-full bg-slate-800 text-slate-400 mb-4'):
                ui.textarea(value=report_text).props('readonly autogrow input-class="font-mono text-xs"').classes('w-full')
