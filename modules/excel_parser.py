import pandas as pd
import re
from typing import Dict, List, Any

# Rubric definitions with normalized search patterns
RUBRIC_DEFINITIONS = [
    {
        "category": "Call Opening & Professionalism",
        "score_hints": ["professionalism", "call opening script"],
        "comment_hints": ["call opening comments", "opening comments", "call opening"]
    },
    {
        "category": "Identification & KYC Checks",
        "score_hints": ["identification and kyc checks", "kyc checks", "identification checks"],
        "comment_hints": ["kyc checks comments", "identification comments", "kyc comments"]
    },
    {
        "category": "Tone & Enthusiasm",
        "score_hints": ["enthusiasm"],
        "comment_hints": ["telephone etiquette (service mindset) commments", "telephone etiquette", "service mindset"]
    },
    {
        "category": "Active Listening & Empathy",
        "score_hints": ["active listening & empathy", "active listening", "empathy"],
        "comment_hints": ["telephone etiquette (service mindset) commments", "telephone etiquette", "service mindset"]
    },
    {
        "category": "Clear Communication & Etiquette",
        "score_hints": ["clear communication"],
        "comment_hints": ["telephone etiquette (service mindset) commments", "telephone etiquette", "service mindset"]
    },
    {
        "category": "Understanding the Issue",
        "score_hints": ["understanding of the issue", "probe the customer"],
        "comment_hints": ["a. process compliance comments", "process compliance comments"]
    },
    {
        "category": "Process Compliance & Troubleshooting",
        "score_hints": ["correct troubleshooting", "systematic troubleshooting"],
        "comment_hints": ["b. process compliance comments", "process compliance comments"]
    },
    {
        "category": "Customer Education",
        "score_hints": ["customer education", "self help"],
        "comment_hints": ["b. process compliance comments", "process compliance comments"]
    },
    {
        "category": "Issue Resolution",
        "score_hints": ["resolve:", "escalates:", "calls back:", "issue resolution category"],
        "comment_hints": ["issue resolution comments", "resolution comments"]
    },
    {
        "category": "Wrap Up",
        "score_hints": ["wrap up"],
        "comment_hints": ["call closing comments", "wrap up comments"]
    },
    {
        "category": "Closing Procedure",
        "score_hints": ["closing procedure", "offers further assistance"],
        "comment_hints": ["call closing comments", "closing comments"]
    }
]

def normalize_text(text: Any) -> str:
    """Strips non-breaking spaces (\xa0), trailing spaces, and standardizes to lowercase."""
    if text is None:
        return ""
    s = str(text).replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", s).lower()

def clean_qa_score(val: Any) -> float:
    """Safely converts QA score values to a float percentage (e.g. 100.0, 95.0, 85.0)."""
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

def is_failed_score(val: Any) -> bool:
    """Detects if a score cell indicates a deduction / fail (0, 0%, or explicit 0)."""
    if pd.isna(val) or val is None:
        return False
    s = str(val).replace("%", "").strip()
    try:
        return float(s) == 0.0
    except ValueError:
        return s.lower() in ["fail", "no", "failed"]

