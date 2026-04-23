import os
import json
import re
from collections import OrderedDict
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")

from db import (
    init_chat_history_table,
    init_memory_facts_table,
    init_memory_vectors_table,
    init_sidebar_tables,
    get_chat_history_page,
    get_chat_history_session,
    count_chat_history,
)


from llm import (
    build_reply_contents,
    build_sql_system_prompt,
    VISUALIZATION_PROMPT_RULES,
)
from memory import MemoryService
from chat_service import process_chat
from sidebar_service import (
    get_heartbeat_page_cached,
    get_signals_page_cached,
    get_landing_suggestions_cached,
    refresh_landing_suggestions,
)

app = FastAPI()

# Table initializations are deferred to `/mcp/setup` to support dynamic connection sizing without crashing on startup.
memory_service = MemoryService()

ADMIN_TOKEN = os.getenv("MEMORY_ADMIN_TOKEN", "").strip()

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    sessionId: str = ""
    userId: str = "default_user"
    instruction: str = ""


class MemorySearchRequest(BaseModel):
    userId: str = "default_user"
    query: str
    topK: int = 10


class MemoryContextPreviewRequest(BaseModel):
    message: str
    sessionId: str = ""
    userId: str = "default_user"
    columns: list[str] = []
    rows: list[list[str]] = []

class FileIngestItem(BaseModel):
    name: str
    content: str


class FileIngestRequest(BaseModel):
    userId: str = "default_user"
    sessionId: str = ""
    files: list[FileIngestItem] = []

class TokenCountRequest(BaseModel):
    text: str = ""
    model: str | None = None

class McpSetupRequest(BaseModel):
    url: str

def _guard_admin(x_admin_token: str | None):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="MEMORY_ADMIN_TOKEN is not configured")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")

@app.get("/mcp/status")
def mcp_status():
    from db.connection import is_configured, get_metadata
    return {
        "configured": is_configured(),
        "metadata": get_metadata()
    }

@app.post("/mcp/setup")
def mcp_setup(req: McpSetupRequest):
    from db.connection import configure_pool
    try:
        configure_pool(req.url)
        # Initialize tables after connection is configured
        init_chat_history_table()
        init_memory_facts_table()
        init_memory_vectors_table()
        init_sidebar_tables()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/mcp/disconnect")
def mcp_disconnect():
    from db.connection import disconnect_pool
    disconnect_pool()
    return {"success": True}


