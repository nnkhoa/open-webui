import json
from datetime import datetime
from .connection import get_connection


def _json_or_none(value):
    if not value:
        return None
    return json.dumps(value, ensure_ascii=False)


def init_chat_history_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS `chat_history` (
            `id`                 INT AUTO_INCREMENT PRIMARY KEY,
            `user_id`            VARCHAR(100) NOT NULL DEFAULT 'default_user',
            `session_id`         VARCHAR(100) NOT NULL,
            `created_at`         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `question`           TEXT NOT NULL,
            `sql_generated`      TEXT,
            `thinking`           TEXT,
            `reply`              TEXT,
            `columns_data`       JSON,
            `rows_data`          JSON,
            `chart_config`       JSON,
            `blocks`             JSON,
            `token_sql_input`    INT DEFAULT 0,
            `token_sql_thinking` INT DEFAULT 0,
            `token_sql_output`   INT DEFAULT 0,
            `token_sql_total`    INT DEFAULT 0,
            `token_sql_breakdown` JSON,
            `token_reply_input`    INT DEFAULT 0,
            `token_reply_thinking` INT DEFAULT 0,
            `token_reply_output`   INT DEFAULT 0,
            `token_reply_total`    INT DEFAULT 0,
            `token_reply_breakdown` JSON,
            `token_grand_total`  INT DEFAULT 0,
            `follow_up_suggestions` JSON,
            INDEX idx_user_session (user_id, session_id),
            INDEX idx_session (session_id),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    conn.commit()
    # Add follow_up_suggestions column if missing (migration for existing tables)
    try:
        cursor = conn.cursor()
        migrations = [
            ("follow_up_suggestions", "ALTER TABLE `chat_history` ADD COLUMN `follow_up_suggestions` JSON"),
            ("token_sql_breakdown", "ALTER TABLE `chat_history` ADD COLUMN `token_sql_breakdown` JSON"),
            ("token_reply_breakdown", "ALTER TABLE `chat_history` ADD COLUMN `token_reply_breakdown` JSON"),
        ]
        for col, ddl in migrations:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name='chat_history' AND column_name=%s",
                (col,),
            )
            exists = cursor.fetchone()[0] > 0
            if not exists:
                cursor.execute(ddl)
                conn.commit()
        cursor.close()
    except Exception:
        pass
    conn.close()


def save_chat(session_id: str, question: str, result: dict, user_id: str = "default_user"):
    conn = get_connection()
    cursor = conn.cursor()
    sql_tokens = result.get("token_usage", {})
    reply_tokens = result.get("reply_token_usage", {})
    grand = result.get("grand_total", {})

    insert_sql = """INSERT INTO `chat_history`
    (user_id, session_id, created_at, question, sql_generated, thinking, reply,
     columns_data, rows_data, chart_config, blocks,
     token_sql_input, token_sql_thinking, token_sql_output, token_sql_total,
     token_sql_breakdown,
     token_reply_input, token_reply_thinking, token_reply_output, token_reply_total,
     token_reply_breakdown,
     token_grand_total, follow_up_suggestions)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    params = (
        user_id, session_id, datetime.now(), question,
        result.get("sql"), result.get("thinking"), result.get("reply"),
        _json_or_none(result.get("columns")),
        _json_or_none(result.get("rows")),
        _json_or_none(result.get("chart_config")),
        _json_or_none(result.get("blocks")),
        sql_tokens.get("input", 0), sql_tokens.get("thinking", 0),
        sql_tokens.get("output", 0), sql_tokens.get("total", 0),
        _json_or_none(sql_tokens),
        reply_tokens.get("input", 0), reply_tokens.get("thinking", 0),
        reply_tokens.get("output", 0), reply_tokens.get("total", 0),
        _json_or_none(reply_tokens),
        grand.get("total", 0),
        _json_or_none(result.get("follow_up_suggestions")),
    )

    cursor.execute(insert_sql, params)
    conn.commit()
    cursor.close()
    conn.close()


def get_chat_history(session_id: str, limit: int = 50, user_id: str = "default_user", cross_session: bool = False) -> list:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if cross_session:
        cursor.execute(
            "SELECT * FROM `chat_history` WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit),
        )
    else:
        cursor.execute(
            "SELECT * FROM `chat_history` WHERE user_id = %s AND session_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, session_id, limit),
        )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def get_chat_history_page(
    user_id: str = "default_user",
    session_id: str = "",
    limit: int = 10,
    offset: int = 0,
    cross_session: bool = True,
) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        safe_limit = max(1, min(int(limit or 10), 100))
        safe_offset = max(0, int(offset or 0))

        if cross_session:
            cursor.execute(
                """
                SELECT id, user_id, session_id, created_at, question, reply
                FROM `chat_history`
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, safe_limit, safe_offset),
            )
        else:
            cursor.execute(
                """
                SELECT id, user_id, session_id, created_at, question, reply
                FROM `chat_history`
                WHERE user_id = %s AND session_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, session_id, safe_limit, safe_offset),
            )

        rows = cursor.fetchall()
        cursor.close()
        return rows
    finally:
        conn.close()


def count_chat_history(user_id: str = "default_user") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM `chat_history` WHERE user_id = %s",
        (user_id,),
    )
    n = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return int(n or 0)


def get_chat_history_session(user_id: str, session_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT *
        FROM `chat_history`
        WHERE user_id = %s AND session_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        (user_id, session_id),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def count_chat_turns(user_id: str, session_id: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM `chat_history` WHERE user_id = %s AND session_id = %s",
        (user_id, session_id),
    )
    n = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return int(n)
