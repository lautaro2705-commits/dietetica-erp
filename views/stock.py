"""
views/stock.py - Movimientos de stock, alertas de stock bajo y vencimiento.
"""

import streamlit as st
from datetime import date
from database import SessionLocal, MovimientoStock
from controllers import (
    listar_productos, registrar_movimiento_stock, productos_bajo_stock,
    productos_proximos_a_vencer,
)
from auth import require_admin
from utils.cache import cached_query, invalidar_cache_productos, TTL_CORTO, TTL_MEDIO


def render():
    st.header("Stock")

    tab_movimiento, tab_alertas, tab_vencimiento, tab_historial = st.tabs([
        "Registrar Movimiento", "Alertas Stock Bajo",
        "🗓️ Vencimientos", "Historial",
    ])

    with tab_movimiento:
        _render_movimiento()

    with tab_alertas:
        _render_alertas()

    with tab_vencimiento:
        _render_vencimientos()

    with tab_historial:
        _render_historial()


def _render_movimiento():
    if not require_admin():
        st.warning("Solo administradores pueden registrar movimientos de stock.")
        return

    productos = cached_query("productos_activos", listar_productos, TTL_MEDIO)
    if not productos:
        st.info("No hay productos cargados.")
        return

    with st.form("mov_stock"):
        prod_options = {f"{p.codigo} — {p.nombre} (Stock: {p.stock_actual})": p.id for p in productos}
        prod_sel = st.selectbox("Producto", list(prod_options.keys()))

        tipo = st.selectbox("Tipo de movimiento", ["entrada", "salida", "ajuste"])

        cantidad = st.number_input(
            "Cantidad (bultos)" if tipo != "ajuste" else "Nuevo stock (bultos)",
            min_value=0.0, step=1.0,
        )
        referencia = st.text_input("Referencia / Motivo", placeholder="ej: Compra proveedor X")

        if st.form_submit_button("Registrar", use_container_width=True):
            try:
                registrar_movimiento_stock(
                    st.session_state["user_id"],
                    prod_options[prod_sel],
                    tipo,
                    cantidad,
                    referencia,
                )
                invalidar_cache_productos()
                st.success("Movimiento registrado correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")


def _render_alertas():
    productos = cached_query("stock_bajo", productos_bajo_stock, TTL_CORTO)
    if not productos:
        st.success("✅ Todos los productos tienen stock suficiente.")
        return

    st.warning(f"{len(productos)} producto(s) con stock bajo o agotado:")

    data = []
    for p in productos:
        data.append({
            "Código": p.codigo,
            "Producto": p.nombre,
            "Stock Actual": p.stock_actual,
            "Stock Mínimo": p.stock_minimo,
            "Faltante": max(0, p.stock_minimo - p.stock_actual),
        })
    st.dataframe(data, use_container_width=True, hide_index=True)


def _render_vencimientos():
    dias = st.slider(
        "Mostrar productos que vencen en los próximos N días",
        min_value=7, max_value=180, value=60, step=7,
    )

    productos = cached_query(f"stock_vencimiento_{dias}", productos_proximos_a_vencer, TTL_MEDIO, dias)

    if not productos:
        st.success(f"✅ No hay productos próximos a vencer en los próximos {dias} días.")
        return

    # Separar vencidos de próximos a vencer
    hoy = date.today()
    vencidos = [p for p in productos if p.fecha_vencimiento < hoy]
    por_vencer = [p for p in productos if p.fecha_vencimiento >= hoy]

    if vencidos:
        st.error(f"🔴 {len(vencidos)} producto(s) VENCIDO(s):")
        data_vencidos = []
        for p in vencidos:
            dias_pasados = (hoy - p.fecha_vencimiento).days
            data_vencidos.append({
                "Código": p.codigo,
                "Producto": p.nombre,
                "Vencimiento": p.fecha_vencimiento.strftime("%d/%m/%Y"),
                "Días vencido": dias_pasados,
                "Stock": f"{p.stock_actual} {p.unidad_medida}",
            })
        st.dataframe(data_vencidos, use_container_width=True, hide_index=True)

    if por_vencer:
        st.warning(f"🟡 {len(por_vencer)} producto(s) próximo(s) a vencer:")
        data_por_vencer = []
        for p in por_vencer:
            dias_restantes = (p.fecha_vencimiento - hoy).days
            data_por_vencer.append({
                "Código": p.codigo,
                "Producto": p.nombre,
                "Vencimiento": p.fecha_vencimiento.strftime("%d/%m/%Y"),
                "Días restantes": dias_restantes,
                "Stock": f"{p.stock_actual} {p.unidad_medida}",
                "Proveedor": p.proveedor.nombre if p.proveedor else "—",
            })
        st.dataframe(data_por_vencer, use_container_width=True, hide_index=True)

    # Resumen
    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("Productos Vencidos", len(vencidos))
    col2.metric("Próximos a Vencer", len(por_vencer))


def _render_historial():
    session = SessionLocal()
    try:
        movimientos = (
            session.query(MovimientoStock)
            .order_by(MovimientoStock.fecha.desc())
            .limit(200)
            .all()
        )
        if not movimientos:
            st.info("No hay movimientos registrados.")
            return

        data = []
        for m in movimientos:
            data.append({
                "Fecha": m.fecha.strftime("%d/%m/%Y %H:%M"),
                "Producto": m.producto.nombre if m.producto else "—",
                "Tipo": m.tipo.upper(),
                "Cantidad": m.cantidad,
                "Referencia": m.referencia,
                "Usuario": m.usuario.nombre if m.usuario else "—",
            })
        st.dataframe(data, use_container_width=True, hide_index=True)
    finally:
        session.close()
