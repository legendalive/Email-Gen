import streamlit as st
import config
from modules.llm_engine import call_llm_resilient

st.set_page_config(
    page_title="QA Email Generator",
    page_icon="✉️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load configuration into session state
if "settings" not in st.session_state:
    st.session_state.settings = config.load_settings()

# ----------------- SIDEBAR: SETTINGS -----------------
with st.sidebar:
    st.title("⚙️ System Settings")
    st.caption("Saved locally. Never pushed to Git.")
    
    # 1. API Keys Section
    st.subheader("🔑 API Configuration")
    openrouter_key = st.text_input(
        "OpenRouter API Key (Primary)",
        value=st.session_state.settings.get("openrouter_api_key", ""),
        type="password",
        help="Primary API. Automatically cycles to the best available free model."
    )
    
    groq_key = st.text_input(
        "Groq API Key (Fallback)",
        value=st.session_state.settings.get("groq_api_key", ""),
        type="password",
        help="Fallback API. If OpenRouter fails, cascades seamlessly to Groq."
    )
    
    # 2. Evaluation Week Section
    st.subheader("📅 Evaluation Scope")
    current_week = st.text_input(
        "Current Week",
        value=st.session_state.settings.get("current_week", "Week 30"),
        placeholder="e.g. Week 30, Week 39",
        help="The week injected into all outgoing feedback emails."
    )
    
    # 3. Custom AI Rules Section
    st.subheader("📝 Supplementary Rules")
    custom_rules = st.text_area(
        "Custom AI Instructions",
        value=st.session_state.settings.get("custom_rules", ""),
        height=130,
        placeholder="Enter supplementary rules here...",
        help="Appended to hardcoded system rules for each email generation."
    )
    
    # Save Action
    if st.button("💾 Save Settings", use_container_width=True, type="primary"):
        new_settings = {
            "openrouter_api_key": openrouter_key.strip(),
            "groq_api_key": groq_key.strip(),
            "current_week": current_week.strip(),
            "custom_rules": custom_rules.strip()
        }
        if config.save_settings(new_settings):
            st.session_state.settings = new_settings
            st.success("Settings saved successfully!")
        else:
            st.error("Error saving settings.")

# ----------------- MAIN VIEW -----------------
st.title("✉️ QA Feedback Email Generator")
st.markdown("Automated consolidation of QA call evaluations into direct agent emails.")

st.divider()

# System Readiness Monitor
col1, col2, col3 = st.columns(3)

has_or = bool(st.session_state.settings.get("openrouter_api_key"))
has_groq = bool(st.session_state.settings.get("groq_api_key"))

with col1:
    st.metric(
        label="OpenRouter (Primary)",
        value="Configured" if has_or else "Missing",
        delta="Ready" if has_or else "- Action Required",
        delta_color="normal" if has_or else "inverse"
    )

with col2:
    st.metric(
        label="Groq (Fallback)",
        value="Configured" if has_groq else "Not Set",
        delta="Protected" if has_groq else "Optional",
        delta_color="normal" if has_groq else "off"
    )

with col3:
    active_week = st.session_state.settings.get("current_week", "Not Set")
    st.metric(
        label="Active Scope",
        value=active_week
    )

st.divider()

# --- DIAGNOSTIC TOOL: Test LLM Fallback Engine ---
st.subheader("🧪 Test AI Engine Connection & Fallback")
st.caption("Verify that your API keys connect and dynamic free model selection succeeds.")

if st.button("Run Connection Test"):
    or_k = st.session_state.settings.get("openrouter_api_key", "").strip()
    gr_k = st.session_state.settings.get("groq_api_key", "").strip()
    
    if not or_k and not gr_k:
        st.warning("Please save at least one API key in the sidebar before testing.")
    else:
        status_box = st.empty()
        with st.spinner("Discovering best available free model..."):
            try:
                response_text, model_used, provider = call_llm_resilient(
                    system_prompt="You are a system diagnostic tester. Respond with only one word: 'CONNECTED'.",
                    user_prompt="Ping",
                    openrouter_key=or_k,
                    groq_key=gr_k,
                    status_callback=lambda msg: status_box.info(msg)
                )
                status_box.empty()
                st.success(f"Connection Successful! Responded via **{provider}** using model: `{model_used}`")
            except Exception as e:
                status_box.empty()
                st.error(f"Test Failed: {str(e)}")

st.divider()
st.subheader("📂 Report Upload & Processing")
st.info("Step 2 Ready. Next up in Step 3: Zero-PII Sanitization & Desanitization Pipeline.")
