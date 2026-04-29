from __future__ import annotations

import re
from typing import Any

from open_webui.models.groups import Groups

ACCESS_DENIED_MESSAGE = "Bạn không có quyền truy cập dữ liệu được yêu cầu. Vui lòng liên hệ admin."
NOT_CONFIGURED_MESSAGE = "Tài khoản của bạn chưa được cấu hình quyền truy cập dữ liệu AI4BI. Vui lòng liên hệ admin."

_TABLE_REF_RE = re.compile(
    r"(?:from|join|update|into|table)\s+`?([a-zA-Z0-9_]+)`?",
    re.IGNORECASE,
)


def _normalize_table_name(value: Any) -> str:
    return str(value or "").strip().strip("`").lower()


def _normalize_allowed_tables(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",")]
        return [p.strip("`").lower() for p in parts if p.strip()]
    if isinstance(raw, (list, tuple, set)):
        normalized: list[str] = []
        for item in raw:
            name = _normalize_table_name(item)
            if name:
                normalized.append(name)
        return normalized
    return []


def _normalize_group_ai4bi(group: Any) -> dict[str, Any] | None:
    data = getattr(group, "data", None) or {}
    if not isinstance(data, dict):
        return None
    ai4bi = data.get("ai4bi") or {}
    if not isinstance(ai4bi, dict):
        return None

    allowed_tables = _normalize_allowed_tables(ai4bi.get("allowed_tables"))
    mcp_url = str(ai4bi.get("mcp_url") or "").strip()
    if not allowed_tables and not mcp_url:
        return None

    return {
        "group_id": getattr(group, "id", None),
        "group_name": getattr(group, "name", ""),
        "mcp_url": mcp_url,
        "allowed_tables": allowed_tables,
        "denied_message": str(ai4bi.get("denied_message") or ACCESS_DENIED_MESSAGE).strip() or ACCESS_DENIED_MESSAGE,
    }


def resolve_ai4bi_access(user_id: str) -> dict[str, Any]:
    groups = Groups.get_groups_by_member_id(user_id)
    configs: list[dict[str, Any]] = []
    for group in groups:
        cfg = _normalize_group_ai4bi(group)
        if cfg:
            configs.append(cfg)

    if not configs:
        return {
            "configured": False,
            "mcp_url": "",
            "allowed_tables": [],
            "group_ids": [],
            "group_names": [],
            "denied_message": NOT_CONFIGURED_MESSAGE,
        }

    allowed_tables: list[str] = []
    for cfg in configs:
        for table in cfg["allowed_tables"]:
            if table not in allowed_tables:
                allowed_tables.append(table)

    mcp_url = ""
    for cfg in configs:
        if cfg["mcp_url"]:
            mcp_url = cfg["mcp_url"]
            break

    return {
        "configured": True,
        "mcp_url": mcp_url,
        "allowed_tables": allowed_tables,
        "group_ids": [cfg["group_id"] for cfg in configs if cfg.get("group_id")],
        "group_names": [cfg["group_name"] for cfg in configs if cfg.get("group_name")],
        "denied_message": configs[0].get("denied_message") or ACCESS_DENIED_MESSAGE,
    }


def ensure_user_has_ai4bi_access(user_id: str) -> dict[str, Any]:
    access = resolve_ai4bi_access(user_id)
    if not access["configured"]:
        raise PermissionError(access["denied_message"])
    if not access["allowed_tables"]:
        raise PermissionError(access["denied_message"])
    return access


def get_pool_key_for_access(access: dict[str, Any]) -> str | None:
    mcp_url = str(access.get("mcp_url") or "").strip()
    return mcp_url or None


def validate_sql_tables(sql: str, allowed_tables: list[str]) -> list[str]:
    allowed = {_normalize_table_name(t) for t in allowed_tables if _normalize_table_name(t)}
    if not allowed:
        raise PermissionError(ACCESS_DENIED_MESSAGE)

    referenced = [_normalize_table_name(m.group(1)) for m in _TABLE_REF_RE.finditer(sql or "")]
    unique_referenced = [t for i, t in enumerate(referenced) if t and t not in referenced[:i]]
    denied = [t for t in unique_referenced if t not in allowed]
    if denied:
        raise PermissionError(f"{ACCESS_DENIED_MESSAGE} Bảng không được phép: {', '.join(denied)}")
    return unique_referenced


def format_allowed_tables_instruction(allowed_tables: list[str]) -> str:
    tables = [f"`{_normalize_table_name(t)}`" for t in allowed_tables if _normalize_table_name(t)]
    if not tables:
        return ""
    return (
        "\n\n<access_control>\n"
        "Chỉ được phép sử dụng các bảng sau: " + ", ".join(tables) + ".\n"
        "Tuyệt đối không dùng bất kỳ bảng nào ngoài danh sách trên.\n"
        "Nếu câu hỏi cần dữ liệu ngoài phạm vi này, hãy trả về đúng chuỗi ACCESS_DENIED.\n"
        "</access_control>"
    )
