import json
import os

CONFIG_FILE = "settings.json"

DEFAULT_CONFIG = {
    "openrouter_api_key": "",
    "groq_api_key": "",
    "current_week": "Week 30",
    "custom_rules": ""
}

def load_settings() -> dict:
    """Loads settings from settings.json or returns defaults."""
    if not os.path.exists(CONFIG_FILE):
        save_settings(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure all default keys exist
            for key, val in DEFAULT_CONFIG.items():
                if key not in data:
                    data[key] = val
            return data
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_settings(settings: dict) -> bool:
    """Saves settings dictionary to local settings.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False
