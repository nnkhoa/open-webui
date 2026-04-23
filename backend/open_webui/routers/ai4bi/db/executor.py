import re
from .connection import get_connection

_DANGEROUS_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str):
    stripped = sql.strip().rstrip(";").strip()
    if not stripped.upper().startswith(("SELECT", "WITH")):
        raise ValueError(f"Chỉ cho phép SELECT queries. Nhận được: {stripped[:50]}...")
    if _DANGEROUS_SQL.search(stripped):
        raise ValueError(f"SQL chứa lệnh nguy hiểm bị chặn: {stripped[:80]}...")


def execute_sql(sql: str) -> dict:
    validate_sql(sql)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    cols = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    from decimal import Decimal
    
    def serialize_val(v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, (int, float)):
            return v
        return str(v) if v is not None else None

    return {"columns": cols, "rows": [[serialize_val(v) for v in row] for row in rows]}


def compute_data_summary(columns: list[str], rows: list[list[str]]) -> dict:
    """Tóm tắt metadata cơ bản — KHÔNG tính toán, SQL đã làm hết."""
    return {
        "total_rows": len(rows),
        "columns": columns,
    }
