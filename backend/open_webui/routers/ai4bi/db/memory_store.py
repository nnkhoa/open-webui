from datetime import datetime
from .connection import get_connection


def init_memory_facts_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS `memory_facts` (
            `id`           INT AUTO_INCREMENT PRIMARY KEY,
            `user_id`      VARCHAR(100) NOT NULL,
            `session_id`   VARCHAR(100) NOT NULL,
            `category`     VARCHAR(50) NOT NULL,
            `content`      TEXT NOT NULL,
            `importance`   TINYINT NOT NULL DEFAULT 1,
            `source_type`  VARCHAR(50) NOT NULL DEFAULT 'fact_extraction',
            `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_mem_user_created (`user_id`, `created_at`),
            INDEX idx_mem_user_category (`user_id`, `category`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    conn.commit()
    cursor.close()
    conn.close()


def insert_memory_fact(user_id: str, session_id: str, category: str, content: str,
                       importance: int = 1, source_type: str = "fact_extraction") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO `memory_facts`
        (user_id, session_id, category, content, importance, source_type, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (user_id, session_id, category, content, importance, source_type, datetime.now()),
    )
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return int(new_id)


def get_memory_facts(user_id: str, limit: int = 20, query: str = "") -> list:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if query:
        cursor.execute(
            """SELECT * FROM `memory_facts`
               WHERE user_id = %s AND content LIKE %s
               ORDER BY importance DESC, created_at DESC LIMIT %s""",
            (user_id, f"%{query}%", limit),
        )
    else:
        cursor.execute(
            """SELECT * FROM `memory_facts`
               WHERE user_id = %s
               ORDER BY importance DESC, created_at DESC LIMIT %s""",
            (user_id, limit),
        )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def delete_memory_fact(user_id: str, memory_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM `memory_facts` WHERE user_id = %s AND id = %s", (user_id, memory_id))
    deleted = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return int(deleted)


def reset_memory_facts(user_id: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM `memory_facts` WHERE user_id = %s", (user_id,))
    deleted = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return int(deleted)
