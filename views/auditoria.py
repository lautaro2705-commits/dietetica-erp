"""
views/auditoria.py - Visor de logs inmutables de auditoría.
"""

import json
import streamlit as st
from controllers import listar_auditoria
from auth import require_admin


def render():
    st.header("Auditoría")

    if not require_admin():
        st.warning("Solo administradores pueden ver los registros de auditoría.")
        return

    st.caption("Registro inmutable de todas las operaciones del sistema.")

    limit = st.selectbox("Mostrar últimos", [50, 100, 200, 500], index=1)
    logs = listar_auditoria(limit=limit)

    if not logs:
        st.info("No hay registros de auditoría.")
        return

    for log in logs:
        icon = _icon_for_action(log.accion)
        with st.expander(
            f"{icon} {log.accion} en **{log.tabla_afectada}** | "
            f"{log.fecha.strftime('%d/%m/%Y %H:%M:%S')} | "
            f"Usuario: {log.usuario.nombre if log.usuario else '—'}"
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Valor Anterior:**")
                try:
                    anterior = json.loads(log.valor_anterior)
                    if anterior:
                        st.json(anterior)
                    else:
                        st.caption("(vacío)")
                except json.JSONDecodeError:
                    st.code(log.valor_anterior)
            with col2:
                st.markdown("**Valor Nuevo:**")
                try:
                    nuevo = json.loads(log.valor_nuevo)
                    if nuevo:
                        st.json(nuevo)
                    else:
                        st.caption("(vacío)")
                except json.JSONDecodeError:
                    st.code(log.valor_nuevo)

            st.caption(f"Registro ID: {log.registro_id} | Log ID: {log.id}")


def _icon_for_action(accion: str) -> str:
    icons = {
        "CREAR": "+",
        "MODIFICAR": "~",
        "DESACTIVAR": "-",
        "VENTA": "$",
        "AUMENTO_MASIVO": "%",
        "MOVIMIENTO_STOCK": "#",
    }
    return icons.get(accion, "?")
