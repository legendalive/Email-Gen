import requests
import json
import time
from typing import Tuple, List, Optional

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

# Curated fast free models (fastest first)
FAST_OPENROUTER_DEFAULTS = [
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "mistralai/mistral-small-24b-instruct-2501:free",
    "openrouter/free"
]

GROQ_FREE_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
]

# In-memory cache to remember what works
_LAST_WORKING_MODEL: Optional[str] = None
_LAST_WORKING_PROVIDER: Optional[str] = None
_CACHED_OR_MODELS: List[str] = []
_LAST_CATALOG_FETCH: float = 0.0

def fetch_openrouter_free_models(api_key: Optional[str] = None) -> List[str]:
    """Fetches free models from OpenRouter, caching the list for 10 minutes."""
    global _CACHED_OR_MODELS, _LAST_CATALOG_FETCH
    now = time.time()
    
    if _CACHED_OR_MODELS and (now - _LAST_CATALOG_FETCH < 600):
        return _CACHED_OR_MODELS

    headers = {"User-Agent": "QA-Email-Generator"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        res = requests.get(OPENROUTER_MODELS_URL, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json().get("data", [])
            free_models = []
            for m in data:
                m_id = m.get("id", "")
                pricing = m.get("pricing", {})
                is_free_price = (
                    str(pricing.get("prompt", "1")) == "0" and 
                    str(pricing.get("completion", "1")) == "0"
                )
                if m_id.endswith(":free") or is_free_price or m_id == "openrouter/free":
                    # Skip slow reasoning models that queue for minutes
                    if "r1" not in m_id.lower() and "reasoning" not in m_id.lower():
                        free_models.append(m_id)

            if free_models:
                def score_model(m_name: str) -> int:
                    score = 0
                    lower = m_name.lower()
                    if "flash" in lower: score += 60
                    if "llama-3.3" in lower: score += 50
                    if "llama-3.1-8b" in lower: score += 45
                    if "qwen" in lower: score += 30
                    if "70b" in lower: score += 20
                    return score

                free_models.sort(key=score_model, reverse=True)
                _CACHED_OR_MODELS = free_models
                _LAST_CATALOG_FETCH = now
                return _CACHED_OR_MODELS
    except Exception:
        pass

    _CACHED_OR_MODELS = FAST_OPENROUTER_DEFAULTS
    return _CACHED_OR_MODELS

def test_openrouter_connection(api_key: str) -> Tuple[bool, str, float]:
    """Tests OpenRouter connectivity and returns (success, model_or_error, latency_sec)."""
    if not api_key:
        return False, "API key is empty", 0.0
    start = time.time()
    models = fetch_openrouter_free_models(api_key)
    for model in models[:3]:
        try:
            res = requests.post(
                OPENROUTER_CHAT_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
                timeout=6
            )
            if res.status_code == 200:
                return True, model, round(time.time() - start, 2)
        except Exception:
            continue
    return False, "No free OpenRouter model responded in time.", round(time.time() - start, 2)

def test_groq_connection(api_key: str) -> Tuple[bool, str, float]:
    """Tests Groq connectivity and returns (success, model_or_error, latency_sec)."""
    if not api_key:
        return False, "API key is empty", 0.0
    start = time.time()
    for model in GROQ_FREE_MODELS:
        try:
            res = requests.post(
                GROQ_CHAT_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
                timeout=5
            )
            if res.status_code == 200:
                return True, model, round(time.time() - start, 2)
        except Exception:
            continue
    return False, "No Groq model responded.", round(time.time() - start, 2)

def call_llm_resilient(
    system_prompt: str,
    user_prompt: str,
    openrouter_key: str,
    groq_key: str,
    status_callback=None
) -> Tuple[str, str, str]:
    """
    High-speed zero-error execution loop with Sticky-Model memory.
    """
    global _LAST_WORKING_MODEL, _LAST_WORKING_PROVIDER

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # --- 1. FAST-PATH: Try Last Working Model First (Instant) ---
    if _LAST_WORKING_MODEL and _LAST_WORKING_PROVIDER:
        try:
            if _LAST_WORKING_PROVIDER == "OpenRouter" and openrouter_key:
                res = requests.post(
                    OPENROUTER_CHAT_URL,
                    headers={"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"},
                    json={"model": _LAST_WORKING_MODEL, "messages": messages, "temperature": 0.2},
                    timeout=8
                )
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"].strip()
                    return content, _LAST_WORKING_MODEL, "OpenRouter"
                    
            elif _LAST_WORKING_PROVIDER == "Groq" and groq_key:
                res = requests.post(
                    GROQ_CHAT_URL,
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={"model": _LAST_WORKING_MODEL, "messages": messages, "temperature": 0.2},
                    timeout=6
                )
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"].strip()
                    return content, _LAST_WORKING_MODEL, "Groq"
        except Exception:
            # Fall through to scan
            pass

    # --- 2. OPENROUTER FREE POOL SCAN ---
    if openrouter_key:
        free_models = fetch_openrouter_free_models(openrouter_key)
        for model in free_models:
            if status_callback:
                status_callback(f"Connecting to: {model}...")
            try:
                res = requests.post(
                    OPENROUTER_CHAT_URL,
                    headers={"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "temperature": 0.2},
                    timeout=8  # Fast 8-second failover
                )
                if res.status_code == 200:
                    choices = res.json().get("choices", [])
                    if choices and "message" in choices[0] and choices[0]["message"].get("content"):
                        content = choices[0]["message"]["content"].strip()
                        _LAST_WORKING_MODEL = model
                        _LAST_WORKING_PROVIDER = "OpenRouter"
                        return content, model, "OpenRouter"
            except Exception:
                continue

    # --- 3. GROQ ULTRA-FAST FALLBACK SCAN ---
    if groq_key:
        for model in GROQ_FREE_MODELS:
            if status_callback:
                status_callback(f"Groq fast failover: {model}...")
            try:
                res = requests.post(
                    GROQ_CHAT_URL,
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "temperature": 0.2},
                    timeout=6
                )
                if res.status_code == 200:
                    choices = res.json().get("choices", [])
                    if choices and "message" in choices[0] and choices[0]["message"].get("content"):
                        content = choices[0]["message"]["content"].strip()
                        _LAST_WORKING_MODEL = model
                        _LAST_WORKING_PROVIDER = "Groq"
                        return content, model, "Groq"
            except Exception:
                continue

    raise RuntimeError("All free models on OpenRouter and Groq timed out. Please test your API keys in the sidebar.")
