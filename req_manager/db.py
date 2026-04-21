from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterator
from zoneinfo import ZoneInfo

DB_PATH = "req_manager.db"
TZ = ZoneInfo("America/Santiago")
ROLE_ADMIN = "Admin"
ROLE_REQUERIMIENTOS = "Requeriemientos"
ROLE_REPORTES = "Reportes"
VALID_ROLES = {ROLE_ADMIN, ROLE_REQUERIMIENTOS, ROLE_REPORTES}
DEFAULT_USERS = [
    ("Administrador", "DEMO123$", ROLE_ADMIN),
    ("gestion", "gestion123$", ROLE_REPORTES),
]
IGNORED_SENDER_EMAILS = {"comunidadvistamar810@gmail.com"}


@dataclass
class EmailRequest:
    requester_name: str
    requester_email: str
    title: str
    detail: str
    source_message_id: str | None = None
    reply_to_message_id: str | None = None
    assignee: str = "Administrador"


def _database_url() -> str | None:
    value = os.getenv("DATABASE_URL", "").strip()
    return value or None


def normalize_role(value: str | None) -> str:
    role = (value or "").strip()
    role_l = role.lower()
    if role_l == "admin":
        return ROLE_ADMIN
    if role_l == "report":
        return ROLE_REPORTES
    if role_l in {"requerimientos", "requeriemientos"}:
        return ROLE_REQUERIMIENTOS
    return role


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


def _require_database_url() -> str:
    url = _database_url()
    if not url:
        raise RuntimeError(
            "Falta DATABASE_URL. Esta aplicación está configurada para usar PostgreSQL."
        )
    if not _is_postgres():
        raise RuntimeError(
            "DATABASE_URL inválida. Debe iniciar con postgres:// o postgresql://"
        )
    return url


