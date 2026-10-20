import requests
import json
from typing import Tuple, List, Optional

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

# Curated fallback list if OpenRouter's model catalog endpoint is temporarily unreachable
DEFAULT_OPENROUTER_FREE_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "deepseek/deepseek-r1:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
]

# High-speed free tier models on Groq
GROQ_FREE_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
]

def fetch_openrouter_free_models(api_key: Optional[str] = None) -> List[str]:
    """
    Dynamically queries OpenRouter for all live models where pricing is $0.
    Sorts models so the most capable ones (70b, Llama, Qwen, Gemini) are attempted first.
    """
    headers = {"User-Agent": "QA-Email-Generator"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        res = requests.get(OPENROUTER_MODELS_URL, headers=headers, timeout=6)
        if res.status_code == 200:
            data = res.json().get("data", [])
            free_models = []
            for m in data:
                m_id = m.get("id", "")
                pricing = m.get("pricing", {})
                
                # Check for zero pricing or :free suffix
                is_free_price = (
                    str(pricing.get("prompt", "1")) == "0" and 
                    str(pricing.get("completion", "1")) == "0"
                )
                if m_id.endswith(":free") or is_free_price or m_id == "openrouter/free":
                    free_models.append(m_id)

            if free_models:
                # Prioritization heuristic: prefer known top-tier model families first
                def score_model(m_name: str) -> int:
                    score = 0
                    lower = m_name.lower()
                    if "70b" in lower: score += 50
                    if "llama-3.3" in lower: score += 40
                    if "gemini" in lower: score += 30
                    if "qwen" in lower: score += 25
                    if "r1" in lower or "deepseek" in lower: score += 20
                    if "openrouter/free" in lower: score += 10
                    return score

                free_models.sort(key=score_model, reverse=True)
                return free_models
    except Exception as e:
        print(f"Warning: Could not dynamically fetch OpenRouter free models: {e}")

    return DEFAULT_OPENROUTER_FREE_MODELS

def call_llm_resilient(
    system_prompt: str,
    user_prompt: str,
    openrouter_key: str,
    groq_key: str,
    status_callback=None
) -> Tuple[str, str, str]:
    """
    Zero-error execution loop:
    1. Cycles through dynamically retrieved OpenRouter free models.
    2. If rate-limited (429), retired (404), or down (5xx), instantly tries the next.
    3. If OpenRouter fails entirely, cascades seamlessly to Groq free models.
    Returns: (generated_text, model_used, provider_used)
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # --- 1. OPENROUTER ATTEMPT LOOP ---
    if openrouter_key:
        free_models = fetch_openrouter_free_models(openrouter_key)
        for model in free_models:
            if status_callback:
                status_callback(f"Trying OpenRouter model: {model}...")
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2
                }
                headers = {
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com",
                    "X-Title": "QA Email Generator"
                }
                response = requests.post(OPENROUTER_CHAT_URL, json=payload, headers=headers, timeout=18)
                
                if response.status_code == 200:
                    resp_json = response.json()
                    choices = resp_json.get("choices", [])
                    if choices and "message" in choices[0] and choices[0]["message"].get("content"):
                        actual_model = resp_json.get("model", model)
                        return choices[0]["message"]["content"].strip(), actual_model, "OpenRouter"
                
                # Any non-200 status (429, 404, 500, etc.) automatically logs and continues to next model
                print(f"OpenRouter model {model} failed with status {response.status_code}. Advancing to next free model...")
            except Exception as e:
                print(f"OpenRouter model {model} request error: {e}. Advancing to next free model...")
                continue

    # --- 2. GROQ FALLBACK LOOP ---
    if groq_key:
        for model in GROQ_FREE_MODELS:
            if status_callback:
                status_callback(f"Cascading to Groq fallback: {model}...")
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2
                }
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                }
                response = requests.post(GROQ_CHAT_URL, json=payload, headers=headers, timeout=12)
                
                if response.status_code == 200:
                    resp_json = response.json()
                    choices = resp_json.get("choices", [])
                    if choices and "message" in choices[0] and choices[0]["message"].get("content"):
                        return choices[0]["message"]["content"].strip(), model, "Groq"
                        
                print(f"Groq model {model} failed with status {response.status_code}. Advancing...")
            except Exception as e:
                print(f"Groq model {model} request error: {e}. Advancing...")
                continue

    raise RuntimeError("All available free models across OpenRouter and Groq were attempted without success. Please verify your API keys.")
