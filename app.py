from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from req_manager.db import (
    authenticate_user,
    create_app_session_token,
    create_requirement,
    ensure_schema,
    get_metrics,
    get_requirement,
    list_requirements,
    ROLE_ADMIN,
    ROLE_REQUERIMIENTOS,
    register_admin_login,
    update_requirement,
)
from req_manager.email_ack import (
    EmailAckConfigError,
    send_acknowledgement,
    send_resolution_notification,
)
from req_manager.email_ingest import EmailConfigError, sync_unseen_emails
from req_manager.ui import apply_dashboard_css

TZ = ZoneInfo("America/Santiago")
load_dotenv()

st.set_page_config(
    page_title="Gestor de Requerimientos",
    page_icon="📨",
    layout="wide",
)
apply_dashboard_css()


def format_dt(value: str | None) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.astimezone(TZ).strftime("%d-%m-%Y %H:%M")
    try:
        return datetime.fromisoformat(value).astimezone(TZ).strftime("%d-%m-%Y %H:%M")
    except (TypeError, ValueError):
        return value


def render_metrics() -> None:
    metrics = get_metrics()
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics.items()):
        col.markdown(
            f"""
<div class="kpi-card">
  <div class="kpi-label">{label}</div>
  <div class="kpi-value">{value}</div>
</div>
""",
            unsafe_allow_html=True,
        )


def require_admin_login() -> bool:
    if st.session_state.get("admin_authenticated", False):
        return True

    st.title("Acceso Administrador")
    st.caption("Ingresa tus credenciales para administrar requerimientos.")

    with st.form("admin_login_form", clear_on_submit=False):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar", use_container_width=True)

    if submitted:
        if authenticate_user(
            username,
            password,
            role=[ROLE_REQUERIMIENTOS, ROLE_ADMIN],
        ):
            register_admin_login(username, _detect_client_ip())
            st.session_state["admin_authenticated"] = True
            st.session_state["admin_username"] = username.strip()
            st.success("Autenticación correcta.")
            st.rerun()
        else:
            st.error("Usuario o contraseña inválidos.")

    st.info("Usuario demo: Administrador")
    return False


def _detect_client_ip() -> str:
    try:
        context = st.context
        if context is None:
            return "No disponible"

        ip_direct = getattr(context, "ip_address", None)
        if ip_direct:
            return str(ip_direct)

        headers = getattr(context, "headers", None)
        if headers:
            xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
            if xff:
                return str(xff).split(",")[0].strip()
            real_ip = headers.get("X-Real-Ip") or headers.get("x-real-ip")
            if real_ip:
                return str(real_ip).strip()
    except Exception:  # noqa: BLE001
        return "No disponible"
    return "No disponible"


def debts_app_url() -> str:
    return (os.getenv("DEBTS_APP_URL", "").strip() or "http://localhost:8504").rstrip("/")


def render_debts_shortcut() -> None:
    st.subheader("Acceso rápido")
    st.caption("Abrir el módulo de deudas con sesión compartida (token temporal).")
    if st.button("Ir al módulo de deudas", use_container_width=False):
        username = st.session_state.get("admin_username", "")
        token = create_app_session_token(
            username=username,
            target_module="debts",
            ttl_minutes=5,
        )
        if not token:
            st.error("No se pudo generar acceso temporal para el módulo de deudas.")
            return
        url = f"{debts_app_url()}?sso_token={token}"
        st.link_button("Abrir Deudas", url=url, use_container_width=False)


def sync_emails_ui() -> None:
    if st.button("Sincronizar correos no leídos", use_container_width=False):
        try:
            parsed = sync_unseen_emails()
            created = 0
            duplicated = 0
            ack_sent = 0
            ack_failed = 0
            actor = st.session_state.get("admin_username", "Administrador")
            for item in parsed:
                req_code = create_requirement(item, actor=actor)
                if req_code:
                    created += 1
                    try:
                        send_acknowledgement(item, req_code)
                        ack_sent += 1
                    except EmailAckConfigError:
                        # Sin SMTP configurado, no bloqueamos el alta del REQ.
                        ack_failed += 1
                    except Exception:  # noqa: BLE001
                        ack_failed += 1
                else:
                    duplicated += 1

            st.success(
                f"Sincronización finalizada. Nuevos: {created} | Duplicados ignorados: {duplicated}"
            )
            if created > 0:
                st.info(
                    f"Acuses enviados: {ack_sent} | Acuses con error: {ack_failed}"
                )
        except EmailConfigError as e:
            st.error(str(e))
        except Exception as e:  # noqa: BLE001
            st.error(f"Error al sincronizar correos: {e}")


