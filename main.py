from nicegui import ui
# We will create ui/layout.py next, so we import it here
from ui.layout import create_layout

# 1. APP CONFIGURATION
# --------------------
# Enable "Casino Night" mode (Dark Mode)
ui.dark_mode().enable() 

# 2. INITIALIZE THE INTERFACE
# ---------------------------
create_layout()

# 3. RUN THE APP
# --------------
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title='Salle Blanche Lab', 
        port=8080, 
        reload=True, 
        favicon='♠️',
        show=True
    )
