import json
import math
from datetime import datetime
from .connection import get_connection


def init_memory_vectors_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS `memory_vectors` (
            `id`          INT AUTO_INCREMENT PRIMARY KEY,
            `memory_id`   VARCHAR(100) NOT NULL,
            `user_id`     VARCHAR(100) NOT NULL,
            `text`        TEXT NOT NULL,
            `embedding`   LONGTEXT NOT NULL,
            `category`    VARCHAR(50) DEFAULT '',
            `importance`  TINYINT DEFAULT 1,
            `session_id`  VARCHAR(100) DEFAULT '',
            `created_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_memory_id (`memory_id`),
            INDEX idx_vec_user (`user_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    conn.commit()
    cursor.close()
    conn.close()


def upsert_memory_vector(memory_id: str, user_id: str, text: str, embedding: list[float],
                         category: str = "", importance: int = 1, session_id: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    embedding_json = json.dumps(embedding)
    cursor.execute(
        """INSERT INTO `memory_vectors`
        (memory_id, user_id, text, embedding, category, importance, session_id, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            text = VALUES(text),
            embedding = VALUES(embedding),
            category = VALUES(category),
            importance = VALUES(importance),
            session_id = VALUES(session_id)""",
        (memory_id, user_id, text, embedding_json, category, importance, session_id, datetime.now()),
    )
    conn.commit()
    cursor.close()
    conn.close()


def search_memory_vectors(user_id: str, query_embedding: list[float], top_k: int = 5) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, memory_id, text, embedding, category, importance FROM `memory_vectors` WHERE user_id = %s",
        (user_id,),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        return []

    scored = []
    for row in rows:
        stored_emb = json.loads(row["embedding"])
        score = _cosine_similarity(query_embedding, stored_emb)
        scored.append({
            "memory_id": row["memory_id"],
            "text": row["text"],
            "category": row["category"],
            "importance": row["importance"],
            "score": score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def delete_memory_vectors_by_user(user_id: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM `memory_vectors` WHERE user_id = %s", (user_id,))
    deleted = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return int(deleted)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
