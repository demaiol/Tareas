from __future__ import annotations

import os
import sqlite3

import psycopg

SQLITE_PATH = "req_manager.db"


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("Falta DATABASE_URL para migrar a PostgreSQL")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    pg_conn = psycopg.connect(database_url)

    try:
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS requirements (
                    id BIGSERIAL PRIMARY KEY,
                    req_code TEXT UNIQUE,
                    requester_name TEXT NOT NULL,
                    requester_email TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    due_at TIMESTAMPTZ NOT NULL,
                    assignee TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response TEXT,
                    resolved_by TEXT,
                    resolved_at TIMESTAMPTZ,
                    source_message_id TEXT UNIQUE,
                    updated_at TIMESTAMPTZ NOT NULL
                )
                """
            )

        rows = sqlite_conn.execute("SELECT * FROM requirements ORDER BY id ASC").fetchall()

        migrated = 0
        with pg_conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO requirements (
                        id,
                        req_code,
                        requester_name,
                        requester_email,
                        title,
                        detail,
                        created_at,
                        due_at,
                        assignee,
                        status,
                        response,
                        resolved_by,
                        resolved_at,
                        source_message_id,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        row["id"],
                        row["req_code"],
                        row["requester_name"],
                        row["requester_email"],
                        row["title"],
                        row["detail"],
                        row["created_at"],
                        row["due_at"],
                        row["assignee"],
                        row["status"],
                        row["response"],
                        row["resolved_by"],
                        row["resolved_at"],
                        row["source_message_id"],
                        row["updated_at"],
                    ),
                )
                migrated += 1

            cur.execute(
                "SELECT setval(pg_get_serial_sequence('requirements', 'id'), COALESCE(MAX(id), 1), true) FROM requirements"
            )

        pg_conn.commit()
        print(f"Migracion completada. Filas procesadas: {migrated}")
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
