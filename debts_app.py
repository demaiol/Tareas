from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from req_manager import db as db
from req_manager.ui import apply_dashboard_css

DEBT_STATUS_OPTIONS = getattr(
    db,
    "DEBT_STATUS_OPTIONS",
    ["Sin accion", "Plan acordado", "Cobranza ejecutiva", "Proceso cerrado"],
)
ROLE_ADMIN = getattr(db, "ROLE_ADMIN", "Admin")
ROLE_REQUERIMIENTOS = getattr(db, "ROLE_REQUERIMIENTOS", "Requeriemientos")

TZ = ZoneInfo("America/Santiago")
load_dotenv()

st.set_page_config(
    page_title="Gestión de Deudas",
    page_icon="💰",
    layout="wide",
)
apply_dashboard_css()


def format_dt(value: str | datetime | None) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.astimezone(TZ).strftime("%d-%m-%Y %H:%M")
    try:
        return datetime.fromisoformat(str(value)).astimezone(TZ).strftime("%d-%m-%Y %H:%M")
    except Exception:  # noqa: BLE001
        return str(value)


def format_amount(value: float | int | str | None) -> str:
    try:
        return f"${float(value):,.0f}".replace(",", ".")
    except Exception:  # noqa: BLE001
        return "$0"


def parse_amount(value: float | int | str | None) -> float:
    try:
        return float(value or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def apartment_sort_key(value: str | None) -> tuple[int, int | str]:
    v = str(value or "").strip()
    if v.isdigit():
        return (0, int(v))
    return (1, v.lower())


def require_admin_login() -> bool:
    token = st.query_params.get("sso_token")
    if token and not st.session_state.get("debts_admin_authenticated", False):
        consume_token = getattr(db, "consume_app_session_token", None)
        sso_data = None
        if callable(consume_token):
            sso_data = consume_token(str(token), target_module="debts")
        if sso_data and sso_data.get("role") in {ROLE_ADMIN, ROLE_REQUERIMIENTOS}:
            username = str(sso_data.get("username") or "Admin")
            register_login = getattr(db, "register_login_event", None)
            if callable(register_login):
                register_login(
                    username=username,
                    ip_address=_detect_client_ip(),
                    module="Deudas",
                )
            st.session_state["debts_admin_authenticated"] = True
            st.session_state["debts_actor"] = username
            st.query_params.clear()
            st.rerun()

    if st.session_state.get("debts_admin_authenticated", False):
        return True

    st.title("Acceso Gestión de Deudas")
    st.caption("Acceso restringido a usuarios con rol Requeriemientos o Admin.")

    with st.form("debts_admin_login_form", clear_on_submit=False):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar", use_container_width=True)

    if submitted:
        authenticate = getattr(db, "authenticate_user", None)
        if callable(authenticate) and authenticate(
            username,
            password,
            role=[ROLE_REQUERIMIENTOS, ROLE_ADMIN],
        ):
            register_login = getattr(db, "register_login_event", None)
            if callable(register_login):
                register_login(
                    username=username,
                    ip_address=_detect_client_ip(),
                    module="Deudas",
                )
            st.session_state["debts_admin_authenticated"] = True
            st.session_state["debts_actor"] = username.strip() or "Admin"
            st.success("Autenticación correcta.")
            st.rerun()
        else:
            st.error("Usuario o contraseña inválidos o sin permisos.")

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


def debts_table(rows: list[dict]) -> pd.DataFrame:
    sorted_rows = sorted(rows, key=lambda r: apartment_sort_key(r.get("apartment_number")))
    return pd.DataFrame(
        [
            {
                "ID": r["id"],
                "Dpto": r["apartment_number"],
                "Monto deuda": format_amount(r["debt_amount"]),
                "Estado": r["status"],
                "Servicios cortados": "Sí" if bool(r["services_cut"]) else "No",
                "Último contacto / intento": r.get("last_contact") or "-",
                "Actualizado": format_dt(r.get("updated_at")),
            }
            for r in sorted_rows
        ]
    )


def amounts_summary_table(items: list[tuple[str, float]]) -> None:
    df = pd.DataFrame(
        [{"Concepto": label, "Monto": format_amount(amount)} for label, amount in items]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_services_cut_pie(rows: list[dict]) -> None:
    cut_yes = sum(1 for r in rows if bool(r.get("services_cut")))
    cut_no = sum(1 for r in rows if not bool(r.get("services_cut")))
    amount_yes = sum(parse_amount(r.get("debt_amount")) for r in rows if bool(r.get("services_cut")))
    amount_no = sum(parse_amount(r.get("debt_amount")) for r in rows if not bool(r.get("services_cut")))
    total_amount = amount_yes + amount_no
    chart_df = pd.DataFrame(
        [
            {
                "Grupo": "Servicios cortados",
                "Cantidad": cut_yes,
                "Monto": amount_yes,
                "MontoFmt": format_amount(amount_yes),
            },
            {
                "Grupo": "Sin servicios cortados",
                "Cantidad": cut_no,
                "Monto": amount_no,
                "MontoFmt": format_amount(amount_no),
            },
        ]
    )

    st.subheader("Deudores por estado de servicios")
    pie = (
        alt.Chart(chart_df)
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
            tooltip=[
                alt.Tooltip("Grupo:N"),
                alt.Tooltip("Cantidad:Q"),
                alt.Tooltip("MontoFmt:N", title="Monto"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(pie, use_container_width=True)
    amounts_summary_table(
        [
            ("Monto total deuda", total_amount),
            ("Servicios cortados", amount_yes),
            ("Sin servicios cortados", amount_no),
        ]
    )


def render_debt_status_chart(rows: list[dict]) -> None:
    counts = {status: 0 for status in DEBT_STATUS_OPTIONS}
    amounts = {status: 0.0 for status in DEBT_STATUS_OPTIONS}
    normalize_status = getattr(db, "normalize_debt_status", None)
    for r in rows:
        if callable(normalize_status):
            status = normalize_status(r.get("status"))
        else:
            status = str(r.get("status") or DEBT_STATUS_OPTIONS[0])
        counts[status] = counts.get(status, 0) + 1
        amounts[status] = amounts.get(status, 0.0) + parse_amount(r.get("debt_amount"))

    status_df = pd.DataFrame(
        [
            {
                "Estado": status,
                "Cantidad": counts.get(status, 0),
                "Monto": amounts.get(status, 0.0),
                "MontoFmt": format_amount(amounts.get(status, 0.0)),
            }
            for status in DEBT_STATUS_OPTIONS
        ]
    )
    total_amount = sum(amounts.values())

    st.subheader("Estado actual de las deudas")
    pie = (
        alt.Chart(status_df)
        .mark_arc(innerRadius=65)
        .encode(
            theta=alt.Theta(field="Cantidad", type="quantitative"),
            color=alt.Color(
                "Estado:N",
                scale=alt.Scale(
                    domain=DEBT_STATUS_OPTIONS,
                    range=["#6b7280", "#2f83a3", "#d64545", "#2c9f7a"],
                ),
            ),
            tooltip=[
                alt.Tooltip("Estado:N"),
                alt.Tooltip("Cantidad:Q"),
                alt.Tooltip("MontoFmt:N", title="Monto"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(pie, use_container_width=True)
    amounts_summary_table(
        [
            ("Monto total deuda", total_amount),
            ("Sin accion", amounts.get("Sin accion", 0.0)),
            ("Plan acordado", amounts.get("Plan acordado", 0.0)),
            ("Cobranza ejecutiva", amounts.get("Cobranza ejecutiva", 0.0)),
            ("Proceso cerrado", amounts.get("Proceso cerrado", 0.0)),
        ]
    )


def create_debt_form() -> None:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Registrar nueva deuda")
    with st.form("create_debt_form", clear_on_submit=True):
        apartment_number = st.text_input("Nro de dpto")
        debt_amount = st.number_input("Monto de la deuda", min_value=0.0, step=1000.0)
        status = st.selectbox("Estado", DEBT_STATUS_OPTIONS)
        services_cut = st.checkbox("Servicios cortados")
        last_contact = st.text_area(
            "Último contacto (o intento)",
            placeholder="Ej: 03-05-2026 llamado telefónico sin respuesta.",
            height=70,
        )
        submitted = st.form_submit_button("Registrar deuda", use_container_width=True)
        if submitted:
            create_debt = getattr(db, "create_community_debt", None)
            if not callable(create_debt):
                st.error("No se pudo registrar la deuda: versión de base de datos desactualizada.")
                st.markdown("</div>", unsafe_allow_html=True)
                return
            debt_id = create_debt(
                apartment_number=apartment_number,
                debt_amount=float(debt_amount),
                status=status,
                services_cut=services_cut,
                last_contact=last_contact,
                actor=st.session_state.get("debts_actor", "Admin"),
            )
            if debt_id:
                st.success(f"Deuda registrada con ID {debt_id}.")
                st.rerun()
            else:
                st.error("No se pudo registrar la deuda. Verifica los datos ingresados.")
    st.markdown("</div>", unsafe_allow_html=True)


def edit_debt_form(rows: list[dict]) -> None:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Actualizar deuda")
    if not rows:
        st.info("No hay deudas registradas para editar.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    sorted_rows = sorted(rows, key=lambda r: apartment_sort_key(r.get("apartment_number")))
    options = [
        f"{r['id']} | Dpto {r['apartment_number']} | {format_amount(r['debt_amount'])} | {r['status']}"
        for r in sorted_rows
    ]
    selected = st.selectbox("Seleccionar registro", options)
    selected_id = int(selected.split("|")[0].strip())
    selected_row = next((r for r in sorted_rows if int(r["id"]) == selected_id), None)
    if not selected_row:
        st.markdown("</div>", unsafe_allow_html=True)
        return

    normalize_status = getattr(db, "normalize_debt_status", None)
    if callable(normalize_status):
        current_status = normalize_status(selected_row.get("status"))
    else:
        current_status = str(selected_row.get("status") or DEBT_STATUS_OPTIONS[0])
    status_index = (
        DEBT_STATUS_OPTIONS.index(current_status)
        if current_status in DEBT_STATUS_OPTIONS
        else 0
    )

    with st.form("edit_debt_form", clear_on_submit=False):
        apartment_number = st.text_input(
            "Nro de dpto",
            value=str(selected_row.get("apartment_number") or ""),
        )
        debt_amount = st.number_input(
            "Monto de la deuda",
            min_value=0.0,
            step=1000.0,
            value=float(selected_row.get("debt_amount") or 0.0),
        )
        status = st.selectbox("Estado", DEBT_STATUS_OPTIONS, index=status_index)
        services_cut = st.checkbox(
            "Servicios cortados",
            value=bool(selected_row.get("services_cut")),
        )
        last_contact = st.text_area(
            "Último contacto (o intento)",
            value=str(selected_row.get("last_contact") or ""),
            height=70,
        )
        submitted = st.form_submit_button("Guardar cambios", use_container_width=True)
        if submitted:
            update_debt = getattr(db, "update_community_debt", None)
            if not callable(update_debt):
                st.error("No se pudo actualizar la deuda: versión de base de datos desactualizada.")
                st.markdown("</div>", unsafe_allow_html=True)
                return
            updated = update_debt(
                debt_id=selected_id,
                apartment_number=apartment_number,
                debt_amount=float(debt_amount),
                status=status,
                services_cut=services_cut,
                last_contact=last_contact,
                actor=st.session_state.get("debts_actor", "Admin"),
            )
            if updated:
                st.success("Deuda actualizada correctamente.")
                st.rerun()
            else:
                st.error("No se pudo actualizar el registro.")

    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    ensure_schema_fn = getattr(db, "ensure_schema", None)
    if not callable(ensure_schema_fn):
        st.error("Módulo de deudas no disponible: falta `ensure_schema` en backend.")
        return
    ensure_schema_fn()
    if not require_admin_login():
        return

    st.title("Gestión de Deudas de Gastos Comunes")
    st.caption(
        f"Registro operativo de deuda por dpto | {datetime.now(TZ).strftime('%d-%m-%Y %H:%M')}"
    )

    list_debts = getattr(db, "list_community_debts", None)
    if not callable(list_debts):
        st.error("Módulo de deudas no disponible: falta `list_community_debts` en backend.")
        return
    rows = list_debts()
    st.subheader("Deudas registradas")
    if rows:
        st.dataframe(debts_table(rows), use_container_width=True, hide_index=True)
        chart_col_1, chart_sep, chart_col_2 = st.columns([1, 0.03, 1])
        with chart_col_1:
            render_debt_status_chart(rows)
        with chart_sep:
            st.markdown(
                """
                <div style="height: 520px; border-left: 1px solid #c9c9c9; margin: 0 auto;"></div>
                """,
                unsafe_allow_html=True,
            )
        with chart_col_2:
            render_services_cut_pie(rows)
    else:
        st.info("No hay deudas registradas.")

    c1, c2 = st.columns([1.0, 1.0], vertical_alignment="top")
    with c1:
        create_debt_form()
    with c2:
        edit_debt_form(rows)


if __name__ == "__main__":
    main()
