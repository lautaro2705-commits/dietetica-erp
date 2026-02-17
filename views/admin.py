"""
views/admin.py - Panel de administración: usuarios, backup/restore y reset de contraseñas.
"""
from __future__ import annotations

import json
from datetime import datetime
import streamlit as st
from controllers import (
    crear_usuario, listar_usuarios, desactivar_usuario,
    generar_backup_completo, restaurar_backup,
    resetear_password,
)
from auth import require_admin


def render():
    st.header("Administración")

    if not require_admin():
        st.warning("Acceso restringido a administradores.")
        return

    tab_usuarios, tab_backup = st.tabs(["Usuarios", "Backup y Restauración"])

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

        # Resetear contraseña
        st.divider()
        st.subheader("Resetear Contraseña")
        reset_options = {f"{u.username} — {u.nombre}": u.id for u in usuarios if u.username != "admin"}
        if reset_options:
            reset_sel = st.selectbox(
                "Seleccionar usuario para resetear",
                list(reset_options.keys()),
                key="reset_user_sel",
            )
            if st.button("🔑 Resetear Contraseña", type="secondary"):
                try:
                    temp_pw = resetear_password(
                        st.session_state["user_id"],
                        reset_options[reset_sel],
                    )
                    st.success(
                        f"Contraseña reseteada. **Contraseña temporal:** `{temp_pw}`\n\n"
                        f"⚠️ Anotala, se muestra solo esta vez."
                    )
                except Exception as e:
                    st.error(f"Error: {e}")

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
    col_export, col_import = st.columns(2)

    with col_export:
        st.subheader("📤 Exportar Backup")
        st.markdown(
            "Descargá una copia completa de todos los datos del sistema "
            "en formato **JSON** con metadata."
        )

        if st.button("Generar Backup", type="primary", use_container_width=True):
            try:
                backup_data = generar_backup_completo()
                json_str = json.dumps(
                    backup_data, ensure_ascii=False, indent=2, default=str
                )
                fecha_str = datetime.now().strftime("%Y-%m-%d")
                filename = f"backup_aqui_y_ahora_{fecha_str}.json"

                # Resumen
                meta = backup_data.get("_metadata", {})
                tablas_info = meta.get("tablas", {})
                total_regs = sum(tablas_info.values())
                st.success(
                    f"Backup generado: **{total_regs} registros** "
                    f"en **{len(tablas_info)} tablas**."
                )

                st.download_button(
                    label=f"⬇️ Descargar {filename}",
                    data=json_str,
                    file_name=filename,
                    mime="application/json",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Error generando backup: {e}")

    with col_import:
        st.subheader("📥 Restaurar Backup")
        st.markdown(
            "Subí un archivo JSON de backup para restaurar datos. "
            "**Modo merge:** solo agrega registros que no existen."
        )

        archivo = st.file_uploader(
            "Seleccionar archivo de backup",
            type=["json"],
            key="restore_file",
        )

        if archivo:
            try:
                contenido = json.loads(archivo.read().decode("utf-8"))
            except Exception as e:
                st.error(f"Error leyendo archivo: {e}")
                return

            # Preview
            meta = contenido.get("_metadata", {})
            datos = contenido.get("datos", contenido)

            if meta:
                st.caption(
                    f"Backup del: {meta.get('fecha', '?')} | "
                    f"Versión: {meta.get('version', '?')}"
                )

            st.markdown("**Registros por tabla:**")
            preview_data = []
            for table, regs in datos.items():
                if table.startswith("_"):
                    continue
                if isinstance(regs, list):
                    preview_data.append({
                        "Tabla": table,
                        "Registros": len(regs),
                    })
            if preview_data:
                st.dataframe(preview_data, use_container_width=True, hide_index=True)

            st.warning(
                "⚠️ La restauración **solo agrega** registros que no existen "
                "(por ID). No sobrescribe datos existentes."
            )

            if st.button("Restaurar Backup", type="primary", use_container_width=True):
                with st.spinner("Restaurando..."):
                    try:
                        resultado = restaurar_backup(
                            st.session_state["user_id"], contenido
                        )
                        total = sum(resultado.values())
                        if total > 0:
                            st.success(f"Restauración completada: {total} registros importados.")
                            with st.expander("Detalle por tabla"):
                                for tabla, count in resultado.items():
                                    if count > 0:
                                        st.caption(f"✅ {tabla}: {count} registros")
                        else:
                            st.info("No se encontraron registros nuevos para importar.")
                    except Exception as e:
                        st.error(f"Error restaurando: {e}")
