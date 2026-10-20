import requests
import json
import time
from typing import Tuple, List, Optional

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

# Global memory to remember winning models during a session
_LAST_WORKING_MODEL: Optional[str] = None
_LAST_WORKING_PROVIDER: Optional[str] = None
_CACHED_OR_MODELS: List[str] = []
_CACHED_GROQ_MODELS: List[str] = []
_LAST_OR_FETCH: float = 0.0
_LAST_GROQ_FETCH: float = 0.0

# ----------------- DYNAMIC MODEL DISCOVERY (ZERO HARDCODING) -----------------

def get_live_groq_chat_models(api_key: str) -> List[str]:
    """
    Dynamically queries Groq for all active chat completion models available to this key.
    Filters out audio/whisper/guardrail models and ranks the best models first.
    """
    global _CACHED_GROQ_MODELS, _LAST_GROQ_FETCH
    now = time.time()
    if _CACHED_GROQ_MODELS and (now - _LAST_GROQ_FETCH < 300):
        return _CACHED_GROQ_MODELS

    headers = {"Authorization": f"Bearer {api_key.strip()}"}
    try:
        res = requests.get(GROQ_MODELS_URL, headers=headers, timeout=6)
        if res.status_code == 200:
            data = res.json().get("data", [])
            chat_models = []
            for m in data:
                m_id = m.get("id", "")
                lower = m_id.lower()
                # Exclude non-chat endpoints
                if any(bad in lower for bad in ["whisper", "guard", "embed", "moderation", "tts", "transcribe"]):
                    continue
                if m.get("active", True) is False:
                    continue
                chat_models.append(m_id)

            if chat_models:
                def rank_groq(name: str) -> int:
                    score = 0
                    n = name.lower()
                    if "70b" in n: score += 50
                    if "versatile" in n: score += 40
                    if "llama-3.3" in n: score += 35
                    if "llama-3" in n: score += 25
                    if "mixtral" in n: score += 20
                    if "qwen" in n: score += 15
                    if "8b" in n: score += 10
                    return score

                chat_models.sort(key=rank_groq, reverse=True)
                _CACHED_GROQ_MODELS = chat_models
                _LAST_GROQ_FETCH = now
                return _CACHED_GROQ_MODELS
    except Exception as e:
        print(f"Warning: Could not dynamically fetch Groq models: {e}")

    return _CACHED_GROQ_MODELS

