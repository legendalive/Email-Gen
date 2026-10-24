import streamlit as st
import streamlit.components.v1 as components
import json
import re
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

def render_copy_toolbar(first_name: str, subject_line: str, email_body: str, key_suffix: int):
    """Renders 3 clean, unclipped copy buttons with rich HTML + plain text clipboard support."""
    rich_html = convert_email_to_rich_html(email_body)
    
    json_name = json.dumps(first_name)
    json_subj = json.dumps(subject_line)
    json_body_plain = json.dumps(email_body)
    json_body_html = json.dumps(rich_html)

    html_code = f"""
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            margin: 0;
            padding: 2px 0 0 0;
            background: transparent;
            overflow: hidden;
        }}
        .toolbar-wrap {{
            display: flex;
            gap: 8px;
            align-items: center;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            flex-wrap: nowrap;
        }}
        .c-btn {{
            background-color: #f0f2f6;
            color: #31333f;
            border: 1px solid #d6d6d8;
            padding: 7px 13px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 6px;
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

    <div class="toolbar-wrap">
        <button id="b_name" class="c-btn" onclick="copyName()">
            👤 Copy Name: {first_name}
        </button>
        <button id="b_subj" class="c-btn" onclick="copySubject()">
            📌 Copy Subject
        </button>
        <button id="b_body" class="c-btn c-btn-red" onclick="copyBody()">
            ✉️ Copy Email Body
        </button>
    </div>

    <script>
    const nameVal = {json_name};
    const subjVal = {json_subj};
    const bodyPlain = {json_body_plain};
    const bodyHtml = {json_body_html};

    function copyName() {{
        doCopyPlain(nameVal, 'b_name', '👤 Copy Name: {first_name}');
    }}

    function copySubject() {{
        doCopyPlain(subjVal, 'b_subj', '📌 Copy Subject');
    }}

    async function copyBody() {{
        if (navigator.clipboard && window.ClipboardItem) {{
            try {{
                const blobHtml = new Blob([bodyHtml], {{ type: 'text/html' }});
                const blobPlain = new Blob([bodyPlain], {{ type: 'text/plain' }});
                const item = new ClipboardItem({{ 'text/html': blobHtml, 'text/plain': blobPlain }});
                await navigator.clipboard.write([item]);
                showSuccess('b_body', '✉️ Copy Email Body');
                return;
            }} catch (err) {{
                console.warn('ClipboardItem failed:', err);
            }}
        }}

        const container = document.createElement('div');
        container.innerHTML = bodyHtml;
        container.style.position = 'fixed';
        container.style.left = '-9999px';
        document.body.appendChild(container);

        const range = document.createRange();
        range.selectNodeContents(container);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);

        try {{
            document.execCommand('copy');
            showSuccess('b_body', '✉️ Copy Email Body');
        }} catch (e) {{
            navigator.clipboard.writeText(bodyPlain);
            showSuccess('b_body', '✉️ Copy Email Body');
        }}
        sel.removeAllRanges();
        document.body.removeChild(container);
    }}

    function doCopyPlain(text, btnId, originalLabel) {{
        if (navigator.clipboard && window.isSecureContext) {{
            navigator.clipboard.writeText(text).then(() => showSuccess(btnId, originalLabel))
            .catch(() => fallbackPlain(text, btnId, originalLabel));
        }} else {{
            fallbackPlain(text, btnId, originalLabel);
        }}
    }}

    function fallbackPlain(text, btnId, originalLabel) {{
        const temp = document.createElement("textarea");
        temp.value = text;
        temp.style.position = "fixed";
        temp.style.left = "-9999px";
        document.body.appendChild(temp);
        temp.focus();
        temp.select();
        try {{
            document.execCommand('copy');
            showSuccess(btnId, originalLabel);
        }} catch(e) {{
            alert("Copy failed. Please copy manually.");
        }}
        document.body.removeChild(temp);
    }}

    function showSuccess(btnId, originalText) {{
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
    components.html(html_code, height=50)

# ----------------- SIDEBAR: SETTINGS -----------------
with st.sidebar:
    st.title("⚙️ System Settings")
    st.caption("Cascade: Gemini → OpenRouter → Groq")

    # 1. Google Gemini Section (FIRST OPTION)
    st.subheader("🌟 Google Gemini (Primary / #1)")
    gemini_key = st.text_input(
        "Gemini API Key",
        value=st.session_state.settings.get("gemini_api_key", ""),
        type="password",
        help="Primary API. Automatically discovers and selects the best active Gemini model."
    )
    if st.button("⚡ Test Gemini", use_container_width=True):
        with st.spinner("Pinging Google Gemini API..."):
            ok, model_or_err, lat = test_gemini_connection(gemini_key.strip())
            if ok:
                st.success(f"Connected in {lat}s!\nModel: `{model_or_err}`")
            else:
                st.error(f"Failed ({lat}s): {model_or_err}")

    st.divider()

    # 2. OpenRouter Section (SECOND OPTION)
    st.subheader("🔑 OpenRouter (Secondary / #2)")
    openrouter_key = st.text_input(
        "OpenRouter API Key",
        value=st.session_state.settings.get("openrouter_api_key", ""),
        type="password",
        help="Secondary option. Dynamically selects live $0 free models."
    )
    if st.button("⚡ Test OpenRouter", use_container_width=True):
        with st.spinner("Testing OpenRouter..."):
            ok, model_or_err, lat = test_openrouter_connection(openrouter_key.strip())
            if ok:
                st.success(f"Connected in {lat}s!\nModel: `{model_or_err}`")
            else:
                st.error(f"Failed ({lat}s): {model_or_err}")

    st.divider()

    # 3. Groq Section (FALLBACK OPTION)
    st.subheader("⚡ Groq (Fallback / #3)")
    groq_key = st.text_input(
        "Groq API Key",
        value=st.session_state.settings.get("groq_api_key", ""),
        type="password",
        help="High-speed fallback pool if Gemini and OpenRouter are unavailable."
    )
    if st.button("⚡ Test Groq", use_container_width=True):
        with st.spinner("Pinging Groq server..."):
            ok, model_or_err, lat = test_groq_connection(groq_key.strip())
            if ok:
                st.success(f"Connected in {lat}s!\nModel: `{model_or_err}`")
            else:
                st.error(f"Failed ({lat}s): {model_or_err}")

    st.divider()

    # 4. Scope & Custom Rules
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

# System Readiness Monitor (4 Columns)
col1, col2, col3, col4 = st.columns(4)
has_gemini = bool(st.session_state.settings.get("gemini_api_key"))
has_or = bool(st.session_state.settings.get("openrouter_api_key"))
has_groq = bool(st.session_state.settings.get("groq_api_key"))

with col1:
    st.metric(
        "Gemini (Primary)",
        "Configured" if has_gemini else "Missing",
        "Ready" if has_gemini else "- Recommended",
        delta_color="normal" if has_gemini else "inverse"
    )
with col2:
    st.metric(
        "OpenRouter",
        "Configured" if has_or else "Not Set",
        "Secondary" if has_or else "Optional",
        delta_color="normal" if has_or else "off"
    )
with col3:
    st.metric(
        "Groq",
        "Configured" if has_groq else "Not Set",
        "Fallback" if has_groq else "Optional",
        delta_color="normal" if has_groq else "off"
    )
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
