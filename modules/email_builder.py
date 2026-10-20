import re
from typing import Dict, List, Any, Tuple
from modules.anonymizer import (
    extract_first_name,
    scrub_sensitive_text
)
from modules.llm_engine import call_llm_resilient

def summarize_missed_area_with_ai(
    category: str,
    raw_reason: str,
    custom_rules: str,
    openrouter_key: str,
    groq_key: str
) -> str:
    """
    Transforms raw reviewer comments into a direct, punchy bullet point
    explaining specifically what the agent did wrong.
    """
    clean_cat = scrub_sensitive_text(category)
    clean_reason = scrub_sensitive_text(raw_reason)

    sys_prompt = (
        "You are a strict QA coach. Write a single, concise bullet point stating specifically "
        "what the agent did wrong on the call based on the reviewer notes.\n"
        "RULES:\n"
        "1. Start directly with what was done wrong (e.g., 'Failed to...', 'Did not...', 'Omitted...').\n"
        "2. Do NOT mention category labels, codes, or reviewer names.\n"
        "3. Zero conversational filler, zero fluff. Maximum 1 clear sentence.\n"
        "4. Never mention company names."
    )
    if custom_rules:
        sys_prompt += f"\nSupplementary guidelines: {custom_rules}"

    user_prompt = f"Category Context: {clean_cat}\nReviewer notes: {clean_reason}\nWhat did the agent do wrong?"
    try:
        summary, _, _ = call_llm_resilient(sys_prompt, user_prompt, openrouter_key, groq_key)
        summary = summary.replace('"', '').replace("'", "").strip()
        summary = re.sub(r"^[-*•\d.]+\s*", "", summary).strip()
        return summary
    except Exception:
        fallback = clean_reason if clean_reason else f"Did not meet requirements for {clean_cat}."
        return fallback

def convert_email_to_rich_html(plain_text: str) -> str:
    """
    Converts plain text email into email-client compliant Rich HTML with inline styles.
    When copied to clipboard as text/html, Gmail and Outlook paste this natively with
    true bold headings and real indented bullet lists.
    """
    html_out = [
        '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; '
        'font-size: 14px; line-height: 1.6; color: #1e293b; max-width: 650px;">'
    ]

    paragraphs = plain_text.split("\n\n")
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Detect call headers like [0790144494 and 85%]
        if para.startswith("[") and "]" in para:
            lines = para.split("\n")
            header = lines[0].strip()
            html_out.append(
                f'<p style="margin: 18px 0 6px 0; font-size: 15px; font-weight: bold; color: #0f172a; '
                f'background-color: #f1f5f9; padding: 6px 10px; border-radius: 4px; display: inline-block;">{header}</p>'
            )

            rest = lines[1:]
            bullets = [l.strip() for l in rest if l.strip().startswith("•")]
            non_bullets = [l.strip() for l in rest if not l.strip().startswith("•")]

            for nb in non_bullets:
                if nb:
                    html_out.append(f'<p style="margin: 4px 0 8px 0; color: #334155;">{nb}</p>')

            if bullets:
                html_out.append('<ul style="margin: 6px 0 16px 0; padding-left: 22px;">')
                for b in bullets:
                    cleaned_b = b.lstrip("•").strip()
                    html_out.append(f'<li style="margin-bottom: 5px; color: #334155;">{cleaned_b}</li>')
                html_out.append('</ul>')

        else:
            # Regular text paragraphs (Greeting, Week Summary, Closing note)
            html_out.append(f'<p style="margin: 0 0 14px 0; color: #1e293b;">{para}</p>')

    html_out.append('</div>')
    return "".join(html_out)

def build_feedback_email_for_agent(
    agent_name: str,
    calls: List[Dict[str, Any]],
    week: str,
    custom_rules: str,
    openrouter_key: str,
    groq_key: str,
    status_callback=None
) -> Tuple[str, str, str]:
    """
    Deterministic Structural Assembler:
    Guarantees true headings, true bullets, exact spacing, and zero verbosity.
    """
    first_name = extract_first_name(agent_name)
    total_calls = len(calls)
    scores = [c["qa_score"] for c in calls]
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    all_100 = all(c["qa_score"] >= 100 and len(c.get("missed_areas", [])) == 0 for c in calls)

    # 1. SPECIAL CASE: All calls 100%
    if all_100:
        email = (
            f"Dear {first_name}\n\n"
            f"Well done for scoring 100% in all the calls audited for this week. keep up the good work."
        )
        return email, "Deterministic Rule", "Internal"

    # 2. Standard Consolidation
    email_blocks = []
    email_blocks.append(f"Dear {first_name}")

    verb = "was" if total_calls == 1 else "were"
    call_word = "call" if total_calls == 1 else "calls"
    email_blocks.append(f"In {week}, {total_calls} of your {call_word} {verb} audited averaging {avg_score}%. Below are the missed areas;")

    has_any_missed_area = False

    for idx, call in enumerate(calls, start=1):
        phone_num = str(call.get("phone", f"Call #{idx}")).strip()
        score_val = call.get("qa_score", 0)
        missed = call.get("missed_areas", [])

        call_header = f"[{phone_num} and {int(score_val) if score_val.is_integer() else score_val}%]"

        if score_val >= 100 and not missed:
            call_content = f"{call_header}\nYou scored 100% in this call. Good job"
            email_blocks.append(call_content)
        else:
            has_any_missed_area = True
            bullet_lines = [call_header]
            for item in missed:
                cat = item.get("category", "")
                reason = item.get("reason", "")
                
                bullet_desc = summarize_missed_area_with_ai(
                    category=cat,
                    raw_reason=reason,
                    custom_rules=custom_rules,
                    openrouter_key=openrouter_key,
                    groq_key=groq_key
                )
                bullet_lines.append(f"• {bullet_desc}")

            email_blocks.append("\n".join(bullet_lines))

    if has_any_missed_area:
        email_blocks.append("Please work on the highlighted areas. I have attached the audited call for your reference.")

    final_email = "\n\n".join(email_blocks)
    return final_email, "Hybrid Engine (Rich Format)", "OpenRouter/Groq"
