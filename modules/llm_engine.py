import requests
import json
import time
from typing import Tuple, List, Optional

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

# Global memory to remember winning models during a session
_LAST_WORKING_MODEL: Optional[str] = None
_LAST_WORKING_PROVIDER: Optional[str] = None
_CACHED_GEMINI_MODELS: List[str] = []
_CACHED_OR_MODELS: List[str] = []
_CACHED_GROQ_MODELS: List[str] = []
_LAST_GEMINI_FETCH: float = 0.0
_LAST_OR_FETCH: float = 0.0
_LAST_GROQ_FETCH: float = 0.0

# ----------------- DYNAMIC MODEL DISCOVERY (ZERO HARDCODING) -----------------

def get_live_gemini_models(api_key: str) -> List[str]:
    """
    Dynamically queries Google Gemini for all models supporting generateContent.
    Ranks best models first (2.5-flash, 2.0-flash, 1.5-flash).
    """
    global _CACHED_GEMINI_MODELS, _LAST_GEMINI_FETCH
    now = time.time()
    if _CACHED_GEMINI_MODELS and (now - _LAST_GEMINI_FETCH < 300):
        return _CACHED_GEMINI_MODELS

    key = api_key.strip()
    try:
        res = requests.get(f"{GEMINI_MODELS_URL}?key={key}", timeout=6)
        if res.status_code == 200:
            data = res.json().get("models", [])
            chat_models = []
            for m in data:
                m_name = m.get("name", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    # Filter out embedding/imagen models
                    lower = m_name.lower()
                    if any(bad in lower for bad in ["embedding", "imagen", "aqa"]):
                        continue
                    clean_id = m_name.replace("models/", "")
                    chat_models.append(clean_id)

            if chat_models:
                def rank_gemini(name: str) -> int:
                    score = 0
                    n = name.lower()
                    if "2.5-flash" in n: score += 60
                    if "2.0-flash" in n: score += 50
                    if "1.5-flash" in n: score += 40
                    if "flash" in n: score += 30
                    if "1.5-pro" in n: score += 20
                    return score

                chat_models.sort(key=rank_gemini, reverse=True)
                _CACHED_GEMINI_MODELS = chat_models
                _LAST_GEMINI_FETCH = now
                return _CACHED_GEMINI_MODELS
    except Exception as e:
        print(f"Warning: Could not fetch Gemini models: {e}")

    return _CACHED_GEMINI_MODELS

def get_live_groq_chat_models(api_key: str) -> List[str]:
    """Dynamically queries Groq for active chat models."""
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
        print(f"Warning: Could not fetch Groq models: {e}")

    return _CACHED_GROQ_MODELS

def fetch_openrouter_free_models(api_key: Optional[str] = None) -> List[str]:
    """Dynamically queries OpenRouter for active $0 free models."""
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
        print(f"Warning: Could not fetch OpenRouter models: {e}")

    return _CACHED_OR_MODELS

# ----------------- DIAGNOSTIC CONNECTION TESTS -----------------

def test_gemini_connection(api_key: str) -> Tuple[bool, str, float]:
    """Tests Gemini connectivity with live model listing and chat test."""
    if not api_key or not api_key.strip():
        return False, "Gemini API key is empty.", 0.0
    key = api_key.strip()
    start = time.time()

    # Step 1: Query models endpoint
    try:
        m_res = requests.get(f"{GEMINI_MODELS_URL}?key={key}", timeout=6)
        lat = round(time.time() - start, 2)
        if m_res.status_code != 200:
            err_msg = m_res.json().get("error", {}).get("message", f"HTTP {m_res.status_code}")
            return False, f"Gemini Error ({m_res.status_code}): {err_msg}", lat
    except Exception as e:
        return False, f"Connection error reaching Google: {str(e)}", round(time.time() - start, 2)

    # Step 2: Get chat models and test generateContent
    models = get_live_gemini_models(key)
    if not models:
        return False, "No active generateContent models returned by Gemini.", round(time.time() - start, 2)

    last_err = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 5}
        }
        try:
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=6)
            lat = round(time.time() - start, 2)
            if res.status_code == 200:
                return True, f"{model} (Selected from {len(models)} live Gemini models)", lat
            else:
                last_err = res.json().get("error", {}).get("message", f"HTTP {res.status_code}")
                continue
        except Exception as e:
            last_err = str(e)
            continue

    return False, f"All Gemini models failed. Last error: {last_err}", round(time.time() - start, 2)