def fetch_openrouter_free_models(api_key: Optional[str] = None) -> List[str]:
    """
    Dynamically queries OpenRouter for all live $0 pricing models.
    Filters out slow reasoning models and ranks best available first.
    """
    global _CACHED_OR_MODELS, _LAST_OR_FETCH
    now = time.time()
    if _CACHED_OR_MODELS and (now - _LAST_OR_FETCH < 300):
        return _CACHED_OR_MODELS

    headers = {"User-Agent": "QA-Email-Generator"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    try:
        res = requests.get(OPENROUTER_MODELS_URL, headers=headers, timeout=6)
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
                def rank_or(name: str) -> int:
                    score = 0
                    n = name.lower()
                    if "flash" in n: score += 60
                    if "70b" in n: score += 50
                    if "llama-3" in n: score += 40
                    if "qwen" in n: score += 30
                    if "openrouter/free" in n: score += 20
                    return score

                free_models.sort(key=rank_or, reverse=True)
                _CACHED_OR_MODELS = free_models
                _LAST_OR_FETCH = now
                return _CACHED_OR_MODELS
    except Exception as e:
        print(f"Warning: Could not dynamically fetch OpenRouter models: {e}")

    return _CACHED_OR_MODELS

# ----------------- DIAGNOSTIC CONNECTION TESTS -----------------

def test_openrouter_connection(api_key: str) -> Tuple[bool, str, float]:
    """Dynamically cycles through available free models on OpenRouter until one succeeds."""
    if not api_key or not api_key.strip():
        return False, "OpenRouter API key is empty.", 0.0
    key = api_key.strip()
    start = time.time()
    models = fetch_openrouter_free_models(key)
    
    if not models:
        return False, "Could not discover any active free models on OpenRouter.", round(time.time() - start, 2)

    last_err = ""
    for model in models:
        try:
            res = requests.post(
                OPENROUTER_CHAT_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
                timeout=6
            )
            lat = round(time.time() - start, 2)
            if res.status_code == 200:
                return True, f"{model} (Selected from {len(models)} live free models)", lat
            elif res.status_code == 401:
                return False, "Unauthorized (401): Invalid OpenRouter API Key.", lat
            else:
                last_err = res.json().get("error", {}).get("message", f"HTTP {res.status_code}")
                continue
        except Exception as e:
            last_err = str(e)
            continue

    return False, f"All OpenRouter models failed. Last error: {last_err}", round(time.time() - start, 2)

def test_groq_connection(api_key: str) -> Tuple[bool, str, float]:
    """
    Dynamically queries Groq for your account's accessible models,
    then cycles through them starting with the best until one connects.
    Zero hardcoded model names.
    """
    if not api_key or not api_key.strip():
        return False, "Groq API key is empty.", 0.0
    key = api_key.strip()
    start = time.time()

    # Step 1: Verify key & query accessible models
    try:
        m_res = requests.get(GROQ_MODELS_URL, headers={"Authorization": f"Bearer {key}"}, timeout=6)
        lat = round(time.time() - start, 2)
        if m_res.status_code == 401:
            return False, "Unauthorized (401): Invalid Groq API Key. Verify from console.groq.com.", lat
        if m_res.status_code != 200:
            err_msg = m_res.json().get("error", {}).get("message", m_res.text)
            return False, f"Groq Error ({m_res.status_code}): {err_msg}", lat
    except Exception as e:
        return False, f"Connection error reaching Groq: {str(e)}", round(time.time() - start, 2)

    # Step 2: Extract chat models dynamically
    models = get_live_groq_chat_models(key)
    if not models:
        return False, "No active chat models were returned by Groq for this account.", round(time.time() - start, 2)

    # Step 3: Cycle through live models starting with best available
    last_err = ""
    for model in models:
        try:
            res = requests.post(
                GROQ_CHAT_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
                timeout=5
            )
            lat = round(time.time() - start, 2)
            if res.status_code == 200:
                return True, f"{model} (Selected from {len(models)} live Groq models)", lat
            else:
                last_err = res.json().get("error", {}).get("message", f"HTTP {res.status_code}")
                continue
        except Exception as e:
            last_err = str(e)
            continue

    return False, f"All {len(models)} Groq models failed. Last error: {last_err}", round(time.time() - start, 2)

# ----------------- RESILIENT GENERATION ENGINE -----------------

def call_llm_resilient(
    system_prompt: str,
    user_prompt: str,
    openrouter_key: str,
    groq_key: str,
    status_callback=None
) -> Tuple[str, str, str]:
    """
    Zero-error dual-provider engine:
    1. Tries last working model first (instant sticky-model speed).
    2. Cycles through all live free models on OpenRouter dynamically.
    3. If OpenRouter fails, cascades through all live chat models on Groq dynamically.
    """
    global _LAST_WORKING_MODEL, _LAST_WORKING_PROVIDER

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # --- 1. STICKY-MODEL FAST PATH ---
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

    # --- 2. DYNAMIC OPENROUTER FREE POOL SCAN ---
    if openrouter_key:
        or_models = fetch_openrouter_free_models(openrouter_key.strip())
        for model in or_models:
            if status_callback:
                status_callback(f"Trying OpenRouter: {model}...")
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

    # --- 3. DYNAMIC GROQ LIVE POOL SCAN ---
    if groq_key:
        groq_models = get_live_groq_chat_models(groq_key.strip())
        for model in groq_models:
            if status_callback:
                status_callback(f"Cascading to Groq: {model}...")
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

    raise RuntimeError("All dynamic models across OpenRouter and Groq were attempted without success.")
