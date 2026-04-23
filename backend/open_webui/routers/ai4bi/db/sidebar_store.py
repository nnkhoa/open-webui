from __future__ import annotations

from datetime import datetime
from typing import Any

from .connection import get_connection


def init_sidebar_tables() -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS `sidebar_signals` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `as_of_sales` DATE NOT NULL,
          `as_of_joint` DATE NOT NULL,
          `rank` INT NOT NULL,
          `type` VARCHAR(16) NOT NULL,
          `title` VARCHAR(255) NOT NULL,
          `description` TEXT NOT NULL,
          `fingerprint` VARCHAR(255) NOT NULL DEFAULT '',
          `source` VARCHAR(16) NOT NULL DEFAULT 'llm',
          `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uniq_asof_rank` (`as_of_sales`, `as_of_joint`, `rank`),
          KEY `idx_asof` (`as_of_sales`, `as_of_joint`)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS `sidebar_heartbeat` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `as_of_sales` DATE NOT NULL,
          `as_of_joint` DATE NOT NULL,
          `rank` INT NOT NULL,
          `label` VARCHAR(255) NOT NULL,
          `value` VARCHAR(255) NOT NULL,
          `delta` VARCHAR(255) NOT NULL DEFAULT '',
          `trend` VARCHAR(16) NOT NULL DEFAULT 'neutral',
          `source` VARCHAR(16) NOT NULL DEFAULT 'llm',
          `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uniq_asof_rank` (`as_of_sales`, `as_of_joint`, `rank`),
          KEY `idx_asof` (`as_of_sales`, `as_of_joint`)
        )
        """
    )
    # V2: cache theo (as_of + instruction_hash) để sidebar phản ánh instruction từ UI.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS `sidebar_signals_v2` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `as_of` DATE NOT NULL,
          `instruction_hash` VARCHAR(64) NOT NULL DEFAULT '',
          `rank` INT NOT NULL,
          `type` VARCHAR(16) NOT NULL,
          `title` VARCHAR(255) NOT NULL,
          `description` TEXT NOT NULL,
          `fingerprint` VARCHAR(255) NOT NULL DEFAULT '',
          `source` VARCHAR(16) NOT NULL DEFAULT 'llm',
          `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uniq_asof_hash_rank` (`as_of`, `instruction_hash`, `rank`),
          KEY `idx_asof_hash` (`as_of`, `instruction_hash`)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS `sidebar_heartbeat_v2` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `as_of` DATE NOT NULL,
          `instruction_hash` VARCHAR(64) NOT NULL DEFAULT '',
          `rank` INT NOT NULL,
          `label` VARCHAR(255) NOT NULL,
          `value` VARCHAR(255) NOT NULL,
          `delta` VARCHAR(255) NOT NULL DEFAULT '',
          `trend` VARCHAR(16) NOT NULL DEFAULT 'neutral',
          `source` VARCHAR(16) NOT NULL DEFAULT 'llm',
          `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uniq_asof_hash_rank` (`as_of`, `instruction_hash`, `rank`),
          KEY `idx_asof_hash` (`as_of`, `instruction_hash`)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS `landing_suggestions` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `user_id` VARCHAR(128) NOT NULL,
          `rank` INT NOT NULL,
          `text` VARCHAR(512) NOT NULL,
          `source` VARCHAR(16) NOT NULL DEFAULT 'llm',
          `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uniq_user_rank` (`user_id`, `rank`),
          KEY `idx_user` (`user_id`)
        )
        """
    )
    conn.commit()
    cursor.close()
    conn.close()


