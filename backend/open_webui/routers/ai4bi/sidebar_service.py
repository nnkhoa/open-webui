from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from db.connection import get_connection
from db.sidebar_store import (
    count_heartbeat_v2,
    count_landing_suggestions,
    count_signals_v2,
    delete_heartbeat_v2,
    delete_landing_suggestions,
    delete_signals_v2,
    get_heartbeat_page_v2,
    get_landing_suggestions,
    get_signals_page_v2,
    insert_heartbeat_v2,
    insert_landing_suggestions,
    insert_signals_v2,
)
from llm import generate_chat, message_text
from prompts import DAILY_HEARTBEAT_PROMPT, DAILY_SIGNALS_PROMPT, LANDING_SUGGESTIONS_PROMPT


_TRUE = {"1", "true", "yes", "on"}

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_llm_json_object_array(text: str) -> list[dict]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    match = re.search(r"\[[\s\S]*\]", raw)
    candidate = match.group(0) if match else raw
    try:
        parsed = json.loads(candidate)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [x for x in parsed if isinstance(x, dict)]


def _qident(name: str) -> str:
    return f"`{(name or '').replace('`', '``')}`"


def _instruction_hash(instruction: str) -> str:
    instr = (instruction or "").strip()
    if not instr:
        return ""
    return hashlib.sha256(instr.encode("utf-8")).hexdigest()


def _is_system_table(table_name: str) -> bool:
    t = (table_name or "").strip().lower()
    if not t:
        return True
    if t.startswith("_meta"):
        return True
    if t.startswith("sidebar_") or t.startswith("landing_") or t.startswith("memory_"):
        return True
    if t in {"chat_history"}:
        return True
    return False


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        s = str(value).strip()
        if not s:
            return None
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def _format_compact_number(value: float, instruction: str = "") -> str:
    try:
        v = float(value)
    except Exception:
        return str(value)
    abs_v = abs(v)
    suffix = ""
    scaled = v
    if abs_v >= 1e9:
        scaled = v / 1e9
        suffix = "B"
    elif abs_v >= 1e6:
        scaled = v / 1e6
        suffix = "M"
    elif abs_v >= 1e3:
        scaled = v / 1e3
        suffix = "K"
    # Intentionally do not guess unit/currency from column names.
    # If unit is needed, it should come from explicit instruction or database metadata.
    return f"{scaled:.1f}{suffix}" if suffix else f"{scaled:,.0f}"


def _pick_anchor_table(tables: list[dict]) -> dict | None:
    # Prefer a table that has both date + numeric (transactional), else largest table.
    candidates = []
    for t in tables:
        name = t.get("name") or ""
        if _is_system_table(name):
            continue
        cols = t.get("columns") or []
        has_date = any((c.get("data_type") in {"date", "datetime", "timestamp"}) for c in cols)
        has_num = any((c.get("data_type") in {"int", "decimal", "float", "double"}) for c in cols)
        score = 0
        if has_date:
            score += 5
        if has_num:
            score += 5
        score += int(t.get("row_count") or 0) // 1000
        candidates.append((score, t))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _pick_date_column(table: str, columns: list[dict]) -> str | None:
    if not columns:
        return None
    candidates: list[str] = []
    for c in columns:
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        dt = str(c.get("data_type") or "").lower().strip()
        if dt in {"date", "datetime", "timestamp"}:
            candidates.append(name)
    if not candidates:
        return None

    # Pick the date-like column that is most populated; tie-break by latest MAX(date).
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        scored: list[tuple[int, date, str]] = []
        for col in candidates:
            try:
                cursor.execute(
                    f"SELECT COUNT({_qident(col)}) AS nn, MAX({_qident(col)}) AS mx FROM {_qident(table)}"
                )
                row = cursor.fetchone() or {}
                nn = int(row.get("nn") or 0)
                mx = _as_date(row.get("mx")) or date.min
                scored.append((nn, mx, col))
            except Exception:
                # If profiling fails for a column, just skip it.
                continue
        if not scored:
            return candidates[0]
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return scored[0][2]
    finally:
        cursor.close()
        conn.close()


