from nicegui import ui
from ui.scorecard import Scorecard
from ui.dashboard import show_dashboard

# 1. APP CONFIGURATION
# --------------------
ui.dark_mode().enable() 

# 2. CONTENT CONTAINER
# --------------------
# This is the "Main Stage". We clear this area and refill it 
# whenever you click a button in the sidebar.
content = ui.column().classes('w-full items-center')

def load_cockpit():
    """Switches the main view to the Live Baccarat Scorecard."""
    content.clear()
    with content:
        Scorecard()

def load_dashboard():
    """Switches the main view to the Strategy Dashboard."""
    content.clear()
    with content:
        show_dashboard()

def load_simulator():
    """Placeholder for the future Simulator module."""
    content.clear()
    with content:
        with ui.column().classes('text-center mt-20'):
            ui.icon('science', size='4xl', color='slate-700')
            ui.label("Simulator Module").classes('text-2xl text-slate-500 font-light')
            ui.label("Coming in Phase 4").classes('text-slate-600')

# 3. LAYOUT & SIDEBAR
# -------------------
# We define the fixed header and sidebar here.

with ui.header().classes('bg-slate-900 text-white shadow-lg items-center'):
    # Hamburger Menu Button
    ui.button(icon='menu', on_click=lambda: left_drawer.toggle()).props('flat color=white')
    
    # App Title
    ui.label('SALLE BLANCHE LAB').classes('text-xl font-bold tracking-widest ml-2')
    
    ui.space() # Pushes next items to the right
    
    # Status Badge
    with ui.row().classes('items-center gap-2'):
        ui.icon('verified', color='yellow').classes('text-lg')
        ui.label('GOLD CHASE 2025').classes('text-xs text-yellow-500 font-mono font-bold')

with ui.left_drawer(value=True).classes('bg-slate-800 text-white') as left_drawer:
    with ui.column().classes('w-full p-4 gap-4'):
        
        # A. Navigation Section
        ui.label('MODULES').classes('text-slate-500 text-xs font-bold tracking-wider')
        with ui.column().classes('gap-2 w-full'):
            ui.button('DASHBOARD', icon='analytics', on_click=load_dashboard).props('flat align=left').classes('w-full text-slate-200 hover:bg-slate-700')
            ui.button('LIVE COCKPIT', icon='casino', on_click=load_cockpit).props('flat align=left').classes('w-full text-slate-200 hover:bg-slate-700')
            ui.button('SIMULATOR', icon='science', on_click=load_simulator).props('flat align=left').classes('w-full text-slate-200 hover:bg-slate-700')
        
        ui.separator().classes('bg-slate-700 my-2')
        
        # B. Doctrine Section (Cheat Codes)
        ui.label('DOCTRINE').classes('text-slate-500 text-xs font-bold tracking-wider')
        
        with ui.card().classes('bg-slate-900 w-full p-3 border-l-4 border-red-500'):
            ui.label('"Act Your Wage"').classes('text-xs italic text-slate-300')
            ui.label('No Tier 3 bets with Tier 2 bankroll.').classes('text-[10px] text-slate-500')

        with ui.card().classes('bg-slate-900 w-full p-3 border-l-4 border-blue-500'):
            ui.label('"Reset to Base"').classes('text-xs italic text-slate-300')
            ui.label('After every press — win or lose.').classes('text-[10px] text-slate-500')

# 4. INITIAL STARTUP
# ------------------
# We load the Dashboard by default so you see your stats immediately.
load_dashboard()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title='Salle Blanche Lab', 
        port=8080, 
        reload=True, 
        favicon='♠️',
        show=True
    )
