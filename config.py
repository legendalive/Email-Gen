import json
import os
from typing import Dict, Any

CONFIG_FILE = "settings.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "gemini_api_key": "",
    "openrouter_api_key": "",
    "groq_api_key": "",
    "current_week": "Week 30",
    "custom_rules": ""
}

def load_settings() -> Dict[str, Any]:
    """
    Loads configuration. 
    Checks Streamlit Cloud secrets first, then local settings.json, then defaults.
    """
    config = DEFAULT_CONFIG.copy()

    # 1. Check Streamlit Cloud Secrets
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            for k in DEFAULT_CONFIG.keys():
                if k in st.secrets:
                    config[k] = str(st.secrets[k])
    except Exception:
        pass

    # 2. Check local settings.json
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    if v:
                        config[k] = v
        except Exception as e:
            print(f"Warning: Could not read {CONFIG_FILE}: {e}")
            
    return config

def save_settings(settings: Dict[str, Any]) -> bool:
    """Saves configuration to local settings.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving {CONFIG_FILE}: {e}")
        return False