def _profile_numeric_sums(
    table: str,
    cols: list[str],
    date_col: str | None,
    start: date | None,
    end_excl: date | None,
) -> list[tuple[str, float, int]]:
    """
    Profile numeric columns by sum(abs(col)) in a time window (if provided).

    Returns: [(col, sum_abs, non_null_count), ...]
    """
    if not table or not cols:
        return []
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        select_parts: list[str] = []
        params: list[Any] = []
        for i, c in enumerate(cols):
            # SUM ignores NULL; if everything is NULL it returns NULL.
            select_parts.append(f"SUM(ABS({_qident(c)})) AS s{i}")
            select_parts.append(f"SUM(CASE WHEN {_qident(c)} IS NOT NULL THEN 1 ELSE 0 END) AS nn{i}")
        where_sql = ""
        if date_col and start and end_excl:
            where_sql = f" WHERE {_qident(date_col)} >= %s AND {_qident(date_col)} < %s"
            params.extend([start, end_excl])
        sql = f"SELECT {', '.join(select_parts)} FROM {_qident(table)}{where_sql}"
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone() or {}
        out: list[tuple[str, float, int]] = []
        for i, c in enumerate(cols):
            s = row.get(f"s{i}")
            nn = row.get(f"nn{i}")
            try:
                sum_abs = float(s or 0)
            except Exception:
                sum_abs = 0.0
            try:
                non_null = int(nn or 0)
            except Exception:
                non_null = 0
            out.append((c, sum_abs, non_null))
        return out
    finally:
        cursor.close()
        conn.close()


def _pick_metric_columns(table: str, date_col: str | None, as_of: date, columns: list[dict], max_n: int = 2) -> list[str]:
    numeric = [c for c in (columns or []) if c.get("data_type") in {"int", "decimal", "float", "double"}]
    if not numeric:
        return []
    candidates: list[str] = []
    for c in numeric:
        name = str(c.get("name") or "").strip()
        lname = name.lower()
        if not name:
            continue
        if lname.endswith("_id") or lname in {"id", "uuid"} or "uuid" in lname:
            continue
        candidates.append(name)
    if not candidates:
        return []

    # Rank purely based on data magnitude in the current window (or whole table if no date_col).
    curr_start, curr_end_excl, _, _ = _window_bounds(as_of)
    profiled = _profile_numeric_sums(
        table=table,
        cols=candidates[:25],  # cap to keep query size bounded
        date_col=date_col,
        start=curr_start if date_col else None,
        end_excl=curr_end_excl if date_col else None,
    )
    if profiled:
        profiled.sort(key=lambda x: (x[1], x[2]), reverse=True)
        picked = [c for (c, _, nn) in profiled if nn > 0][: max(1, int(max_n))]
        if picked:
            return picked

    # Fallback: first N numeric columns (no name-based preference).
    out: list[str] = []
    seen: set[str] = set()
    for n in candidates:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
        if len(out) >= max_n:
            break
    return out


