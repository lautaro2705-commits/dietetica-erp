"""
views/clientes.py - Gestión de clientes, cuenta corriente y precios especiales.
"""

import streamlit as st
from controllers import (
    crear_cliente, listar_clientes, obtener_cliente,
    registrar_pago_cliente, listar_movimientos_cuenta,
    listar_productos, listar_precios_especiales,
    asignar_precio_especial, eliminar_precio_especial,
    actualizar_descuento_cliente,
)
from auth import require_admin
from utils.cache import (
    cached_query, invalidar_cache_clientes, invalidar_cache_productos,
    TTL_MEDIO, TTL_LARGO,
)


def render():
    st.header("Clientes")

    tab_listado, tab_nuevo, tab_cuenta, tab_precios = st.tabs([
        "Listado", "Nuevo Cliente", "Cuenta Corriente", "Precios Especiales"
    ])

    with tab_listado:
        _render_listado()

    with tab_nuevo:
        _render_nuevo_cliente()

    with tab_cuenta:
        _render_cuenta_corriente()

    with tab_precios:
        if not require_admin():
            st.warning("Solo administradores pueden gestionar precios especiales.")
        else:
            _render_precios_especiales()


def _render_listado():
    clientes = cached_query("clientes_activos", listar_clientes, TTL_MEDIO)
    if not clientes:
        st.info("No hay clientes cargados.")
        return

    busqueda = st.text_input("Buscar cliente", placeholder="Nombre, CUIT...",
                             key="buscar_cli")
    if busqueda:
        clientes = [c for c in clientes
                    if busqueda.lower() in c.nombre.lower()
                    or busqueda.lower() in (c.cuit or "").lower()]

    data = []
    for c in clientes:
        desc_txt = f"{c.descuento_general_pct:g}%" if getattr(c, 'descuento_general_pct', 0) > 0 else "—"
        data.append({
            "ID": c.id,
            "Nombre": c.nombre,
            "CUIT": c.cuit or "—",
            "Teléfono": c.telefono or "—",
            "Email": c.email or "—",
            "Descuento": desc_txt,
            "Saldo Cta. Cte.": f"${c.saldo_cuenta_corriente:,.2f}",
        })
    st.dataframe(data, use_container_width=True, hide_index=True)

    # Resumen de deudas
    deudores = [c for c in clientes if c.saldo_cuenta_corriente > 0]
    if deudores:
        total_deuda = sum(c.saldo_cuenta_corriente for c in deudores)
        st.warning(
            f"**{len(deudores)} cliente(s)** con saldo pendiente. "
            f"Total por cobrar: **${total_deuda:,.2f}**"
        )


