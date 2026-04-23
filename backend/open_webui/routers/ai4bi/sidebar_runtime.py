from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from sqlalchemy import inspect, text

from open_webui.internal.db import Base, engine, metadata_obj
from open_webui.models.users import UserModel
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.models import get_all_models

from .prompts import DAILY_HEARTBEAT_PROMPT, DAILY_SIGNALS_PROMPT


_CACHE_TTL_SECONDS = 30
_SNAPSHOT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

_EXCLUDED_TABLES = {
    "alembic_version",
    "ai4bi_sidebar_signals",
    "ai4bi_sidebar_heartbeat",
}


def _cache_key(instruction: str) -> str:
    return re.sub(r"\s+", " ", (instruction or "")).strip().lower()


def _get_cached_snapshot(instruction: str) -> dict[str, Any] | None:
    key = _cache_key(instruction)
    cached = _SNAPSHOT_CACHE.get(key)
    if not cached:
        return None
    ts, payload = cached
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _SNAPSHOT_CACHE.pop(key, None)
        return None
    return payload


def _set_cached_snapshot(instruction: str, payload: dict[str, Any]) -> None:
    _SNAPSHOT_CACHE[_cache_key(instruction)] = (time.time(), payload)
    if len(_SNAPSHOT_CACHE) > 64:
        oldest = sorted(_SNAPSHOT_CACHE.items(), key=lambda item: item[1][0])[:16]
        for key, _ in oldest:
            _SNAPSHOT_CACHE.pop(key, None)


def _quote(name: str) -> str:
    return engine.dialect.identifier_preparer.quote_identifier(name)


def _qualified_table_name(table_name: str) -> str:
    schema = metadata_obj.schema
    if schema:
        return f"{_quote(schema)}.{_quote(table_name)}"
    return _quote(table_name)


def _normalize_type(raw_type: Any) -> str:
    text_type = str(raw_type or "").lower()
    if "timestamp" in text_type:
        return "timestamp"
    if text_type.startswith("date"):
        return "date"
    if "time" in text_type:
        return "datetime"
    if any(token in text_type for token in ("bigint", "integer", "smallint")):
        return "int"
    if any(token in text_type for token in ("numeric", "decimal")):
        return "decimal"
    if any(token in text_type for token in ("double", "real")):
        return "double"
    if "float" in text_type:
        return "float"
    if any(token in text_type for token in ("varchar", "character varying")):
        return "varchar"
    if any(token in text_type for token in ("char", "character")):
        return "char"
    if any(token in text_type for token in ("text", "json", "jsonb", "uuid")):
        return "text"
    return text_type or "text"


def _internal_table_names() -> set[str]:
    names = set()
    for key in Base.metadata.tables.keys():
        names.add(key.split(".")[-1])
    return names | _EXCLUDED_TABLES


def _business_tables() -> list[dict[str, Any]]:
    schema = metadata_obj.schema
    inspector = inspect(engine)
    internal_tables = _internal_table_names()
    table_names = [
        name
        for name in inspector.get_table_names(schema=schema)
        if name not in internal_tables and not name.startswith("sqlite_")
    ]

    tables: list[dict[str, Any]] = []
    with engine.connect() as conn:
        for table_name in table_names:
            columns_info = inspector.get_columns(table_name, schema=schema)
            columns = []
            for index, column in enumerate(columns_info, start=1):
                columns.append(
                    {
                        "name": column["name"],
                        "data_type": _normalize_type(column.get("type")),
                        "full_type": str(column.get("type") or ""),
                        "nullable": bool(column.get("nullable", True)),
                        "default": column.get("default"),
                        "description": (column.get("comment") or "").strip()
                        or f"Mo ta du lieu cua cot `{column['name']}`.",
                        "position": index,
                    }
                )

            row_count = conn.execute(text(f"SELECT COUNT(*) FROM {_qualified_table_name(table_name)}")).scalar()
            tables.append(
                {
                    "name": table_name,
                    "description": "",
                    "column_count": len(columns),
                    "row_count": int(row_count or 0),
                    "columns": columns,
                }
            )

    tables.sort(key=lambda table: int(table.get("row_count") or 0), reverse=True)
    return tables


def _is_money_metric(metric_name: str) -> bool:
    lowered = (metric_name or "").lower()
    return any(
        token in lowered for token in ("revenue", "amount", "total", "value", "price", "cost", "profit", "sales")
    )