def _parse_varchar_len(full_type: str) -> int | None:
    m = re.search(r"\((\d+)\)", (full_type or ""))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _pick_dimension_columns(table: str, date_col: str | None, as_of: date, columns: list[dict], max_n: int = 6) -> list[str]:
    dims = []
    for c in (columns or []):
        dt = str(c.get("data_type") or "").lower()
        name = str(c.get("name") or "")
        lname = name.lower()
        if dt not in {"varchar", "char", "text"}:
            continue
        if lname.endswith("_id") or lname in {"id", "uuid"} or "uuid" in lname:
            continue
        full_type = str(c.get("full_type") or "")
        if dt in {"varchar", "char"}:
            ln = _parse_varchar_len(full_type)
            if ln is not None and ln > 256:
                continue
        dims.append(name)

    if not dims:
        return []

    # Filter to low/medium cardinality dimensions based on data (no name heuristics).
    curr_start, curr_end_excl, _, _ = _window_bounds(as_of)
    candidates = dims[:25]  # cap to keep query count bounded
    scored: list[tuple[float, str]] = []
    for n in candidates:
        distinct = _count_distinct_sample(
            table,
            n,
            date_col,
            curr_start if date_col else None,
            curr_end_excl if date_col else None,
        )
        if distinct is None:
            continue
        if distinct < 2:
            continue
        if distinct > 200:
            continue
        # Prefer dimensions that are informative but not too high-cardinality.
        # Peak around ~10 distinct values.
        score = 100.0 - abs(float(distinct) - 10.0)
        scored.append((score, n))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        out: list[str] = []
        seen: set[str] = set()
        for _, n in scored:
            if n and n not in seen:
                seen.add(n)
                out.append(n)
            if len(out) >= max_n:
                break
        if out:
            return out

    # Fallback: return first N dimension-like columns (stable, schema-driven).
    out: list[str] = []
    seen: set[str] = set()
    for n in dims:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
        if len(out) >= max_n:
            break
    return out


def _detect_as_of(table: str, date_col: str | None) -> date:
    if not table or not date_col:
        return datetime.utcnow().date()
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT MAX({_qident(date_col)}) AS max_d FROM {_qident(table)}"
        )
        row = cursor.fetchone() or {}
        d = _as_date(row.get("max_d"))
        return d or datetime.utcnow().date()
    finally:
        cursor.close()
        conn.close()


def _window_bounds(as_of: date) -> tuple[date, date, date, date]:
    # Current window: last 7 days inclusive (as_of-6 .. as_of), end exclusive = as_of+1
    curr_end_excl = as_of + timedelta(days=1)
    curr_start = as_of - timedelta(days=6)
    prev_end_excl = curr_start
    prev_start = curr_start - timedelta(days=7)
    return curr_start, curr_end_excl, prev_start, prev_end_excl


def _count_distinct_sample(table: str, col: str, date_col: str | None, start: date | None, end_excl: date | None) -> int | None:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if date_col and start and end_excl:
            sql = (
                f"SELECT COUNT(DISTINCT x) AS n FROM ("
                f" SELECT {_qident(col)} AS x FROM {_qident(table)}"
                f" WHERE {_qident(date_col)} >= %s AND {_qident(date_col)} < %s"
                f" LIMIT 50000"
                f") t"
            )
            cursor.execute(sql, (start, end_excl))
        else:
            sql = (
                f"SELECT COUNT(DISTINCT x) AS n FROM ("
                f" SELECT {_qident(col)} AS x FROM {_qident(table)}"
                f" LIMIT 50000"
                f") t"
            )
            cursor.execute(sql)
        row = cursor.fetchone() or {}
        return int(row.get("n") or 0)
    except Exception:
        return None
    finally:
        cursor.close()
        conn.close()


