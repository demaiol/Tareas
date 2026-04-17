from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from req_manager.db import (
    create_requirement,
    ensure_schema,
    get_metrics,
    get_requirement,
    list_requirements,
    update_requirement,
)
from req_manager.email_ingest import EmailConfigError, sync_unseen_emails

TZ = ZoneInfo("America/Santiago")
load_dotenv()

st.set_page_config(
    page_title="Gestor Ejecutivo de Requerimientos",
    page_icon="📨",
    layout="wide",
)

st.markdown(
    """
<style>
.main {
    background: radial-gradient(circle at 15% 15%, #edf4ff, #f9fbff 38%, #ffffff 80%);
}
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2.2rem;
}
h1, h2, h3 {
    font-family: "Avenir Next", "Helvetica Neue", sans-serif;
    color: #1f2d3d;
}
.kpi-card {
    border-radius: 14px;
    border: 1px solid #e4ebf5;
    padding: 14px 16px;
    background: white;
    box-shadow: 0 7px 24px rgba(43, 83, 126, 0.08);
}
.kpi-label {
    font-size: 0.9rem;
    color: #5a6d84;
}
.kpi-value {
    font-size: 1.6rem;
    font-weight: 700;
    color: #10253f;
}
.section-box {
    border-radius: 14px;
    border: 1px solid #e4ebf5;
    padding: 16px;
    background: white;
    box-shadow: 0 7px 24px rgba(43, 83, 126, 0.08);
}
</style>
""",
    unsafe_allow_html=True,
)


def format_dt(value: str | None) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value).astimezone(TZ).strftime("%d-%m-%Y %H:%M")
    except ValueError:
        return value


def render_metrics() -> None:
    metrics = get_metrics()
    cols = st.columns(5)
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


def sync_emails_ui() -> None:
    with st.sidebar:
        st.subheader("Integración de correo")
        st.caption("Conectado vía IMAP/Gmail. Configurar variables en `.env`.")

        if st.button("Sincronizar correos no leídos", use_container_width=True):
            try:
                parsed = sync_unseen_emails()
                created = 0
                duplicated = 0
                for item in parsed:
                    req_code = create_requirement(item)
                    if req_code:
                        created += 1
                    else:
                        duplicated += 1

                st.success(
                    f"Sincronización finalizada. Nuevos: {created} | Duplicados ignorados: {duplicated}"
                )
            except EmailConfigError as e:
                st.error(str(e))
            except Exception as e:  # noqa: BLE001
                st.error(f"Error al sincronizar correos: {e}")

        st.caption(
            "Modo Gmail: `GMAIL_USER`, `GMAIL_APP_PASSWORD` (opcional `GMAIL_FOLDER`)."
        )
        st.caption(
            "Modo IMAP: `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD` (opcional `IMAP_FOLDER`)."
        )


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
                "Alta": format_dt(r["created_at"]),
                "Vencimiento": format_dt(r["due_at"]),
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
    c4.write(f"**Fecha alta:** {format_dt(req['created_at'])}")
    c5.write(f"**Vencimiento:** {format_dt(req['due_at'])}")

    st.write(f"**Título:** {req['title']}")
    st.text_area("Detalle original", req["detail"], height=160, disabled=True)

    with st.form(f"update_form_{req_code}"):
        status = st.selectbox(
            "Nuevo estado",
            ["Nuevo", "En progreso", "Resuelto", "Vencido"],
            index=["Nuevo", "En progreso", "Resuelto", "Vencido"].index(req["status"]),
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
            update_requirement(req_code, status, response, resolved_by)
            st.success("Requerimiento actualizado correctamente.")
            st.rerun()

    if req["resolved_at"]:
        st.caption(f"Fecha resolución: {format_dt(req['resolved_at'])}")

    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    ensure_schema()
    sync_emails_ui()

    st.title("Gestor Ejecutivo de Requerimientos")
    st.caption(
        f"Control de solicitudes por correo | Fecha actual: {datetime.now(TZ).strftime('%d-%m-%Y %H:%M')}"
    )

    render_metrics()

    st.markdown("### Reporte operativo")
    filter_col, refresh_col = st.columns([2, 1])

    with filter_col:
        status_filter = st.selectbox(
            "Filtrar por estado",
            ["Todos", "Nuevo", "En progreso", "Resuelto", "Vencido"],
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
    st.dataframe(df, use_container_width=True, hide_index=True)

    req_options = df["REQ"].tolist()
    selected_req = st.selectbox("Seleccionar REQ para gestión", req_options)
    requirement_editor(selected_req)


if __name__ == "__main__":
    main()
