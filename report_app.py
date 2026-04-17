from __future__ import annotations

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st
from zoneinfo import ZoneInfo

from req_manager.db import authenticate_user, ensure_schema, get_metrics, list_requirements

TZ = ZoneInfo("America/Santiago")

st.set_page_config(
    page_title="Reporte Ejecutivo de Requerimientos",
    page_icon="📊",
    layout="wide",
)

st.markdown(
    """
<style>
.main {
    background: radial-gradient(circle at 12% 10%, #eefaf7, #f9fcff 36%, #ffffff 80%);
}
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
}
h1, h2, h3 {
    font-family: "Avenir Next", "Helvetica Neue", sans-serif;
    color: #153044;
}
.kpi-card {
    border-radius: 14px;
    border: 1px solid #dde9f1;
    padding: 14px 16px;
    background: white;
    box-shadow: 0 7px 22px rgba(27, 74, 112, 0.10);
}
.kpi-label {
    font-size: 0.9rem;
    color: #547188;
}
.kpi-value {
    font-size: 1.6rem;
    font-weight: 700;
    color: #10253f;
}
.info-box {
    border-radius: 12px;
    border: 1px solid #d9e8f4;
    padding: 10px 12px;
    background: #f5fbff;
    color: #244965;
}
</style>
""",
    unsafe_allow_html=True,
)


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
        if authenticate_user(username, password, role="report"):
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


def build_topic_charts_df(rows: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not rows:
        return pd.DataFrame(columns=["Tema", "Cantidad"]), pd.DataFrame(
            columns=["Tema", "Cantidad"]
        )

    data = [
        {
            "Tema": r["title"],
            "Estado": r["status"],
        }
        for r in rows
    ]
    df = pd.DataFrame(data)

    pending_df = (
        df[df["Estado"].isin(["Nuevo", "En progreso"])]
        .groupby("Tema", as_index=False)
        .size()
        .rename(columns={"size": "Cantidad"})
        .sort_values("Cantidad", ascending=False)
        .head(10)
    )

    resolved_df = (
        df[df["Estado"] == "Resuelto"]
        .groupby("Tema", as_index=False)
        .size()
        .rename(columns={"size": "Cantidad"})
        .sort_values("Cantidad", ascending=False)
        .head(10)
    )

    return pending_df, resolved_df


def render_charts(metrics: dict[str, int], rows: list) -> None:
    status_df = build_status_df(metrics)
    full_status_df = build_full_status_df(metrics)
    pending_topics_df, resolved_topics_df = build_topic_charts_df(rows)

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

    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Temas pendientes (Top 10)")
        if pending_topics_df.empty:
            st.info("No hay temas pendientes.")
        else:
            pending_chart = (
                alt.Chart(pending_topics_df)
                .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    x=alt.X("Cantidad:Q"),
                    y=alt.Y("Tema:N", sort="-x"),
                    color=alt.value("#f08a4b"),
                    tooltip=["Tema", "Cantidad"],
                )
                .properties(height=360)
            )
            st.altair_chart(pending_chart, use_container_width=True)

    with col4:
        st.subheader("Temas resueltos (Top 10)")
        if resolved_topics_df.empty:
            st.info("Aún no hay temas resueltos.")
        else:
            resolved_chart = (
                alt.Chart(resolved_topics_df)
                .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    x=alt.X("Cantidad:Q"),
                    y=alt.Y("Tema:N", sort="-x"),
                    color=alt.value("#2c9f7a"),
                    tooltip=["Tema", "Cantidad"],
                )
                .properties(height=360)
            )
            st.altair_chart(resolved_chart, use_container_width=True)


def render_read_only_table(rows: list) -> None:
    st.subheader("Detalle operativo (solo lectura)")
    if not rows:
        st.info("No hay requerimientos registrados todavía.")
        return

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
    st.dataframe(df, use_container_width=True, hide_index=True)


def main() -> None:
    ensure_schema()

    if not require_report_login():
        return

    rows = list_requirements("Todos")
    metrics = get_metrics()

    st.title("Reporte Ejecutivo de Requerimientos")
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
    render_read_only_table(rows)


if __name__ == "__main__":
    main()
