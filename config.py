import json
import os
from typing import Dict, Any

CONFIG_FILE = "settings.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "openrouter_api_key": "",
    "groq_api_key": "",
    "current_week": "Week 30",
    "custom_rules": ""
}

def load_settings() -> Dict[str, Any]:
    """Loads configuration from local storage or returns safe defaults."""
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config.update(saved)
        except Exception as e:
            print(f"Warning: Could not read {CONFIG_FILE}: {e}")
    return config

def save_settings(settings: Dict[str, Any]) -> bool:
    """Saves configuration to settings.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving {CONFIG_FILE}: {e}")
        return False
