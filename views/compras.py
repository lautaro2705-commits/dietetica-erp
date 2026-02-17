"""
views/compras.py - Registro de compras a proveedores e historial.
"""

import streamlit as st
from datetime import date, timedelta

from controllers import (
    listar_productos, listar_proveedores,
    procesar_compra, listar_compras, obtener_detalle_compra,
)


def render():
    st.header("Compras")

    tab_nueva, tab_historial = st.tabs(["Nueva Compra", "Historial"])

    with tab_nueva:
        _render_nueva_compra()

    with tab_historial:
        _render_historial()


def _render_nueva_compra():
    # Inicializar carrito de compra en session_state
    if "carrito_compra" not in st.session_state:
        st.session_state["carrito_compra"] = []

    productos = listar_productos()
    if not productos:
        st.info("No hay productos cargados. Cargá productos primero.")
        return

    proveedores = listar_proveedores()

    # Datos de cabecera
    col_prov, col_fact = st.columns(2)
    with col_prov:
        prov_options = {"Sin proveedor": None}
        for p in proveedores:
            prov_options[p.nombre] = p.id
        prov_sel = st.selectbox("Proveedor", list(prov_options.keys()))
    with col_fact:
        numero_factura = st.text_input("Nº Factura / Remito", placeholder="Opcional")

    st.divider()
    st.subheader("Agregar productos")

    prod_options = {f"{p.codigo} — {p.nombre} (Stock: {p.stock_actual})": p for p in productos}
    prod_sel = st.selectbox("Producto", list(prod_options.keys()), key="compra_prod_sel")
    prod = prod_options[prod_sel] if prod_sel else None

    if prod:
        col1, col2, col3 = st.columns(3)
        with col1:
            cantidad = st.number_input(
                "Cantidad (bultos)", min_value=0.01, value=1.0, step=1.0,
                key="compra_cant",
            )
        with col2:
            precio_unitario = st.number_input(
                "Precio unitario (costo por bulto) $",
                min_value=0.0, value=float(prod.precio_costo), step=100.0,
                key="compra_precio",
            )
        with col3:
            actualizar_costo = st.checkbox(
                "Actualizar precio de costo",
                value=True,
                key="compra_act_costo",
                help="Si se activa, el precio de costo del producto se actualiza al precio de esta compra",
            )

        subtotal = round(precio_unitario * cantidad, 2)
        st.info(f"Subtotal: **${subtotal:,.2f}**")

        if st.button("Agregar a la compra", type="primary"):
            st.session_state["carrito_compra"].append({
                "producto_id": prod.id,
                "producto_nombre": prod.nombre,
                "producto_codigo": prod.codigo,
                "cantidad": cantidad,
                "precio_unitario": precio_unitario,
                "subtotal": subtotal,
                "actualizar_costo": actualizar_costo,
            })
            st.success("Producto agregado.")
            st.rerun()

    # Mostrar carrito de compra
    st.divider()
    st.subheader("Detalle de la compra")

    carrito = st.session_state["carrito_compra"]
    if not carrito:
        st.caption("No hay productos agregados a esta compra.")
    else:
        total = 0.0
        for i, item in enumerate(carrito):
            col1, col2, col3, col4 = st.columns([3, 1, 1, 0.5])
            col1.write(
                f"**{item['producto_codigo']}** — {item['producto_nombre']} "
                f"x{item['cantidad']} bultos"
            )
            col2.write(f"${item['precio_unitario']:,.2f} c/u")
            col3.write(f"${item['subtotal']:,.2f}")
            if col4.button("X", key=f"rm_compra_{i}"):
                carrito.pop(i)
                st.rerun()
            total += item["subtotal"]

            if item["actualizar_costo"]:
                col1.caption("↳ Actualiza costo")

        st.markdown(f"### Total compra: ${total:,.2f}")

        observaciones = st.text_input("Observaciones", key="obs_compra")

        col_confirm, col_vaciar = st.columns([3, 1])
        with col_confirm:
            if st.button("Confirmar Compra", type="primary", use_container_width=True):
                try:
                    items_para_compra = [
                        {
                            "producto_id": item["producto_id"],
                            "cantidad": item["cantidad"],
                            "precio_unitario": item["precio_unitario"],
                            "actualizar_costo": item["actualizar_costo"],
                        }
                        for item in carrito
                    ]
                    compra = procesar_compra(
                        st.session_state["user_id"],
                        prov_options[prov_sel],
                        items_para_compra,
                        numero_factura,
                        observaciones,
                    )
                    st.session_state["carrito_compra"] = []
                    st.success(
                        f"Compra #{compra.id} registrada. "
                        f"Total: ${compra.total:,.2f} — "
                        f"Stock actualizado para {len(items_para_compra)} producto(s)."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al procesar compra: {e}")
        with col_vaciar:
            if st.button("Vaciar", use_container_width=True):
                st.session_state["carrito_compra"] = []
                st.rerun()


def _render_historial():
    col1, col2 = st.columns(2)
    with col1:
        fecha_desde = st.date_input(
            "Desde", value=date.today() - timedelta(days=30), key="compra_desde"
        )
    with col2:
        fecha_hasta = st.date_input("Hasta", value=date.today(), key="compra_hasta")

    compras = listar_compras(fecha_desde, fecha_hasta)

    if not compras:
        st.info("No hay compras en el período seleccionado.")
        return

    for c in compras:
        prov_nombre = c.proveedor.nombre if c.proveedor else "Sin proveedor"
        factura_info = f" | Fact: {c.numero_factura}" if c.numero_factura else ""
        with st.expander(
            f"Compra #{c.id} | {c.fecha.strftime('%d/%m/%Y %H:%M')} | "
            f"**${c.total:,.2f}** | {prov_nombre}{factura_info}"
        ):
            detalles = obtener_detalle_compra(c.id)
            data = []
            for d in detalles:
                data.append({
                    "Producto": d.producto.nombre if d.producto else "—",
                    "Cantidad": d.cantidad,
                    "Precio Unit.": f"${d.precio_unitario:,.2f}",
                    "Subtotal": f"${d.subtotal:,.2f}",
                    "Actualizó Costo": "Sí" if d.actualizar_costo else "No",
                })
            st.dataframe(data, use_container_width=True, hide_index=True)
            if c.observaciones:
                st.caption(f"Obs: {c.observaciones}")
            st.caption(f"Registrada por: {c.usuario.nombre if c.usuario else '—'}")