def _render_nuevo_cliente():
    with st.form("nuevo_cliente"):
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Nombre *", placeholder="Juan Pérez")
            cuit = st.text_input("CUIT", placeholder="20-12345678-9")
            telefono = st.text_input("Teléfono", placeholder="351-1234567")
        with col2:
            email = st.text_input("Email", placeholder="cliente@email.com")
            direccion = st.text_area("Dirección", placeholder="Calle 123, Ciudad")

        if st.form_submit_button("Crear Cliente", use_container_width=True):
            if not nombre:
                st.error("El nombre es obligatorio.")
            else:
                try:
                    crear_cliente(
                        st.session_state["user_id"],
                        nombre=nombre, cuit=cuit, telefono=telefono,
                        email=email, direccion=direccion,
                    )
                    invalidar_cache_clientes()
                    st.success(f"Cliente '{nombre}' creado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


def _render_cuenta_corriente():
    clientes = cached_query("clientes_activos", listar_clientes, TTL_MEDIO)
    if not clientes:
        st.info("No hay clientes cargados.")
        return

    cli_options = {f"{c.nombre} (Saldo: ${c.saldo_cuenta_corriente:,.2f})": c.id
                   for c in clientes}
    cli_sel = st.selectbox("Seleccionar cliente", list(cli_options.keys()))
    cliente_id = cli_options[cli_sel]

    cliente = obtener_cliente(cliente_id)
    if not cliente:
        return

    # Info del cliente
    col1, col2, col3 = st.columns(3)
    col1.metric("Saldo Pendiente", f"${cliente.saldo_cuenta_corriente:,.2f}")
    col2.write(f"**CUIT:** {cliente.cuit or '—'}")
    col3.write(f"**Tel:** {cliente.telefono or '—'}")

    # Registrar pago
    st.divider()
    st.subheader("Registrar Pago")

    with st.form("pago_cta_cte"):
        col_m, col_r = st.columns([1, 2])
        with col_m:
            monto = st.number_input(
                "Monto del pago $", min_value=0.01, step=100.0,
                value=min(float(max(cliente.saldo_cuenta_corriente, 0.01)), 10000.0),
            )
        with col_r:
            referencia = st.text_input(
                "Referencia", value="Pago en efectivo",
                placeholder="ej: Transferencia 15/02",
            )
        if st.form_submit_button("Registrar Pago", use_container_width=True):
            try:
                registrar_pago_cliente(
                    st.session_state["user_id"],
                    cliente_id, monto, referencia,
                )
                invalidar_cache_clientes()
                st.success(f"Pago de ${monto:,.2f} registrado.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # Historial de movimientos
    st.divider()
    st.subheader("Historial de Movimientos")

    movimientos = listar_movimientos_cuenta(cliente_id)
    if not movimientos:
        st.caption("Sin movimientos registrados.")
    else:
        data = []
        for m in movimientos:
            data.append({
                "Fecha": m.fecha.strftime("%d/%m/%Y %H:%M"),
                "Tipo": "📤 Cargo" if m.tipo == "cargo" else "📥 Pago",
                "Monto": f"${m.monto:,.2f}",
                "Referencia": m.referencia,
                "Usuario": m.usuario.nombre if m.usuario else "—",
            })
        st.dataframe(data, use_container_width=True, hide_index=True)


def _render_precios_especiales():
    """Tab para gestionar descuento general y precios fijos por producto/cliente."""
    clientes = cached_query("clientes_activos", listar_clientes, TTL_MEDIO)
    if not clientes:
        st.info("No hay clientes cargados.")
        return

    cli_options = {f"{c.nombre}": c.id for c in clientes}
    cli_sel = st.selectbox(
        "Seleccionar cliente", list(cli_options.keys()),
        key="pe_cliente_sel",
    )
    cliente_id = cli_options[cli_sel]
    cliente = obtener_cliente(cliente_id)
    if not cliente:
        return

    # --- Descuento general ---
    st.subheader("Descuento General (%)")
    st.caption(
        "Se aplica como porcentaje de descuento sobre el precio mayorista "
        "en todas las ventas de este cliente (a menos que exista un precio fijo)."
    )
    desc_actual = getattr(cliente, 'descuento_general_pct', 0.0) or 0.0

    with st.form("descuento_form"):
        nuevo_desc = st.number_input(
            "Descuento %", min_value=0.0, max_value=100.0,
            value=float(desc_actual), step=1.0,
        )
        if st.form_submit_button("Guardar Descuento", use_container_width=True):
            try:
                actualizar_descuento_cliente(
                    st.session_state["user_id"], cliente_id, nuevo_desc,
                )
                invalidar_cache_clientes()
                st.success(f"Descuento actualizado a {nuevo_desc:g}%.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # --- Precios fijos por producto ---
    st.divider()
    st.subheader("Precios Fijos por Producto")
    st.caption(
        "Precio fijo para productos específicos. Tiene prioridad sobre el descuento general."
    )

    precios = listar_precios_especiales(cliente_id)
    if precios:
        data = []
        for pe in precios:
            prod_nombre = pe.producto.nombre if pe.producto else "—"
            prod_codigo = pe.producto.codigo if pe.producto else "—"
            data.append({
                "ID": pe.id,
                "Código": prod_codigo,
                "Producto": prod_nombre,
                "Precio Fijo": f"${pe.precio_fijo:,.2f}",
            })
        st.dataframe(data, use_container_width=True, hide_index=True)

        # Eliminar precio especial
        pe_del_options = {
            f"{pe.producto.codigo} — {pe.producto.nombre} (${pe.precio_fijo:,.2f})": pe.id
            for pe in precios if pe.producto
        }
        if pe_del_options:
            pe_del_sel = st.selectbox(
                "Eliminar precio especial",
                list(pe_del_options.keys()),
                key="pe_del_sel",
            )
            if st.button("Eliminar", key="btn_del_pe"):
                try:
                    eliminar_precio_especial(
                        st.session_state["user_id"],
                        pe_del_options[pe_del_sel],
                    )
                    invalidar_cache_clientes()
                    st.success("Precio especial eliminado.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    else:
        st.caption("No hay precios fijos configurados para este cliente.")

    # Agregar nuevo precio especial
    st.divider()
    st.markdown("**Agregar precio fijo:**")

    productos = cached_query("productos_activos", listar_productos, TTL_MEDIO)
    if not productos:
        st.caption("No hay productos cargados.")
        return

    with st.form("nuevo_pe"):
        prod_options = {f"{p.codigo} — {p.nombre} (May: ${p.precio_venta_mayorista:,.2f})": p.id
                        for p in productos}
        prod_sel = st.selectbox("Producto", list(prod_options.keys()))
        precio_fijo = st.number_input(
            "Precio fijo $", min_value=0.01, step=100.0, value=100.0,
        )
        if st.form_submit_button("Asignar Precio", use_container_width=True):
            try:
                asignar_precio_especial(
                    st.session_state["user_id"],
                    cliente_id,
                    prod_options[prod_sel],
                    precio_fijo,
                )
                invalidar_cache_clientes()
                st.success("Precio especial asignado.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
