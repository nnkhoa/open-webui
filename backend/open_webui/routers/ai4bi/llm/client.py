import os
import hashlib
import time
from openai import OpenAI

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "local-9router-key"
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "http://localhost:20128/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "cx/gpt-5-codex-mini")
if OPENROUTER_MODEL.startswith("openai/cx/"):
    OPENROUTER_MODEL = OPENROUTER_MODEL.replace("openai/", "", 1)

AGENTIC_ENABLED = os.getenv("AGENTIC_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
AGENTIC_MAX_STEPS = int(os.getenv("AGENTIC_MAX_STEPS", "2"))

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
)

EXTRA_HEADERS = {
    "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:3000"),
    "X-Title": os.getenv("OPENROUTER_APP_NAME", "AI4BI"),
}


def count_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    non_ascii = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii // 2)

_EXACT_COUNT_CACHE: dict[str, tuple[float, int]] = {}
_EXACT_BASELINE_CACHE: dict[str, tuple[float, int]] = {}
_EXACT_CACHE_TTL_SEC = float(os.getenv("TOKEN_COUNT_CACHE_TTL_SEC", "3600") or 3600)


def _cache_get(cache: dict, key: str) -> int | None:
    item = cache.get(key)
    if not item:
        return None
    ts, value = item
    if (time.time() - ts) > _EXACT_CACHE_TTL_SEC:
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: dict, key: str, value: int):
    cache[key] = (time.time(), int(value))
    # Best-effort cap (simple FIFO-ish eviction)
    if len(cache) > 4000:
        for k in list(cache.keys())[:500]:
            cache.pop(k, None)


def count_tokens_exact(text: str, model: str | None = None) -> int:
    """
    Exact-ish token counting via provider usage to match the active model tokenizer.
    Returns token count of the *content text* (not including system/user wrapper overhead).
    Implementation: prompt_tokens(system+user(text)) - prompt_tokens(system+user("")).
    """
    text = text or ""
    resolved_model = (model or OPENROUTER_MODEL or "").strip()
    if not resolved_model:
        return count_tokens(text)

    text_key = hashlib.sha256(f"{resolved_model}\n{text}".encode("utf-8")).hexdigest()
    cached = _cache_get(_EXACT_COUNT_CACHE, text_key)
    if cached is not None:
        return cached

    base_key = hashlib.sha256(f"{resolved_model}\n__baseline__".encode("utf-8")).hexdigest()
    baseline = _cache_get(_EXACT_BASELINE_CACHE, base_key)

    try:
        if baseline is None:
            res0 = client.chat.completions.create(
                model=resolved_model,
                temperature=0,
                max_tokens=1,
                messages=[
                    {"role": "system", "content": "Reply with OK."},
                    {"role": "user", "content": ""},
                ],
                extra_headers=EXTRA_HEADERS,
            )
            usage0 = getattr(res0, "usage", None)
            baseline_val = int(getattr(usage0, "prompt_tokens", 0) or 0) if usage0 else 0
            baseline = baseline_val
            _cache_set(_EXACT_BASELINE_CACHE, base_key, baseline_val)

        res = client.chat.completions.create(
            model=resolved_model,
            temperature=0,
            max_tokens=1,
            messages=[
                {"role": "system", "content": "Reply with OK."},
                {"role": "user", "content": text},
            ],
            extra_headers=EXTRA_HEADERS,
        )
        usage = getattr(res, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        value = max(0, prompt_tokens - int(baseline or 0))
        _cache_set(_EXACT_COUNT_CACHE, text_key, value)
        return value
    except Exception:
        # Fallback to heuristic if provider counting fails.
        value = count_tokens(text)
        _cache_set(_EXACT_COUNT_CACHE, text_key, value)
        return value


def extract_thinking(response) -> str:
    if not response or not hasattr(response, "choices") or not response.choices:
        return ""
    msg = response.choices[0].message
    # 1. Direct property (OpenRouter reasoning_content or Reasoning part)
    reasoning = getattr(msg, "reasoning_content", "") or ""
    if not reasoning and hasattr(msg, "reasoning"):
        reasoning = getattr(msg, "reasoning", "") or ""
    if not reasoning and hasattr(msg, "model_extra") and msg.model_extra:
        reasoning = msg.model_extra.get("reasoning_content") or msg.model_extra.get("reasoning") or ""
    
    # 2. Extract from content tags (fallback for models that wrap thought in text)
    if not reasoning:
        text = message_text(msg)
        import re
        match = re.search(r'<(thought|thinking|reasoning)>([\s\S]*?)<\/\1>', text, re.I)
        if match:
            reasoning = match.group(2).strip()
            
    return str(reasoning)


def extract_token_usage(usage) -> dict:
    thinking_tokens = getattr(usage, "completion_tokens_details", None)
    thinking_count = 0
    if thinking_tokens and hasattr(thinking_tokens, "reasoning_tokens"):
        thinking_count = thinking_tokens.reasoning_tokens or 0
    
    return {
        "input": getattr(usage, "prompt_tokens", 0) or 0,
        "thinking": thinking_count,
        "output": getattr(usage, "completion_tokens", 0) or 0,
        "total": getattr(usage, "total_tokens", 0) or 0,
    }


def message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "".join(parts)
    return str(content or "")


def generate_chat(system_prompt: str, user_prompt: str, temperature: float = 0.0):
    return client.chat.completions.create(
        model=OPENROUTER_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        extra_headers=EXTRA_HEADERS,
        extra_body={
            "include_reasoning": True
        }
    )


def stream_chat(system_prompt: str, user_prompt: str, temperature: float = 0.0):
    kwargs = dict(
        model=OPENROUTER_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        extra_headers=EXTRA_HEADERS,
        stream=True,
        extra_body={"include_reasoning": True},
    )
    try:
        return client.chat.completions.create(**kwargs, stream_options={"include_usage": True})
    except TypeError:
        # Older client versions may not support stream_options.
        return client.chat.completions.create(**kwargs)
