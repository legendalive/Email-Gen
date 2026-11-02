import pandas as pd
import re
from typing import Dict, List, Any

# Independent rubric mapping with consolidated family labels
INDEPENDENT_RUBRICS = [
    {
        "category": "Call Opening & Professionalism",
        "family": "call_opening",
        "score_col_hints": ["professionalism - check if ccr", "professionalism"],
        "comment_col_hints": ["call opening comments", "opening comments"]
    },
    {
        "category": "KYC & Verification",
        "family": "kyc",
        "score_col_hints": ["identification and kyc checks:", "identification and kyc checks"],
        "comment_col_hints": ["kyc checks comments", "identification comments"]
    },
    {
        "category": "Tone & Enthusiasm",
        "family": "etiquette",
        "score_col_hints": ["enthusiasm: check if ccr's", "enthusiasm:"],
        "comment_col_hints": ["telephone etiquette (service mindset) commments", "telephone etiquette"]
    },
    {
        "category": "Active Listening & Empathy",
        "family": "etiquette",
        "score_col_hints": ["active listening & empathy:", "active listening & empathy"],
        "comment_col_hints": ["telephone etiquette (service mindset) commments", "telephone etiquette"]
    },
    {
        "category": "Clear Communication & Etiquette",
        "family": "etiquette",
        "score_col_hints": ["clear communication: check that ccr", "clear communication:"],
        "comment_col_hints": ["telephone etiquette (service mindset) commments", "telephone etiquette"]
    },
    {
        "category": "Understanding the Issue",
        "family": "process",
        "score_col_hints": ["understanding of the issue: did the ccr", "understanding of the issue:"],
        "comment_col_hints": ["a. process compliance comments", "process compliance comments"]
    },
    {
        "category": "Process Compliance & Troubleshooting",
        "family": "process",
        "score_col_hints": ["correct troubleshooting: (1) check", "correct troubleshooting:"],
        "comment_col_hints": ["b. process compliance comments", "process compliance comments"]
    },
    {
        "category": "Customer Education",
        "family": "process",
        "score_col_hints": ["customer education: check that ccr", "customer education:"],
        "comment_col_hints": ["b. process compliance comments", "process compliance comments"]
    },
    {
        "category": "Issue Resolution",
        "family": "resolution",
        "score_col_hints": ["resolve: check that ccr"],
        "comment_col_hints": ["issue resolution comments"]
    },
    {
        "category": "Issue Escalation",
        "family": "resolution",
        "score_col_hints": ["escalates: check that ccr"],
        "comment_col_hints": ["issue resolution comments"]
    },
    {
        "category": "Callback Procedure",
        "family": "resolution",
        "score_col_hints": ["calls back: check that ccr"],
        "comment_col_hints": ["issue resolution comments"]
    },
    {
        "category": "Wrap Up & Documentation",
        "family": "closing",
        "score_col_hints": ["wrap up : check that ccr", "wrap up:"],
        "comment_col_hints": ["call closing comments"]
    },
    {
        "category": "Closing Procedure",
        "family": "closing",
        "score_col_hints": ["closing procedure: check that ccr", "closing procedure:"],
        "comment_col_hints": ["call closing comments"]
    }
]

