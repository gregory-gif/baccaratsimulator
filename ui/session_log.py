from nicegui import ui
from utils.persistence import load_profile

def show_session_log():
    # 1. Load Data
    profile = load_profile()
    history = profile.get('history', [])
    
    # 2. Reverse history to show newest first
    # We add an ID for the table
    rows = []
    for i, entry in enumerate(reversed(history)):
        rows.append({
            'id': len(history) - i,
            'date': entry.get('date', 'N/A'),
            'start': f"€{entry.get('start_ga', 0):.0f}",
            'end': f"€{entry.get('end_ga', 0):.0f}",
            'pnl': entry.get('pnl', 0),
            'shoes': entry.get('shoes', 0)
        })

    # 3. UI Layout
    with ui.column().classes('w-full max-w-4xl mx-auto gap-6 p-4'):
        ui.label('OFFICIAL SESSION LOG').classes('text-2xl font-light text-slate-300')

        if not rows:
            with ui.card().classes('w-full bg-slate-900 p-8 items-center'):
                ui.icon('history_toggle_off', size='4xl', color='slate-700')
                ui.label('No sessions recorded yet.').classes('text-slate-500')
                ui.label('Go to Live Cockpit to play.').classes('text-sm text-slate-600')
        else:
            # AG Grid Table (Professional Data View)
            with ui.card().classes('w-full bg-slate-900 p-0 overflow-hidden'):
                ui.aggrid({
                    'columnDefs': [
                        {'headerName': '#', 'field': 'id', 'width': 70, 'sortable': True},
                        {'headerName': 'Date', 'field': 'date', 'width': 180, 'sortable': True},
                        {'headerName': 'Start', 'field': 'start', 'width': 100},
                        {'headerName': 'End', 'field': 'end', 'width': 100},
                        {'headerName': 'Shoes', 'field': 'shoes', 'width': 90},
                        {
                            'headerName': 'PnL', 
                            'field': 'pnl', 
                            'width': 120, 
                            'sortable': True,
                            'cellStyle': {'font-weight': 'bold'},
                            # Color coding positive/negative values
                            'cellClassRules': {
                                'text-green-400': 'x >= 0',
                                'text-red-400': 'x < 0'
                            },
                            # Format as currency
                            'valueFormatter': "'€' + value" 
                        },
                    ],
                    'rowData': rows,
                    'rowSelection': 'single',
                }).classes('h-96 w-full theme-balham-dark')
                
            # Export / Summary
            with ui.row().classes('w-full justify-end text-slate-500 text-xs'):
                ui.label(f"Total Sessions: {len(rows)}")
