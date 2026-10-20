import streamlit as st
import config
from modules.llm_engine import call_llm_resilient
from modules.anonymizer import (
    extract_first_name,
    create_anonymized_payload,
    restore_pii
)
from modules.excel_parser import parse_excel_report

st.set_page_config(
    page_title="QA Email Generator",
    page_icon="✉️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load configuration into session state
if "settings" not in st.session_state:
    st.session_state.settings = config.load_settings()

if "parsed_agents" not in st.session_state:
    st.session_state.parsed_agents = None

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

# ----------------- EXCEL UPLOAD SECTION -----------------
st.subheader("📂 1. Upload QA Evaluation Report")
uploaded_file = st.file_uploader("Upload Excel QA Report (.xlsx, .xls)", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        with st.spinner("Parsing evaluations, grouping by agent, and extracting category fails..."):
            parsed_data = parse_excel_report(uploaded_file)
            st.session_state.parsed_agents = parsed_data
            
        total_agents = len(parsed_data)
        total_calls = sum(len(calls) for calls in parsed_data.values())
        
        st.success(f"Report Parsed Successfully! Detected **{total_calls} calls** across **{total_agents} agents**.")
        
        # Display Overview Table
        summary_rows = []
        for agent, calls in parsed_data.items():
            scores = [c["qa_score"] for c in calls]
            avg_score = round(sum(scores) / len(scores)) if scores else 0
            fails_count = sum(len(c["missed_areas"]) for c in calls)
            summary_rows.append({
                "Agent Name": agent,
                "First Name": extract_first_name(agent),
                "Calls Audited": len(calls),
                "Average QA Score": f"{avg_score}%",
                "Total Missed Areas": fails_count,
                "All 100%": "✅ Yes" if avg_score >= 100 and fails_count == 0 else "❌ No"
            })
        
        st.dataframe(summary_rows, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error parsing file: {e}")

st.divider()
st.subheader("🚀 2. Email Generation & Review")
st.info("Step 4 Ready! The Excel ingestion engine is active.\n\nNext up in Step 5: Email Prompt Assembler & Next/Back Viewer Interface.")