def parse_excel_report(file_bytes) -> Dict[str, List[Dict[str, Any]]]:
    """
    Enhanced Excel Ingestion:
    Discovers every failed category, comment, and explanation across all audit columns.
    """
    df = pd.read_excel(file_bytes)
    raw_cols = list(df.columns)
    
    # Map normalized column names back to original DataFrame columns
    norm_to_orig = {normalize_text(col): col for col in raw_cols}
    norm_cols = list(norm_to_orig.keys())

    def match_col(hints: List[str]) -> str:
        for hint in hints:
            h_norm = normalize_text(hint)
            for nc in norm_cols:
                if h_norm in nc:
                    return norm_to_orig[nc]
        return ""

    agent_col = match_col(["name of customer care representative", "ccr) being scored", "agent name"])
    phone_col = match_col(["customer's phone number", "phone number", "calling number"])
    qa_score_col = match_col(["qa score"])
    overall_comment_col = match_col(["overall comments on ccr call performance", "overall comments"])
    crit_flag_col = match_col(["did the ccr make a critical error"])
    crit_desc_col = match_col(["critical error comments", "specific critical error made"])

    if not agent_col:
        raise ValueError("Could not locate CCR Agent Name column in the uploaded file.")
    if not phone_col:
        raise ValueError("Could not locate Customer Phone Number column in the uploaded file.")
    if not qa_score_col:
        raise ValueError("Could not locate 'QA score' column in the uploaded file.")

    grouped_agents: Dict[str, List[Dict[str, Any]]] = {}

    for _, row in df.iterrows():
        agent_name = str(row.get(agent_col, "")).strip()
        if not agent_name or agent_name.lower() in ["nan", "none"]:
            continue

        calling_number = str(row.get(phone_col, "Unknown Number")).strip()
        qa_score = clean_qa_score(row.get(qa_score_col, 0))
        overall_comment = str(row.get(overall_comment_col, "")).strip() if overall_comment_col else ""
        if overall_comment.lower() in ["nan", "none"]:
            overall_comment = ""

        missed_areas = []

        # 1. Critical Errors Check
        if crit_flag_col:
            flag_val = str(row.get(crit_flag_col, "")).strip().lower()
            if flag_val in ["yes", "true", "1"]:
                crit_desc = str(row.get(crit_desc_col, "Critical error committed.")).strip()
                if not crit_desc or crit_desc.lower() in ["nan", "none"]:
                    crit_desc = "Critical process violation occurred on this call."
                missed_areas.append({"category": "Critical Process Compliance", "reason": crit_desc})

        # 2. Rubric-by-Rubric Fail Scan
        for rubric in RUBRIC_DEFINITIONS:
            s_col = match_col(rubric["score_hints"])
            if s_col:
                score_val = row.get(s_col)
                if is_failed_score(score_val):
                    # Discovered 0: Extract the reason from comment column
                    reason_text = ""
                    c_col = match_col(rubric["comment_hints"])
                    if c_col:
                        val = str(row.get(c_col, "")).strip()
                        if val and val.lower() not in ["nan", "none", "mindset okay", "introduced professionally", "complied to the authentification checks"]:
                            reason_text = val

                    # Fallback to overall comment or category description
                    if not reason_text:
                        reason_text = overall_comment if overall_comment else f"Did not meet audit standards for {rubric['category']}."

                    missed_areas.append({
                        "category": rubric["category"],
                        "reason": reason_text
                    })

        # 3. SAFETY NET: If QA score was penalized (< 100%) but missed_areas is still empty
        if qa_score < 100 and len(missed_areas) == 0:
            deduction = int(100 - qa_score) if (100 - qa_score).is_integer() else round(100 - qa_score, 1)
            
            # Check if any comment exists anywhere in the row
            found_any_comment = ""
            for nc, oc in norm_to_orig.items():
                if "comment" in nc:
                    c_val = str(row.get(oc, "")).strip()
                    if c_val and c_val.lower() not in ["nan", "none", "mindset okay", "the performance met expectation", "the call was closed professionally"]:
                        found_any_comment = c_val
                        break
            
            if found_any_comment:
                missed_areas.append({
                    "category": "Process Compliance",
                    "reason": found_any_comment
                })
            elif overall_comment:
                missed_areas.append({
                    "category": "Call Evaluation",
                    "reason": overall_comment
                })
            else:
                missed_areas.append({
                    "category": "Process Compliance",
                    "reason": f"Deduction of {deduction}% applied based on QA evaluation guidelines."
                })

        call_data = {
            "phone": calling_number,
            "qa_score": qa_score,
            "missed_areas": missed_areas
        }

        if agent_name not in grouped_agents:
            grouped_agents[agent_name] = []
        grouped_agents[agent_name].append(call_data)

    # Sort alphabetically by Agent Name (A to Z)
    return dict(sorted(grouped_agents.items(), key=lambda x: x[0].strip().lower()))