def build_table(rows: list) -> pd.DataFrame:
    data = []
    for r in rows:
        data.append(
            {
                "REQ": r["req_code"],
                "Estado": r["status"],
                "Solicitante": r["requester_name"],
                "Correo": r["requester_email"],
                "Título": r["title"],
                "Asignado": r["assignee"],
                "Fecha de Ingreso": format_dt(r["created_at"]),
                "Fecha Objetivo": format_dt(r["due_at"]),
                "Actualizado": format_dt(r["updated_at"]),
            }
        )
    return pd.DataFrame(data)


def requirement_editor(req_code: str) -> None:
    req = get_requirement(req_code)
    if not req:
        st.warning("No se encontró el requerimiento seleccionado.")
        return

    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader(f"Detalle {req['req_code']}")

    c1, c2 = st.columns(2)
    c1.write(f"**Solicitante:** {req['requester_name']} ({req['requester_email']})")
    c2.write(f"**Asignado:** {req['assignee']}")

    c3, c4, c5 = st.columns(3)
    c3.write(f"**Estado actual:** {req['status']}")
    c4.write(f"**Fecha de Ingreso:** {format_dt(req['created_at'])}")
    c5.write(f"**Fecha Objetivo:** {format_dt(req['due_at'])}")

    st.write(f"**Título:** {req['title']}")
    st.text_area("Detalle original", req["detail"], height=160, disabled=True)

    with st.form(f"update_form_{req_code}"):
        status = st.selectbox(
            "Nuevo estado",
            ["Nuevo", "En progreso", "Resuelto"],
            index=["Nuevo", "En progreso", "Resuelto"].index(req["status"]),
        )
        response = st.text_area(
            "Respuesta / resolución",
            value=req["response"] or "",
            height=140,
            placeholder="Registrar aquí la respuesta ejecutada para el solicitante...",
        )
        resolved_by = st.text_input(
            "Resuelto por",
            value=req["resolved_by"] or "Administrador",
        )

        submitted = st.form_submit_button("Guardar actualización", use_container_width=True)
        if submitted:
            closing_now = status == "Resuelto" and req["status"] != "Resuelto"
            update_requirement(
                req_code,
                status,
                response,
                resolved_by,
                actor=st.session_state.get("admin_username", "Administrador"),
            )
            st.success("Requerimiento actualizado correctamente.")
            if closing_now:
                updated_req = get_requirement(req_code) or req
                try:
                    send_resolution_notification(updated_req)
                    st.info("Se envió correo de cierre al solicitante.")
                except EmailAckConfigError:
                    st.warning(
                        "REQ cerrado, pero no se pudo enviar correo de cierre por falta de configuración SMTP."
                    )
                except Exception:  # noqa: BLE001
                    st.warning(
                        "REQ cerrado, pero ocurrió un error al enviar el correo de cierre."
                    )
            st.rerun()

    if req["resolved_at"]:
        st.caption(f"Fecha resolución: {format_dt(req['resolved_at'])}")

    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    ensure_schema()

    if not require_admin_login():
        return

    st.title("Gestor de Requerimientos")
    st.caption(
        f"Control de solicitudes por correo | Fecha actual: {datetime.now(TZ).strftime('%d-%m-%Y %H:%M')}"
    )
    render_debts_shortcut()
    sync_emails_ui()

    render_metrics()

    st.markdown("### Reporte operativo")
    filter_col, refresh_col = st.columns([2, 1])

    with filter_col:
        status_filter = st.selectbox(
            "Filtrar por estado",
            ["Todos", "Nuevo", "En progreso", "Resuelto"],
        )

    with refresh_col:
        st.write("")
        if st.button("Refrescar reporte", use_container_width=True):
            st.rerun()

    rows = list_requirements(status_filter)
    if not rows:
        st.info("No hay requerimientos aún. Sincroniza la bandeja de correo para comenzar.")
        return

    df = build_table(rows)
    table_event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="req_table",
    )

    selected_req = None
    selected_rows = getattr(getattr(table_event, "selection", None), "rows", [])
    if selected_rows:
        selected_req = str(df.iloc[selected_rows[0]]["REQ"])
        st.session_state["selected_req"] = selected_req

    if not selected_req:
        st.caption(
            "Haz click en una fila del reporte para abrir su detalle y poder actualizarlo."
        )
        return

    requirement_editor(selected_req)


if __name__ == "__main__":
    main()
