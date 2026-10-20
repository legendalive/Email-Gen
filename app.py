import streamlit as st
import streamlit.components.v1 as components
import re
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
    st.session_state.parsed_agents = None
    st.session_state.generated_emails = {}
    st.session_state.current_agent_idx = 0
    st.session_state.uploader_key += 1

def get_subject_line(week_setting: str) -> str:
    cleaned = (week_setting or "").strip()
    digits = re.findall(r"\d+", cleaned)
    week_num = digits[0] if digits else cleaned.replace("Week", "").replace("week", "").strip() or "30"
    return f"Coaching session for week {week_num}"

def render_copy_toolbar(first_name: str, subject_line: str, email_body: str, key_suffix: int):
    """Renders 3 independent copy buttons via hidden DOM textareas to prevent string collisions."""
    # Escape any HTML special characters for the hidden textareas
    safe_first_name = first_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_subject = subject_line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_body = email_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    html_code = f"""
    <style>
        .toolbar-wrap {{
            display: flex;
            gap: 10px;
            align-items: center;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            flex-wrap: wrap;
            margin: 4px 0 10px 0;
        }}
        .c-btn {{
            background-color: #f0f2f6;
            color: #31333f;
            border: 1px solid #d6d6d8;
            padding: 8px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.15s ease-in-out;
        }}
        .c-btn:hover {{
            background-color: #e4e7eb;
            border-color: #ff4b4b;
            color: #ff4b4b;
        }}
        .c-btn-red {{
            background-color: #ff4b4b;
            color: #ffffff;
            border: 1px solid #ff4b4b;
        }}
        .c-btn-red:hover {{
            background-color: #e03b3b;
            color: #ffffff;
        }}
    </style>

    <!-- Hidden text sources ensuring 100% accurate separation -->
    <textarea id="src_name_{key_suffix}" style="display:none;">{safe_first_name}</textarea>
    <textarea id="src_subj_{key_suffix}" style="display:none;">{safe_subject}</textarea>
    <textarea id="src_body_{key_suffix}" style="display:none;">{safe_body}</textarea>

    <div class="toolbar-wrap">
        <button id="b_name_{key_suffix}" class="c-btn" onclick="copyFromArea('src_name_{key_suffix}', 'b_name_{key_suffix}', '👤 Copy First Name: {safe_first_name}')">
            👤 Copy First Name: {safe_first_name}
        </button>
        <button id="b_subj_{key_suffix}" class="c-btn" onclick="copyFromArea('src_subj_{key_suffix}', 'b_subj_{key_suffix}', '📌 Copy Subject: {safe_subject}')">
            📌 Copy Subject
        </button>
        <button id="b_body_{key_suffix}" class="c-btn c-btn-red" onclick="copyFromArea('src_body_{key_suffix}', 'b_body_{key_suffix}', '✉️ Copy Email Body')">
            ✉️ Copy Email Body
        </button>
    </div>

    <script>
    function copyFromArea(srcId, btnId, originalText) {{
        const src = document.getElementById(srcId);
        if (!src) return;
        const val = src.value;

        if (navigator.clipboard && window.isSecureContext) {{
            navigator.clipboard.writeText(val).then(() => showCheck(btnId, originalText))
            .catch(() => execFallback(val, btnId, originalText));
        }} else {{
            execFallback(val, btnId, originalText);
        }}
    }}

    function execFallback(text, btnId, originalText) {{
        const temp = document.createElement("textarea");
        temp.value = text;
        temp.style.position = "fixed";
        temp.style.left = "-9999px";
        document.body.appendChild(temp);
        temp.focus();
        temp.select();
        try {{
            document.execCommand('copy');
            showCheck(btnId, originalText);
        }} catch(e) {{
            alert("Please copy manually.");
        }}
        document.body.removeChild(temp);
    }}

    function showCheck(btnId, originalText) {{
        const btn = document.getElementById(btnId);
        if (btn) {{
            btn.innerHTML = "✅ Copied!";
            btn.style.backgroundColor = "#28a745";
            btn.style.borderColor = "#28a745";
            btn.style.color = "#ffffff";
            setTimeout(() => {{
                btn.innerHTML = originalText;
                btn.style.backgroundColor = "";
                btn.style.borderColor = "";
                btn.style.color = "";
            }}, 2000);
        }}
    }}
    </script>
    """
    components.html(html_code, height=52)