def normalize_str(val: Any) -> str:
    """Strips non-breaking spaces, excess whitespace, and lowers string."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", s).lower()

def clean_qa_score(val: Any) -> float:
    """Converts score values to clean percentage floats."""
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

def is_strictly_zero(val: Any) -> bool:
    """Returns True ONLY if a cell is numeric 0."""
    if pd.isna(val) or val is None:
        return False
    s = str(val).replace("%", "").strip()
    try:
        return float(s) == 0.0
    except ValueError:
        return s.lower() in ["fail", "failed"]

def parse_excel_report(file_bytes) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parses the QA report and consolidates duplicate failures that share
    the exact same underlying reviewer comment.
    """
    df = pd.read_excel(file_bytes)
    raw_cols = list(df.columns)
    norm_col_map = {normalize_str(c): c for c in raw_cols}
    norm_cols = list(norm_col_map.keys())

    def find_col(hints: List[str]) -> str:
        for hint in hints:
            h_norm = normalize_str(hint)
            for nc in norm_cols:
                if h_norm in nc:
                    return norm_col_map[nc]
        return ""

    agent_col = find_col(["name of customer care representative", "ccr) being scored", "agent name"])
    phone_col = find_col(["customer's phone number", "phone number", "calling number"])
    qa_score_col = find_col(["qa score"])
    overall_comment_col = find_col(["overall comments on ccr call performance", "overall comments"])
    crit_flag_col = find_col(["did the ccr make a critical error"])
    crit_desc_col = find_col(["critical error comments", "specific critical error made"])

    if not agent_col or not phone_col or not qa_score_col:
        raise ValueError("Essential columns (Agent Name, Phone Number, or QA Score) missing from Excel sheet.")

    grouped_agents: Dict[str, List[Dict[str, Any]]] = {}

    for _, row in df.iterrows():
        agent_name = str(row.get(agent_col, "")).strip()
        if not agent_name or agent_name.lower() in ["nan", "none"]:
            continue

        calling_number = str(row.get(phone_col, "Unknown Number")).strip()
        if calling_number.endswith(".0"):
            calling_number = calling_number[:-2]

        qa_score = clean_qa_score(row.get(qa_score_col, 0))
        overall_comment = str(row.get(overall_comment_col, "")).strip() if overall_comment_col else ""
        if overall_comment.lower() in ["nan", "none"]:
            overall_comment = ""

        raw_missed_areas = []

        # 1. Critical Errors Check
        if crit_flag_col:
            flag_val = str(row.get(crit_flag_col, "")).strip().lower()
            if flag_val in ["yes", "true", "1"]:
                crit_desc = str(row.get(crit_desc_col, "Critical error committed.")).strip()
                if not crit_desc or crit_desc.lower() in ["nan", "none"]:
                    crit_desc = "Critical process violation occurred on this call."
                raw_missed_areas.append({
                    "family": "critical",
                    "category": "Critical Process Compliance",
                    "reason": crit_desc,
                    "comment_key": "critical"
                })

        # 2. Check each rubric
        for rubric in INDEPENDENT_RUBRICS:
            s_col = find_col(rubric["score_col_hints"])
            if s_col:
                raw_score = row.get(s_col)
                if is_strictly_zero(raw_score):
                    reason_comment = ""
                    c_col = find_col(rubric["comment_col_hints"])
                    comment_source_key = c_col if c_col else "none"
                    if c_col:
                        c_val = str(row.get(c_col, "")).strip()
                        if c_val and c_val.lower() not in ["nan", "none", "mindset okay", "okay", "professional call opening.", "kyc done well."]:
                            reason_comment = c_val

                    # If specific comment was blank, use overall comments
                    if not reason_comment:
                        reason_comment = overall_comment if overall_comment else f"Did not meet requirement for {rubric['category']}."
                        comment_source_key = "overall"

                    raw_missed_areas.append({
                        "family": rubric["family"],
                        "category": rubric["category"],
                        "reason": reason_comment,
                        "comment_key": comment_source_key
                    })

        # 3. DEDUPLICATION: Merge items sharing the same family & same comment text
        deduped_missed_areas = []
        seen_keys = set()

        for item in raw_missed_areas:
            # Create a unique signature of the core issue
            norm_reason = normalize_str(item["reason"])
            # Key combines the rubric family + the normalized comment
            unique_sig = (item["family"], norm_reason)

            if unique_sig in seen_keys:
                # Same problem already captured under this family; skip redundant duplicate
                continue

            seen_keys.add(unique_sig)
            deduped_missed_areas.append({
                "category": item["category"],
                "reason": item["reason"]
            })

        # Fail-safe: Penalized score but no missed areas
        if qa_score < 100 and len(deduped_missed_areas) == 0:
            deduction = int(100 - qa_score) if (100 - qa_score).is_integer() else round(100 - qa_score, 1)
            reason = overall_comment if overall_comment else f"Points deducted ({deduction}% penalty) according to quality evaluation standard."
            deduped_missed_areas.append({
                "category": "Process Compliance",
                "reason": reason
            })

        call_data = {
            "phone": calling_number,
            "qa_score": qa_score,
            "missed_areas": deduped_missed_areas
        }

        if agent_name not in grouped_agents:
            grouped_agents[agent_name] = []
        grouped_agents[agent_name].append(call_data)

    return dict(sorted(grouped_agents.items(), key=lambda x: x[0].strip().lower()))