@app.get("/mcp/tables")
def mcp_tables():
    from db.schema import get_tables_schema
    import traceback
    try:
        tables = get_tables_schema()
        return {
            "success": True,
            "tables": tables,
            "total": len(tables)
        }
    except Exception as e:
        print("Error in /mcp/tables:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


_TOKEN_COUNT_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_TOKEN_COUNT_CACHE_MAX = 128


def _token_cache_get(key: str) -> dict | None:
    v = _TOKEN_COUNT_CACHE.get(key)
    if v is None:
        return None
    _TOKEN_COUNT_CACHE.move_to_end(key)
    return v


def _token_cache_set(key: str, value: dict) -> None:
    _TOKEN_COUNT_CACHE[key] = value
    _TOKEN_COUNT_CACHE.move_to_end(key)
    while len(_TOKEN_COUNT_CACHE) > _TOKEN_COUNT_CACHE_MAX:
        _TOKEN_COUNT_CACHE.popitem(last=False)

def _maybe_json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except Exception:
            return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return json.loads(value)
        except Exception:
            return None
    return None

def _preview_text(text: str, max_len: int = 140) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if not cleaned:
        return ""
    return cleaned if len(cleaned) <= max_len else (cleaned[: max_len - 1] + "…")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(v) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def _infer_suggested_questions(tables: list[dict], instruction: str = "", max_n: int = 4) -> list[str]:
    """
    Generate schema-driven suggested questions (no domain hard-coding).
    `instruction` (from UI) can provide extra context about the domain.
    """
    instr = (instruction or "").strip()
    questions: list[str] = []

    # pick a primary table: largest by rows, fallback first table
    tables_sorted = sorted(tables, key=lambda t: int(t.get("row_count") or 0), reverse=True)
    top = tables_sorted[0] if tables_sorted else None
    if top:
        tname = top.get("name") or ""
        if tname:
            questions.append(f"Cho tôi xem tổng quan về bảng `{tname}` (các cột chính và ý nghĩa)")

            cols = top.get("columns") or []
            date_col = ""
            numeric_col = ""
            for c in cols:
                cname = str(c.get("name") or "")
                ctype = str(c.get("data_type") or "").lower()
                if not date_col and (ctype in {"date", "datetime", "timestamp"} or "date" in cname.lower()):
                    date_col = cname
                if not numeric_col and ctype in {"int", "decimal", "float", "double"}:
                    numeric_col = cname
                if date_col and numeric_col:
                    break

            if date_col:
                questions.append(f"Xu hướng số bản ghi theo thời gian trong `{tname}` (dựa trên cột `{date_col}`)")
            if date_col and numeric_col:
                questions.append(f"Tổng/Trung bình `{numeric_col}` theo tháng trong `{tname}` (dựa trên `{date_col}`)")
            elif numeric_col:
                questions.append(f"Phân phối và top giá trị của cột `{numeric_col}` trong `{tname}`")

    # Add a generic exploration question, optionally referencing instruction context
    if instr:
        questions.append("Dựa trên instruction của tôi, hãy đề xuất 3 chỉ số quan trọng nhất và cách truy vấn chúng")
    else:
        questions.append("Đề xuất 3 chỉ số quan trọng nhất từ schema hiện tại và cách truy vấn chúng")

    # Dedupe + trim to max_n
    seen = set()
    out: list[str] = []
    for q in questions:
        qn = re.sub(r"\s+", " ", (q or "")).strip()
        if not qn:
            continue
        key = qn.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(qn)
        if len(out) >= max_n:
            break
    return out

# NOTE:
# Sidebar content (signals/heartbeat/landing suggestions) is generated in
# `backend/sidebar_service.py` and is designed to be schema-driven (no domain hard-coding).
@app.post("/chat")
async def chat(req: ChatRequest):
    sse_stream = await process_chat(
        message=req.message,
        session_id=req.sessionId,
        user_id=req.userId,
        instruction=req.instruction,
        memory_service=memory_service,
    )
    return StreamingResponse(
        sse_stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/tokens/count")
def tokens_count(req: TokenCountRequest):
    text = req.text or ""
    model_override = (req.model or "").strip()
    env_model = (os.getenv("OPENROUTER_MODEL") or "").strip()
    model = model_override or env_model

    # Cache by (model + text)
    key_src = f"{model}\n{text}"
    cache_key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
    cached = _token_cache_get(cache_key)
    if cached is not None:
        return cached

    # Count via provider usage to match the actual model tokenizer.
    # NOTE: This triggers a tiny completion request (max_tokens=1) and may incur latency/cost.
    tokens: int | None = None
    exact = False
    error: str | None = None
    resolved_model: str | None = model or None

    try:
        from llm.client import client as llm_client, EXTRA_HEADERS, OPENROUTER_MODEL

        resolved_model = model or OPENROUTER_MODEL
        res = llm_client.chat.completions.create(
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
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        if isinstance(prompt_tokens, int):
            tokens = int(prompt_tokens)
            exact = True
        else:
            error = "Provider did not return prompt token usage."
    except Exception as e:
        error = str(e)

    payload = {
        "tokens": tokens,
        "exact": exact,
        "model": resolved_model,
        "error": error,
    }
    _token_cache_set(cache_key, payload)
    return payload


@app.get("/chat/history")
def chat_history(userId: str = "default_user", limit: int = 10, offset: int = 0):
    try:
        items = get_chat_history_page(user_id=userId, limit=limit, offset=offset, cross_session=True)
        total = count_chat_history(user_id=userId)
        safe_limit = max(1, min(int(limit or 10), 100))
        safe_offset = max(0, int(offset or 0))
        next_offset = safe_offset + len(items)
        has_more = next_offset < total

        return {
            "items": [
                {
                    "id": row.get("id"),
                    "sessionId": row.get("session_id") or "",
                    "createdAt": row.get("created_at").isoformat() if row.get("created_at") else None,
                    "question": row.get("question") or "",
                    "replyPreview": _preview_text(row.get("reply") or ""),
                }
                for row in items
            ],
            "limit": safe_limit,
            "offset": safe_offset,
            "nextOffset": next_offset,
            "total": total,
            "hasMore": has_more,
            "isConfigured": True
        }
    except Exception as e:
        if "DATABASE_NOT_CONFIGURED" in str(e):
            return {"items": [], "total": 0, "hasMore": False, "isConfigured": False}
        raise e


@app.get("/chat/history/session")
def chat_history_session(sessionId: str, userId: str = "default_user"):
    if not sessionId:
        raise HTTPException(status_code=400, detail="sessionId is required")

    rows = get_chat_history_session(user_id=userId, session_id=sessionId)
    items = []
    for row in rows:
        sql_breakdown = _maybe_json(row.get("token_sql_breakdown")) or {}
        reply_breakdown = _maybe_json(row.get("token_reply_breakdown")) or {}
        if not isinstance(sql_breakdown, dict):
            sql_breakdown = {}
        if not isinstance(reply_breakdown, dict):
            reply_breakdown = {}

        items.append(
            {
                "id": row.get("id"),
                "sessionId": row.get("session_id") or "",
                "createdAt": row.get("created_at").isoformat() if row.get("created_at") else None,
                "question": row.get("question") or "",
                "sql": row.get("sql_generated") or "",
                "thinking": row.get("thinking") or "",
                "reply": row.get("reply") or "",
                "columns": _maybe_json(row.get("columns_data")) or [],
                "rows": _maybe_json(row.get("rows_data")) or [],
                "chartConfig": _maybe_json(row.get("chart_config")) or None,
                "blocks": _maybe_json(row.get("blocks")) or [],
                "tokenUsage": {
                    **sql_breakdown,
                    "input": int(row.get("token_sql_input") or 0),
                    "thinking": int(row.get("token_sql_thinking") or 0),
                    "output": int(row.get("token_sql_output") or 0),
                    "total": int(row.get("token_sql_total") or 0),
                },
                "replyTokenUsage": {
                    **reply_breakdown,
                    "input": int(row.get("token_reply_input") or 0),
                    "thinking": int(row.get("token_reply_thinking") or 0),
                    "output": int(row.get("token_reply_output") or 0),
                    "total": int(row.get("token_reply_total") or 0),
                },
                "followUpSuggestions": _maybe_json(row.get("follow_up_suggestions")) or [],
            }
        )

    return {"sessionId": sessionId, "items": items}


class FollowUpRequest(BaseModel):
    question: str
    reply: str


@app.post("/chat/generate-followup")
def generate_followup(req: FollowUpRequest):
    try:
        from llm import generate_followup_questions_detailed
        result = generate_followup_questions_detailed(
            req.question, req.reply, [], [], "",
        )
        return {"questions": result.get("questions", [])}
    except Exception as e:
        return {"questions": [], "error": str(e)}


@app.get("/signals")
def signals(limit: int = 5, offset: int = 0, instruction: str = ""):
    try:
        data = get_signals_page_cached(limit=limit, offset=offset, instruction=instruction)
        return {**data, "isConfigured": True}
    except Exception as e:
        if "DATABASE_NOT_CONFIGURED" in str(e):
            return {"items": [], "total": 0, "hasMore": False, "isConfigured": False}
        raise e


@app.get("/heartbeat")
def heartbeat(limit: int = 4, offset: int = 0, instruction: str = ""):
    try:
        data = get_heartbeat_page_cached(limit=limit, offset=offset, instruction=instruction)
        return {**data, "isConfigured": True}
    except Exception as e:
        if "DATABASE_NOT_CONFIGURED" in str(e):
            return {"items": [], "total": 0, "hasMore": False, "isConfigured": False}
        raise e


@app.get("/landing-suggestions")
def landing_suggestions(userId: str = "default_user", instruction: str = ""):
    try:
        data = get_landing_suggestions_cached(user_id=userId, instruction=instruction)
        return {**data, "isConfigured": True}
    except Exception as e:
        if "DATABASE_NOT_CONFIGURED" in str(e):
            return {"items": [], "total": 0, "isConfigured": False}
        raise e


@app.post("/landing-suggestions/refresh")
def landing_suggestions_refresh(userId: str = "default_user", instruction: str = ""):
    return refresh_landing_suggestions(user_id=userId, instruction=instruction)


@app.post("/files/ingest")
def ingest_files(req: FileIngestRequest):
    if not req.files:
        return {"status": "ok", "ingested": 0, "results": []}
    results = []
    for f in req.files:
        results.append(
            memory_service.ingest_reference_file(
                user_id=req.userId,
                session_id=req.sessionId,
                filename=f.name,
                content=f.content,
            )
        )
    ingested = sum(1 for r in results if r.get("status") == "ok")
    return {"status": "ok", "ingested": ingested, "results": results}


@app.get("/memory/admin/overview")
def memory_admin_overview(userId: str = "default_user", x_admin_token: str | None = Header(default=None)):
    _guard_admin(x_admin_token)
    return memory_service.admin_overview(user_id=userId)


@app.post("/memory/admin/search")
def memory_admin_search(req: MemorySearchRequest, x_admin_token: str | None = Header(default=None)):
    _guard_admin(x_admin_token)
    return memory_service.admin_search(user_id=req.userId, query=req.query, top_k=req.topK)


@app.delete("/memory/admin/items/{memory_id}")
def memory_admin_delete(memory_id: int, userId: str = "default_user", x_admin_token: str | None = Header(default=None)):
    _guard_admin(x_admin_token)
    return memory_service.admin_delete_item(user_id=userId, memory_id=memory_id)


@app.post("/memory/admin/reset")
def memory_admin_reset(userId: str = "default_user", x_admin_token: str | None = Header(default=None)):
    _guard_admin(x_admin_token)
    return memory_service.admin_reset(user_id=userId)


@app.post("/memory/admin/rebuild")
def memory_admin_rebuild(userId: str = "default_user", x_admin_token: str | None = Header(default=None)):
    _guard_admin(x_admin_token)
    return memory_service.admin_rebuild(user_id=userId)


@app.post("/memory/admin/context-preview")
def memory_admin_context_preview(req: MemoryContextPreviewRequest, x_admin_token: str | None = Header(default=None)):
    _guard_admin(x_admin_token)
    sql_ctx = memory_service.build_stage_memory_context(req.userId, req.sessionId, req.message, stage="sql")
    reply_ctx = memory_service.build_stage_memory_context(req.userId, req.sessionId, req.message, stage="reply")
    sql_prompt = build_sql_system_prompt(memory_context=sql_ctx.render())
    reply_data = build_reply_contents(
        question=req.message, columns=req.columns or [], rows=req.rows or [],
        memory_context=reply_ctx.render(),
    )
    return {
        "user_id": req.userId,
        "session_id": req.sessionId,
        "message": req.message,
        "memory_context": {"sql": sql_ctx.render(), "reply": reply_ctx.render()},
        "stage1_sql_prompt": {"system_prompt": sql_prompt["prompt"], "user_content": req.message},
        "stage2_reply_prompt": {"system_prompt": VISUALIZATION_PROMPT_RULES, "user_content": reply_data["contents"]},
    }

@app.get("/database/summary")
def database_summary(instruction: str = ""):
    """
    Get generic database summary that works for ANY database schema.
    Automatically detects tables, columns, row counts, and provides sample data.
    """
    try:
        from db.schema import get_tables_schema

        tables = get_tables_schema()

        summary = {
            "database_name": "Unknown",
            "total_tables": len(tables),
            "total_rows": 0,
            "tables": [],
            "largest_tables": [],
            "suggested_questions": []
        }

        # Get database name from connection metadata
        try:
            from db.connection import get_metadata
            metadata = get_metadata()
            summary["database_name"] = metadata.get("database", "Unknown")
        except:
            pass

        # Process tables
        tables_with_rows = []
        for table in tables:
            table_info = {
                "name": table["name"],
                "description": table.get("description", ""),
                "row_count": table.get("row_count", 0),
                "column_count": table.get("column_count", 0),
                "columns": [col["name"] for col in table.get("columns", [])[:10]]
            }
            summary["tables"].append(table_info)
            summary["total_rows"] += table.get("row_count", 0)

            if table.get("row_count", 0) > 0:
                tables_with_rows.append(table_info)

        # Sort tables by row count (largest first)
        summary["largest_tables"] = sorted(
            tables_with_rows,
            key=lambda x: x["row_count"],
            reverse=True
        )[:10]

        # Generate suggested questions based on actual schema (+ optional instruction from UI)
        summary["suggested_questions"] = _infer_suggested_questions(tables, instruction=instruction, max_n=4)

        return summary

    except Exception as e:
        if "DATABASE_NOT_CONFIGURED" in str(e):
            return {
                "database_name": "Not Configured",
                "total_tables": 0,
                "total_rows": 0,
                "tables": [],
                "isConfigured": False,
                "error": "Please connect MCP database first"
            }
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/database/sample")
def database_sample_data(limit: int = 5):
    """
    Get sample data from all tables for preview.
    Works with ANY database schema.

    Args:
        limit: Number of rows per table to sample (default: 5)
    """
    try:
        from db.schema import get_all_tables
        all_tables = get_all_tables()

        sample_data = {}
        for table_name, table_data in all_tables.items():
            sample_data[table_name] = {
                "columns": table_data["columns"],
                "row_count": len(table_data["rows"]),
                "sample_rows": table_data["rows"][:limit]
            }

        return {
            "success": True,
            "total_tables": len(sample_data),
            "data": sample_data,
            "isConfigured": True
        }

    except Exception as e:
        if "DATABASE_NOT_CONFIGURED" in str(e):
            return {
                "success": False,
                "total_tables": 0,
                "data": {},
                "isConfigured": False,
                "error": "Please connect MCP database first"
            }
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import sys, uvicorn
    if "--serve" in sys.argv:
        uvicorn.run(app, host="0.0.0.0", port=8333)
