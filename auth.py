"""
auth.py - Autenticación y gestión de sesión Streamlit.
"""
from __future__ import annotations

import streamlit as st
from database import SessionLocal, Usuario, verify_password


def login(username: str, password: str) -> Usuario | None:
    """Valida credenciales y retorna el usuario o None."""
    session = SessionLocal()
    try:
        user = session.query(Usuario).filter_by(
            username=username, activo=True
        ).first()
        if user and verify_password(password, user.password_hash, user.password_salt):
            return user
        return None
    finally:
        session.close()


def show_login_form():
    """Muestra el formulario de login y gestiona la sesión."""
    st.markdown(
        """
        <div style="text-align:center; padding: 2rem 0 1rem 0;">
            <h1 style="margin-bottom:0.2rem;">&#127793; Aquí y Ahora</h1>
            <p style="color:#888; font-size:1.1rem;">Sistema de Gestión Mayorista</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Ingresar", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.error("Completá usuario y contraseña.")
                    return

                user = login(username, password)
                if user:
                    st.session_state["user_id"] = user.id
                    st.session_state["username"] = user.username
                    st.session_state["nombre"] = user.nombre
                    st.session_state["rol"] = user.rol
                    st.session_state["logged_in"] = True
                    st.rerun()
                else:
                    st.error("Credenciales inválidas.")


def require_login():
    """Retorna True si el usuario está logueado, sino muestra login."""
    if not st.session_state.get("logged_in"):
        show_login_form()
        return False
    return True


def require_admin():
    """Retorna True si el usuario es admin."""
    return st.session_state.get("rol") == "admin"


def logout():
    """Limpia la sesión."""
    for key in ["user_id", "username", "nombre", "rol", "logged_in"]:
        st.session_state.pop(key, None)
    st.rerun()
