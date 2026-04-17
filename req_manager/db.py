from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterator
from zoneinfo import ZoneInfo

DB_PATH = "req_manager.db"
TZ = ZoneInfo("America/Santiago")
DEFAULT_USERS = [
    ("Administrador", "DEMO123$", "admin"),
    ("gestion", "gestion123$", "report"),
]


@dataclass
class EmailRequest:
    requester_name: str
    requester_email: str
    title: str
    detail: str
    source_message_id: str | None = None
    assignee: str = "Administrador"


def _database_url() -> str | None:
    value = os.getenv("DATABASE_URL", "").strip()
    return value or None


def _is_postgres() -> bool:
    url = _database_url()
    if not url:
        return False
    return url.startswith("postgres://") or url.startswith("postgresql://")


def _require_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg, dict_row
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "DATABASE_URL está configurado, pero falta instalar psycopg. "
            "Instala dependencias con requirements.txt"
        ) from exc


@contextmanager
def get_conn() -> Iterator[Any]:
    if _is_postgres():
        psycopg, dict_row = _require_psycopg()
        conn = psycopg.connect(_database_url(), row_factory=dict_row)
        try:
            yield conn
        finally:
            conn.close()
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(row)


def _to_dict_list(rows: list[Any]) -> list[dict[str, Any]]:
    return [_to_dict(r) for r in rows]


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def ensure_schema() -> None:
    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
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
                # Migracion: eliminamos estado legacy 'Vencido'.
                cur.execute(
                    "UPDATE requirements SET status = 'En progreso' WHERE status = 'Vencido'"
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGSERIAL PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        role TEXT NOT NULL,
                        active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                for username, password, role in DEFAULT_USERS:
                    cur.execute(
                        """
                        INSERT INTO users (username, password, role, active)
                        VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (username) DO NOTHING
                        """,
                        (username, password, role),
                    )
            conn.commit()
            return

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                req_code TEXT UNIQUE,
                requester_name TEXT NOT NULL,
                requester_email TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL,
                due_at TEXT NOT NULL,
                assignee TEXT NOT NULL,
                status TEXT NOT NULL,
                response TEXT,
                resolved_by TEXT,
                resolved_at TEXT,
                source_message_id TEXT UNIQUE,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "UPDATE requirements SET status = 'En progreso' WHERE status = 'Vencido'"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        now = now_iso()
        for username, password, role in DEFAULT_USERS:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (username, password, role, active, created_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (username, password, role, now),
            )
        conn.commit()


def create_requirement(item: EmailRequest) -> str | None:
    created = datetime.now(TZ)
    due = created + timedelta(hours=48)

    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                if item.source_message_id:
                    cur.execute(
                        "SELECT req_code FROM requirements WHERE source_message_id = %s",
                        (item.source_message_id,),
                    )
                    existing = cur.fetchone()
                    if existing:
                        return None

                cur.execute(
                    """
                    INSERT INTO requirements (
                        requester_name,
                        requester_email,
                        title,
                        detail,
                        created_at,
                        due_at,
                        assignee,
                        status,
                        source_message_id,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        item.requester_name,
                        item.requester_email,
                        item.title,
                        item.detail,
                        created,
                        due,
                        item.assignee,
                        "Nuevo",
                        item.source_message_id,
                        created,
                    ),
                )
                row = cur.fetchone()
                row_id = int(row["id"])
                req_code = f"REQ-{row_id:06d}"
                cur.execute(
                    "UPDATE requirements SET req_code = %s WHERE id = %s",
                    (req_code, row_id),
                )
            conn.commit()
            return req_code

        if item.source_message_id:
            existing = conn.execute(
                "SELECT req_code FROM requirements WHERE source_message_id = ?",
                (item.source_message_id,),
            ).fetchone()
            if existing:
                return None

        cur = conn.execute(
            """
            INSERT INTO requirements (
                requester_name,
                requester_email,
                title,
                detail,
                created_at,
                due_at,
                assignee,
                status,
                source_message_id,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.requester_name,
                item.requester_email,
                item.title,
                item.detail,
                created.isoformat(timespec="seconds"),
                due.isoformat(timespec="seconds"),
                item.assignee,
                "Nuevo",
                item.source_message_id,
                created.isoformat(timespec="seconds"),
            ),
        )
        row_id = cur.lastrowid
        req_code = f"REQ-{row_id:06d}"
        conn.execute(
            "UPDATE requirements SET req_code = ? WHERE id = ?", (req_code, row_id)
        )
        conn.commit()
        return req_code


def list_requirements(status: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                if status and status != "Todos":
                    cur.execute(
                        "SELECT * FROM requirements WHERE status = %s ORDER BY created_at DESC",
                        (status,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM requirements
                        ORDER BY
                            CASE WHEN status = 'Resuelto' THEN 1 ELSE 0 END ASC,
                            created_at DESC
                        """
                    )
                rows = cur.fetchall()
            return _to_dict_list(rows)

        if status and status != "Todos":
            rows = conn.execute(
                "SELECT * FROM requirements WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM requirements
                ORDER BY
                    CASE WHEN status = 'Resuelto' THEN 1 ELSE 0 END ASC,
                    datetime(created_at) DESC
                """
            ).fetchall()
        return _to_dict_list(rows)


def get_requirement(req_code: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM requirements WHERE req_code = %s", (req_code,))
                row = cur.fetchone()
            return _to_dict(row) if row else None

        row = conn.execute(
            "SELECT * FROM requirements WHERE req_code = ?", (req_code,)
        ).fetchone()
        return _to_dict(row) if row else None


def update_requirement(req_code: str, status: str, response: str, resolved_by: str) -> None:
    ts = datetime.now(TZ)
    resolved_at = ts if status == "Resuelto" else None

    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE requirements
                    SET status = %s, response = %s, resolved_by = %s, resolved_at = %s, updated_at = %s
                    WHERE req_code = %s
                    """,
                    (status, response.strip(), resolved_by.strip(), resolved_at, ts, req_code),
                )
            conn.commit()
            return

        conn.execute(
            """
            UPDATE requirements
            SET status = ?, response = ?, resolved_by = ?, resolved_at = ?, updated_at = ?
            WHERE req_code = ?
            """,
            (
                status,
                response.strip(),
                resolved_by.strip(),
                ts.isoformat(timespec="seconds"),
                ts.isoformat(timespec="seconds"),
                req_code,
            )
            if resolved_at
            else (
                status,
                response.strip(),
                resolved_by.strip(),
                None,
                ts.isoformat(timespec="seconds"),
                req_code,
            ),
        )
        conn.commit()


def refresh_overdue_statuses() -> None:
    return None


def _count_by_status(conn: Any, status: str) -> int:
    if _is_postgres():
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM requirements WHERE status = %s", (status,))
            row = cur.fetchone()
            return int(row["c"])

    row = conn.execute(
        "SELECT COUNT(*) as c FROM requirements WHERE status = ?", (status,)
    ).fetchone()
    return int(row["c"])


def get_metrics() -> dict[str, int]:
    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM requirements")
                total = int(cur.fetchone()["c"])
        else:
            total = int(conn.execute("SELECT COUNT(*) as c FROM requirements").fetchone()["c"])

        nuevo = _count_by_status(conn, "Nuevo")
        progreso = _count_by_status(conn, "En progreso")
        resuelto = _count_by_status(conn, "Resuelto")

    return {
        "Total": total,
        "Nuevo": nuevo,
        "En progreso": progreso,
        "Resuelto": resuelto,
    }


def authenticate_user(username: str, password: str, role: str | None = None) -> bool:
    username = username.strip()
    if not username or not password:
        return False

    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                if role:
                    cur.execute(
                        """
                        SELECT 1
                        FROM users
                        WHERE username = %s
                          AND password = %s
                          AND role = %s
                          AND active = TRUE
                        LIMIT 1
                        """,
                        (username, password, role),
                    )
                else:
                    cur.execute(
                        """
                        SELECT 1
                        FROM users
                        WHERE username = %s
                          AND password = %s
                          AND active = TRUE
                        LIMIT 1
                        """,
                        (username, password),
                    )
                return cur.fetchone() is not None

        if role:
            row = conn.execute(
                """
                SELECT 1
                FROM users
                WHERE username = ?
                  AND password = ?
                  AND role = ?
                  AND active = 1
                LIMIT 1
                """,
                (username, password, role),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT 1
                FROM users
                WHERE username = ?
                  AND password = ?
                  AND active = 1
                LIMIT 1
                """,
                (username, password),
            ).fetchone()
        return row is not None
