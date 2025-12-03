import json
import os
from datetime import datetime

# File where we store the Director's data
DATA_FILE = 'lab_data.json'

DEFAULT_PROFILE = {
    "ga": 1700.0,          # Game Account (Starting Bankroll)
    "ytd_pnl": 0.0,        # Year-to-Date Profit/Loss
    "contributions": 0.0,  # Total Monthly Contributions
    "luxury_tax_paid": 0.0,
    "sessions_played": 0,
    "current_tier": 1,
    "history": []          # Log of all sessions
}

def load_profile():
    """Loads the profile from disk. If missing, creates a default one."""
    if not os.path.exists(DATA_FILE):
        save_profile(DEFAULT_PROFILE)
        return DEFAULT_PROFILE
    
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # Backup corrupt file if needed, but for now just reset
        return DEFAULT_PROFILE

def save_profile(data):
    """Writes the profile to disk."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def log_session_result(start_ga: float, end_ga: float, shoes_played: int):
    """Updates the profile after a session ends."""
    profile = load_profile()
    
    session_pnl = end_ga - start_ga
    
    # Update Totals
    profile["ga"] = end_ga
    profile["ytd_pnl"] += session_pnl
    profile["sessions_played"] += 1
    
    # Log Entry
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "start_ga": start_ga,
        "end_ga": end_ga,
        "pnl": session_pnl,
        "shoes": shoes_played
    }
    profile["history"].append(entry)
    
    save_profile(profile)
    return profile
