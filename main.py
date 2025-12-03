from nicegui import ui
from ui.scorecard import Scorecard
from ui.dashboard import show_dashboard
from ui.simulator import show_simulator
from ui.session_log import show_session_log # <--- New Import

# 1. APP CONFIGURATION
ui.dark_mode().enable() 

# 2. CONTENT CONTAINER
content = ui.column().classes('w-full items-center')

def load_cockpit():
    content.clear()
    with content:
        Scorecard()

def load_dashboard():
    content.clear()
    with content:
        show_dashboard()

def load_simulator():
    content.clear()
    with content:
        show_simulator()

def load_session_log():
    content.clear()
    with content:
        show_session_log() # <--- Load the new module

# 3. LAYOUT & SIDEBAR
with ui.header().classes('bg-slate-900 text-white shadow-lg items-center'):
    ui.button(icon='menu', on_click=lambda: left_drawer.toggle()).props('flat color=white')
    ui.label('SALLE BLANCHE LAB').classes('text-xl font-bold tracking-widest ml-2')
    ui.space()
    with ui.row().classes('items-center gap-2'):
        ui.icon('verified', color='yellow').classes('text-lg')
        ui.label('GOLD CHASE 2025').classes('text-xs text-yellow-500 font-mono font-bold')

with ui.left_drawer(value=True).classes('bg-slate-800 text-white') as left_drawer:
    with ui.column().classes('w-full p-4 gap-4'):
        
        ui.label('MODULES').classes('text-slate-500 text-xs font-bold tracking-wider')
        with ui.column().classes('gap-2 w-full'):
            ui.button('DASHBOARD', icon='analytics', on_click=load_dashboard).props('flat align=left').classes('w-full text-slate-200 hover:bg-slate-700')
            ui.button('LIVE COCKPIT', icon='casino', on_click=load_cockpit).props('flat align=left').classes('w-full text-slate-200 hover:bg-slate-700')
            # New Button Added Here
            ui.button('SESSION LOG', icon='history', on_click=load_session_log).props('flat align=left').classes('w-full text-slate-200 hover:bg-slate-700')
            ui.button('SIMULATOR', icon='science', on_click=load_simulator).props('flat align=left').classes('w-full text-slate-200 hover:bg-slate-700')
        
        ui.separator().classes('bg-slate-700 my-2')
        
        ui.label('DOCTRINE').classes('text-slate-500 text-xs font-bold tracking-wider')
        with ui.card().classes('bg-slate-900 w-full p-3 border-l-4 border-red-500'):
            ui.label('"Act Your Wage"').classes('text-xs italic text-slate-300')
        with ui.card().classes('bg-slate-900 w-full p-3 border-l-4 border-blue-500'):
            ui.label('"Reset to Base"').classes('text-xs italic text-slate-300')

# 4. INITIAL STARTUP
load_dashboard()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='Salle Blanche Lab', port=8080, reload=True, favicon='♠️', show=True)