@contextmanager
def get_conn() -> Iterator[Any]:
    psycopg, dict_row = _require_psycopg()
    conn = psycopg.connect(_require_database_url(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def _to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


def _to_dict_list(rows: list[Any]) -> list[dict[str, Any]]:
    return [_to_dict(r) for r in rows]


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def normalize_message_id(value: str | None) -> str | None:
    if not value:
        return None
    msg_id = str(value).strip()
    if not msg_id:
        return None

    if "<" in msg_id and ">" in msg_id:
        start = msg_id.find("<")
        end = msg_id.find(">", start + 1)
        if end > start:
            return msg_id[start : end + 1]
    return msg_id


def _is_ignored_sender(email: str | None) -> bool:
    value = (email or "").strip().lower()
    return value in IGNORED_SENDER_EMAILS


def requirement_exists_by_source_message_id(message_id: str | None) -> bool:
    normalized = normalize_message_id(message_id)
    if not normalized:
        return False

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM requirements
                WHERE source_message_id = %s
                LIMIT 1
                """,
                (normalized,),
            )
            return cur.fetchone() is not None


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
                cur.execute("UPDATE users SET role = %s WHERE lower(role) = 'admin'", (ROLE_ADMIN,))
                cur.execute(
                    "UPDATE users SET role = %s WHERE lower(role) = 'report'",
                    (ROLE_REPORTES,),
                )
                cur.execute(
                    "UPDATE users SET role = %s WHERE lower(role) = 'requerimientos'",
                    (ROLE_REQUERIMIENTOS,),
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_login_events (
                        id BIGSERIAL PRIMARY KEY,
                        username TEXT NOT NULL,
                        ip_address TEXT NOT NULL,
                        logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                # Alineamos secuencias para evitar colisiones de PK al insertar.
                cur.execute(
                    """
                    SELECT setval(
                        pg_get_serial_sequence('requirements', 'id'),
                        COALESCE(MAX(id), 1),
                        TRUE
                    )
                    FROM requirements
                    """
                )
                cur.execute(
                    """
                    SELECT setval(
                        pg_get_serial_sequence('users', 'id'),
                        COALESCE(MAX(id), 1),
                        TRUE
                    )
                    FROM users
                    """
                )
                cur.execute(
                    """
                    SELECT setval(
                        pg_get_serial_sequence('admin_login_events', 'id'),
                        COALESCE(MAX(id), 1),
                        TRUE
                    )
                    FROM admin_login_events
                    """
                )
                for username, password, role in DEFAULT_USERS:
                    cur.execute(
                        """
                        INSERT INTO users (username, password, role, active)
                        SELECT %s, %s, %s, TRUE
                        WHERE NOT EXISTS (
                            SELECT 1 FROM users WHERE username = %s
                        )
                        """,
                        (username, password, role, username),
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_login_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                logged_at TEXT NOT NULL
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
    if _is_ignored_sender(item.requester_email):
        return None

    if requirement_exists_by_source_message_id(item.reply_to_message_id):
        return None

    source_message_id = normalize_message_id(item.source_message_id)
    created = datetime.now(TZ)
    due = created + timedelta(hours=48)

    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                if source_message_id:
                    cur.execute(
                        "SELECT req_code FROM requirements WHERE source_message_id = %s",
                        (source_message_id,),
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
                        source_message_id,
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

        if source_message_id:
            existing = conn.execute(
                "SELECT req_code FROM requirements WHERE source_message_id = ?",
                (source_message_id,),
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
                source_message_id,
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


def list_users() -> list[dict[str, Any]]:
    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT username, role, active, created_at
                    FROM users
                    ORDER BY username ASC
                    """
                )
                rows = cur.fetchall()
            return _to_dict_list(rows)

        rows = conn.execute(
            """
            SELECT username, role, active, created_at
            FROM users
            ORDER BY username ASC
            """
        ).fetchall()
        return _to_dict_list(rows)


def create_user(username: str, password: str, role: str, active: bool = True) -> bool:
    username = username.strip()
    password = password.strip()
    role = normalize_role(role)
    if not username or not password or role not in VALID_ROLES:
        return False

    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, password, role, active)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (username) DO NOTHING
                    RETURNING username
                    """,
                    (username, password, role, active),
                )
                created = cur.fetchone() is not None
            conn.commit()
            return created

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO users (username, password, role, active, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, password, role, 1 if active else 0, now_iso()),
        )
        conn.commit()
        return cur.rowcount > 0


def update_user(
    username: str,
    role: str,
    active: bool,
    new_password: str | None = None,
) -> bool:
    username = username.strip()
    role = normalize_role(role)
    if not username or role not in VALID_ROLES:
        return False

    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                if new_password and new_password.strip():
                    cur.execute(
                        """
                        UPDATE users
                        SET role = %s, active = %s, password = %s
                        WHERE username = %s
                        """,
                        (role, active, new_password.strip(), username),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE users
                        SET role = %s, active = %s
                        WHERE username = %s
                        """,
                        (role, active, username),
                    )
                updated = cur.rowcount > 0
            conn.commit()
            return updated

        if new_password and new_password.strip():
            cur = conn.execute(
                """
                UPDATE users
                SET role = ?, active = ?, password = ?
                WHERE username = ?
                """,
                (role, 1 if active else 0, new_password.strip(), username),
            )
        else:
            cur = conn.execute(
                """
                UPDATE users
                SET role = ?, active = ?
                WHERE username = ?
                """,
                (role, 1 if active else 0, username),
            )
        conn.commit()
        return cur.rowcount > 0


def authenticate_user(
    username: str,
    password: str,
    role: str | list[str] | tuple[str, ...] | None = None,
) -> bool:
    username = username.strip()
    if not username or not password:
        return False

    roles: list[str] | None = None
    if role is not None:
        role_values = [role] if isinstance(role, str) else list(role)
        roles = [normalize_role(r) for r in role_values if normalize_role(r) in VALID_ROLES]
        if not roles:
            return False

    with get_conn() as conn:
        with conn.cursor() as cur:
            if roles:
                cur.execute(
                    """
                    SELECT 1
                    FROM users
                    WHERE username = %s
                      AND password = %s
                      AND role = ANY(%s)
                      AND active = TRUE
                    LIMIT 1
                    """,
                    (username, password, roles),
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


def register_admin_login(username: str, ip_address: str) -> None:
    username = username.strip()
    ip = (ip_address or "").strip() or "No disponible"
    if not username:
        return

    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_login_events (username, ip_address, logged_at)
                    VALUES (%s, %s, %s)
                    """,
                    (username, ip, datetime.now(TZ)),
                )
            conn.commit()
            return

        conn.execute(
            """
            INSERT INTO admin_login_events (username, ip_address, logged_at)
            VALUES (?, ?, ?)
            """,
            (username, ip, now_iso()),
        )
        conn.commit()


def list_admin_logins(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    with get_conn() as conn:
        if _is_postgres():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT username, ip_address, logged_at
                    FROM admin_login_events
                    ORDER BY logged_at DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
                rows = cur.fetchall()
            return _to_dict_list(rows)

        rows = conn.execute(
            """
            SELECT username, ip_address, logged_at
            FROM admin_login_events
            ORDER BY datetime(logged_at) DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        return _to_dict_list(rows)