# ----------------- SIDEBAR: SETTINGS -----------------
with st.sidebar:
    st.title("⚙️ System Settings")
    st.caption("Saved locally / via Cloud Secrets.")
    
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

    st.subheader("⚡ Groq (Ultra-Fast Fallback)")
    groq_key = st.text_input(
        "Groq API Key",
        value=st.session_state.settings.get("groq_api_key", ""),
        type="password"
    )
    if st.button("⚡ Test Groq", use_container_width=True):
        with st.spinner("Testing Groq API..."):
            ok, model_or_err, lat = test_groq_connection(groq_key.strip())
            if ok:
                st.success(f"Connected in {lat}s!\nModel: `{model_or_err}`")
            else:
                st.error(f"Failed ({lat}s): {model_or_err}")

    st.divider()

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

# 1. EXCEL UPLOAD
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

# 2. EMAIL GENERATION
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
                status_box.info(f"Generating for {agent} ({idx + 1}/{total_agents})...")
                
                email_text, model, prov = build_feedback_email_for_agent(
                    agent_name=agent,
                    calls=calls,
                    week=week_val,
                    custom_rules=custom_r,
                    openrouter_key=or_k,
                    groq_key=gr_k,
                    status_callback=lambda msg: status_box.info(f"Agent {idx + 1}/{total_agents}: {msg}")
                )
                
                st.session_state.generated_emails[agent] = {
                    "email": email_text,
                    "model": model,
                    "provider": prov
                }
                progress_bar.progress((idx + 1) / total_agents)
            
            status_box.success("🎉 All emails generated successfully!")

# 3. EMAIL REVIEW & NAVIGATION
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
    first_name_only = extract_first_name(current_agent)
    agent_record = st.session_state.generated_emails[current_agent]
    agent_calls = st.session_state.parsed_agents[current_agent]
    
    scores = [c["qa_score"] for c in agent_calls]
    avg_s = round(sum(scores) / len(scores)) if scores else 0
    subject_line = get_subject_line(st.session_state.settings.get("current_week", "Week 30"))

    # Agent Identity Card with disambiguation box
    top_c1, top_c2 = st.columns([3, 2])
    with top_c1:
        st.markdown(f"### **Agent {curr_idx + 1} of {num_agents}: {first_name_only}**")
        st.caption(f"Calls Audited: {len(agent_calls)} | Average QA: {avg_s}% | Engine: `{agent_record['model']}` ({agent_record['provider']})")
    with top_c2:
        st.info(f"🏷️ **Full Agent Identity:** `{current_agent}`")

    # Copy Toolbar (First name only, subject, body)
    render_copy_toolbar(
        first_name=first_name_only,
        subject_line=subject_line,
        email_body=agent_record["email"],
        key_suffix=curr_idx
    )
    
    # Formatted Preview & Editor Tabs
    tab_edit, tab_preview = st.tabs(["✏️ Email Editor", "👁️ Formatted Preview (Headings & Bullets)"])
    
    with tab_edit:
        edited_email = st.text_area(
            label=f"Subject: {subject_line}",
            value=agent_record["email"],
            height=300,
            key=f"editor_{curr_idx}"
        )
        st.session_state.generated_emails[current_agent]["email"] = edited_email

    with tab_preview:
        # Renders headings and bullet points formatted as they will appear
        preview_md = edited_email.replace("\n", "\n\n")
        st.markdown(f"**Subject:** `{subject_line}`")
        st.markdown(edited_email)

    # Navigation Buttons
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
            file_name=f"Feedback_{first_name_only}_{st.session_state.settings.get('current_week', 'Week')}.txt",
            mime="text/plain",
            use_container_width=True
        )

    with b_col4:
        all_emails_export = []
        for a_name in agents:
            all_emails_export.append("=" * 60)
            all_emails_export.append(f"AGENT: {a_name}")
            all_emails_export.append(f"SUBJECT: {subject_line}")
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
