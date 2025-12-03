from nicegui import ui
import plotly.graph_objects as go
from utils.persistence import load_profile
from engine.ecosystem import calculate_luxury_tax

def show_dashboard():
    # 1. Load Data
    profile = load_profile()
    history = profile.get('history', [])
    current_ga = profile['ga']
    ytd_pnl = profile['ytd_pnl']
    
    # 2. Key Metrics
    contributions = profile.get('contributions', 0)
    # Calculate Luxury Tax exposure
    potential_tax = calculate_luxury_tax(current_ga, profile.get('luxury_tax_paid', 0))
    
    # 3. Build UI
    with ui.column().classes('w-full max-w-4xl mx-auto gap-6 p-4'):
        
        # --- HEADER STATS ---
        with ui.grid(columns=3).classes('w-full gap-4'):
            # Bankroll Card
            with ui.card().classes('bg-slate-900 border-l-4 border-blue-500 p-4'):
                ui.label('GAME ACCOUNT').classes('text-xs text-slate-500 font-bold')
                ui.label(f"€{current_ga:,.0f}").classes('text-3xl text-white font-black')
                if current_ga < 1500:
                    ui.label('INSOLVENCY RISK').classes('text-xs text-red-500 font-bold blink')
            
            # YTD Performance
            color = 'text-green-400' if ytd_pnl >= 0 else 'text-red-400'
            with ui.card().classes('bg-slate-900 border-l-4 border-purple-500 p-4'):
                ui.label('YTD PnL').classes('text-xs text-slate-500 font-bold')
                ui.label(f"€{ytd_pnl:,.0f}").classes(f'text-3xl font-black {color}')
                ui.label(f"{len(history)} Sessions").classes('text-xs text-slate-600')

            # Luxury Tax / Ecosystem
            with ui.card().classes('bg-slate-900 border-l-4 border-yellow-500 p-4'):
                ui.label('LUXURY TAX').classes('text-xs text-slate-500 font-bold')
                if potential_tax > 0:
                    ui.label(f"DUE: €{potential_tax:,.0f}").classes('text-3xl text-yellow-400 font-black')
                    ui.label('Withdraw at year end').classes('text-xs text-slate-600')
                else:
                    ui.label("€0").classes('text-3xl text-slate-700 font-black')
                    ui.label('Safe (< €12,500)').classes('text-xs text-slate-600')

        # --- PERFORMANCE CHART (Plotly) ---
        with ui.card().classes('w-full bg-slate-900 p-4'):
            ui.label('PERFORMANCE TRAJECTORY').classes('text-slate-500 text-xs font-bold mb-4')
            
            if not history:
                ui.label('No sessions recorded yet.').classes('text-slate-600 italic')
            else:
                # Prepare Data
                dates = [h['date'] for h in history]
                pnls = [h['end_ga'] for h in history] # We plot GA over time
                
                # Create Plot
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=dates, y=pnls,
                    mode='lines+markers',
                    name='Bankroll',
                    line=dict(color='#00ff88', width=3),
                    marker=dict(size=8)
                ))
                
                # Styling for Dark Mode
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#94a3b8'),
                    margin=dict(l=20, r=20, t=10, b=20),
                    xaxis=dict(showgrid=False),
                    yaxis=dict(gridcolor='#334155')
                )
                
                ui.plotly(fig).classes('w-full h-64')

        # --- RECENT HISTORY ---
        with ui.card().classes('w-full bg-slate-800 p-0'):
            ui.label('RECENT LOGS').classes('p-4 text-slate-500 text-xs font-bold')
            
            with ui.column().classes('w-full gap-0'):
                for session in reversed(history[-5:]): # Show last 5
                    pnl = session['pnl']
                    color = 'text-green-400' if pnl >= 0 else 'text-red-400'
                    icon = 'trending_up' if pnl >= 0 else 'trending_down'
                    
                    with ui.row().classes('w-full p-4 border-t border-slate-700 justify-between items-center'):
                        with ui.row().classes('gap-4 items-center'):
                            ui.icon(icon).classes(color)
                            with ui.column().classes('gap-0'):
                                ui.label(session['date']).classes('text-white text-sm font-bold')
                                ui.label(f"Start: €{session['start_ga']}").classes('text-xs text-slate-500')
                        
                        ui.label(f"€{pnl:+}").classes(f'text-lg font-bold {color}')
