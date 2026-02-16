"""
views/admin.py - Panel de administración: usuarios y backup.
"""

import os
import streamlit as st
from controllers import crear_usuario, listar_usuarios, desactivar_usuario
from auth import require_admin
from database import DB_PATH


def render():
    st.header("Administración")

    if not require_admin():
        st.warning("Acceso restringido a administradores.")
        return

    tab_usuarios, tab_backup = st.tabs(["Usuarios", "Backup"])

    with tab_usuarios:
        _render_usuarios()

    with tab_backup:
        _render_backup()


def _render_usuarios():
    usuarios = listar_usuarios()

    if usuarios:
        data = []
        for u in usuarios:
            data.append({
                "ID": u.id,
                "Usuario": u.username,
                "Nombre": u.nombre,
                "Rol": u.rol.upper(),
                "Estado": "Activo" if u.activo else "Inactivo",
            })
        st.dataframe(data, use_container_width=True, hide_index=True)

        # Toggle activo/inactivo
        st.subheader("Activar / Desactivar Usuario")
        toggle_options = {f"{u.username} — {u.nombre}": u.id for u in usuarios if u.username != "admin"}
        if toggle_options:
            user_sel = st.selectbox("Seleccionar usuario", list(toggle_options.keys()))
            if st.button("Cambiar estado"):
                try:
                    desactivar_usuario(st.session_state["user_id"], toggle_options[user_sel])
                    st.success("Estado actualizado.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    st.divider()
    st.subheader("Crear Nuevo Usuario")

    with st.form("nuevo_usuario"):
        col1, col2 = st.columns(2)
        with col1:
            username = st.text_input("Nombre de usuario *")
            nombre = st.text_input("Nombre completo *")
        with col2:
            password = st.text_input("Contraseña *", type="password")
            rol = st.selectbox("Rol", ["vendedor", "admin"])

        if st.form_submit_button("Crear Usuario", use_container_width=True):
            if not username or not password or not nombre:
                st.error("Todos los campos marcados con * son obligatorios.")
            else:
                try:
                    crear_usuario(
                        st.session_state["user_id"],
                        username, password, nombre, rol,
                    )
                    st.success(f"Usuario '{username}' creado exitosamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


def _render_backup():
    st.subheader("Exportar Backup de Base de Datos")
    st.markdown(
        "Descargá una copia completa de la base de datos SQLite. "
        "Este archivo contiene **todos** los datos del sistema."
    )

    if os.path.exists(DB_PATH):
        file_size = os.path.getsize(DB_PATH)
        st.caption(f"Archivo: `dietetica.db` | Tamaño: {file_size / 1024:.1f} KB")

        with open(DB_PATH, "rb") as f:
            st.download_button(
                label="Descargar Backup (.db)",
                data=f,
                file_name="dietetica_backup.db",
                mime="application/octet-stream",
                use_container_width=True,
                type="primary",
            )
    else:
        st.error("No se encontró el archivo de base de datos.")
