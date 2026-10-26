import re
from typing import Dict, List, Any, Tuple
from modules.anonymizer import (
    extract_first_name,
    scrub_sensitive_text
)
from modules.llm_engine import call_llm_resilient

CATEGORY_CLEAN_MAP = {
    "call opening": "Call Opening & Professionalism",
    "identification": "KYC & Verification",
    "enthusiasm": "Tone & Enthusiasm",
    "active listening": "Active Listening & Empathy",
    "clear communication": "Clear Communication & Etiquette",
    "telephone etiquette": "Clear Communication & Etiquette",
    "understanding": "Understanding the Issue",
    "troubleshooting": "Process Compliance & Troubleshooting",
    "process compliance": "Process Compliance",
    "customer education": "Customer Education",
    "issue resolution": "Issue Resolution",
    "resolve": "Issue Resolution",
    "escalates": "Issue Escalation",
    "calls back": "Callback Procedure",
    "call closing": "Closing Procedure",
    "closing procedure": "Closing Procedure",
    "critical error": "Critical Process Compliance"
}

def clean_category_name(raw_cat: str) -> str:
    """Standardizes rubric names into clean corporate headings."""
    lower = raw_cat.lower()
    for key, val in CATEGORY_CLEAN_MAP.items():
        if key in lower:
            return val
    cleaned = raw_cat.split("-")[-1].strip()
    return cleaned.title() if cleaned else "Process Compliance"

def summarize_missed_area_with_ai(
    category: str,
    raw_reason: str,
    custom_rules: str,
    gemini_key: str = "",
    openrouter_key: str = "",
    groq_key: str = ""
) -> str:
    """
    Transforms reviewer notes into actionable, positive coaching advice starting
    with an active directive verb. Cascades: Gemini -> OpenRouter -> Groq.
    """
    clean_cat = scrub_sensitive_text(category)
    clean_reason = scrub_sensitive_text(raw_reason)

    sys_prompt = (
        "You are an executive QA coach writing formal email feedback to an agent.\n"
        "Transform the audit notes into a single constructive, actionable coaching sentence.\n"
        "RULES:\n"
        "1. Start directly with an active directive verb (e.g., 'Personalize the conversation...', "
        "'Offer further assistance...', 'Ensure mandatory verification is completed...').\n"
        "2. Do NOT mention category labels, codes, or reviewer names.\n"
        "3. Zero conversational filler, zero preamble. Maximum 1 concise sentence.\n"
        "4. Never mention company names."
    )
    if custom_rules:
        sys_prompt += f"\nSupplementary guidelines: {custom_rules}"

    user_prompt = f"Category: {clean_cat}\nNotes: {clean_reason}\nProvide positive, formal coaching advice:"
    try:
        advice, _, _ = call_llm_resilient(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            gemini_key=gemini_key,
            openrouter_key=openrouter_key,
            groq_key=groq_key
        )
        advice = advice.replace('"', '').replace("'", "").strip()
        advice = re.sub(r"^[-*•◦\d.]+\s*", "", advice).strip()
        return advice
    except Exception:
        fallback = clean_reason if clean_reason else f"Adhere to company procedures for {clean_cat}."
        return fallback

def convert_email_to_rich_html(plain_text: str) -> str:
    """
    Converts plain text into email-client compliant Rich HTML with native nested lists.
    Enforces font-size: 9pt with unforced native colors.
    """
    html_out = [
        '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; '
        'font-size: 9pt; line-height: 1.5; max-width: 650px;">'
    ]

    blocks = plain_text.split("\n\n")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if block.startswith("• Call") or "\n• Call" in block:
            lines = block.split("\n")
            html_out.append('<ul style="list-style-type: disc; margin: 10px 0 14px 0; padding-left: 18px;">')
            
            in_sublist = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("• Call"):
                    if in_sublist:
                        html_out.append('</ul></li>')
                        in_sublist = False
                    
                    call_title = stripped.lstrip("•").strip()
                    html_out.append(f'<li style="margin-bottom: 8px; font-size: 9pt;"><b>{call_title}</b>')
                    html_out.append('<ul style="list-style-type: circle; margin-top: 3px; margin-bottom: 5px; padding-left: 20px;">')
                    in_sublist = True
                elif stripped.startswith("◦"):
                    item_text = stripped.lstrip("◦").strip()
                    if ":" in item_text:
                        cat_part, advice_part = item_text.split(":", 1)
                        formatted_item = f"<b>{cat_part.strip()}:</b> {advice_part.strip()}"
                    else:
                        formatted_item = item_text
                    html_out.append(f'<li style="margin-bottom: 3px; font-weight: normal; font-size: 9pt;">{formatted_item}</li>')
                elif stripped:
                    html_out.append(f'<li style="margin-bottom: 3px; font-weight: normal; font-size: 9pt;">{stripped}</li>')

            if in_sublist:
                html_out.append('</ul></li>')
            html_out.append('</ul>')

        else:
            html_out.append(f'<p style="margin: 0 0 10px 0; font-size: 9pt;">{block}</p>')

    html_out.append('</div>')
    return "".join(html_out)