def delete_landing_suggestions(user_id: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM `landing_suggestions` WHERE `user_id`=%s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()


def insert_landing_suggestions(user_id: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    conn = get_connection()
    cursor = conn.cursor()
    values = []
    for r in rows:
        values.append((
            user_id,
            int(r.get("rank") or 0),
            str(r.get("text") or ""),
            str(r.get("source") or "llm"),
            r.get("created_at") or datetime.utcnow(),
        ))
    cursor.executemany(
        """
        INSERT INTO `landing_suggestions`
          (`user_id`,`rank`,`text`,`source`,`created_at`)
        VALUES (%s,%s,%s,%s,%s)
        """,
        values,
    )
    conn.commit()
    cursor.close()
    conn.close()


def count_landing_suggestions(user_id: str) -> int:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT COUNT(*) AS n FROM `landing_suggestions` WHERE `user_id`=%s",
        (user_id,),
    )
    row = cursor.fetchone() or {}
    cursor.close()
    conn.close()
    return int(row.get("n") or 0)


def get_landing_suggestions(user_id: str, limit: int = 4) -> list[dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT `rank`,`text`,`source`,`created_at`
        FROM `landing_suggestions`
        WHERE `user_id`=%s
        ORDER BY `rank` ASC
        LIMIT %s
        """,
        (user_id, int(limit)),
    )
    rows = cursor.fetchall() or []
    cursor.close()
    conn.close()
    return rows


def delete_signals(as_of_sales: str, as_of_joint: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM `sidebar_signals` WHERE `as_of_sales`=%s AND `as_of_joint`=%s",
        (as_of_sales, as_of_joint),
    )
    conn.commit()
    cursor.close()
    conn.close()


def insert_signals(as_of_sales: str, as_of_joint: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    conn = get_connection()
    cursor = conn.cursor()
    values = []
    for r in rows:
        values.append(
            (
                as_of_sales,
                as_of_joint,
                int(r.get("rank") or 0),
                str(r.get("type") or ""),
                str(r.get("title") or ""),
                str(r.get("description") or ""),
                str(r.get("fingerprint") or ""),
                str(r.get("source") or "llm"),
                r.get("created_at") or datetime.utcnow(),
            )
        )
    cursor.executemany(
        """
        INSERT INTO `sidebar_signals`
          (`as_of_sales`,`as_of_joint`,`rank`,`type`,`title`,`description`,`fingerprint`,`source`,`created_at`)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        values,
    )
    conn.commit()
    cursor.close()
    conn.close()


def count_signals(as_of_sales: str, as_of_joint: str) -> int:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT COUNT(*) AS n FROM `sidebar_signals` WHERE `as_of_sales`=%s AND `as_of_joint`=%s",
        (as_of_sales, as_of_joint),
    )
    row = cursor.fetchone() or {}
    cursor.close()
    conn.close()
    return int(row.get("n") or 0)


def get_signals_page(as_of_sales: str, as_of_joint: str, limit: int, offset: int) -> list[dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT `rank`,`type`,`title`,`description`,`created_at`
        FROM `sidebar_signals`
        WHERE `as_of_sales`=%s AND `as_of_joint`=%s
        ORDER BY `rank` ASC
        LIMIT %s OFFSET %s
        """,
        (as_of_sales, as_of_joint, int(limit), int(offset)),
    )
    rows = cursor.fetchall() or []
    cursor.close()
    conn.close()
    return rows


def delete_signals_v2(as_of: str, instruction_hash: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM `sidebar_signals_v2` WHERE `as_of`=%s AND `instruction_hash`=%s",
        (as_of, instruction_hash),
    )
    conn.commit()
    cursor.close()
    conn.close()


def insert_signals_v2(as_of: str, instruction_hash: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    conn = get_connection()
    cursor = conn.cursor()
    values = []
    for r in rows:
        values.append(
            (
                as_of,
                instruction_hash,
                int(r.get("rank") or 0),
                str(r.get("type") or ""),
                str(r.get("title") or ""),
                str(r.get("description") or ""),
                str(r.get("fingerprint") or ""),
                str(r.get("source") or "llm"),
                r.get("created_at") or datetime.utcnow(),
            )
        )
    cursor.executemany(
        """
        INSERT INTO `sidebar_signals_v2`
          (`as_of`,`instruction_hash`,`rank`,`type`,`title`,`description`,`fingerprint`,`source`,`created_at`)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        values,
    )
    conn.commit()
    cursor.close()
    conn.close()


def count_signals_v2(as_of: str, instruction_hash: str) -> int:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT COUNT(*) AS n FROM `sidebar_signals_v2` WHERE `as_of`=%s AND `instruction_hash`=%s",
        (as_of, instruction_hash),
    )
    row = cursor.fetchone() or {}
    cursor.close()
    conn.close()
    return int(row.get("n") or 0)