def _compute_metrics(table: str, date_col: str | None, metric_cols: list[str], dim_cols: list[str], as_of: date) -> list[dict]:
    metrics: list[dict] = []
    curr_start, curr_end_excl, prev_start, prev_end_excl = _window_bounds(as_of)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Volume (count)
        if date_col:
            cursor.execute(
                f"""
                SELECT
                  SUM(CASE WHEN {_qident(date_col)} >= %s AND {_qident(date_col)} < %s THEN 1 ELSE 0 END) AS curr,
                  SUM(CASE WHEN {_qident(date_col)} >= %s AND {_qident(date_col)} < %s THEN 1 ELSE 0 END) AS prev
                FROM {_qident(table)}
                """,
                (curr_start, curr_end_excl, prev_start, prev_end_excl),
            )
            row = cursor.fetchone() or {}
            curr = float(row.get("curr") or 0)
            prev = float(row.get("prev") or 0)
            metrics.append({
                "metric": "count_rows",
                "dimension": "",
                "current": curr,
                "previous": prev,
                "delta": curr - prev,
                "delta_pct": ((curr - prev) / prev) if prev else None,
                "table": table,
                "date_col": date_col,
            })
        else:
            cursor.execute(f"SELECT COUNT(*) AS n FROM {_qident(table)}")
            row = cursor.fetchone() or {}
            metrics.append({
                "metric": "count_rows",
                "dimension": "",
                "current": float(row.get("n") or 0),
                "previous": None,
                "delta": None,
                "delta_pct": None,
                "table": table,
                "date_col": "",
            })

        # Overall sums
        for mcol in (metric_cols or [])[:2]:
            if date_col:
                cursor.execute(
                    f"""
                    SELECT
                      SUM(CASE WHEN {_qident(date_col)} >= %s AND {_qident(date_col)} < %s THEN {_qident(mcol)} ELSE 0 END) AS curr,
                      SUM(CASE WHEN {_qident(date_col)} >= %s AND {_qident(date_col)} < %s THEN {_qident(mcol)} ELSE 0 END) AS prev
                    FROM {_qident(table)}
                    """,
                    (curr_start, curr_end_excl, prev_start, prev_end_excl),
                )
                row = cursor.fetchone() or {}
                curr = float(row.get("curr") or 0)
                prev = float(row.get("prev") or 0)
                metrics.append({
                    "metric": mcol,
                    "dimension": "",
                    "current": curr,
                    "previous": prev,
                    "delta": curr - prev,
                    "delta_pct": ((curr - prev) / prev) if prev else None,
                    "table": table,
                    "date_col": date_col,
                })
            else:
                cursor.execute(f"SELECT SUM({_qident(mcol)}) AS s FROM {_qident(table)}")
                row = cursor.fetchone() or {}
                curr = float(row.get("s") or 0)
                metrics.append({
                    "metric": mcol,
                    "dimension": "",
                    "current": curr,
                    "previous": None,
                    "delta": None,
                    "delta_pct": None,
                    "table": table,
                    "date_col": "",
                })

        # Dimension moves (only for first metric col to keep query count low)
        if metric_cols and dim_cols:
            mcol = metric_cols[0]
            # Choose 1-2 low-cardinality dimensions
            usable_dims: list[str] = []
            for dcol in dim_cols:
                n = _count_distinct_sample(table, dcol, date_col, curr_start if date_col else None, curr_end_excl if date_col else None)
                if n is None:
                    continue
                if 2 <= n <= 50:
                    usable_dims.append(dcol)
                if len(usable_dims) >= 2:
                    break

            for dcol in usable_dims:
                if date_col:
                    cursor.execute(
                        f"""
                        SELECT
                          COALESCE(CAST({_qident(dcol)} AS CHAR), '(null)') AS dim_value,
                          SUM(CASE WHEN {_qident(date_col)} >= %s AND {_qident(date_col)} < %s THEN {_qident(mcol)} ELSE 0 END) AS curr,
                          SUM(CASE WHEN {_qident(date_col)} >= %s AND {_qident(date_col)} < %s THEN {_qident(mcol)} ELSE 0 END) AS prev
                        FROM {_qident(table)}
                        GROUP BY dim_value
                        ORDER BY ABS(COALESCE(curr,0) - COALESCE(prev,0)) DESC
                        LIMIT 20
                        """,
                        (curr_start, curr_end_excl, prev_start, prev_end_excl),
                    )
                else:
                    cursor.execute(
                        f"""
                        SELECT
                          COALESCE(CAST({_qident(dcol)} AS CHAR), '(null)') AS dim_value,
                          SUM({_qident(mcol)}) AS curr,
                          NULL AS prev
                        FROM {_qident(table)}
                        GROUP BY dim_value
                        ORDER BY ABS(COALESCE(curr,0)) DESC
                        LIMIT 20
                        """
                    )
                rows = cursor.fetchall() or []
                for r in rows:
                    dim_val = str(r.get("dim_value") or "").strip()
                    curr = float(r.get("curr") or 0)
                    prev = float(r.get("prev") or 0) if r.get("prev") is not None else None
                    delta = (curr - prev) if prev is not None else None
                    pct = (delta / prev) if (prev not in (None, 0)) else None
                    metrics.append({
                        "metric": mcol,
                        "dimension": dcol,
                        "dimension_value": dim_val,
                        "current": curr,
                        "previous": prev,
                        "delta": delta,
                        "delta_pct": pct,
                        "table": table,
                        "date_col": date_col or "",
                    })

        return metrics
    finally:
        cursor.close()
        conn.close()


