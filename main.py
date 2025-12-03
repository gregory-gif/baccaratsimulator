from nicegui import ui
from ui.layout import create_layout
from ui.scorecard import Scorecard  # <--- Importing the file you just made

ui.dark_mode().enable()
create_layout()

# Start the module
Scorecard(tier_level=1) 

ui.run(title='Salle Blanche Lab')
