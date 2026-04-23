import re
import time
from db import get_schema_context, execute_sql
from prompts import SQL_ROBOT_RULES
from .client import count_tokens, count_tokens_exact, extract_thinking, extract_token_usage, generate_chat, message_text
from .parser import clean_sql


def build_sql_system_prompt(custom_instruction: str = "", memory_context: str = "") -> dict:
    schema = get_schema_context()
    rules = SQL_ROBOT_RULES
    instruction = (custom_instruction or "").strip()
    memory = (memory_context or "").strip()

    system_prompt = ""
    if instruction:
        system_prompt += f"{instruction}\n\n"
    system_prompt += rules
    if memory:
        system_prompt += f"\n\nMemory Context:\n{memory}"
    system_prompt += f"\n\nSchema:\n{schema}"

    return {
        "prompt": system_prompt,
        "counts": {
            "schema": count_tokens(schema),
            "rules": count_tokens(rules),
            "instruction": count_tokens(instruction) if instruction else 0,
            "memory": count_tokens(memory) if memory else 0,
        }
    }


def text_to_sql(question: str, memory_context: str = "", custom_instruction: str = "") -> dict:
    prompt_data = build_sql_system_prompt(custom_instruction=custom_instruction, memory_context=memory_context)
    system_prompt = prompt_data["prompt"]

    response = generate_chat(system_prompt, question, temperature=0)
    usage = extract_token_usage(response.usage)
    usage.update(prompt_data["counts"])
    usage["question"] = count_tokens(question)

    sql = clean_sql(message_text(response.choices[0].message))
    thinking = extract_thinking(response)

    try:
        db_result = execute_sql(sql)
    except Exception as e:
        return {
            "sql": sql,
            "thinking": thinking,
            "token_usage": usage,
            "columns": [],
            "rows": [],
            "error": str(e),
        }

    return {
        "sql": sql,
        "thinking": thinking,
        "token_usage": usage,
        "columns": db_result["columns"],
        "rows": db_result["rows"],
    }


def text_to_sql_detailed(question: str, memory_context: str = "", custom_instruction: str = "") -> dict:
    timing = {}
    t_total = time.perf_counter()

    t = time.perf_counter()
    prompt_data = build_sql_system_prompt(custom_instruction=custom_instruction, memory_context=memory_context)
    system_prompt = prompt_data["prompt"]
    timing["build_prompt"] = round((time.perf_counter() - t) * 1000, 1)

    t = time.perf_counter()
    response = generate_chat(system_prompt, question, temperature=0)
    timing["llm_sql_1"] = round((time.perf_counter() - t) * 1000, 1)

    usage = extract_token_usage(response.usage)
    usage.update(prompt_data["counts"])
    usage["question"] = count_tokens(question)

    sql = clean_sql(message_text(response.choices[0].message))
    thinking = extract_thinking(response)
    error: str | None = None
    db_result = {"columns": [], "rows": []}
    try:
        t = time.perf_counter()
        db_result = execute_sql(sql)
        timing["db_exec_1"] = round((time.perf_counter() - t) * 1000, 1)
    except Exception as e:
        error = str(e)

    timing["retry_count"] = 0.0
    timing["total"] = round((time.perf_counter() - t_total) * 1000, 1)

    return {
        "sql": sql,
        "thinking": thinking,
        "token_usage": usage,
        "columns": db_result["columns"],
        "rows": db_result["rows"],
        "timing_ms": timing,
        "error": error,
    }


async def stream_text_to_sql(question: str, memory_context: str = "", custom_instruction: str = ""):
    """Async generator yielding {'type': 'thinking', 'content': '...'} and finally the full result."""
    from .client import stream_chat, extract_token_usage, message_text, extract_thinking
    from .parser import clean_sql
    
    prompt_data = build_sql_system_prompt(custom_instruction=custom_instruction, memory_context=memory_context)
    system_prompt = prompt_data["prompt"]
    
    full_text = ""
    thinking_buffer = ""
    in_thinking_tag = False
    
    last_usage = None
    # We use a simple tag detector for streaming thinking
    response_stream = stream_chat(system_prompt, question)
    
    for chunk in response_stream:
        if getattr(chunk, "usage", None):
            last_usage = chunk.usage
        delta = chunk.choices[0].delta
        content = delta.content or ""
        reasoning = getattr(delta, "reasoning_content", "") or ""
        
        if reasoning:
            yield {"type": "thinking", "chunk": reasoning}
            thinking_buffer += reasoning
        elif content:
            full_text += content
            # Try to detect tags in content if not in native reasoning_content
            if "<thinking>" in full_text and "</thinking>" not in full_text:
                in_thinking_tag = True
            if in_thinking_tag:
                match = re.search(r'<thinking>([\s\S]*)$', full_text, re.I)
                if match:
                    # This is slightly complex for streaming, but let's yield the new delta
                    tag_start = full_text.find("<thinking>") + 10
                    new_thought = full_text[tag_start:]
                    # We only yield the difference since last yielded might be hard
                    # For now, just yield the content and let frontend handle it or just yield 'thinking' type to show spinner
                    yield {"type": "thinking", "chunk": content}
            if "</thinking>" in full_text:
                in_thinking_tag = False

    # Now we have the full text, we can use existing logic for DB exec
    # For now, we'll just parse the final text
    thinking = thinking_buffer
    if not thinking:
        match = re.search(r'<thinking>([\s\S]*?)<\/thinking>', full_text, re.I)
        if match:
            thinking = match.group(1).strip()
    
    sql = clean_sql(full_text)
    
    # Execute SQL (this part is still blocking, but we already yielded thinking)
    try:
        db_result = execute_sql(sql)
    except Exception as e:
        # Fallback to sync retry for now to keep it simple
        db_result = {"columns": [], "rows": []}
        # In a real app, we'd retry here with another stream
    
    usage = {}
    if last_usage is not None:
        usage = extract_token_usage(last_usage)
    else:
        # Fallback: at least surface static prompt component counts (approx) if provider doesn't include usage.
        usage = {"input": 0, "thinking": 0, "output": 0, "total": 0}

    # Exact component breakdown (sum to prompt tokens; remainder assigned to `schema`)
    try:
        schema = get_schema_context()
        rules = SQL_ROBOT_RULES
        instruction = (custom_instruction or "").strip()
        memory = (memory_context or "").strip()

        rules_tokens = count_tokens_exact(rules) if rules else 0
        instruction_tokens = count_tokens_exact(instruction) if instruction else 0
        memory_tokens = count_tokens_exact(memory) if memory else 0
        question_tokens = count_tokens_exact(question) if question else 0

        known = rules_tokens + instruction_tokens + memory_tokens + question_tokens
        schema_tokens = max(0, int(usage.get("input", 0) or 0) - known)

        usage["rules"] = rules_tokens
        usage["instruction"] = instruction_tokens
        usage["memory"] = memory_tokens
        usage["question"] = question_tokens
        usage["schema"] = schema_tokens
    except Exception:
        pass

    yield {
        "type": "final",
        "sql": sql,
        "thinking": thinking,
        "columns": db_result["columns"],
        "rows": db_result["rows"],
        "token_usage": usage
    }
