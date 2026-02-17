"""
views/gastos.py - Registro y listado de gastos operativos.
"""

import streamlit as st
from datetime import date, timedelta
from controllers import registrar_gasto, listar_gastos
from utils.cache import cached_query, invalidar_cache_gastos, TTL_CORTO


CATEGORIAS_GASTO = [
    "General", "Alquiler", "Servicios", "Sueldos", "Transporte",
    "Impuestos", "Mantenimiento", "Insumos", "Marketing", "Otros",
]


def render():
    st.header("Gastos Operativos")

    tab_nuevo, tab_listado = st.tabs(["Registrar Gasto", "Historial"])

    with tab_nuevo:
        _render_nuevo_gasto()

    with tab_listado:
        _render_historial()


def _render_nuevo_gasto():
    with st.form("nuevo_gasto"):
        descripcion = st.text_input("Descripción *", placeholder="ej: Factura de luz")
        col1, col2 = st.columns(2)
        with col1:
            monto = st.number_input("Monto $", min_value=0.01, step=100.0)
        with col2:
            categoria = st.selectbox("Categoría", CATEGORIAS_GASTO)

        if st.form_submit_button("Registrar Gasto", use_container_width=True):
            if not descripcion:
                st.error("La descripción es obligatoria.")
            else:
                try:
                    gasto = registrar_gasto(
                        st.session_state["user_id"],
                        descripcion, monto, categoria,
                    )
                    invalidar_cache_gastos()
                    st.success(f"Gasto registrado: ${monto:,.2f} — {descripcion}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


def _render_historial():
    col1, col2 = st.columns(2)
    with col1:
        fecha_desde = st.date_input("Desde", value=date.today() - timedelta(days=30), key="gasto_desde")
    with col2:
        fecha_hasta = st.date_input("Hasta", value=date.today(), key="gasto_hasta")

    gastos = cached_query(
        f"gastos_{fecha_desde}_{fecha_hasta}",
        listar_gastos, TTL_CORTO, fecha_desde, fecha_hasta,
    )

    if not gastos:
        st.info("No hay gastos en el período seleccionado.")
        return

    total = sum(g.monto for g in gastos)
    st.metric("Total Gastos", f"${total:,.2f}")

    data = []
    for g in gastos:
        data.append({
            "Fecha": g.fecha.strftime("%d/%m/%Y"),
            "Descripción": g.descripcion,
            "Categoría": g.categoria_gasto,
            "Monto": f"${g.monto:,.2f}",
            "Registrado por": g.usuario.nombre if g.usuario else "—",
        })
    st.dataframe(data, use_container_width=True, hide_index=True)