def _build_signals_input(as_of: date, metrics: list[dict], n: int) -> dict[str, Any]:
    # Keep payload small: only include a subset + rounded numbers
    slim = []
    for m in metrics[:200]:
        slim.append({
            "metric": m.get("metric"),
            "dimension": m.get("dimension") or "",
            "dimension_value": m.get("dimension_value") or "",
            "current": m.get("current"),
            "previous": m.get("previous"),
            "delta": m.get("delta"),
            "delta_pct": m.get("delta_pct"),
        })
    return {
        "asOf": as_of.isoformat(),
        "n": int(n),
        "metrics": slim,
    }


def _build_heartbeat_input(as_of: date, metrics: list[dict], n: int, instruction: str) -> dict[str, Any]:
    # Convert to a KPI-like list
    kpis = []
    for m in metrics:
        metric = str(m.get("metric") or "")
        dim = str(m.get("dimension") or "")
        dim_val = str(m.get("dimension_value") or "")
        label = metric
        if dim and dim_val:
            label = f"{metric} • {dim_val}"
        value = m.get("current")
        prev = m.get("previous")
        delta = m.get("delta")
        pct = m.get("delta_pct")
        kpis.append({
            "label": label[:32],
            "value": _format_compact_number(float(value or 0), instruction=instruction) if value is not None else "",
            "delta": (f"{pct*100:+.1f}% so với kỳ trước" if isinstance(pct, (int, float)) else ""),
            "delta_pct": pct,
        })
    # Prioritize ones with pct and higher absolute change
    def score(x: dict) -> float:
        p = x.get("delta_pct")
        if isinstance(p, (int, float)):
            return abs(float(p))
        return 0.0
    kpis.sort(key=score, reverse=True)
    return {
        "asOf": as_of.isoformat(),
        "n": int(n),
        "metrics": kpis[: min(50, len(kpis))],
    }


def _generate_signals_llm(input_payload: dict[str, Any]) -> list[dict]:
    resp = generate_chat(
        system_prompt=DAILY_SIGNALS_PROMPT,
        user_prompt=json.dumps(input_payload, ensure_ascii=False),
        temperature=0.3,
    )
    text = message_text(resp.choices[0].message)
    parsed = _parse_llm_json_object_array(text)
    out: list[dict] = []
    for item in parsed:
        t = str(item.get("type") or "").strip().lower()
        if t not in {"critical", "watch", "positive"}:
            t = "watch"
        title = str(item.get("title") or "").strip()
        desc = str(item.get("desc") or item.get("description") or "").strip()
        fingerprint = str(item.get("fingerprint") or "").strip()
        if not title or not desc:
            continue
        out.append({
            "type": t,
            "title": title[:255],
            "description": desc,
            "fingerprint": fingerprint[:255],
            "source": "llm",
            "created_at": datetime.utcnow(),
        })
    return out


