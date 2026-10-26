import streamlit as st
import streamlit.components.v1 as components
import json
import re
import html
import config
from modules.anonymizer import extract_first_name
from modules.excel_parser import parse_excel_report
from modules.email_builder import build_feedback_email_for_agent, convert_email_to_rich_html
from modules.llm_engine import (
    test_gemini_connection,
    test_openrouter_connection,
    test_groq_connection
)

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

def render_copy_toolbar(first_name: str, subject_line: str, email_body: str):
    """
    Robust, crash-proof copy toolbar. Stores content in hidden HTML containers
    to prevent script collisions or React unmounting errors.
    """
    rich_html = convert_email_to_rich_html(email_body)
    
    # Safely escape text for HTML containers
    escaped_name = html.escape(first_name)
    escaped_subject = html.escape(subject_line)
    escaped_plain_body = html.escape(email_body)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            padding: 2px 0 0 0;
            background: transparent;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            gap: 8px;
            align-items: center;
            overflow: hidden;
        }}
        .c-btn {{
            background-color: #f0f2f6;
            color: #31333f;
            border: 1px solid #d6d6d8;
            padding: 7px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 5px;
            white-space: nowrap;
            height: 38px;
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
    </head>
    <body>
        <button class="c-btn" onclick="copyPlain('{escaped_name}', this)">
            👤 Copy Name: {escaped_name}
        </button>
        <button class="c-btn" onclick="copyPlain('{escaped_subject}', this)">
            📌 Copy Subject
        </button>
        <button class="c-btn c-btn-red" onclick="copyRich(this)">
            ✉️ Copy Email Body
        </button>

        <!-- Hidden Data Containers -->
        <div id="hidden_rich" style="display:none;">{rich_html}</div>
        <textarea id="hidden_plain" style="display:none;">{escaped_plain_body}</textarea>

        <script>
        function copyPlain(text, btn) {{
            navigator.clipboard.writeText(text).then(() => flashSuccess(btn));
        }}

        async function copyRich(btn) {{
            const htmlData = document.getElementById('hidden_rich').innerHTML;
            const plainData = document.getElementById('hidden_plain').value;

            if (navigator.clipboard && window.ClipboardItem) {{
                try {{
                    const blobHtml = new Blob([htmlData], {{ type: 'text/html' }});
                    const blobPlain = new Blob([plainData], {{ type: 'text/plain' }});
                    const item = new ClipboardItem({{ 'text/html': blobHtml, 'text/plain': blobPlain }});
                    await navigator.clipboard.write([item]);
                    flashSuccess(btn);
                    return;
                }} catch (e) {{
                    console.warn('ClipboardItem error, falling back:', e);
                }}
            }}

            navigator.clipboard.writeText(plainData).then(() => flashSuccess(btn));
        }}

        function flashSuccess(btn) {{
            const original = btn.innerHTML;
            btn.innerHTML = "✅ Copied!";
            btn.style.backgroundColor = "#28a745";
            btn.style.borderColor = "#28a745";
            btn.style.color = "#ffffff";
            setTimeout(() => {{
                btn.innerHTML = original;
                btn.style.backgroundColor = "";
                btn.style.borderColor = "";
                btn.style.color = "";
            }}, 2000);
        }}
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=46)

# ----------------- SIDEBAR: SETTINGS -----------------
with st.sidebar:
    st.title("⚙️ System Settings")
    st.caption("Cascade: Gemini → OpenRouter → Groq")

    # 1. Google Gemini (PRIMARY / #1)
    st.subheader("🌟 Google Gemini (Primary / #1)")
    gemini_key = st.text_input(
        "Gemini API Key",
        value=st.session_state.settings.get("gemini_api_key", ""),
        type="password"
    )
    if st.button("⚡ Test Gemini", use_container_width=True):
        with st.spinner("Testing Google Gemini..."):
            ok, model_or_err, lat = test_gemini_connection(gemini_key.strip())
            if ok:
                st.success(f"Connected in {lat}s!\nModel: `{model_or_err}`")
            else:
                st.error(f"Failed ({lat}s): {model_or_err}")

    st.divider()

    # 2. OpenRouter (SECONDARY / #2)
    st.subheader("🔑 OpenRouter (Secondary / #2)")
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

    st.divider()

    # 3. Groq (FALLBACK / #3)
    st.subheader("⚡ Groq (Fallback / #3)")
    groq_key = st.text_input(
        "Groq API Key",
        value=st.session_state.settings.get("groq_api_key", ""),
        type="password"
    )
    if st.button("⚡ Test Groq", use_container_width=True):
        with st.spinner("Pinging Groq server..."):
            ok, model_or_err, lat = test_groq_connection(groq_key.strip())
            if ok:
                st.success(f"Connected in {lat}s!\nModel: `{model_or_err}`")
            else:
                st.error(f"Failed ({lat}s): {model_or_err}")

    st.divider()

    # 4. Scope & Rules
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
            "gemini_api_key": gemini_key.strip(),
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

# System Readiness Monitor
col1, col2, col3, col4 = st.columns(4)
has_gemini = bool(st.session_state.settings.get("gemini_api_key"))
has_or = bool(st.session_state.settings.get("openrouter_api_key"))
has_groq = bool(st.session_state.settings.get("groq_api_key"))

with col1:
    st.metric("Gemini (Primary)", "Configured" if has_gemini else "Missing", "Ready" if has_gemini else "- Recommended", delta_color="normal" if has_gemini else "inverse")
with col2:
    st.metric("OpenRouter", "Configured" if has_or else "Not Set", "Secondary" if has_or else "Optional", delta_color="normal" if has_or else "off")
with col3:
    st.metric("Groq", "Configured" if has_groq else "Not Set", "Fallback" if has_groq else "Optional", delta_color="normal" if has_groq else "off")
with col4:
    st.metric("Target Scope", st.session_state.settings.get("current_week", "Not Set"))

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
        st.success(f"Report Loaded: **{total_calls} calls** across **{total_agents} agents** (Alphabetized A-Z).")
    except Exception as e:
        st.error(f"Error parsing Excel file: {e}")

if st.session_state.parsed_agents:
    with st.expander("📊 View Parsed Agents Summary Table (Alphabetical)", expanded=False):
        summary_rows = []
        for agent in sorted(st.session_state.parsed_agents.keys(), key=lambda x: x.strip().lower()):
            calls = st.session_state.parsed_agents[agent]
            scores = [c["qa_score"] for c in calls]
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0
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
    agents_list = sorted(list(st.session_state.parsed_agents.keys()), key=lambda x: x.strip().lower())
    total_agents = len(agents_list)

    if st.button("⚡ Generate Emails for All Agents", type="primary"):
        gem_k = st.session_state.settings.get("gemini_api_key", "").strip()
        or_k = st.session_state.settings.get("openrouter_api_key", "").strip()
        gr_k = st.session_state.settings.get("groq_api_key", "").strip()
        week_val = st.session_state.settings.get("current_week", "Week 30")
        custom_r = st.session_state.settings.get("custom_rules", "")

        if not gem_k and not or_k and not gr_k:
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
                    gemini_key=gem_k,
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

            status_box.success("🎉 All emails generated successfully in formal nested format!")

# 3. EMAIL REVIEW & NAVIGATION (ALPHABETICAL)
if st.session_state.generated_emails and st.session_state.parsed_agents:
    st.divider()
    st.subheader("📨 3. Review Generated Feedback Emails")

    agents = sorted(list(st.session_state.generated_emails.keys()), key=lambda x: x.strip().lower())
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
    raw_avg = sum(scores) / len(scores) if scores else 0
    avg_s = f"{int(raw_avg)}" if raw_avg.is_integer() else f"{round(raw_avg, 1)}"
    subject_line = get_subject_line(st.session_state.settings.get("current_week", "Week 30"))

    # Top info line + Individual Agent Regenerate Button
    top_c1, top_c2, top_c3 = st.columns([3, 2, 1.3])
    with top_c1:
        st.markdown(f"### **Agent {curr_idx + 1} of {num_agents}: {first_name_only}**")
        st.caption(f"Calls Audited: {len(agent_calls)} | Average QA: {avg_s}% | Engine: `{agent_record['model']}` ({agent_record['provider']})")
    with top_c2:
        st.info(f"🏷️ **Full Agent Identity:** `{current_agent}`")
    with top_c3:
        st.write("")
        if st.button("🔄 Regenerate Email", key=f"regen_{curr_idx}", help="Resend only this agent's calls to the AI for a fresh draft", use_container_width=True):
            gem_k = st.session_state.settings.get("gemini_api_key", "").strip()
            or_k = st.session_state.settings.get("openrouter_api_key", "").strip()
            gr_k = st.session_state.settings.get("groq_api_key", "").strip()
            week_val = st.session_state.settings.get("current_week", "Week 30")
            custom_r = st.session_state.settings.get("custom_rules", "")

            with st.spinner(f"Regenerating email for {first_name_only}..."):
                new_email, new_model, new_prov = build_feedback_email_for_agent(
                    agent_name=current_agent,
                    calls=agent_calls,
                    week=week_val,
                    custom_rules=custom_r,
                    gemini_key=gem_k,
                    openrouter_key=or_k,
                    groq_key=gr_k
                )
                st.session_state.generated_emails[current_agent] = {
                    "email": new_email,
                    "model": new_model,
                    "provider": new_prov
                }
                st.session_state[f"editor_box_{curr_idx}"] = new_email
                st.rerun()

    active_email_text = agent_record.get("email", "")

    # Action Row: Copy Toolbar + Previous / Next
    bar_copy_col, bar_prev_col, bar_next_col = st.columns([3.8, 1.1, 1.1])

    with bar_copy_col:
        render_copy_toolbar(
            first_name=first_name_only,
            subject_line=subject_line,
            email_body=active_email_text
        )

    with bar_prev_col:
        if st.button("⬅️ Previous", disabled=(curr_idx == 0), use_container_width=True):
            st.session_state.current_agent_idx -= 1
            st.rerun()

    with bar_next_col:
        if st.button("Next ➡️", disabled=(curr_idx == num_agents - 1), use_container_width=True, type="primary"):
            st.session_state.current_agent_idx += 1
            st.rerun()

    # Email Tabs: Formatted Preview (First!) & Editor
    tab_preview, tab_edit = st.tabs(["👁️ Live Formatted Preview", "✏️ Edit Email Draft"])

    with tab_preview:
        st.markdown(f"**Subject:** `{subject_line}`")
        rendered_rich_html = convert_email_to_rich_html(active_email_text)
        st.markdown(rendered_rich_html, unsafe_allow_html=True)

    with tab_edit:
        edited_email = st.text_area(
            label=f"Subject: {subject_line}",
            value=active_email_text,
            height=320,
            key=f"editor_box_{curr_idx}"
        )
        st.session_state.generated_emails[current_agent]["email"] = edited_email
        active_email_text = edited_email

    st.write("")

    # Download Buttons at Bottom
    week_suffix = st.session_state.settings.get("current_week", "Week").replace(" ", "_")
    single_filename = f"Feedback_{first_name_only}_{week_suffix}.txt"
    batch_filename = f"All_Feedback_Emails_{week_suffix}.txt"

    d_col1, d_col2 = st.columns(2)
    with d_col1:
        st.download_button(
            label=f"💾 Download {first_name_only}'s Email (.txt)",
            data=active_email_text,
            file_name=single_filename,
            mime="text/plain",
            use_container_width=True
        )

    with d_col2:
        all_emails_export = []
        for a_name in agents:
            all_emails_export.append("=" * 60)
            all_emails_export.append(f"AGENT: {a_name}")
            all_emails_export.append(f"SUBJECT: {subject_line}")
            all_emails_export.append("=" * 60)
            all_emails_export.append(st.session_state.generated_emails[a_name].get("email", ""))
            all_emails_export.append("\n\n")

        all_export_text = "\n".join(all_emails_export)
        st.download_button(
            label="📦 Download All Emails (.txt)",
            data=all_export_text,
            file_name=batch_filename,
            mime="text/plain",
            use_container_width=True
        )

else:
    if not st.session_state.parsed_agents:
        st.info("Upload an Excel report above to begin generating emails.")
