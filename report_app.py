from __future__ import annotations

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

from req_manager.db import (
    DEBT_STATUS_OPTIONS,
    authenticate_user,
    ensure_schema,
    get_metrics,
    list_community_debts,
    list_admin_logins,
    list_requirements,
    normalize_debt_status,
    register_login_event,
    ROLE_ADMIN,
    ROLE_REPORTES,
)
from req_manager.ui import apply_dashboard_css

TZ = ZoneInfo("America/Santiago")
load_dotenv()

st.set_page_config(
    page_title="Reporte Ejecutivo",
    page_icon="📊",
    layout="wide",
)
apply_dashboard_css()


def require_report_login() -> bool:
    if st.session_state.get("report_authenticated", False):
        return True

    st.title("Acceso Reportes")
    st.caption("Ingresa tus credenciales para ver el módulo de reportes.")

    with st.form("report_login_form", clear_on_submit=False):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar", use_container_width=True)

    if submitted:
        if authenticate_user(
            username,
            password,
            role=[ROLE_REPORTES, ROLE_ADMIN],
        ):
            register_login_event(username=username, ip_address=_detect_client_ip(), module="Reportes")
            st.session_state["report_authenticated"] = True
            st.success("Autenticación correcta.")
            st.rerun()
        else:
            st.error("Usuario o contraseña inválidos.")

    return False


def render_kpis(metrics: dict[str, int]) -> None:
    total = metrics["Total"]
    resolved = metrics["Resuelto"]
    pending = total - resolved
    resolution_rate = (resolved / total * 100) if total else 0.0

    cards = {
        "Total": total,
        "Pendientes": pending,
        "Resueltos": resolved,
        "% Resolución": f"{resolution_rate:.1f}%",
    }

    cols = st.columns(len(cards))
    for col, (label, value) in zip(cols, cards.items()):
        col.markdown(
            f"""
<div class="kpi-card">
  <div class="kpi-label">{label}</div>
  <div class="kpi-value">{value}</div>
</div>
""",
            unsafe_allow_html=True,
        )


def format_dt(value: str | datetime | None) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.astimezone(TZ).strftime("%d-%m-%Y %H:%M")
    try:
        return datetime.fromisoformat(value).astimezone(TZ).strftime("%d-%m-%Y %H:%M")
    except (TypeError, ValueError):
        return str(value)


def to_dt(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def build_status_df(metrics: dict[str, int]) -> pd.DataFrame:
    pending = metrics["Total"] - metrics["Resuelto"]
    return pd.DataFrame(
        [
            {"Grupo": "Resueltos", "Cantidad": metrics["Resuelto"]},
            {"Grupo": "Pendientes", "Cantidad": pending},
        ]
    )


def build_full_status_df(metrics: dict[str, int]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Estado": "Nuevo", "Cantidad": metrics["Nuevo"]},
            {"Estado": "En progreso", "Cantidad": metrics["En progreso"]},
            {"Estado": "Resuelto", "Cantidad": metrics["Resuelto"]},
        ]
    )


def build_pending_due_df(rows: list) -> pd.DataFrame:
    inside_due = 0
    overdue = 0
    now = datetime.now(TZ)

    for r in rows:
        if r["status"] == "Resuelto":
            continue

        due_at = to_dt(r.get("due_at"))
        if due_at is None:
            overdue += 1
            continue

        # Unificamos zona horaria para comparación estable.
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=TZ)
        else:
            due_at = due_at.astimezone(TZ)

        if due_at >= now:
            inside_due += 1
        else:
            overdue += 1

    return pd.DataFrame(
        [
            {"Grupo": "Dentro de vencimiento", "Cantidad": inside_due},
            {"Grupo": "Excedidos de vencimiento", "Cantidad": overdue},
        ]
    )


