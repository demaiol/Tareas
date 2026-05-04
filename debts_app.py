from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from req_manager.db import (
    DEBT_STATUS_OPTIONS,
    ROLE_ADMIN,
    authenticate_user,
    create_community_debt,
    ensure_schema,
    list_community_debts,
    normalize_debt_status,
    update_community_debt,
)
from req_manager.ui import apply_dashboard_css

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


def require_admin_login() -> bool:
    if st.session_state.get("debts_admin_authenticated", False):
        return True

    st.title("Acceso Gestión de Deudas")
    st.caption("Acceso restringido a usuarios con rol Admin.")

    with st.form("debts_admin_login_form", clear_on_submit=False):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar", use_container_width=True)

    if submitted:
        if authenticate_user(username, password, role=ROLE_ADMIN):
            st.session_state["debts_admin_authenticated"] = True
            st.session_state["debts_actor"] = username.strip() or "Admin"
            st.success("Autenticación correcta.")
            st.rerun()
        else:
            st.error("Usuario o contraseña inválidos o sin permisos.")

    return False


def debts_table(rows: list[dict]) -> pd.DataFrame:
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
            for r in rows
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
            height=100,
        )
        submitted = st.form_submit_button("Registrar deuda", use_container_width=True)
        if submitted:
            debt_id = create_community_debt(
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

    options = [
        f"{r['id']} | Dpto {r['apartment_number']} | {format_amount(r['debt_amount'])} | {r['status']}"
        for r in rows
    ]
    selected = st.selectbox("Seleccionar registro", options)
    selected_id = int(selected.split("|")[0].strip())
    selected_row = next((r for r in rows if int(r["id"]) == selected_id), None)
    if not selected_row:
        st.markdown("</div>", unsafe_allow_html=True)
        return

    current_status = normalize_debt_status(selected_row.get("status"))
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
            height=100,
        )
        submitted = st.form_submit_button("Guardar cambios", use_container_width=True)
        if submitted:
            updated = update_community_debt(
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
    ensure_schema()
    if not require_admin_login():
        return

    st.title("Gestión de Deudas de Gastos Comunes")
    st.caption(
        f"Registro operativo de deuda por dpto | {datetime.now(TZ).strftime('%d-%m-%Y %H:%M')}"
    )

    rows = list_community_debts()
    st.subheader("Deudas registradas")
    if rows:
        st.dataframe(debts_table(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No hay deudas registradas.")

    c1, c2 = st.columns(2)
    with c1:
        create_debt_form()
    with c2:
        edit_debt_form(rows)


if __name__ == "__main__":
    main()
