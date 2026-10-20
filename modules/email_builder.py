from typing import Dict, List, Any, Tuple
from modules.anonymizer import (
    extract_first_name,
    create_anonymized_payload,
    restore_pii
)
from modules.llm_engine import call_llm_resilient

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
    Constructs the prompt, enforces hardcoded QA formatting rules,
    runs the zero-PII sanitization pipeline, calls the resilient LLM engine,
    and restores real agent names and customer calling numbers.
    
    Returns: (final_email_text, model_used, provider_used)
    """
    first_name = extract_first_name(agent_name)
    total_calls = len(calls)
    scores = [c["qa_score"] for c in calls]
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    all_100 = all(c["qa_score"] >= 100 and len(c.get("missed_areas", [])) == 0 for c in calls)

    # 1. Hardcoded Fast-Path: If ALL calls scored 100%, return the exact required message directly
    if all_100:
        email = (
            f"Dear {first_name}\n\n"
            f"Well done for scoring 100% in all the calls audited for this week. keep up the good work."
        )
        return email, "Rule-Engine (Instant)", "Internal"

    # 2. Anonymize all data before preparing the LLM prompt (Zero PII)
    agent_token, anon_calls, token_map = create_anonymized_payload(agent_name, calls)

    # 3. Build Strict System Prompt
    system_prompt = (
        "You are an automated Quality Assurance email generator.\n"
        "Generate direct feedback emails based strictly on QA audit scores and missed areas.\n\n"
        "STRICT HARDCODED RULES:\n"
        "1. ZERO verbosity. NO introductory filler, NO pleasantries beyond 'Dear [Name]', NO fluff.\n"
        "2. NO signatures of any kind. Never sign off with a name, role, or team.\n"
        "3. Maintain EXACT structure as follows:\n\n"
        f"Dear {agent_token}\n\n"
        f"In {week}, {total_calls} of your calls {'was' if total_calls == 1 else 'were'} audited averaging {avg_score}%. Below are the missed areas;\n\n"
        "For each call:\n"
        "[Calling Number and score]\n"
        "• Bullet point stating clearly what the agent did wrong\n"
        "• Bullet point stating clearly what the agent did wrong\n\n"
        "If a specific call scored 100%, the section for that call MUST be exactly:\n"
        "[Calling Number and 100%]\n"
        "You scored 100% in this call. Good job\n\n"
        "After listing all calls, end with this exact line (only if there are missed areas):\n"
        "Please work on the highlighted areas. I have attached the audited call for your reference.\n\n"
        "4. DO NOT mention company names, evaluator names, or email addresses.\n"
        "5. Under each call header, list ONLY what they did wrong in concise bullet points."
    )

    if custom_rules and custom_rules.strip():
        system_prompt += f"\n\nSUPPLEMENTARY RULES (Follow these alongside the above):\n{custom_rules.strip()}"

    # 4. Build User Prompt with Anonymized Data
    user_prompt_lines = [
        f"Generate the feedback email for {agent_token}.",
        f"Evaluation scope: {week}",
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
                user_prompt_lines.append(f"- Category: {item['category']} | Missed Detail: {item['reason']}")

    user_prompt = "\n".join(user_prompt_lines)

    # 5. Call LLM through the Resilient Multi-Provider Fallback Engine
    raw_response, model_used, provider = call_llm_resilient(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        openrouter_key=openrouter_key,
        groq_key=groq_key,
        status_callback=status_callback
    )

    # 6. Re-insert real agent name and customer phone numbers locally
    final_email = restore_pii(raw_response, token_map)

    return final_email, model_used, provider
