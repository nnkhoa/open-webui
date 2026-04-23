"""
UI Messages Configuration for AI4BI Backend
Centralized Vietnamese messages for easy localization and customization
"""

# Status messages for SSE streaming
STATUS_MESSAGES = {
    "preparing_context": {
        "step": 0,
        "text": "Đang chuẩn bị ngữ cảnh và bộ nhớ..."
    },
    "analyzing_question": {
        "step": 1,
        "text": "Đang phân tích câu hỏi và tạo truy vấn SQL..."
    },
    "received_data": {
        "step": 2,
        "text": "Đã nhận dữ liệu từ database..."
    },
    "agentic_evaluation": {
        "step": 2,
        "text": "Đang đánh giá thông tin và lập kế hoạch phân tích sâu..."
    },
    "synthesizing": {
        "step": 3,
        "text": "Đang tổng hợp dữ liệu và trực quan hóa phân tích..."
    }
}

# Error messages
ERROR_MESSAGES = {
    "database_not_configured": "DATABASE_NOT_CONFIGURED: Please configure MCP connection first.",
    "connection_failed": "Failed to get database connection",
    "sql_generation_failed": "Failed to generate SQL query",
    "data_retrieval_failed": "Failed to retrieve data from database"
}


def get_status_message(key: str) -> dict:
    """
    Get status message by key with fallback.

    Args:
        key: Message key from STATUS_MESSAGES

    Returns:
        dict with 'step' and 'text' keys
    """
    return STATUS_MESSAGES.get(key, {"step": 0, "text": "Đang xử lý..."})


def get_error_message(key: str) -> str:
    """
    Get error message by key with fallback.

    Args:
        key: Message key from ERROR_MESSAGES

    Returns:
        Error message string
    """
    return ERROR_MESSAGES.get(key, "An error occurred")