def _format_compact_number(value: float, instruction: str = "", money: bool = False) -> str:
    try:
        number = float(value)
    except Exception:
        return str(value)

    absolute = abs(number)
    suffix = ""
    scaled = number
    if absolute >= 1e9:
        scaled = number / 1e9
        suffix = "B"
    elif absolute >= 1e6:
        scaled = number / 1e6
        suffix = "M"
    elif absolute >= 1e3:
        scaled = number / 1e3
        suffix = "K"

    currency = ""
    normalized_instruction = (instruction or "").lower()
    if money and ("vnd" in normalized_instruction or "₫" in normalized_instruction):
        currency = "₫"

    if suffix:
        return f"{scaled:.1f}{suffix}{currency}"
    return f"{scaled:,.0f}{currency}"


def _pick_anchor_table(tables: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for table in tables:
        columns = table.get("columns") or []
        has_date = any(column.get("data_type") in {"date", "datetime", "timestamp"} for column in columns)
        has_numeric = any(column.get("data_type") in {"int", "decimal", "float", "double"} for column in columns)
        score = 0
        if has_date:
            score += 5
        if has_numeric:
            score += 5
        score += min(int(table.get("row_count") or 0) // 1000, 20)
        candidates.append((score, table))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _pick_date_column(columns: list[dict[str, Any]]) -> str | None:
    preferred = ("sale_date", "transaction_date", "created_at", "date", "updated_at")
    by_name = {str(column.get("name") or ""): column for column in columns}
    for name in preferred:
        column = by_name.get(name)
        if column and column.get("data_type") in {"date", "datetime", "timestamp"}:
            return name

    for column in columns:
        name = str(column.get("name") or "")
        if column.get("data_type") in {"date", "datetime", "timestamp"} or "date" in name.lower():
            return name
    return None


def _pick_metric_columns(columns: list[dict[str, Any]], max_n: int = 2) -> list[str]:
    numeric = [column for column in columns if column.get("data_type") in {"int", "decimal", "float", "double"}]
    preferred = (
        "revenue",
        "sales",
        "amount",
        "total",
        "value",
        "cost",
        "profit",
        "margin",
        "qty",
        "quantity",
        "count",
    )
    scored: list[tuple[int, str]] = []
    for column in numeric:
        name = str(column.get("name") or "")
        lowered = name.lower()
        if lowered == "id" or lowered.endswith("_id"):
            continue
        score = 0
        for index, token in enumerate(preferred):
            if token in lowered:
                score += len(preferred) - index
        scored.append((score, name))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[str] = []
    for _, name in scored:
        if name not in selected:
            selected.append(name)
        if len(selected) >= max_n:
            break
    return selected


def _pick_dimension_columns(columns: list[dict[str, Any]], max_n: int = 2) -> list[str]:
    dimensions: list[str] = []
    preferred = ("name", "type", "status", "category", "segment", "region", "department", "customer", "product")
    scored: list[tuple[int, str]] = []

    for column in columns:
        data_type = str(column.get("data_type") or "")
        name = str(column.get("name") or "")
        lowered = name.lower()
        if data_type not in {"varchar", "char", "text"}:
            continue
        if lowered == "id" or lowered.endswith("_id") or "uuid" in lowered:
            continue
        score = 0
        for index, token in enumerate(preferred):
            if token in lowered:
                score += len(preferred) - index
        scored.append((score, name))

    scored.sort(key=lambda item: item[0], reverse=True)
    for _, name in scored:
        if name not in dimensions:
            dimensions.append(name)
        if len(dimensions) >= max_n:
            break
    return dimensions


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _detect_as_of(table_name: str, date_column: str | None) -> date:
    if not date_column:
        return datetime.now(timezone.utc).date()

    query = text(f"SELECT MAX({_quote(date_column)}) AS max_d FROM {_qualified_table_name(table_name)}")
    with engine.connect() as conn:
        result = conn.execute(query).scalar()
    return _as_date(result) or datetime.now(timezone.utc).date()


def _window_bounds(as_of: date) -> tuple[date, date, date, date]:
    current_end = as_of + timedelta(days=1)
    current_start = as_of - timedelta(days=6)
    previous_end = current_start
    previous_start = current_start - timedelta(days=7)
    return current_start, current_end, previous_start, previous_end


def _count_distinct_sample(
    table_name: str,
    column_name: str,
    date_column: str | None,
    start: date | None,
    end_exclusive: date | None,
) -> int | None:
    params: dict[str, Any] = {}
    query = f"SELECT COUNT(DISTINCT x) FROM (SELECT {_quote(column_name)} AS x FROM {_qualified_table_name(table_name)}"
    if date_column and start and end_exclusive:
        query += f" WHERE {_quote(date_column)} >= :start AND {_quote(date_column)} < :end_exclusive"
        params["start"] = start
        params["end_exclusive"] = end_exclusive
    query += " LIMIT 50000) AS sampled"

    try:
        with engine.connect() as conn:
            return int(conn.execute(text(query), params).scalar() or 0)
    except Exception:
        return None


def _compute_metrics(
    table_name: str,
    date_column: str | None,
    metric_columns: list[str],
    dimension_columns: list[str],
    as_of: date,
) -> list[dict[str, Any]]:
    current_start, current_end, previous_start, previous_end = _window_bounds(as_of)
    metrics: list[dict[str, Any]] = []

    with engine.connect() as conn:
        if date_column:
            row = (
                conn.execute(
                    text(
                        f"""
                        SELECT
                            SUM(CASE WHEN {_quote(date_column)} >= :current_start AND {_quote(date_column)} < :current_end THEN 1 ELSE 0 END) AS current_value,
                            SUM(CASE WHEN {_quote(date_column)} >= :previous_start AND {_quote(date_column)} < :previous_end THEN 1 ELSE 0 END) AS previous_value
                        FROM {_qualified_table_name(table_name)}
                        """
                    ),
                    {
                        "current_start": current_start,
                        "current_end": current_end,
                        "previous_start": previous_start,
                        "previous_end": previous_end,
                    },
                )
                .mappings()
                .first()
            )
            current_value = float((row or {}).get("current_value") or 0)
            previous_value = float((row or {}).get("previous_value") or 0)
        else:
            current_value = float(
                conn.execute(text(f"SELECT COUNT(*) FROM {_qualified_table_name(table_name)}")).scalar() or 0
            )
            previous_value = 0.0

        metrics.append(
            {
                "metric": "count_rows",
                "dimension": "",
                "current": current_value,
                "previous": previous_value if date_column else None,
                "delta": current_value - previous_value if date_column else None,
                "delta_pct": ((current_value - previous_value) / previous_value) if date_column and previous_value else None,
            }
        )

        for metric_name in metric_columns[:2]:
            if date_column:
                row = (
                    conn.execute(
                        text(
                            f"""
                            SELECT
                                SUM(CASE WHEN {_quote(date_column)} >= :current_start AND {_quote(date_column)} < :current_end THEN {_quote(metric_name)} ELSE 0 END) AS current_value,
                                SUM(CASE WHEN {_quote(date_column)} >= :previous_start AND {_quote(date_column)} < :previous_end THEN {_quote(metric_name)} ELSE 0 END) AS previous_value
                            FROM {_qualified_table_name(table_name)}
                            """
                        ),
                        {
                            "current_start": current_start,
                            "current_end": current_end,
                            "previous_start": previous_start,
                            "previous_end": previous_end,
                        },
                    )
                    .mappings()
                    .first()
                )
                current_value = float((row or {}).get("current_value") or 0)
                previous_value = float((row or {}).get("previous_value") or 0)
                delta = current_value - previous_value
                delta_pct = (delta / previous_value) if previous_value else None
            else:
                current_value = float(
                    conn.execute(
                        text(f"SELECT SUM({_quote(metric_name)}) FROM {_qualified_table_name(table_name)}")
                    ).scalar()
                    or 0
                )
                previous_value = None
                delta = None
                delta_pct = None

            metrics.append(
                {
                    "metric": metric_name,
                    "dimension": "",
                    "current": current_value,
                    "previous": previous_value,
                    "delta": delta,
                    "delta_pct": delta_pct,
                }
            )

        if metric_columns and dimension_columns:
            primary_metric = metric_columns[0]
            usable_dimensions: list[str] = []
            for dimension_name in dimension_columns:
                distinct_count = _count_distinct_sample(
                    table_name,
                    dimension_name,
                    date_column,
                    current_start if date_column else None,
                    current_end if date_column else None,
                )
                if distinct_count is None:
                    continue
                if 2 <= distinct_count <= 50:
                    usable_dimensions.append(dimension_name)
                if len(usable_dimensions) >= 2:
                    break

            for dimension_name in usable_dimensions:
                if date_column:
                    rows = conn.execute(
                        text(
                            f"""
                            SELECT
                                COALESCE(CAST({_quote(dimension_name)} AS TEXT), '(null)') AS dimension_value,
                                SUM(CASE WHEN {_quote(date_column)} >= :current_start AND {_quote(date_column)} < :current_end THEN {_quote(primary_metric)} ELSE 0 END) AS current_value,
                                SUM(CASE WHEN {_quote(date_column)} >= :previous_start AND {_quote(date_column)} < :previous_end THEN {_quote(primary_metric)} ELSE 0 END) AS previous_value
                            FROM {_qualified_table_name(table_name)}
                            GROUP BY COALESCE(CAST({_quote(dimension_name)} AS TEXT), '(null)')
                            ORDER BY ABS(COALESCE(SUM(CASE WHEN {_quote(date_column)} >= :current_start AND {_quote(date_column)} < :current_end THEN {_quote(primary_metric)} ELSE 0 END), 0) - COALESCE(SUM(CASE WHEN {_quote(date_column)} >= :previous_start AND {_quote(date_column)} < :previous_end THEN {_quote(primary_metric)} ELSE 0 END), 0)) DESC
                            LIMIT 20
                            """
                        ),
                        {
                            "current_start": current_start,
                            "current_end": current_end,
                            "previous_start": previous_start,
                            "previous_end": previous_end,
                        },
                    ).mappings()
                else:
                    rows = conn.execute(
                        text(
                            f"""
                            SELECT
                                COALESCE(CAST({_quote(dimension_name)} AS TEXT), '(null)') AS dimension_value,
                                SUM({_quote(primary_metric)}) AS current_value
                            FROM {_qualified_table_name(table_name)}
                            GROUP BY COALESCE(CAST({_quote(dimension_name)} AS TEXT), '(null)')
                            ORDER BY ABS(COALESCE(SUM({_quote(primary_metric)}), 0)) DESC
                            LIMIT 20
                            """
                        )
                    ).mappings()

                for row in rows:
                    current_value = float(row.get("current_value") or 0)
                    previous_value = row.get("previous_value")
                    previous_float = float(previous_value or 0) if previous_value is not None else None
                    delta = (current_value - previous_float) if previous_float is not None else None
                    delta_pct = (delta / previous_float) if previous_float not in (None, 0) else None
                    metrics.append(
                        {
                            "metric": primary_metric,
                            "dimension": dimension_name,
                            "dimension_value": str(row.get("dimension_value") or "").strip(),
                            "current": current_value,
                            "previous": previous_float,
                            "delta": delta,
                            "delta_pct": delta_pct,
                        }
                    )

    return metrics


def _build_signals_input(as_of: date, metrics: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    return {
        "asOf": as_of.isoformat(),
        "n": int(limit),
        "metrics": [
            {
                "metric": item.get("metric"),
                "dimension": item.get("dimension") or "",
                "dimension_value": item.get("dimension_value") or "",
                "current": item.get("current"),
                "previous": item.get("previous"),
                "delta": item.get("delta"),
                "delta_pct": item.get("delta_pct"),
            }
            for item in metrics[:200]
        ],
    }


def _build_heartbeat_input(
    as_of: date,
    metrics: list[dict[str, Any]],
    limit: int,
    instruction: str,
) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    for item in metrics:
        metric_name = str(item.get("metric") or "")
        dimension_name = str(item.get("dimension") or "")
        dimension_value = str(item.get("dimension_value") or "")
        label = metric_name
        if dimension_name and dimension_value:
            label = f"{metric_name} • {dimension_value}"

        cards.append(
            {
                "label": label[:32],
                "value": _format_compact_number(
                    float(item.get("current") or 0),
                    instruction=instruction,
                    money=_is_money_metric(metric_name),
                ),
                "delta": (
                    f"{float(item.get('delta_pct')) * 100:+.1f}% so voi ky truoc"
                    if isinstance(item.get("delta_pct"), (int, float))
                    else ""
                ),
                "delta_pct": item.get("delta_pct"),
            }
        )

    cards.sort(
        key=lambda item: abs(float(item.get("delta_pct") or 0)) if isinstance(item.get("delta_pct"), (int, float)) else 0,
        reverse=True,
    )

    return {
        "asOf": as_of.isoformat(),
        "n": int(limit),
        "metrics": cards[: min(50, len(cards))],
    }


def _extract_message_text(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(content)


def _parse_json_array(raw_text: str) -> list[dict[str, Any]]:
    text_value = (raw_text or "").strip()
    if text_value.startswith("```"):
        text_value = text_value.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    match = re.search(r"\[[\s\S]*\]", text_value)
    candidate = match.group(0) if match else text_value
    try:
        parsed = json.loads(candidate)
    except Exception:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


async def _pick_model_id(request: Request, user: UserModel) -> str:
    await get_all_models(request, refresh=True, user=user)
    models = request.app.state.MODELS or {}

    default_models = [
        item.strip()
        for item in str(getattr(request.app.state.config, "DEFAULT_MODELS", "") or "").split(",")
        if item.strip()
    ]

    for model_id in default_models:
        model = models.get(model_id)
        if model and model.get("owned_by") != "arena":
            return model_id

    for model_id, model in models.items():
        if model.get("owned_by") != "arena":
            return model_id

    raise RuntimeError("No usable model is available in Open WebUI.")


async def _generate_json_payload(
    request: Request,
    user: UserModel,
    system_prompt: str,
    user_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    model_id = await _pick_model_id(request, user)
    response = await generate_chat_completion(
        request,
        {
            "model": model_id,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        },
        user,
        bypass_filter=True,
        bypass_system_prompt=True,
    )
    return _parse_json_array(_extract_message_text(response))


def _normalize_signals(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        signal_type = str(item.get("type") or "").strip().lower()
        if signal_type not in {"critical", "watch", "positive"}:
            signal_type = "watch"
        title = str(item.get("title") or "").strip()
        description = str(item.get("desc") or item.get("description") or "").strip()
        if not title or not description:
            continue
        normalized.append(
            {
                "id": index,
                "rank": index,
                "type": signal_type,
                "title": title,
                "desc": description,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
        )
    return normalized


def _normalize_heartbeat(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        trend = str(item.get("trend") or "neutral").strip().lower()
        if trend not in {"up", "down", "neutral"}:
            trend = "neutral"
        if not label or not value:
            continue
        normalized.append(
            {
                "id": index,
                "rank": index,
                "label": label,
                "value": value,
                "delta": str(item.get("delta") or "").strip(),
                "trend": trend,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
        )
    return normalized


async def build_sidebar_snapshot(request: Request, user: UserModel, instruction: str = "") -> dict[str, Any]:
    cached = _get_cached_snapshot(instruction)
    if cached is not None:
        return cached

    tables = _business_tables()
    if not tables:
        payload = {
            "configured": False,
            "signals": [],
            "heartbeat": [],
            "error": "Khong tim thay bang du lieu nghiep vu trong PostgreSQL hien tai.",
        }
        _set_cached_snapshot(instruction, payload)
        return payload

    anchor_table = _pick_anchor_table(tables)
    if not anchor_table:
        payload = {
            "configured": False,
            "signals": [],
            "heartbeat": [],
            "error": "Khong xac dinh duoc bang du lieu phu hop de tao sidebar.",
        }
        _set_cached_snapshot(instruction, payload)
        return payload

    columns = anchor_table.get("columns") or []
    date_column = _pick_date_column(columns)
    metric_columns = _pick_metric_columns(columns)
    dimension_columns = _pick_dimension_columns(columns)
    as_of = _detect_as_of(str(anchor_table.get("name") or ""), date_column)
    metrics = _compute_metrics(str(anchor_table.get("name") or ""), date_column, metric_columns, dimension_columns, as_of)

    if not metrics:
        payload = {
            "configured": False,
            "signals": [],
            "heartbeat": [],
            "error": "Khong tao duoc metric tu schema PostgreSQL hien tai.",
        }
        _set_cached_snapshot(instruction, payload)
        return payload

    signal_payload = _build_signals_input(as_of, metrics, 8)
    heartbeat_payload = _build_heartbeat_input(as_of, metrics, 8, instruction)

    signals = _normalize_signals(await _generate_json_payload(request, user, DAILY_SIGNALS_PROMPT, signal_payload))
    heartbeat = _normalize_heartbeat(
        await _generate_json_payload(request, user, DAILY_HEARTBEAT_PROMPT, heartbeat_payload)
    )

    payload = {
        "configured": True,
        "signals": signals,
        "heartbeat": heartbeat,
        "table": anchor_table.get("name"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "error": "",
    }
    _set_cached_snapshot(instruction, payload)
    return payload
