import streamlit as st
import config
from modules.anonymizer import extract_first_name
from modules.excel_parser import parse_excel_report
from modules.email_builder import build_feedback_email_for_agent
from modules.llm_engine import test_openrouter_connection, test_groq_connection

st.set_page_config(
    page_title="QA Email Generator",
    page_icon="✉️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Session State
if "settings" not in st.session_state:
    st.session_state.settings = config.load_settings()

if "parsed_agents" not in st.session_state:
    st.session_state.parsed_agents = None

if "generated_emails" not in st.session_state:
    st.session_state.generated_emails = {}

if "current_agent_idx" not in st.session_state:
    st.session_state.current_agent_idx = 0

if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

def clear_all_data():
    """Resets all parsed and generated data for a clean session."""
    st.session_state.parsed_agents = None
    st.session_state.generated_emails = {}
    st.session_state.current_agent_idx = 0
    st.session_state.uploader_key += 1

# ----------------- SIDEBAR: SETTINGS -----------------
with st.sidebar:
    st.title("⚙️ System Settings")
    st.caption("Saved locally / via Cloud Secrets.")
    
    # 1. OpenRouter Section with Dedicated Test Button
    st.subheader("🔑 OpenRouter (Primary)")
    openrouter_key = st.text_input(
        "OpenRouter API Key",
        value=st.session_state.settings.get("openrouter_api_key", ""),
        type="password"
    )
    if st.button("⚡ Test OpenRouter", use_container_width=True):
        with st.spinner("Testing OpenRouter..."):
            ok, model_or_err, lat = test_openrouter_connection(openrouter_key.strip())
            if ok:
                st.success(f"Connected in {lat}s!\nModel: `{model_or_err}`")
            else:
                st.error(f"Failed ({lat}s): {model_or_err}")

    # 2. Groq Section with Dedicated Test Button
    st.subheader("⚡ Groq (Ultra-Fast Fallback)")
    groq_key = st.text_input(
        "Groq API Key",
        value=st.session_state.settings.get("groq_api_key", ""),
        type="password"
    )
    if st.button("⚡ Test Groq", use_container_width=True):
        with st.spinner("Testing Groq..."):
            ok, model_or_err, lat = test_groq_connection(groq_key.strip())
            if ok:
                st.success(f"Connected in {lat}s!\nModel: `{model_or_err}`")
            else:
                st.error(f"Failed ({lat}s): {model_or_err}")

    st.divider()

    # 3. Scope & Rules
    st.subheader("📅 Scope & Rules")
    current_week = st.text_input(
        "Current Week",
        value=st.session_state.settings.get("current_week", "Week 30"),
        placeholder="e.g. Week 30, Week 39"
    )
    
    custom_rules = st.text_area(
        "Custom AI Instructions",
        value=st.session_state.settings.get("custom_rules", ""),
        height=100,
        placeholder="Supplementary instructions..."
    )
    
    if st.button("💾 Save Settings", use_container_width=True, type="primary"):
        new_settings = {
            "openrouter_api_key": openrouter_key.strip(),
            "groq_api_key": groq_key.strip(),
            "current_week": current_week.strip(),
            "custom_rules": custom_rules.strip()
        }
        if config.save_settings(new_settings):
            st.session_state.settings = new_settings
            st.success("Settings saved!")
        else:
            st.error("Error saving settings.")

# ----------------- MAIN VIEW -----------------
title_col, clear_col = st.columns([4, 1])
with title_col:
    st.title("✉️ QA Feedback Email Generator")
    st.markdown("Consolidate call evaluations into direct agent emails with zero PII leakage.")
with clear_col:
    st.write("")
    st.write("")
    if st.button("🗑️ Clear Everything", type="secondary", use_container_width=True):
        clear_all_data()
        st.rerun()

st.divider()

# System Monitor
col1, col2, col3 = st.columns(3)
has_or = bool(st.session_state.settings.get("openrouter_api_key"))
has_groq = bool(st.session_state.settings.get("groq_api_key"))

with col1:
    st.metric("OpenRouter (Primary)", "Configured" if has_or else "Missing", "Ready" if has_or else "- Required", delta_color="normal" if has_or else "inverse")
with col2:
    st.metric("Groq (Fallback)", "Configured" if has_groq else "Not Set", "Protected" if has_groq else "Optional", delta_color="normal" if has_groq else "off")
with col3:
    st.metric("Target Week Scope", st.session_state.settings.get("current_week", "Not Set"))

st.divider()

# ----------------- 1. EXCEL UPLOAD SECTION -----------------
st.subheader("📂 1. Upload QA Evaluation Report")
uploaded_file = st.file_uploader(
    "Upload Excel QA Report (.xlsx, .xls)",
    type=["xlsx", "xls"],
    key=f"uploader_{st.session_state.uploader_key}"
)

if uploaded_file is not None and st.session_state.parsed_agents is None:
    try:
        parsed_data = parse_excel_report(uploaded_file)
        st.session_state.parsed_agents = parsed_data
        
        total_agents = len(parsed_data)
        total_calls = sum(len(calls) for calls in parsed_data.values())
        st.success(f"Report Loaded: **{total_calls} calls** across **{total_agents} agents**.")
    except Exception as e:
        st.error(f"Error parsing Excel file: {e}")

if st.session_state.parsed_agents:
    with st.expander("📊 View Parsed Agents Summary Table", expanded=False):
        summary_rows = []
        for agent, calls in st.session_state.parsed_agents.items():
            scores = [c["qa_score"] for c in calls]
            avg_score = round(sum(scores) / len(scores)) if scores else 0
            fails_count = sum(len(c["missed_areas"]) for c in calls)
            summary_rows.append({
                "Agent Name": agent,
                "First Name": extract_first_name(agent),
                "Calls Audited": len(calls),
                "Average QA Score": f"{avg_score}%",
                "Missed Areas": fails_count,
                "All 100%": "✅ Yes" if avg_score >= 100 and fails_count == 0 else "❌ No"
            })
        st.dataframe(summary_rows, use_container_width=True)

st.divider()

# ----------------- 2. EMAIL GENERATION SECTION -----------------
st.subheader("🚀 2. Email Generation")

if st.session_state.parsed_agents:
    agents_list = list(st.session_state.parsed_agents.keys())
    total_agents = len(agents_list)
    
    if st.button("⚡ Generate Emails for All Agents", type="primary"):
        or_k = st.session_state.settings.get("openrouter_api_key", "").strip()
        gr_k = st.session_state.settings.get("groq_api_key", "").strip()
        week_val = st.session_state.settings.get("current_week", "Week 30")
        custom_r = st.session_state.settings.get("custom_rules", "")
        
        if not or_k and not gr_k:
            st.error("Please configure at least one API key in the sidebar before generating emails.")
        else:
            progress_bar = st.progress(0.0)
            status_box = st.empty()
            
            for idx, agent in enumerate(agents_list):
                calls = st.session_state.parsed_agents[agent]
                status_box.info(f"Processing agent {idx + 1} of {total_agents}: **{agent}**...")
                
                email_text, model, prov = build_feedback_email_for_agent(
                    agent_name=agent,
                    calls=calls,
                    week=week_val,
                    custom_rules=custom_r,
                    openrouter_key=or_k,
                    groq_key=gr_k,
                    status_callback=lambda msg: status_box.info(f"Agent {idx + 1}/{total_agents} ({agent}): {msg}")
                )
                
                st.session_state.generated_emails[agent] = {
                    "email": email_text,
                    "model": model,
                    "provider": prov
                }
                progress_bar.progress((idx + 1) / total_agents)
            
            status_box.success("🎉 All emails generated successfully!")

# ----------------- 3. EMAIL REVIEW & NAVIGATION -----------------
if st.session_state.generated_emails and st.session_state.parsed_agents:
    st.divider()
    st.subheader("📨 3. Review Generated Feedback Emails")
    
    agents = list(st.session_state.generated_emails.keys())
    num_agents = len(agents)
    
    if st.session_state.current_agent_idx >= num_agents:
        st.session_state.current_agent_idx = num_agents - 1
    if st.session_state.current_agent_idx < 0:
        st.session_state.current_agent_idx = 0
        
    curr_idx = st.session_state.current_agent_idx
    current_agent = agents[curr_idx]
    agent_record = st.session_state.generated_emails[current_agent]
    agent_calls = st.session_state.parsed_agents[current_agent]
    
    scores = [c["qa_score"] for c in agent_calls]
    avg_s = round(sum(scores) / len(scores)) if scores else 0

    hdr1, hdr2 = st.columns([3, 1])
    with hdr1:
        st.markdown(f"### **Agent ({curr_idx + 1} of {num_agents}): {current_agent}**")
        st.caption(f"Audited Calls: {len(agent_calls)} | Average QA Score: {avg_s}% | Engine: `{agent_record['model']}` ({agent_record['provider']})")
    
    edited_email = st.text_area(
        label="Feedback Email Draft (Editable)",
        value=agent_record["email"],
        height=320,
        key=f"editor_{curr_idx}"
    )
    st.session_state.generated_emails[current_agent]["email"] = edited_email
    
    b_col1, b_col2, b_col3, b_col4 = st.columns([1, 1, 1.5, 1.5])
    
    with b_col1:
        if st.button("⬅️ Previous", disabled=(curr_idx == 0), use_container_width=True):
            st.session_state.current_agent_idx -= 1
            st.rerun()
            
    with b_col2:
        if st.button("Next ➡️", disabled=(curr_idx == num_agents - 1), use_container_width=True):
            st.session_state.current_agent_idx += 1
            st.rerun()
            
    with b_col3:
        st.download_button(
            label="💾 Download This Email",
            data=edited_email,
            file_name=f"Feedback_{extract_first_name(current_agent)}_{st.session_state.settings.get('current_week', 'Week')}.txt",
            mime="text/plain",
            use_container_width=True
        )

    with b_col4:
        all_emails_export = []
        for a_name in agents:
            all_emails_export.append("=" * 60)
            all_emails_export.append(f"AGENT: {a_name}")
            all_emails_export.append("=" * 60)
            all_emails_export.append(st.session_state.generated_emails[a_name]["email"])
            all_emails_export.append("\n\n")
            
        st.download_button(
            label="📦 Download All Emails (.txt)",
            data="\n".join(all_emails_export),
            file_name=f"All_Feedback_Emails_{st.session_state.settings.get('current_week', 'Week')}.txt",
            mime="text/plain",
            use_container_width=True
        )

else:
    if not st.session_state.parsed_agents:
        st.info("Upload an Excel report above to begin generating emails.")
