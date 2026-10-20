import re
from typing import Dict, List, Any, Tuple
from modules.anonymizer import (
    extract_first_name,
    create_anonymized_payload,
    restore_pii
)
from modules.llm_engine import call_llm_resilient

def clean_formatted_bullets(text: str) -> str:
    """Standardizes bullet points into true unicode bullets (• ) with clean indentation."""
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Convert asterisk, dash, or number bullets to true unicode bullet
        if re.match(r"^[-*•]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            clean_item = re.sub(r"^[-*•\d.]+\s*", "", stripped)
            cleaned_lines.append(f"• {clean_item}")
        else:
            cleaned_lines.append(line)
    
    # Ensure double line breaks between paragraphs
    joined = "\n".join(cleaned_lines)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()

def build_feedback_email_for_agent(
    agent_name: str,
    calls: List[Dict[str, Any]],
    week: str,
    custom_rules: str,
    openrouter_key: str,
    groq_key: str,
    status_callback=None
) -> Tuple[str, str, str]:
    """Generates strictly formatted QA feedback emails with true headings and bullets."""
    first_name = extract_first_name(agent_name)
    total_calls = len(calls)
    scores = [c["qa_score"] for c in calls]
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    all_100 = all(c["qa_score"] >= 100 and len(c.get("missed_areas", [])) == 0 for c in calls)

    # Hardcoded Fast-Path: 100% in all calls
    if all_100:
        email = (
            f"Dear {first_name}\n\n"
            f"Well done for scoring 100% in all the calls audited for this week. keep up the good work."
        )
        return email, "Deterministic Rule", "Internal"

    # Zero-PII Payload
    agent_token, anon_calls, token_map = create_anonymized_payload(agent_name, calls)

    system_prompt = (
        "You are an automated Quality Assurance email writer.\n"
        "Generate direct, strictly formatted feedback emails following these exact layout rules.\n\n"
        "FORMATTING RULES:\n"
        "1. ZERO verbosity. No pleasantries beyond 'Dear [Name]', no sign-offs, no signatures.\n"
        "2. Structure MUST strictly match this template:\n\n"
        f"Dear {agent_token}\n\n"
        f"In {week}, {total_calls} of your calls {'was' if total_calls == 1 else 'were'} audited averaging {avg_score}%. Below are the missed areas;\n\n"
        "For each call that had missed areas:\n"
        "[Calling Number and score]\n"
        "• State clearly and concisely what was done wrong\n"
        "• State clearly and concisely what was done wrong\n\n"
        "If a specific call scored 100%, write exactly:\n"
        "[Calling Number and 100%]\n"
        "You scored 100% in this call. Good job\n\n"
        "End with this exact sentence:\n"
        "Please work on the highlighted areas. I have attached the audited call for your reference.\n\n"
        "3. Use true bullet points (• ) for missed areas. Never use numbers, dashes, or asterisks.\n"
        "4. Never mention company names, reviewer names, or email addresses."
    )

    if custom_rules and custom_rules.strip():
        system_prompt += f"\n\nSUPPLEMENTARY INSTRUCTIONS:\n{custom_rules.strip()}"

    user_prompt_lines = [
        f"Generate the feedback email for {agent_token}.",
        f"Target Scope: {week}",
        f"Total calls: {total_calls}",
        f"Average QA Score: {avg_score}%\n",
        "Audited Calls Data:"
    ]

    for c in anon_calls:
        phone_tok = c["phone_token"]
        score_val = c["qa_score"]
        user_prompt_lines.append(f"\nCall: [{phone_tok} and {score_val}%]")
        if c["is_100"] and not c["missed_areas"]:
            user_prompt_lines.append("- Score: 100% (No missed areas)")
        else:
            for item in c["missed_areas"]:
                user_prompt_lines.append(f"- Category: {item['category']} | Reason: {item['reason']}")

    user_prompt = "\n".join(user_prompt_lines)

    raw_response, model_used, provider = call_llm_resilient(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        openrouter_key=openrouter_key,
        groq_key=groq_key,
        status_callback=status_callback
    )

    # Re-insert real agent name & calling numbers
    restored_email = restore_pii(raw_response, token_map)
    final_email = clean_formatted_bullets(restored_email)

    return final_email, model_used, provider
