import re
from typing import Dict, List, Any, Tuple

# Company names, brands, and internal system labels to scrub from text
FORBIDDEN_IDENTIFIERS = [
    r"\bm-kopa\b",
    r"\bmkopa\b",
    r"\bcci inbound\b",
    r"\bcci\b",
]

# Regex patterns for accidental phone numbers and email addresses in comments
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(\+?\d{1,4}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4,6}")

def extract_first_name(full_name: str) -> str:
    """Extracts and cleanly capitalizes the first name from a full name."""
    if not full_name or not isinstance(full_name, str):
        return "Team Member"
    parts = full_name.strip().split()
    return parts[0].capitalize() if parts else "Team Member"

def scrub_sensitive_text(text: str) -> str:
    """
    Strips email addresses, company names, and stray contact details
    from raw reviewer comments before passing them to the AI.
    """
    if not text or not isinstance(text, str):
        return ""
    
    cleaned = text
    # 1. Scrub emails
    cleaned = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", cleaned)
    
    # 2. Scrub company names
    for pattern in FORBIDDEN_IDENTIFIERS:
        cleaned = re.sub(pattern, "the company", cleaned, flags=re.IGNORECASE)
    
    # 3. Scrub stray phone numbers in comments
    cleaned = PHONE_PATTERN.sub("[PHONE_REDACTED]", cleaned)
    
    return cleaned.strip()

def create_anonymized_payload(
    agent_full_name: str,
    calls_data: List[Dict[str, Any]]
) -> Tuple[str, List[Dict[str, Any]], Dict[str, str]]:
    """
    Prepares data for the LLM by replacing:
    - Agent first name with {{AGENT_FIRST_NAME}}
    - Each customer phone with {{CALL_1_NUMBER}}, {{CALL_2_NUMBER}}, etc.
    - Stripping all evaluator details and company names.
    
    Returns:
      (anonymized_agent_token, anonymized_calls_list, pii_restoration_map)
    """
    first_name = extract_first_name(agent_full_name)
    agent_token = "{{AGENT_FIRST_NAME}}"
    
    restoration_map: Dict[str, str] = {
        agent_token: first_name,
        "[First name]": first_name,
        "[First Name]": first_name
    }
    
    anonymized_calls = []
    
    for idx, call in enumerate(calls_data, start=1):
        phone_token = f"{{{{CALL_{idx}_NUMBER}}}}"
        raw_phone = str(call.get("phone", f"Call-{idx}")).strip()
        restoration_map[phone_token] = raw_phone
        
        # Scrub comments for any category failures
        scrubbed_missed_areas = []
        for fail in call.get("missed_areas", []):
            scrubbed_missed_areas.append({
                "category": scrub_sensitive_text(fail.get("category", "")),
                "reason": scrub_sensitive_text(fail.get("reason", ""))
            })
            
        anonymized_calls.append({
            "call_index": idx,
            "phone_token": phone_token,
            "qa_score": call.get("qa_score", 0),
            "is_100": call.get("qa_score", 0) >= 100,
            "missed_areas": scrubbed_missed_areas
        })
        
    return agent_token, anonymized_calls, restoration_map

def restore_pii(text: str, restoration_map: Dict[str, str]) -> str:
    """
    Swaps all privacy tokens (e.g. {{AGENT_FIRST_NAME}}, {{CALL_1_NUMBER}})
    back to the actual agent first name and real phone numbers.
    """
    if not text:
        return ""
    
    restored = text
    for token, original_value in restoration_map.items():
        restored = restored.replace(token, original_value)
        
    return restored