def build_feedback_email_for_agent(
    agent_name: str,
    calls: List[Dict[str, Any]],
    week: str,
    custom_rules: str,
    gemini_key: str = "",
    openrouter_key: str = "",
    groq_key: str = "",
    status_callback=None
) -> Tuple[str, str, str]:
    """
    Formal QA Breakdown Assembler:
    Guarantees every penalized call (< 100%) has an explanatory coaching bullet.
    """
    first_name = extract_first_name(agent_name)
    total_calls = len(calls)
    scores = [c["qa_score"] for c in calls]
    
    raw_avg = sum(scores) / len(scores) if scores else 0
    avg_score_str = f"{int(raw_avg)}" if raw_avg.is_integer() else f"{round(raw_avg, 1)}"
    
    all_100 = all(c["qa_score"] >= 100 and len(c.get("missed_areas", [])) == 0 for c in calls)

    # 1. SPECIAL CASE: All calls 100%
    if all_100:
        email = (
            f"Hi {first_name},\n\n"
            f"Well done for scoring 100% in all the calls audited for this week. keep up the good work."
        )
        return email, "Deterministic Rule", "Internal"

    # 2. Formal Structure
    email_blocks = []
    email_blocks.append(f"Hi {first_name},")

    clean_week = week.strip().lower() if week.strip().lower().startswith("week") else f"week {week.strip()}"
    call_word = "call was" if total_calls == 1 else "calls were"
    email_blocks.append(f"{total_calls} of your {call_word} audited for {clean_week}. You averaged {avg_score_str}%. Below is a breakdown of the audited calls")

    call_sections = []
    has_any_missed = False

    for idx, call in enumerate(calls, start=1):
        phone_num = str(call.get("phone", f"070000000{idx}")).strip()
        score_val = call.get("qa_score", 0)
        score_str = f"{int(score_val)}" if score_val.is_integer() else f"{round(score_val, 1)}"
        missed = call.get("missed_areas", [])

        call_lines = [f"• Call {phone_num} ({score_str}%)"]

        if score_val >= 100 and not missed:
            call_lines.append("    ◦ You scored 100% in this call. Good job")
        else:
            has_any_missed = True
            
            # Guarantee: If score < 100, we NEVER output a blank call without coaching advice
            if not missed:
                deduction = 100 - score_val
                ded_str = f"{int(deduction)}" if deduction.is_integer() else f"{round(deduction, 1)}"
                call_lines.append(f"    ◦ Process Compliance: Review call handling procedures to recover the {ded_str}% deduction on this interaction.")
            else:
                for item in missed:
                    raw_cat = item.get("category", "")
                    cat_label = clean_category_name(raw_cat)
                    reason = item.get("reason", "")
                    
                    coaching_advice = summarize_missed_area_with_ai(
                        category=raw_cat,
                        raw_reason=reason,
                        custom_rules=custom_rules,
                        gemini_key=gemini_key,
                        openrouter_key=openrouter_key,
                        groq_key=groq_key
                    )
                    call_lines.append(f"    ◦ {cat_label}: {coaching_advice}")

        call_sections.append("\n".join(call_lines))

    email_blocks.append("\n\n".join(call_sections))

    if has_any_missed:
        email_blocks.append("I have attached your penalized calls. Please work on the highlighted areas.")

    final_email = "\n\n".join(email_blocks)
    return final_email, "Formal Nested Engine", "Gemini/OpenRouter/Groq"