def _generate_heartbeat_llm(input_payload: dict[str, Any]) -> list[dict]:
    resp = generate_chat(
        system_prompt=DAILY_HEARTBEAT_PROMPT,
        user_prompt=json.dumps(input_payload, ensure_ascii=False),
        temperature=0.3,
    )
    text = message_text(resp.choices[0].message)
    parsed = _parse_llm_json_object_array(text)
    out: list[dict] = []
    for item in parsed:
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        delta = str(item.get("delta") or "").strip()
        trend = str(item.get("trend") or "neutral").strip().lower()
        if trend not in {"up", "down", "neutral"}:
            trend = "neutral"
        if not label or not value:
            continue
        out.append({
            "label": label[:255],
            "value": value[:255],
            "delta": delta[:255],
            "trend": trend,
            "source": "llm",
            "created_at": datetime.utcnow(),
        })
    return out


def _signals_fallback(metrics: list[dict], n: int) -> list[dict]:
    # Pick top movers by abs(delta_pct) then abs(delta)
    rows = []
    for m in metrics:
        pct = m.get("delta_pct")
        if not isinstance(pct, (int, float)):
            continue
        delta = float(m.get("delta") or 0)
        rows.append((abs(float(pct)) * max(1.0, abs(delta)), m))
    rows.sort(key=lambda x: x[0], reverse=True)
    out: list[dict] = []
    for _, m in rows[: max(1, int(n))]:
        metric = str(m.get("metric") or "metric")
        dim_val = str(m.get("dimension_value") or "").strip()
        pct = float(m.get("delta_pct") or 0)
        direction = "tăng" if pct > 0 else "giảm"
        pct_txt = f"{abs(pct)*100:.1f}%"
        title = f"{metric} {direction} {pct_txt}"
        if dim_val:
            title = f"{metric} ({dim_val}) {direction} {pct_txt}"
        t = "positive" if pct > 0 else ("critical" if pct < -0.15 else "watch")
        out.append({
            "type": t,
            "title": title[:255],
            "description": f"So với kỳ trước: {direction} {pct_txt}.",
            "fingerprint": f"{metric}:{dim_val}"[:255],
            "source": "fallback",
            "created_at": datetime.utcnow(),
        })
    return out


def _heartbeat_fallback(metrics: list[dict], n: int, instruction: str) -> list[dict]:
    out: list[dict] = []
    # Use top overall metrics first
    overall = [m for m in metrics if not m.get("dimension")]
    for m in overall[: max(1, int(n))]:
        label = str(m.get("metric") or "metric")[:255]
        value = _format_compact_number(
            float(m.get("current") or 0),
            instruction=instruction,
        )[:255]
        pct = m.get("delta_pct")
        delta_txt = f"{float(pct)*100:+.1f}% so với kỳ trước" if isinstance(pct, (int, float)) else ""
        trend = "up" if isinstance(pct, (int, float)) and pct > 0 else ("down" if isinstance(pct, (int, float)) and pct < 0 else "neutral")
        out.append({
            "label": label,
            "value": value,
            "delta": delta_txt[:255],
            "trend": trend,
            "source": "fallback",
            "created_at": datetime.utcnow(),
        })
        if len(out) >= int(n):
            break
    return out


