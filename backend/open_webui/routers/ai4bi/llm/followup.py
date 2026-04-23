import json
import os
import re
import time
from prompts import FOLLOWUP_SYSTEM_PROMPT
from .client import count_tokens, generate_chat, message_text
from .parser import parse_json_array


def _normalize_followups(items: list[str], current_question: str, max_count: int) -> list[str]:
    current_norm = re.sub(r"\s+", " ", current_question.strip()).lower()
    seen = set()
    out = []
    for item in items:
        text = item.strip().strip("-").strip()
        if not text:
            continue
        key = re.sub(r"\s+", " ", text.strip()).lower()
        if not key or key == current_norm or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max_count:
            break
    return out


def generate_followup_questions(question: str, reply: str, columns: list, rows: list,
                                memory_context: str = "") -> list[str]:
    enabled = os.getenv("FOLLOWUP_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return []

    max_count = int(os.getenv("FOLLOWUP_COUNT", "4"))
    max_rows = int(os.getenv("FOLLOWUP_MAX_ROWS", "20"))
    max_text_chars = int(os.getenv("FOLLOWUP_MAX_TEXT_CHARS", "1200"))
    sample_rows = rows[:max_rows]
    data_text = json.dumps({"columns": columns, "rows": sample_rows}, ensure_ascii=False)
    if len(data_text) > max_text_chars:
        data_text = data_text[:max_text_chars] + "..."

    user_prompt = (
        f"Memory Context:\n{memory_context}\n\n"
        f"Câu hỏi user vừa hỏi:\n{question}\n\n"
        f"Assistant vừa trả lời:\n{reply}\n\n"
        f"Dữ liệu tổng quan:\n{data_text}\n\n"
        f"Hãy trả về {max_count} câu hỏi follow-up khác nhau, JSON array."
    )

    try:
        response = generate_chat(FOLLOWUP_SYSTEM_PROMPT, user_prompt, temperature=0.2)
        parsed = parse_json_array(message_text(response.choices[0].message))
    except Exception:
        parsed = []
    return _normalize_followups(parsed, current_question=question, max_count=max_count)


def generate_followup_questions_detailed(question: str, reply: str, columns: list, rows: list,
                                         memory_context: str = "") -> dict:
    timing = {}
    t_total = time.perf_counter()
    enabled = os.getenv("FOLLOWUP_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return {"questions": [], "timing_ms": {"disabled": 1.0, "total": 0.0}}

    t = time.perf_counter()
    max_count = int(os.getenv("FOLLOWUP_COUNT", "4"))
    max_rows = int(os.getenv("FOLLOWUP_MAX_ROWS", "20"))
    max_text_chars = int(os.getenv("FOLLOWUP_MAX_TEXT_CHARS", "1200"))
    sample_rows = rows[:max_rows]
    data_text = json.dumps({"columns": columns, "rows": sample_rows}, ensure_ascii=False)
    if len(data_text) > max_text_chars:
        data_text = data_text[:max_text_chars] + "..."
    timing["prepare_input"] = round((time.perf_counter() - t) * 1000, 1)

    user_prompt = (
        f"Memory Context:\n{memory_context}\n\n"
        f"Câu hỏi user vừa hỏi:\n{question}\n\n"
        f"Assistant vừa trả lời:\n{reply}\n\n"
        f"Dữ liệu tổng quan:\n{data_text}\n\n"
        f"Hãy trả về {max_count} câu hỏi follow-up khác nhau, JSON array."
    )

    try:
        t = time.perf_counter()
        response = generate_chat(FOLLOWUP_SYSTEM_PROMPT, user_prompt, temperature=0.2)
        timing["llm_followup"] = round((time.perf_counter() - t) * 1000, 1)
        parsed = parse_json_array(message_text(response.choices[0].message))
    except Exception:
        parsed = []

    t = time.perf_counter()
    questions = _normalize_followups(parsed, current_question=question, max_count=max_count)
    timing["normalize_followup"] = round((time.perf_counter() - t) * 1000, 1)
    timing["total"] = round((time.perf_counter() - t_total) * 1000, 1)
    return {"questions": questions, "timing_ms": timing}
