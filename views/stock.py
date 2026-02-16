"""
views/stock.py - Movimientos de stock y alertas.
"""

import streamlit as st
from database import SessionLocal, MovimientoStock
from controllers import (
    listar_productos, registrar_movimiento_stock, productos_bajo_stock,
)
from auth import require_admin


def render():
    st.header("Stock")

    tab_movimiento, tab_alertas, tab_historial = st.tabs([
        "Registrar Movimiento", "Alertas Stock Bajo", "Historial"
    ])

    with tab_movimiento:
        _render_movimiento()

    with tab_alertas:
        _render_alertas()

    with tab_historial:
        _render_historial()


def _render_movimiento():
    if not require_admin():
        st.warning("Solo administradores pueden registrar movimientos de stock.")
        return

    productos = listar_productos()
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
                st.success("Movimiento registrado correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")


def _render_alertas():
    productos = productos_bajo_stock()
    if not productos:
        st.success("Todos los productos tienen stock suficiente.")
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