def get_signals_page_cached(limit: int = 5, offset: int = 0, instruction: str = "") -> dict[str, Any]:
    limit = max(1, int(limit or 5))
    offset = max(0, int(offset or 0))

    from db.schema import get_tables_schema
    tables = get_tables_schema()
    anchor = _pick_anchor_table(tables) or {}
    table = str(anchor.get("name") or "")
    if not table:
        return {"items": [], "total": 0, "hasMore": False, "nextOffset": offset, "message": "No tables found."}

    date_col = _pick_date_column(table, anchor.get("columns") or [])
    as_of = _detect_as_of(table, date_col)
    metric_cols = _pick_metric_columns(table, date_col, as_of, anchor.get("columns") or [], max_n=2)
    dim_cols = _pick_dimension_columns(table, date_col, as_of, anchor.get("columns") or [], max_n=6)
    as_of_str = as_of.isoformat()

    ihash = _instruction_hash(instruction)
    desired = int(os.getenv("SIDEBAR_SIGNALS_COUNT", "10") or 10)

    # Cache
    if count_signals_v2(as_of_str, ihash) < desired:
        metrics = _compute_metrics(table, date_col, metric_cols, dim_cols, as_of)
        use_llm = os.getenv("SIDEBAR_USE_LLM", "true").lower() in _TRUE
        signals: list[dict] = []
        if use_llm:
            try:
                payload = _build_signals_input(as_of, metrics, desired)
                signals = _generate_signals_llm(payload)
            except Exception as e:
                print(f"[SIDEBAR] signals LLM failed: {e}")
                signals = []
        if not signals:
            signals = _signals_fallback(metrics, desired)

        delete_signals_v2(as_of_str, ihash)
        rows = []
        for i, s in enumerate(signals[:desired]):
            rows.append({**s, "rank": i + 1})
        insert_signals_v2(as_of_str, ihash, rows)

    total = count_signals_v2(as_of_str, ihash)
    page = get_signals_page_v2(as_of_str, ihash, limit=limit, offset=offset)
    items = []
    for r in page:
        items.append({
            "id": int(r.get("rank") or 0),
            "type": str(r.get("type") or "watch"),
            "title": str(r.get("title") or ""),
            "desc": str(r.get("description") or ""),
            "createdAt": r.get("created_at").isoformat() if r.get("created_at") else _now_iso(),
        })

    next_offset = offset + len(items)
    return {
        "items": items,
        "total": total,
        "hasMore": next_offset < total,
        "nextOffset": next_offset,
        "asOf": as_of_str,
    }


def get_heartbeat_page_cached(limit: int = 4, offset: int = 0, instruction: str = "") -> dict[str, Any]:
    limit = max(1, int(limit or 4))
    offset = max(0, int(offset or 0))

    from db.schema import get_tables_schema
    tables = get_tables_schema()
    anchor = _pick_anchor_table(tables) or {}
    table = str(anchor.get("name") or "")
    if not table:
        return {"items": [], "total": 0, "hasMore": False, "nextOffset": offset, "message": "No tables found."}

    date_col = _pick_date_column(table, anchor.get("columns") or [])
    as_of = _detect_as_of(table, date_col)
    metric_cols = _pick_metric_columns(table, date_col, as_of, anchor.get("columns") or [], max_n=2)
    dim_cols = _pick_dimension_columns(table, date_col, as_of, anchor.get("columns") or [], max_n=6)
    as_of_str = as_of.isoformat()

    ihash = _instruction_hash(instruction)
    desired = int(os.getenv("SIDEBAR_HEARTBEAT_COUNT", "8") or 8)

    if count_heartbeat_v2(as_of_str, ihash) < desired:
        metrics = _compute_metrics(table, date_col, metric_cols, dim_cols, as_of)
        use_llm = os.getenv("SIDEBAR_USE_LLM", "true").lower() in _TRUE
        hb: list[dict] = []
        if use_llm:
            try:
                payload = _build_heartbeat_input(as_of, metrics, desired, instruction=instruction)
                hb = _generate_heartbeat_llm(payload)
            except Exception as e:
                print(f"[SIDEBAR] heartbeat LLM failed: {e}")
                hb = []
        if not hb:
            hb = _heartbeat_fallback(metrics, desired, instruction=instruction)

        delete_heartbeat_v2(as_of_str, ihash)
        rows = []
        for i, k in enumerate(hb[:desired]):
            rows.append({**k, "rank": i + 1})
        insert_heartbeat_v2(as_of_str, ihash, rows)

    total = count_heartbeat_v2(as_of_str, ihash)
    page = get_heartbeat_page_v2(as_of_str, ihash, limit=limit, offset=offset)
    items = []
    for r in page:
        items.append({
            "id": int(r.get("rank") or 0),
            "label": str(r.get("label") or ""),
            "value": str(r.get("value") or ""),
            "delta": str(r.get("delta") or ""),
            "trend": str(r.get("trend") or "neutral"),
            "createdAt": r.get("created_at").isoformat() if r.get("created_at") else _now_iso(),
        })

    next_offset = offset + len(items)
    return {
        "items": items,
        "total": total,
        "hasMore": next_offset < total,
        "nextOffset": next_offset,
        "asOf": as_of_str,
    }