def get_signals_page_v2(as_of: str, instruction_hash: str, limit: int, offset: int) -> list[dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT `rank`,`type`,`title`,`description`,`created_at`
        FROM `sidebar_signals_v2`
        WHERE `as_of`=%s AND `instruction_hash`=%s
        ORDER BY `rank` ASC
        LIMIT %s OFFSET %s
        """,
        (as_of, instruction_hash, int(limit), int(offset)),
    )
    rows = cursor.fetchall() or []
    cursor.close()
    conn.close()
    return rows


def delete_heartbeat(as_of_sales: str, as_of_joint: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM `sidebar_heartbeat` WHERE `as_of_sales`=%s AND `as_of_joint`=%s",
        (as_of_sales, as_of_joint),
    )
    conn.commit()
    cursor.close()
    conn.close()


def insert_heartbeat(as_of_sales: str, as_of_joint: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    conn = get_connection()
    cursor = conn.cursor()
    values = []
    for r in rows:
        values.append(
            (
                as_of_sales,
                as_of_joint,
                int(r.get("rank") or 0),
                str(r.get("label") or ""),
                str(r.get("value") or ""),
                str(r.get("delta") or ""),
                str(r.get("trend") or "neutral"),
                str(r.get("source") or "llm"),
                r.get("created_at") or datetime.utcnow(),
            )
        )
    cursor.executemany(
        """
        INSERT INTO `sidebar_heartbeat`
          (`as_of_sales`,`as_of_joint`,`rank`,`label`,`value`,`delta`,`trend`,`source`,`created_at`)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        values,
    )
    conn.commit()
    cursor.close()
    conn.close()


def count_heartbeat(as_of_sales: str, as_of_joint: str) -> int:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT COUNT(*) AS n FROM `sidebar_heartbeat` WHERE `as_of_sales`=%s AND `as_of_joint`=%s",
        (as_of_sales, as_of_joint),
    )
    row = cursor.fetchone() or {}
    cursor.close()
    conn.close()
    return int(row.get("n") or 0)


def get_heartbeat_page(as_of_sales: str, as_of_joint: str, limit: int, offset: int) -> list[dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT `rank`,`label`,`value`,`delta`,`trend`,`created_at`
        FROM `sidebar_heartbeat`
        WHERE `as_of_sales`=%s AND `as_of_joint`=%s
        ORDER BY `rank` ASC
        LIMIT %s OFFSET %s
        """,
        (as_of_sales, as_of_joint, int(limit), int(offset)),
    )
    rows = cursor.fetchall() or []
    cursor.close()
    conn.close()
    return rows


def delete_heartbeat_v2(as_of: str, instruction_hash: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM `sidebar_heartbeat_v2` WHERE `as_of`=%s AND `instruction_hash`=%s",
        (as_of, instruction_hash),
    )
    conn.commit()
    cursor.close()
    conn.close()


def insert_heartbeat_v2(as_of: str, instruction_hash: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    conn = get_connection()
    cursor = conn.cursor()
    values = []
    for r in rows:
        values.append(
            (
                as_of,
                instruction_hash,
                int(r.get("rank") or 0),
                str(r.get("label") or ""),
                str(r.get("value") or ""),
                str(r.get("delta") or ""),
                str(r.get("trend") or "neutral"),
                str(r.get("source") or "llm"),
                r.get("created_at") or datetime.utcnow(),
            )
        )
    cursor.executemany(
        """
        INSERT INTO `sidebar_heartbeat_v2`
          (`as_of`,`instruction_hash`,`rank`,`label`,`value`,`delta`,`trend`,`source`,`created_at`)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        values,
    )
    conn.commit()
    cursor.close()
    conn.close()


def count_heartbeat_v2(as_of: str, instruction_hash: str) -> int:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT COUNT(*) AS n FROM `sidebar_heartbeat_v2` WHERE `as_of`=%s AND `instruction_hash`=%s",
        (as_of, instruction_hash),
    )
    row = cursor.fetchone() or {}
    cursor.close()
    conn.close()
    return int(row.get("n") or 0)


def get_heartbeat_page_v2(as_of: str, instruction_hash: str, limit: int, offset: int) -> list[dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT `rank`,`label`,`value`,`delta`,`trend`,`created_at`
        FROM `sidebar_heartbeat_v2`
        WHERE `as_of`=%s AND `instruction_hash`=%s
        ORDER BY `rank` ASC
        LIMIT %s OFFSET %s
        """,
        (as_of, instruction_hash, int(limit), int(offset)),
    )
    rows = cursor.fetchall() or []
    cursor.close()
    conn.close()
    return rows
