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
    """Uses LLM to summarize a missed area into a single concise sentence describing what went wrong."""
    clean_cat = scrub_sensitive_text(category)
    clean_reason = scrub_sensitive_text(raw_reason)

    # If the comment is already very brief and direct, use it without overhead
    if len(clean_reason.split()) <= 8 and "failed" not in clean_reason.lower():
        return f"{clean_cat}: {clean_reason}"

    sys_prompt = (
        "You are a strict QA coach. Summarize what the agent did wrong into a single concise phrase. "
        "Do not write greetings, pleasantries, or preamble. Aim for 0 verbosity. "
        "Never mention company names or customer names."
    )
    if custom_rules:
        sys_prompt += f"\nSupplementary rules: {custom_rules}"

    user_prompt = f"Category: {clean_cat}\nReviewer notes: {clean_reason}\nWhat did the agent do wrong?"
    try:
        summary, _, _ = call_llm_resilient(sys_prompt, user_prompt, openrouter_key, groq_key)
        # Clean any trailing punctuation or extra quotes
        summary = summary.replace('"', '').replace("'", "").strip()
        return f"{clean_cat}: {summary}"
    except Exception:
        return f"{clean_cat}: {clean_reason}"

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
    Guarantees true headings, true unicode bullets, exact paragraph spacing,
    and 100% adherence to rules without relying on LLM to format lines.
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

    # 2. Standard Structural Build
    email_blocks = []
    email_blocks.append(f"Dear {first_name}")
    
    verb = "was" if total_calls == 1 else "were"
    call_word = "call" if total_calls == 1 else "calls"
    email_blocks.append(f"In {week}, {total_calls} of your {call_word} {verb} audited averaging {avg_score}%. Below are the missed areas;")

    has_any_missed_area = False
    models_used = set()

    for idx, call in enumerate(calls, start=1):
        phone_num = str(call.get("phone", f"Call #{idx}")).strip()
        score_val = call.get("qa_score", 0)
        missed = call.get("missed_areas", [])

        # Heading format: [Calling Number and score]
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
                
                # Polish the missed point
                bullet_desc = summarize_missed_area_with_ai(
                    category=cat,
                    raw_reason=reason,
                    custom_rules=custom_rules,
                    openrouter_key=openrouter_key,
                    groq_key=groq_key
                )
                bullet_lines.append(f"• {bullet_desc}")
                
            email_blocks.append("\n".join(bullet_lines))

    # Closing statement
    if has_any_missed_area:
        email_blocks.append("Please work on the highlighted areas. I have attached the audited call for your reference.")

    final_email = "\n\n".join(email_blocks)
    return final_email, "Hybrid Engine (Deterministic + LLM)", "OpenRouter/Groq"