def test_openrouter_connection(api_key: str) -> Tuple[bool, str, float]:
    """Dynamically cycles through available free models on OpenRouter."""
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
    """Dynamically queries Groq for accessible models and cycles through them."""
    if not api_key or not api_key.strip():
        return False, "Groq API key is empty.", 0.0
    key = api_key.strip()
    start = time.time()

    try:
        m_res = requests.get(GROQ_MODELS_URL, headers={"Authorization": f"Bearer {key}"}, timeout=6)
        lat = round(time.time() - start, 2)
        if m_res.status_code == 401:
            return False, "Unauthorized (401): Invalid Groq API Key.", lat
        if m_res.status_code != 200:
            err_msg = m_res.json().get("error", {}).get("message", m_res.text)
            return False, f"Groq Error ({m_res.status_code}): {err_msg}", lat
    except Exception as e:
        return False, f"Connection error reaching Groq: {str(e)}", round(time.time() - start, 2)

    models = get_live_groq_chat_models(key)
    if not models:
        return False, "No active chat models were returned by Groq for this account.", round(time.time() - start, 2)

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
    gemini_key: str = "",
    openrouter_key: str = "",
    groq_key: str = "",
    status_callback=None
) -> Tuple[str, str, str]:
    """
    Multi-tier Zero-Error Resilient Fallback Engine:
    1. Tries last working model (fast path).
    2. Primary: Google Gemini API (fastest, high quality).
    3. Secondary: OpenRouter dynamic free pool.
    4. Fallback: Groq dynamic live pool.
    """
    global _LAST_WORKING_MODEL, _LAST_WORKING_PROVIDER

    # 1. FAST PATH: Last working model
    if _LAST_WORKING_MODEL and _LAST_WORKING_PROVIDER:
        try:
            if _LAST_WORKING_PROVIDER == "Gemini" and gemini_key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{_LAST_WORKING_MODEL}:generateContent?key={gemini_key.strip()}"
                payload = {
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                    "generationConfig": {"temperature": 0.2}
                }
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=8)
                if res.status_code == 200:
                    text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return text, _LAST_WORKING_MODEL, "Gemini"

            elif _LAST_WORKING_PROVIDER == "OpenRouter" and openrouter_key:
                res = requests.post(
                    OPENROUTER_CHAT_URL,
                    headers={"Authorization": f"Bearer {openrouter_key.strip()}", "Content-Type": "application/json"},
                    json={"model": _LAST_WORKING_MODEL, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": 0.2},
                    timeout=8
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"].strip(), _LAST_WORKING_MODEL, "OpenRouter"

            elif _LAST_WORKING_PROVIDER == "Groq" and groq_key:
                res = requests.post(
                    GROQ_CHAT_URL,
                    headers={"Authorization": f"Bearer {groq_key.strip()}", "Content-Type": "application/json"},
                    json={"model": _LAST_WORKING_MODEL, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": 0.2},
                    timeout=6
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"].strip(), _LAST_WORKING_MODEL, "Groq"
        except Exception:
            pass

    # 2. OPTION 1: GOOGLE GEMINI (PRIMARY)
    if gemini_key and gemini_key.strip():
        gemini_models = get_live_gemini_models(gemini_key.strip())
        for model in gemini_models:
            if status_callback:
                status_callback(f"Connecting to Gemini: {model}...")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key.strip()}"
            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {"temperature": 0.2}
            }
            try:
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=8)
                if res.status_code == 200:
                    choices = res.json().get("candidates", [])
                    if choices and "content" in choices[0] and "parts" in choices[0]["content"]:
                        content = choices[0]["content"]["parts"][0]["text"].strip()
                        _LAST_WORKING_MODEL = model
                        _LAST_WORKING_PROVIDER = "Gemini"
                        return content, model, "Gemini"
            except Exception:
                continue

    # 3. OPTION 2: OPENROUTER FREE POOL (SECONDARY)
    if openrouter_key and openrouter_key.strip():
        or_models = fetch_openrouter_free_models(openrouter_key.strip())
        for model in or_models:
            if status_callback:
                status_callback(f"Trying OpenRouter: {model}...")
            try:
                res = requests.post(
                    OPENROUTER_CHAT_URL,
                    headers={"Authorization": f"Bearer {openrouter_key.strip()}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": 0.2},
                    timeout=8
                )
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"].strip()
                    _LAST_WORKING_MODEL = model
                    _LAST_WORKING_PROVIDER = "OpenRouter"
                    return content, model, "OpenRouter"
            except Exception:
                continue

    # 4. OPTION 3: GROQ LIVE POOL (FALLBACK)
    if groq_key and groq_key.strip():
        groq_models = get_live_groq_chat_models(groq_key.strip())
        for model in groq_models:
            if status_callback:
                status_callback(f"Cascading to Groq: {model}...")
            try:
                res = requests.post(
                    GROQ_CHAT_URL,
                    headers={"Authorization": f"Bearer {groq_key.strip()}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": 0.2},
                    timeout=6
                )
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"].strip()
                    _LAST_WORKING_MODEL = model
                    _LAST_WORKING_PROVIDER = "Groq"
                    return content, model, "Groq"
            except Exception:
                continue

    raise RuntimeError("All models across Gemini, OpenRouter, and Groq failed. Please check keys in the sidebar.")
