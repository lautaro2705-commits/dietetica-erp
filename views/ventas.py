"""
views/ventas.py - Registro de ventas e historial.
"""

import streamlit as st
from datetime import date, timedelta

from controllers import (
    listar_productos, listar_fracciones, calcular_precio_fraccion,
    procesar_venta, listar_ventas, obtener_detalle_venta,
)


def render():
    st.header("Ventas")

    tab_nueva, tab_historial = st.tabs(["Nueva Venta", "Historial"])

    with tab_nueva:
        _render_nueva_venta()

    with tab_historial:
        _render_historial()


def _render_nueva_venta():
    # Inicializar carrito en session_state
    if "carrito" not in st.session_state:
        st.session_state["carrito"] = []

    productos = listar_productos()
    if not productos:
        st.info("No hay productos cargados. Cargá productos primero.")
        return

    tipo_venta = st.radio("Tipo de venta", ["minorista", "mayorista"], horizontal=True)

    st.subheader("Agregar al carrito")
    prod_options = {f"{p.codigo} — {p.nombre}": p for p in productos}
    prod_sel = st.selectbox("Producto", list(prod_options.keys()))
    prod = prod_options[prod_sel] if prod_sel else None

    if prod:
        fracciones = listar_fracciones(prod.id)
        frac_options = {"Bulto completo": None}
        for f in fracciones:
            precio = calcular_precio_fraccion(prod, f)
            frac_options[f"{f.nombre} (${precio:,.2f})"] = f

        frac_sel = st.selectbox("Presentación", list(frac_options.keys()))
        frac = frac_options[frac_sel]

        cantidad = st.number_input("Cantidad", min_value=1, value=1, step=1)

        if frac:
            precio_unit = calcular_precio_fraccion(prod, frac)
        elif tipo_venta == "mayorista":
            precio_unit = prod.precio_venta_mayorista
        else:
            precio_unit = prod.precio_costo * (1 + prod.margen_minorista_pct / 100)

        precio_unit = round(precio_unit, 2)
        subtotal = round(precio_unit * cantidad, 2)

        st.info(f"Precio unitario: **${precio_unit:,.2f}** | Subtotal: **${subtotal:,.2f}**")

        if st.button("Agregar al carrito", type="primary"):
            st.session_state["carrito"].append({
                "producto_id": prod.id,
                "producto_nombre": prod.nombre,
                "fraccion_id": frac.id if frac else None,
                "fraccion_nombre": frac.nombre if frac else "Bulto",
                "cantidad": cantidad,
                "precio_unitario": precio_unit,
                "subtotal": subtotal,
            })
            st.success("Agregado al carrito.")
            st.rerun()

    # Mostrar carrito
    st.divider()
    st.subheader("Carrito")

    carrito = st.session_state["carrito"]
    if not carrito:
        st.caption("El carrito está vacío.")
    else:
        total = 0.0
        for i, item in enumerate(carrito):
            col1, col2, col3 = st.columns([3, 1, 1])
            col1.write(f"**{item['producto_nombre']}** ({item['fraccion_nombre']}) x{item['cantidad']}")
            col2.write(f"${item['subtotal']:,.2f}")
            if col3.button("X", key=f"rm_{i}"):
                carrito.pop(i)
                st.rerun()
            total += item["subtotal"]

        st.markdown(f"### Total: ${total:,.2f}")

        col_obs, col_btn = st.columns([3, 1])
        with col_obs:
            observaciones = st.text_input("Observaciones", key="obs_venta")
        with col_btn:
            st.write("")  # spacer
            if st.button("Confirmar Venta", type="primary", use_container_width=True):
                try:
                    items_para_venta = [
                        {
                            "producto_id": item["producto_id"],
                            "fraccion_id": item["fraccion_id"],
                            "cantidad": item["cantidad"],
                        }
                        for item in carrito
                    ]
                    venta = procesar_venta(
                        st.session_state["user_id"],
                        tipo_venta,
                        items_para_venta,
                        observaciones,
                    )
                    st.session_state["carrito"] = []
                    st.success(f"Venta #{venta.id} registrada. Total: ${venta.total:,.2f}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al procesar venta: {e}")

        if st.button("Vaciar carrito"):
            st.session_state["carrito"] = []
            st.rerun()


def _render_historial():
    col1, col2 = st.columns(2)
    with col1:
        fecha_desde = st.date_input("Desde", value=date.today() - timedelta(days=30))
    with col2:
        fecha_hasta = st.date_input("Hasta", value=date.today())

    ventas = listar_ventas(fecha_desde, fecha_hasta)

    if not ventas:
        st.info("No hay ventas en el período seleccionado.")
        return

    for v in ventas:
        with st.expander(
            f"Venta #{v.id} | {v.fecha.strftime('%d/%m/%Y %H:%M')} | "
            f"**${v.total:,.2f}** | {v.tipo.upper()}"
        ):
            detalles = obtener_detalle_venta(v.id)
            data = []
            for d in detalles:
                data.append({
                    "Producto": d.producto.nombre if d.producto else "—",
                    "Fracción": d.fraccion.nombre if d.fraccion else "Bulto",
                    "Cantidad": d.cantidad,
                    "Precio Unit.": f"${d.precio_unitario:,.2f}",
                    "Subtotal": f"${d.subtotal:,.2f}",
                })
            st.dataframe(data, use_container_width=True, hide_index=True)
            if v.observaciones:
                st.caption(f"Obs: {v.observaciones}")