def _build_landing_user_prompt(user_id: str, instruction: str = "") -> str:
    from db import get_chat_history, get_schema_context
    from memory import MemoryService

    memory_svc = MemoryService()

    history_rows = get_chat_history(session_id="", user_id=user_id, limit=10, cross_session=True)
    history_lines = []
    for row in reversed(history_rows):
        q = (row.get("question") or "").strip()
        if q:
            history_lines.append(f"- {q}")
    history_block = "\n".join(history_lines) if history_lines else "(Chưa có lịch sử hội thoại)"

    fact_block = memory_svc._build_fact_block(user_id, top_k=5)
    if not fact_block:
        fact_block = "(Chưa có thông tin sở thích)"

    try:
        schema = get_schema_context()
        if len(schema) > 2000:
            schema = schema[:2000] + "\n..."
    except Exception:
        schema = "(Không lấy được schema)"

    instr = (instruction or "").strip()
    instruction_block = f"[Instruction]\n{instr}\n\n" if instr else ""
    return (
        f"{instruction_block}"
        f"[Conversation History]\n{history_block}\n\n"
        f"[Fact Memory]\n{fact_block}\n\n"
        f"[Schema Overview]\n{schema}"
    )


def _generate_landing_suggestions_llm(user_id: str, instruction: str = "") -> list[dict]:
    user_prompt = _build_landing_user_prompt(user_id, instruction=instruction)
    temperature = float(os.getenv("LANDING_LLM_TEMPERATURE", "0.5") or 0.5)
    resp = generate_chat(
        system_prompt=LANDING_SUGGESTIONS_PROMPT,
        user_prompt=user_prompt,
        temperature=temperature,
    )
    text = message_text(resp.choices[0].message)
    parsed = _parse_llm_json_string_array(text)

    out: list[dict] = []
    created_at = datetime.utcnow()
    for idx, item in enumerate(parsed[:4]):
        t = item.strip()
        if not t:
            continue
        out.append({"rank": idx + 1, "text": t, "source": "llm", "created_at": created_at})
    return out


def _parse_llm_json_string_array(text: str) -> list[str]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    match = re.search(r"\[[\s\S]*\]", raw)
    candidate = match.group(0) if match else raw
    try:
        parsed = json.loads(candidate)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(x).strip() for x in parsed if isinstance(x, str) and x.strip()]


def _ensure_landing_suggestions(user_id: str, instruction: str = "") -> None:
    if count_landing_suggestions(user_id) >= 4:
        return

    items: list[dict] = []
    use_llm = os.getenv("LANDING_USE_LLM", "true").lower() in {"1", "true", "yes", "on"}
    if use_llm:
        try:
            items = _generate_landing_suggestions_llm(user_id, instruction=instruction)
        except Exception as e:
            print(f"[LANDING] LLM generation failed: {e}")
            items = []

    if not items:
        return

    delete_landing_suggestions(user_id)
    insert_landing_suggestions(user_id, items[:4])


def get_landing_suggestions_cached(user_id: str, instruction: str = "") -> dict[str, Any]:
    _ensure_landing_suggestions(user_id, instruction=instruction)
    rows = get_landing_suggestions(user_id, limit=4)
    items = [str(r.get("text") or "") for r in rows if r.get("text")]
    return {"items": items}


def refresh_landing_suggestions(user_id: str, instruction: str = "") -> dict[str, Any]:
    delete_landing_suggestions(user_id)
    _ensure_landing_suggestions(user_id, instruction=instruction)
    rows = get_landing_suggestions(user_id, limit=4)
    items = [str(r.get("text") or "") for r in rows if r.get("text")]
    return {"items": items}