def render_charts(metrics: dict[str, int], rows: list) -> None:
    status_df = build_status_df(metrics)
    full_status_df = build_full_status_df(metrics)
    pending_due_df = build_pending_due_df(rows)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Resueltos vs Pendientes")
        pie = (
            alt.Chart(status_df)
            .mark_arc(innerRadius=70)
            .encode(
                theta=alt.Theta(field="Cantidad", type="quantitative"),
                color=alt.Color(
                    field="Grupo",
                    type="nominal",
                    scale=alt.Scale(range=["#2c9f7a", "#f08a4b"]),
                ),
                tooltip=["Grupo", "Cantidad"],
            )
            .properties(height=330)
        )
        st.altair_chart(pie, use_container_width=True)

    with col2:
        st.subheader("Estado de requerimientos")
        bars = (
            alt.Chart(full_status_df)
            .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
            .encode(
                x=alt.X("Estado:N", sort=["Nuevo", "En progreso", "Resuelto"]),
                y=alt.Y("Cantidad:Q"),
                color=alt.Color(
                    "Estado:N",
                    scale=alt.Scale(
                        domain=["Nuevo", "En progreso", "Resuelto"],
                        range=["#4b7bec", "#f5a623", "#2c9f7a"],
                    ),
                ),
                tooltip=["Estado", "Cantidad"],
            )
            .properties(height=330)
        )
        st.altair_chart(bars, use_container_width=True)

    st.subheader("Requerimientos no resueltos por vencimiento")
    pending_due_chart = (
        alt.Chart(pending_due_df)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X(
                "Grupo:N",
                sort=["Dentro de vencimiento", "Excedidos de vencimiento"],
            ),
            y=alt.Y("Cantidad:Q"),
            color=alt.Color(
                "Grupo:N",
                scale=alt.Scale(
                    domain=["Dentro de vencimiento", "Excedidos de vencimiento"],
                    range=["#2c9f7a", "#d64545"],
                ),
            ),
            tooltip=["Grupo", "Cantidad"],
        )
        .properties(height=320)
    )
    st.altair_chart(pending_due_chart, use_container_width=True)


def render_read_only_table(rows: list) -> str | None:
    st.subheader("Detalle operativo (solo lectura)")
    if not rows:
        st.info("No hay requerimientos registrados todavía.")
        return None

    df = pd.DataFrame(
        [
            {
                "REQ": r["req_code"],
                "Estado": r["status"],
                "Solicitante": r["requester_name"],
                "Correo": r["requester_email"],
                "Tema": r["title"],
                "Asignado": r["assignee"],
                "Fecha alta": format_dt(r["created_at"]),
                "Fecha vencimiento": format_dt(r["due_at"]),
                "Actualizado": format_dt(r["updated_at"]),
            }
            for r in rows
        ]
    )
    table_event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="report_req_table",
    )
    selected_rows = getattr(getattr(table_event, "selection", None), "rows", [])
    if selected_rows:
        selected_req = str(df.iloc[selected_rows[0]]["REQ"])
        st.session_state["report_selected_req"] = selected_req
        return selected_req

    return st.session_state.get("report_selected_req")


def render_requirement_resolution(rows: list, req_code: str | None) -> None:
    if not req_code:
        st.caption("Selecciona una fila para ver detalle y resolución del requerimiento.")
        return

    selected = next((r for r in rows if str(r["req_code"]) == str(req_code)), None)
    if not selected:
        st.caption("Selecciona una fila para ver detalle y resolución del requerimiento.")
        return

    st.markdown("### Detalle de Requerimiento")
    c1, c2 = st.columns(2)
    c1.write(f"**REQ:** {selected['req_code']}")
    c2.write(f"**Estado:** {selected['status']}")

    c3, c4 = st.columns(2)
    c3.write(
        f"**Solicitante:** {selected['requester_name']} ({selected['requester_email']})"
    )
    c4.write(f"**Asignado:** {selected['assignee']}")

    c5, c6, c7 = st.columns(3)
    c5.write(f"**Fecha alta:** {format_dt(selected['created_at'])}")
    c6.write(f"**Fecha vencimiento:** {format_dt(selected['due_at'])}")
    c7.write(f"**Última actualización:** {format_dt(selected['updated_at'])}")

    st.write(f"**Tema:** {selected['title']}")
    st.text_area("Detalle original", selected["detail"], height=140, disabled=True)

    st.write(f"**Resuelto por:** {selected.get('resolved_by') or '-'}")
    st.write(f"**Fecha de cierre:** {format_dt(selected.get('resolved_at'))}")
    st.text_area(
        "Resolución registrada",
        selected.get("response") or "Sin resolución registrada.",
        height=140,
        disabled=True,
    )


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


