import json
from db import execute_sql
from prompts import AGENTIC_PLANNING_PROMPT
from .client import AGENTIC_ENABLED, generate_chat, message_text


def stream_agentic_evaluate(question: str, columns: list, rows: list,
                            schema_context: str, memory_context: str = ""):
    if not AGENTIC_ENABLED:
        return
        
    sample = rows[:20]
    user_prompt = (
        f"Câu hỏi user: {question}\n\n"
        f"Data hiện có ({len(rows)} rows, {len(columns)} cols):\n"
        f"Columns: {json.dumps(columns, ensure_ascii=False)}\n"
        f"Sample (first {len(sample)} rows): {json.dumps(sample, ensure_ascii=False)}\n\n"
        f"Schema:\n{schema_context}\n\n"
        f"Memory:\n{memory_context}"
    )

    full_text = ""
    full_thinking = ""
    
    from .client import stream_chat
    response = stream_chat(AGENTIC_PLANNING_PROMPT, user_prompt, temperature=0)
    
    for chunk in response:
        delta = chunk.choices[0].delta.content if chunk.choices[0].delta.content else ""
        reasoning = ""
        if hasattr(chunk.choices[0].delta, "reasoning_content"):
            reasoning = chunk.choices[0].delta.reasoning_content or ""
        elif hasattr(chunk.choices[0].delta, "reasoning"):
            reasoning = chunk.choices[0].delta.reasoning or ""
            
        if reasoning:
            full_thinking += reasoning
            yield {"type": "thinking", "content": reasoning}
            
        if delta:
            full_text += delta

    try:
        content = full_text.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
        
        final_result = {"thinking": full_thinking, "sufficient": result.get("sufficient", True), "reason": result.get("reason", "")}
        if not final_result["sufficient"]:
            final_result["additional_sql"] = result.get("additional_sql", "").strip()
            
        yield {"type": "final", "result": final_result}
    except Exception as e:
        print(f"[AGENTIC] Evaluation failed to parse: {e}")
        yield {"type": "final", "result": {"thinking": full_thinking, "sufficient": True}}


def agentic_evaluate(question: str, columns: list, rows: list,
                     schema_context: str, memory_context: str = "") -> dict | None:
    # Legacy wrapper if needed, but we'll use the stream version
    gen = stream_agentic_evaluate(question, columns, rows, schema_context, memory_context)
    res = None
    for part in gen:
        if part["type"] == "final":
            res = part["result"]
    return res


def execute_agentic_step(evaluation: dict) -> dict | None:
    sql = evaluation.get("additional_sql", "")
    if not sql:
        return None
    try:
        result = execute_sql(sql)
        return {
            "sql": sql,
            "reason": evaluation.get("reason", ""),
            "columns": result["columns"],
            "rows": result["rows"],
        }
    except Exception as e:
        print(f"[AGENTIC] Additional query failed: {e}")
        return None
