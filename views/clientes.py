"""
views/clientes.py - Gestión de clientes y cuenta corriente.
"""

import streamlit as st
from controllers import (
    crear_cliente, listar_clientes, obtener_cliente,
    registrar_pago_cliente, listar_movimientos_cuenta,
)


def render():
    st.header("Clientes")

    tab_listado, tab_nuevo, tab_cuenta = st.tabs([
        "Listado", "Nuevo Cliente", "Cuenta Corriente"
    ])

    with tab_listado:
        _render_listado()

    with tab_nuevo:
        _render_nuevo_cliente()

    with tab_cuenta:
        _render_cuenta_corriente()


def _render_listado():
    clientes = listar_clientes()
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
        data.append({
            "ID": c.id,
            "Nombre": c.nombre,
            "CUIT": c.cuit or "—",
            "Teléfono": c.telefono or "—",
            "Email": c.email or "—",
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
                    st.success(f"Cliente '{nombre}' creado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


def _render_cuenta_corriente():
    clientes = listar_clientes()
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
