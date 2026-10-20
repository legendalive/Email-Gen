import streamlit as st
import config

st.set_page_config(
    page_title="QA Email Generator",
    page_icon="✉️",
    layout="wide"
)

# Load existing configuration
settings = config.load_settings()

# Initialize session state
if "settings" not in st.session_state:
    st.session_state.settings = settings

# --- SIDEBAR: SETTINGS ---
st.sidebar.title("⚙️ Settings")

# 1. API Keys
st.sidebar.subheader("API Keys")
openrouter_key = st.sidebar.text_input(
    "OpenRouter API Key (Primary)",
    value=st.session_state.settings.get("openrouter_api_key", ""),
    type="password",
    help="Primary API. The system will dynamically select the best available free model."
)

groq_key = st.sidebar.text_input(
    "Groq API Key (Fallback)",
    value=st.session_state.settings.get("groq_api_key", ""),
    type="password",
    help="Fallback API. If OpenRouter fails, the app seamlessly falls back to Groq free tier."
)

# 2. Week Selection
st.sidebar.subheader("Evaluation Week")
current_week = st.sidebar.text_input(
    "Current Week",
    value=st.session_state.settings.get("current_week", "Week 30"),
    help="e.g., Week 30, Week 39"
)

# 3. Custom Supplementary Rules
st.sidebar.subheader("Supplementary AI Rules")
custom_rules = st.sidebar.text_area(
    "Additional Instructions",
    value=st.session_state.settings.get("custom_rules", ""),
    height=140,
    help="Any supplementary guidelines to inject alongside the hardcoded rules."
)

# Save Settings Button
if st.sidebar.button("💾 Save Settings", use_container_width=True):
    updated = {
        "openrouter_api_key": openrouter_key.strip(),
        "groq_api_key": groq_key.strip(),
        "current_week": current_week.strip(),
        "custom_rules": custom_rules.strip()
    }
    if config.save_settings(updated):
        st.session_state.settings = updated
        st.sidebar.success("Settings saved successfully!")
    else:
        st.sidebar.error("Failed to save settings.")

# --- MAIN PAGE PLACEHOLDER ---
st.title("✉️ QA Feedback Email Generator")
st.caption("Zero-PII, Multi-call QA consolidation with automated failover")

st.info("System Ready. Please configure and verify your settings in the sidebar.")

# Status display
col1, col2, col3 = st.columns(3)
with col1:
    or_status = "🟢 Configured" if st.session_state.settings.get("openrouter_api_key") else "🔴 Missing"
    st.metric("OpenRouter Key", or_status)
with col2:
    groq_status = "🟢 Configured" if st.session_state.settings.get("groq_api_key") else "⚪ Optional/Missing"
    st.metric("Groq Key (Fallback)", groq_status)
with col3:
    st.metric("Active Week", st.session_state.settings.get("current_week", "N/A"))
