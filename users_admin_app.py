from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from req_manager.db import authenticate_user, create_user, ensure_schema, list_users, update_user

TZ = ZoneInfo("America/Santiago")
load_dotenv()

st.set_page_config(
    page_title="Administración de Usuarios",
    page_icon="👥",
    layout="wide",
)

st.markdown(
    """
<style>
.main {
    background: radial-gradient(circle at 15% 12%, #f2f7ff, #fbfdff 40%, #ffffff 82%);
}
.section-box {
    border-radius: 12px;
    border: 1px solid #dce8f5;
    padding: 14px;
    background: #ffffff;
    box-shadow: 0 8px 20px rgba(31, 71, 112, 0.08);
}
</style>
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


def require_admin_login() -> bool:
    if st.session_state.get("users_admin_authenticated", False):
        return True

    st.title("Acceso Administración de Usuarios")
    st.caption("Acceso restringido a usuarios con rol administrador.")

    with st.form("users_admin_login", clear_on_submit=False):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar", use_container_width=True)

    if submitted:
        if authenticate_user(username, password, role="admin"):
            st.session_state["users_admin_authenticated"] = True
            st.success("Autenticación correcta.")
            st.rerun()
        else:
            st.error("Usuario o contraseña inválidos o sin permisos de administrador.")

    return False


def users_table(users: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Usuario": u["username"],
                "Rol": u["role"],
                "Activo": "Sí" if bool(u["active"]) else "No",
                "Creado": format_dt(u.get("created_at")),
            }
            for u in users
        ]
    )


def create_user_form() -> None:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Alta de usuario")

    with st.form("create_user_form", clear_on_submit=True):
        new_user = st.text_input("Nuevo usuario")
        new_password = st.text_input("Contraseña", type="password")
        new_role = st.selectbox("Rol", ["admin", "report"])
        new_active = st.checkbox("Usuario activo", value=True)
        submitted = st.form_submit_button("Crear usuario", use_container_width=True)

        if submitted:
            created = create_user(new_user, new_password, new_role, new_active)
            if created:
                st.success("Usuario creado correctamente.")
                st.rerun()
            else:
                st.error(
                    "No se pudo crear el usuario. Verifica datos o que el usuario no exista."
                )

    st.markdown("</div>", unsafe_allow_html=True)


def edit_user_form(users: list[dict]) -> None:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Edición de usuario")

    usernames = [u["username"] for u in users]
    if not usernames:
        st.info("No hay usuarios para editar.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    selected_username = st.selectbox("Seleccionar usuario", usernames)
    selected = next((u for u in users if u["username"] == selected_username), None)
    if not selected:
        st.markdown("</div>", unsafe_allow_html=True)
        return

    with st.form("edit_user_form", clear_on_submit=False):
        role = st.selectbox(
            "Rol",
            ["admin", "report"],
            index=["admin", "report"].index(selected["role"])
            if selected["role"] in {"admin", "report"}
            else 1,
        )
        active = st.checkbox("Usuario activo", value=bool(selected["active"]))
        new_password = st.text_input(
            "Nueva contraseña (opcional)",
            type="password",
            help="Si lo dejas vacío, se mantiene la contraseña actual.",
        )

        submitted = st.form_submit_button("Guardar cambios", use_container_width=True)
        if submitted:
            updated = update_user(selected_username, role, active, new_password)
            if updated:
                st.success("Usuario actualizado correctamente.")
                st.rerun()
            else:
                st.error("No se pudo actualizar el usuario.")

    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    ensure_schema()

    if not require_admin_login():
        return

    st.title("Administración de Usuarios")
    st.caption(
        f"Gestión de accesos | {datetime.now(TZ).strftime('%d-%m-%Y %H:%M')}"
    )

    users = list_users()
    st.subheader("Usuarios registrados")
    if users:
        st.dataframe(users_table(users), use_container_width=True, hide_index=True)
    else:
        st.info("No hay usuarios registrados.")

    c1, c2 = st.columns(2)
    with c1:
        create_user_form()
    with c2:
        edit_user_form(users)


if __name__ == "__main__":
    main()