def render_admin_logins() -> None:
    st.subheader("Últimos logins en Administrador")
    logs = list_admin_logins(limit=50)
    if not logs:
        st.caption("No hay logins registrados todavía.")
        return

    df = pd.DataFrame(
        [
            {
                "Usuario": r.get("username", "-"),
                "Módulo": r.get("module", "Administrador"),
                "IP": r.get("ip_address", "No disponible"),
                "Día y Hora": format_dt(r.get("logged_at")),
            }
            for r in logs
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_debts_charts() -> None:
    rows = list_community_debts()
    if not rows:
        st.subheader("Estado de deudas")
        st.caption("No hay deudas registradas.")
        return

    counts = {status: 0 for status in DEBT_STATUS_OPTIONS}
    cut_yes = 0
    cut_no = 0
    for r in rows:
        status = normalize_debt_status(r.get("status"))
        counts[status] = counts.get(status, 0) + 1
        if bool(r.get("services_cut")):
            cut_yes += 1
        else:
            cut_no += 1

    status_df = pd.DataFrame(
        [{"Grupo": s, "Cantidad": counts.get(s, 0)} for s in DEBT_STATUS_OPTIONS]
    )
    cut_df = pd.DataFrame(
        [
            {"Grupo": "Servicios cortados", "Cantidad": cut_yes},
            {"Grupo": "Sin servicios cortados", "Cantidad": cut_no},
        ]
    )

    st.subheader("Estado de deudas de gastos comunes")
    c1, c2 = st.columns(2)
    with c1:
        st.caption("Deudas por estado")
        pie_status = (
            alt.Chart(status_df)
            .mark_arc(innerRadius=65)
            .encode(
                theta=alt.Theta(field="Cantidad", type="quantitative"),
                color=alt.Color(
                    field="Grupo",
                    type="nominal",
                    scale=alt.Scale(
                        domain=DEBT_STATUS_OPTIONS,
                        range=["#6b7280", "#2f83a3", "#d64545", "#2c9f7a"],
                    ),
                ),
                tooltip=["Grupo", "Cantidad"],
            )
            .properties(height=280)
        )
        st.altair_chart(pie_status, use_container_width=True)
    with c2:
        st.caption("Deudores con/sin servicios cortados")
        pie_cut = (
            alt.Chart(cut_df)
            .mark_arc(innerRadius=65)
            .encode(
                theta=alt.Theta(field="Cantidad", type="quantitative"),
                color=alt.Color(
                    field="Grupo",
                    type="nominal",
                    scale=alt.Scale(
                        domain=["Servicios cortados", "Sin servicios cortados"],
                        range=["#d64545", "#2c9f7a"],
                    ),
                ),
                tooltip=["Grupo", "Cantidad"],
            )
            .properties(height=280)
        )
        st.altair_chart(pie_cut, use_container_width=True)


def main() -> None:
    ensure_schema()

    if not require_report_login():
        return

    rows = list_requirements("Todos")
    metrics = get_metrics()

    st.title("Reporte Ejecutivo")
    st.caption(
        f"Vista de monitoreo sin edición | {datetime.now(TZ).strftime('%d-%m-%Y %H:%M')}"
    )

    st.markdown(
        '<div class="info-box">Este módulo es de solo lectura. No permite modificar requerimientos.</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    render_kpis(metrics)
    st.write("")
    render_charts(metrics, rows)
    st.write("")
    render_debts_charts()
    st.write("")
    selected_req = render_read_only_table(rows)
    st.write("")
    render_requirement_resolution(rows, selected_req)
    st.write("")
    render_admin_logins()


if __name__ == "__main__":
    main()
