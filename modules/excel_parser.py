import pandas as pd
import re
from typing import Dict, List, Any

# Rubric score columns and their corresponding comment/explanation columns
RUBRIC_MAPPINGS = [
    {
        "category": "Call Opening & Professionalism",
        "score_col_hints": ["professionalism"],
        "comment_col_hints": ["call opening comments", "opening comments"]
    },
    {
        "category": "Identification and KYC Checks",
        "score_col_hints": ["identification and kyc checks", "kyc checks:"],
        "comment_col_hints": ["kyc checks comments", "identification comments"]
    },
    {
        "category": "Telephone Etiquette - Enthusiasm",
        "score_col_hints": ["enthusiasm:"],
        "comment_col_hints": ["telephone etiquette (service mindset) commments", "telephone etiquette"]
    },
    {
        "category": "Telephone Etiquette - Active Listening & Empathy",
        "score_col_hints": ["active listening & empathy", "active listening"],
        "comment_col_hints": ["telephone etiquette (service mindset) commments", "telephone etiquette"]
    },
    {
        "category": "Telephone Etiquette - Clear Communication",
        "score_col_hints": ["clear communication"],
        "comment_col_hints": ["telephone etiquette (service mindset) commments", "telephone etiquette"]
    },
    {
        "category": "Process Compliance - Understanding of Issue",
        "score_col_hints": ["understanding of the issue"],
        "comment_col_hints": ["a. process compliance comments", "process compliance comments"]
    },
    {
        "category": "Process Compliance - Troubleshooting",
        "score_col_hints": ["correct troubleshooting"],
        "comment_col_hints": ["b. process compliance comments", "process compliance comments"]
    },
    {
        "category": "Process Compliance - Customer Education",
        "score_col_hints": ["customer education"],
        "comment_col_hints": ["b. process compliance comments", "process compliance comments"]
    },
    {
        "category": "Issue Resolution",
        "score_col_hints": ["resolve:", "escalates:", "calls back:"],
        "comment_col_hints": ["issue resolution comments"]
    },
    {
        "category": "Call Closing - Wrap Up & Closing Procedure",
        "score_col_hints": ["wrap up :", "closing procedure:"],
        "comment_col_hints": ["call closing comments"]
    }
]

def find_column(columns: List[str], search_terms: List[str]) -> str:
    """Finds a column name in the sheet matching any of the search terms."""
    for term in search_terms:
        for col in columns:
            if term.lower() in str(col).lower():
                return col
    return ""

def clean_qa_score(val: Any) -> float:
    """Safely converts QA score values like '100%', '85', 0.85 to a float percentage (e.g. 100.0, 85.0)."""
    if pd.isna(val) or val is None or val == "":
        return 0.0
    s = str(val).replace("%", "").strip()
    try:
        score = float(s)
        if 0 < score <= 1.0:
            score = score * 100
        return round(score, 1)
    except ValueError:
        return 0.0

def parse_excel_report(file_bytes) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parses the QA Excel file:
    - Ignores 'Total score', uses 'QA score'.
    - Groups rows by Agent Name.
    - Flags any rubric category with a 0 as a missed area.
    - Sorts all agents in strict alphabetical order (A-Z).
    """
    df = pd.read_excel(file_bytes)
    cols = list(df.columns)
    
    agent_col = find_column(cols, ["name of customer care representative", "ccr) being scored", "agent name"])
    phone_col = find_column(cols, ["customer's phone number", "phone number", "calling number"])
    qa_score_col = find_column(cols, ["qa score"])
    crit_error_flag_col = find_column(cols, ["did the ccr make a critical error"])
    crit_error_comment_col = find_column(cols, ["critical error comments", "specific critical error"])
    
    if not agent_col:
        raise ValueError("Could not find CCR Agent Name column in the uploaded file.")
    if not phone_col:
        raise ValueError("Could not find Customer Phone Number column in the uploaded file.")
    if not qa_score_col:
        raise ValueError("Could not find 'QA score' column in the uploaded file.")

    grouped_agents: Dict[str, List[Dict[str, Any]]] = {}

    for _, row in df.iterrows():
        agent_name = str(row.get(agent_col, "")).strip()
        if not agent_name or agent_name.lower() == "nan":
            continue

        calling_number = str(row.get(phone_col, "Unknown Number")).strip()
        qa_score = clean_qa_score(row.get(qa_score_col, 0))

        missed_areas = []

        # Check for Critical Errors
        if crit_error_flag_col:
            flag_val = str(row.get(crit_error_flag_col, "")).strip().lower()
            if flag_val in ["yes", "true", "1"]:
                crit_desc = str(row.get(crit_error_comment_col, "Critical error committed.")).strip()
                if crit_desc.lower() == "nan" or not crit_desc:
                    crit_desc = "Critical error flagged on call."
                missed_areas.append({
                    "category": "Critical Error",
                    "reason": crit_desc
                })

        # Scan each rubric category for a score of 0
        for rubric in RUBRIC_MAPPINGS:
            for s_hint in rubric["score_col_hints"]:
                matched_s_col = find_column(cols, [s_hint])
                if matched_s_col:
                    raw_score = row.get(matched_s_col)
                    try:
                        numeric_score = float(str(raw_score).replace("%", "").strip())
                    except (ValueError, TypeError):
                        numeric_score = None

                    if numeric_score == 0:
                        reason_text = ""
                        for c_hint in rubric["comment_col_hints"]:
                            matched_c_col = find_column(cols, [c_hint])
                            if matched_c_col:
                                c_val = str(row.get(matched_c_col, "")).strip()
                                if c_val and c_val.lower() != "nan":
                                    reason_text = c_val
                                    break
                        
                        if not reason_text:
                            reason_text = f"Failed requirements for {rubric['category']}."

                        missed_areas.append({
                            "category": rubric["category"],
                            "reason": reason_text
                        })
                        break

        call_data = {
            "phone": calling_number,
            "qa_score": qa_score,
            "missed_areas": missed_areas
        }

        if agent_name not in grouped_agents:
            grouped_agents[agent_name] = []
        grouped_agents[agent_name].append(call_data)

    # Sort dictionary alphabetically by Agent Name (A to Z)
    sorted_agents = dict(sorted(grouped_agents.items(), key=lambda item: item[0].strip().lower()))
    return sorted_agents
