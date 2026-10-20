import requests
import json
import time
from typing import Tuple, List, Optional

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

FAST_OPENROUTER_DEFAULTS = [
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "openrouter/free"
]

GROQ_MODELS_PRIORITY = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
]

_LAST_WORKING_MODEL: Optional[str] = None
_LAST_WORKING_PROVIDER: Optional[str] = None
_CACHED_OR_MODELS: List[str] = []
_LAST_CATALOG_FETCH: float = 0.0

def fetch_openrouter_free_models(api_key: Optional[str] = None) -> List[str]:
    """Fetches live free models from OpenRouter."""
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
                is_free = (
                    str(pricing.get("prompt", "1")) == "0" and 
                    str(pricing.get("completion", "1")) == "0"
                )
                if m_id.endswith(":free") or is_free or m_id == "openrouter/free":
                    if "r1" not in m_id.lower() and "reasoning" not in m_id.lower():
                        free_models.append(m_id)

            if free_models:
                free_models.sort(key=lambda x: ("flash" in x.lower()) * 50 + ("llama-3" in x.lower()) * 40, reverse=True)
                _CACHED_OR_MODELS = free_models
                _LAST_CATALOG_FETCH = now
                return _CACHED_OR_MODELS
    except Exception:
        pass

    _CACHED_OR_MODELS = FAST_OPENROUTER_DEFAULTS
    return _CACHED_OR_MODELS

def test_openrouter_connection(api_key: str) -> Tuple[bool, str, float]:
    """Tests OpenRouter connectivity and returns the exact error on failure."""
    if not api_key or not api_key.strip():
        return False, "OpenRouter API key is empty.", 0.0
    key = api_key.strip()
    start = time.time()
    models = fetch_openrouter_free_models(key)
    for model in models[:3]:
        try:
            res = requests.post(
                OPENROUTER_CHAT_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
                timeout=6
            )
            lat = round(time.time() - start, 2)
            if res.status_code == 200:
                return True, model, lat
            elif res.status_code == 401:
                return False, "Unauthorized (401): Invalid OpenRouter API Key.", lat
            else:
                err_msg = res.json().get("error", {}).get("message", f"HTTP {res.status_code}")
                return False, f"OpenRouter Error ({res.status_code}): {err_msg}", lat
        except Exception as e:
            continue
    return False, "No free OpenRouter model responded in time.", round(time.time() - start, 2)

def test_groq_connection(api_key: str) -> Tuple[bool, str, float]:
    """Tests Groq with zero error swallowing, displaying exact status from Groq servers."""
    if not api_key or not api_key.strip():
        return False, "Groq API key is empty.", 0.0
    key = api_key.strip()
    start = time.time()

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }

    try:
        res = requests.post(GROQ_CHAT_URL, headers=headers, json=payload, timeout=6)
        lat = round(time.time() - start, 2)
        if res.status_code == 200:
            return True, "llama-3.1-8b-instant", lat
        
        # Parse exact error directly from Groq's response
        try:
            err_json = res.json()
            err_msg = err_json.get("error", {}).get("message", res.text)
        except Exception:
            err_msg = res.text

        return False, f"Groq Error ({res.status_code}): {err_msg}", lat
    except Exception as e:
        return False, f"Network Connection Error: {str(e)}", round(time.time() - start, 2)

def call_llm_resilient(
    system_prompt: str,
    user_prompt: str,
    openrouter_key: str,
    groq_key: str,
    status_callback=None
) -> Tuple[str, str, str]:
    """Zero-error resilient fallback engine."""
    global _LAST_WORKING_MODEL, _LAST_WORKING_PROVIDER

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # 1. Fast-Path: Try last working model
    if _LAST_WORKING_MODEL and _LAST_WORKING_PROVIDER:
        try:
            if _LAST_WORKING_PROVIDER == "OpenRouter" and openrouter_key:
                res = requests.post(
                    OPENROUTER_CHAT_URL,
                    headers={"Authorization": f"Bearer {openrouter_key.strip()}", "Content-Type": "application/json"},
                    json={"model": _LAST_WORKING_MODEL, "messages": messages, "temperature": 0.2},
                    timeout=8
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"].strip(), _LAST_WORKING_MODEL, "OpenRouter"
                    
            elif _LAST_WORKING_PROVIDER == "Groq" and groq_key:
                res = requests.post(
                    GROQ_CHAT_URL,
                    headers={"Authorization": f"Bearer {groq_key.strip()}", "Content-Type": "application/json"},
                    json={"model": _LAST_WORKING_MODEL, "messages": messages, "temperature": 0.2},
                    timeout=6
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"].strip(), _LAST_WORKING_MODEL, "Groq"
        except Exception:
            pass

    # 2. OpenRouter free pool scan
    if openrouter_key:
        free_models = fetch_openrouter_free_models(openrouter_key.strip())
        for model in free_models:
            if status_callback:
                status_callback(f"Connecting: {model}...")
            try:
                res = requests.post(
                    OPENROUTER_CHAT_URL,
                    headers={"Authorization": f"Bearer {openrouter_key.strip()}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "temperature": 0.2},
                    timeout=8
                )
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"].strip()
                    _LAST_WORKING_MODEL = model
                    _LAST_WORKING_PROVIDER = "OpenRouter"
                    return content, model, "OpenRouter"
            except Exception:
                continue

    # 3. Groq fallback scan
    if groq_key:
        for model in GROQ_MODELS_PRIORITY:
            if status_callback:
                status_callback(f"Groq fallback: {model}...")
            try:
                res = requests.post(
                    GROQ_CHAT_URL,
                    headers={"Authorization": f"Bearer {groq_key.strip()}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "temperature": 0.2},
                    timeout=6
                )
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"].strip()
                    _LAST_WORKING_MODEL = model
                    _LAST_WORKING_PROVIDER = "Groq"
                    return content, model, "Groq"
            except Exception:
                continue

    raise RuntimeError("All free models on OpenRouter and Groq failed. Please check keys in the sidebar.")
