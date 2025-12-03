from nicegui import ui
from ui.layout import create_layout
from ui.scorecard import Scorecard

# 1. APP CONFIGURATION
ui.dark_mode().enable() 

# 2. INITIALIZE THE INTERFACE
create_layout()

# We now initialize Scorecard WITHOUT arguments
# It will automatically find your bankroll from utils/persistence.py
with ui.column().classes('w-full items-center'):
    Scorecard() 

# 3. RUN THE APP
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title='Salle Blanche Lab', 
        port=8080, 
        reload=True, 
        favicon='♠️',
        show=True
    )
