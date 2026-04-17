from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator
from zoneinfo import ZoneInfo

DB_PATH = "req_manager.db"
TZ = ZoneInfo("America/Santiago")


@dataclass
class EmailRequest:
    requester_name: str
    requester_email: str
    title: str
    detail: str
    source_message_id: str | None = None
    assignee: str = "Administrador"


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def ensure_schema() -> None:
    with get_conn() as conn:
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
        # Migracion: eliminamos estado legacy 'Vencido'.
        conn.execute(
            "UPDATE requirements SET status = 'En progreso' WHERE status = 'Vencido'"
        )
        conn.commit()


def create_requirement(item: EmailRequest) -> str | None:
    created = datetime.now(TZ)
    due = created + timedelta(hours=48)

    with get_conn() as conn:
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


def list_requirements(status: str | None = None) -> list[sqlite3.Row]:
    with get_conn() as conn:
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
    return rows


def get_requirement(req_code: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM requirements WHERE req_code = ?", (req_code,)
        ).fetchone()


def update_requirement(req_code: str, status: str, response: str, resolved_by: str) -> None:
    ts = now_iso()
    resolved_at = ts if status == "Resuelto" else None

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE requirements
            SET status = ?, response = ?, resolved_by = ?, resolved_at = ?, updated_at = ?
            WHERE req_code = ?
            """,
            (status, response.strip(), resolved_by.strip(), resolved_at, ts, req_code),
        )
        conn.commit()


def refresh_overdue_statuses() -> None:
    # Estado 'Vencido' eliminado por requerimiento funcional.
    return None


def get_metrics() -> dict[str, int]:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM requirements").fetchone()["c"]
        nuevo = conn.execute(
            "SELECT COUNT(*) as c FROM requirements WHERE status = 'Nuevo'"
        ).fetchone()["c"]
        progreso = conn.execute(
            "SELECT COUNT(*) as c FROM requirements WHERE status = 'En progreso'"
        ).fetchone()["c"]
        resuelto = conn.execute(
            "SELECT COUNT(*) as c FROM requirements WHERE status = 'Resuelto'"
        ).fetchone()["c"]
    return {
        "Total": total,
        "Nuevo": nuevo,
        "En progreso": progreso,
        "Resuelto": resuelto,
    }
