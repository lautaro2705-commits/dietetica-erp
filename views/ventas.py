"""
views/ventas.py - Registro de ventas, historial, tickets PDF, devoluciones y scanner de códigos.
"""

import streamlit as st
import streamlit.components.v1 as components
from datetime import date, timedelta

from controllers import (
    listar_productos, listar_fracciones, calcular_precio_fraccion,
    procesar_venta, listar_ventas, obtener_detalle_venta,
    listar_clientes, caja_abierta_hoy,
    anular_venta, devolucion_parcial,
    obtener_precio_cliente,
)
from utils.ticket_pdf import generar_ticket_pdf, generar_link_whatsapp
from utils.barcode_scanner import get_barcode_scanner_html, get_scanner_height
from utils.cache import (
    cached_query, invalidar_cache_ventas, invalidar_cache_productos,
    invalidar_cache_clientes, TTL_CORTO, TTL_MEDIO,
)


def render():
    st.header("Ventas")

    # Bloqueo por caja cerrada (cacheado 15s)
    caja_ok = cached_query("caja_abierta", caja_abierta_hoy, TTL_CORTO)
    if not caja_ok:
        st.warning(
            "⚠️ La caja no está abierta. Abrí la caja en **Caja Diaria** "
            "antes de registrar ventas."
        )

    tab_nueva, tab_historial = st.tabs(["Nueva Venta", "Historial"])

    with tab_nueva:
        _render_nueva_venta(caja_ok)

    with tab_historial:
        _render_historial()


def _render_nueva_venta(caja_ok: bool = False):
    # Bloquear si caja no está abierta
    if not caja_ok:
        st.info("Abrí la caja diaria para poder registrar ventas.")
        return

    # Inicializar carrito en session_state
    if "carrito" not in st.session_state:
        st.session_state["carrito"] = []

    # Queries cacheadas — evita re-queries en cada rerun
    productos = cached_query("productos_activos", listar_productos, TTL_MEDIO)
    if not productos:
        st.info("No hay productos cargados. Cargá productos primero.")
        return

    # Cabecera: tipo de venta, método de pago, cliente
    col_tipo, col_pago, col_cli = st.columns(3)
    with col_tipo:
        tipo_venta = st.radio("Tipo de venta", ["minorista", "mayorista"], horizontal=True)
    with col_pago:
        metodo_pago = st.selectbox(
            "Método de pago",
            ["efectivo", "transferencia", "cuenta_corriente"],
            format_func=lambda x: {
                "efectivo": "💵 Efectivo",
                "transferencia": "🏦 Transferencia",
                "cuenta_corriente": "📋 Cuenta Corriente",
            }[x],
        )
    with col_cli:
        clientes = cached_query("clientes_activos", listar_clientes, TTL_MEDIO)
        cli_options = {"Sin cliente": None}
        for c in clientes:
            cli_options[f"{c.nombre}"] = c.id
        cli_sel = st.selectbox("Cliente", list(cli_options.keys()))
        cliente_id = cli_options[cli_sel]

    # Validación: cuenta corriente requiere cliente
    if metodo_pago == "cuenta_corriente" and not cliente_id:
        st.warning("Para vender en cuenta corriente, seleccioná un cliente.")

    st.divider()

    # --- Búsqueda rápida por código y Scanner ---
    col_busqueda, col_scanner = st.columns([3, 1])
    with col_busqueda:
        codigo_busqueda = st.text_input(
            "Búsqueda rápida por código",
            placeholder="Escribí o escaneá un código de barras...",
            key="codigo_rapido",
        )
    with col_scanner:
        st.write("")  # spacer
        mostrar_scanner = st.toggle("📷 Scanner", key="toggle_scanner")

    # Scanner de cámara
    if mostrar_scanner:
        st.caption("Apuntá la cámara al código de barras:")
        components.html(
            get_barcode_scanner_html("ventas_scanner"),
            height=get_scanner_height(),
        )
        st.caption("El código escaneado aparecerá en el campo de búsqueda.")

    # Si hay código en búsqueda rápida, buscar y agregar
    if codigo_busqueda:
        matches = [p for p in productos if p.codigo.lower() == codigo_busqueda.strip().lower()]
        if matches:
            prod_match = matches[0]
            precio, etiqueta = obtener_precio_cliente(cliente_id, prod_match.id, tipo_venta)
            etiqueta_txt = f" {etiqueta}" if etiqueta else ""
            st.success(
                f"Encontrado: **{prod_match.nombre}** — "
                f"${precio:,.2f}{etiqueta_txt}"
            )
        else:
            st.warning(f"Producto con código '{codigo_busqueda}' no encontrado.")

    st.subheader("Agregar al carrito")
    prod_options = {f"{p.codigo} — {p.nombre}": p for p in productos}
    prod_sel = st.selectbox("Producto", list(prod_options.keys()))
    prod = prod_options[prod_sel] if prod_sel else None

    if prod:
        fracciones = cached_query(
            f"fracciones_{prod.id}", listar_fracciones, TTL_MEDIO, prod.id,
        )
        frac_options = {"Bulto completo": None}
        for f in fracciones:
            precio = calcular_precio_fraccion(prod, f)
            frac_options[f"{f.nombre} (${precio:,.2f})"] = f

        frac_sel = st.selectbox("Presentación", list(frac_options.keys()))
        frac = frac_options[frac_sel]

        cantidad = st.number_input("Cantidad", min_value=1, value=1, step=1)

        # Resolver precio con lógica de precios especiales
        if frac:
            precio_unit = calcular_precio_fraccion(prod, frac)
            etiqueta = ""
        else:
            precio_unit, etiqueta = obtener_precio_cliente(
                cliente_id, prod.id, tipo_venta,
            )

        precio_unit = round(precio_unit, 2)
        subtotal = round(precio_unit * cantidad, 2)

        etiqueta_txt = f" {etiqueta}" if etiqueta else ""
        st.info(
            f"Precio unitario: **${precio_unit:,.2f}**{etiqueta_txt} | "
            f"Subtotal: **${subtotal:,.2f}**"
        )

        if st.button("Agregar al carrito", type="primary"):
            st.session_state["carrito"].append({
                "producto_id": prod.id,
                "producto_nombre": prod.nombre,
                "fraccion_id": frac.id if frac else None,
                "fraccion_nombre": frac.nombre if frac else "Bulto",
                "cantidad": cantidad,
                "precio_unitario": precio_unit,
                "subtotal": subtotal,
                "etiqueta_precio": etiqueta,
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
            etiq = f" {item.get('etiqueta_precio', '')}" if item.get('etiqueta_precio') else ""
            col1.write(
                f"**{item['producto_nombre']}** ({item['fraccion_nombre']}) "
                f"x{item['cantidad']}{etiq}"
            )
            col2.write(f"${item['subtotal']:,.2f}")
            if col3.button("X", key=f"rm_{i}"):
                carrito.pop(i)
                st.rerun()
            total += item["subtotal"]

        st.markdown(f"### Total: ${total:,.2f}")

        # Mostrar info de pago
        pago_label = {"efectivo": "💵 Efectivo", "transferencia": "🏦 Transferencia",
                      "cuenta_corriente": "📋 Cuenta Corriente"}
        st.caption(
            f"Pago: {pago_label[metodo_pago]}"
            + (f" | Cliente: {cli_sel}" if cliente_id else "")
        )

        col_obs, col_btn = st.columns([3, 1])
        with col_obs:
            observaciones = st.text_input("Observaciones", key="obs_venta")
        with col_btn:
            st.write("")  # spacer
            can_sell = metodo_pago != "cuenta_corriente" or cliente_id is not None
            if st.button("Confirmar Venta", type="primary",
                         use_container_width=True, disabled=not can_sell):
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
                        metodo_pago=metodo_pago,
                        cliente_id=cliente_id,
                    )
                    # Invalidar caches afectadas por la venta
                    invalidar_cache_ventas()
                    invalidar_cache_productos()
                    if cliente_id:
                        invalidar_cache_clientes()
                    st.session_state["carrito"] = []
                    st.success(f"Venta #{venta.id} registrada. Total: ${venta.total:,.2f}")

                    # Ticket PDF + WhatsApp
                    _render_ticket_post_venta(venta.id, venta.total)

                except Exception as e:
                    st.error(f"Error al procesar venta: {e}")

        if st.button("Vaciar carrito"):
            st.session_state["carrito"] = []
            st.rerun()


def _render_ticket_post_venta(venta_id: int, total: float):
    """Muestra botones de ticket PDF y WhatsApp post-confirmación."""
    try:
        pdf_bytes = generar_ticket_pdf(venta_id)
        col_pdf, col_wa = st.columns(2)
        with col_pdf:
            st.download_button(
                "📄 Descargar Ticket PDF",
                data=pdf_bytes,
                file_name=f"ticket_venta_{venta_id}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with col_wa:
            link_wa = generar_link_whatsapp(venta_id, total)
            st.link_button(
                "📱 Compartir por WhatsApp",
                url=link_wa,
                use_container_width=True,
            )
    except Exception as e:
        st.warning(f"No se pudo generar el ticket: {e}")


def _render_historial():
    col1, col2 = st.columns(2)
    with col1:
        fecha_desde = st.date_input("Desde", value=date.today() - timedelta(days=30))
    with col2:
        fecha_hasta = st.date_input("Hasta", value=date.today())

    ventas = cached_query(
        f"ventas_{fecha_desde}_{fecha_hasta}",
        listar_ventas, TTL_CORTO, fecha_desde, fecha_hasta,
    )

    if not ventas:
        st.info("No hay ventas en el período seleccionado.")
        return

    pago_icons = {"efectivo": "💵", "transferencia": "🏦",
                  "cuenta_corriente": "📋"}

    for v in ventas:
        metodo = getattr(v, "metodo_pago", "efectivo") or "efectivo"
        icon = pago_icons.get(metodo, "")
        anulada = getattr(v, "anulada", False)
        anulada_txt = " ❌ ANULADA" if anulada else ""
        cliente_txt = f" | {v.cliente.nombre}" if v.cliente else ""

        with st.expander(
            f"Venta #{v.id} | {v.fecha.strftime('%d/%m/%Y %H:%M')} | "
            f"**${v.total:,.2f}** | {v.tipo.upper()} {icon}{cliente_txt}{anulada_txt}"
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

            metodo_label = {"efectivo": "Efectivo", "transferencia": "Transferencia",
                            "cuenta_corriente": "Cuenta Corriente"}
            st.caption(
                f"Pago: {metodo_label.get(metodo, metodo)}"
                + (f" | Cliente: {v.cliente.nombre}" if v.cliente else "")
            )
            if v.observaciones:
                st.caption(f"Obs: {v.observaciones}")

            # Ticket PDF desde historial
            col_tk, col_wa = st.columns(2)
            with col_tk:
                try:
                    pdf_bytes = generar_ticket_pdf(v.id)
                    st.download_button(
                        "📄 Ticket PDF",
                        data=pdf_bytes,
                        file_name=f"ticket_venta_{v.id}.pdf",
                        mime="application/pdf",
                        key=f"tk_{v.id}",
                        use_container_width=True,
                    )
                except Exception:
                    st.caption("No se pudo generar ticket.")
            with col_wa:
                link_wa = generar_link_whatsapp(v.id, v.total)
                st.link_button(
                    "📱 WhatsApp",
                    url=link_wa,
                    key=f"wa_{v.id}",
                    use_container_width=True,
                )

            # Devoluciones (solo admin, solo ventas no anuladas)
            if not anulada and st.session_state.get("rol") == "admin":
                st.divider()
                _render_devoluciones(v, detalles)


def _render_devoluciones(venta, detalles):
    """Botones de anulación total y devolución parcial (solo admin)."""
    col_anular, col_devolver = st.columns(2)

    with col_anular:
        with st.popover("🚫 Anular Venta", use_container_width=True):
            st.warning(
                f"¿Estás seguro de anular la Venta #{venta.id}?\n\n"
                f"Se reingresará el stock y se revertirá el cobro."
            )
            motivo = st.text_input(
                "Motivo de anulación",
                key=f"motivo_anular_{venta.id}",
                max_chars=300,
            )
            if st.button("Confirmar Anulación", key=f"btn_anular_{venta.id}",
                         type="primary"):
                try:
                    anular_venta(
                        st.session_state["user_id"],
                        venta.id,
                        motivo,
                    )
                    invalidar_cache_ventas()
                    invalidar_cache_productos()
                    invalidar_cache_clientes()
                    st.success(f"Venta #{venta.id} anulada correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al anular: {e}")

    with col_devolver:
        with st.popover("↩️ Devolución Parcial", use_container_width=True):
            st.info("Seleccioná los items y cantidades a devolver:")

            items_devolver = []
            for d in detalles:
                nombre = d.producto.nombre if d.producto else "—"
                frac_txt = f" ({d.fraccion.nombre})" if d.fraccion else ""
                cant_devolver = st.number_input(
                    f"{nombre}{frac_txt} (máx: {d.cantidad:g})",
                    min_value=0.0,
                    max_value=float(d.cantidad),
                    value=0.0,
                    step=1.0,
                    key=f"dev_{venta.id}_{d.id}",
                )
                if cant_devolver > 0:
                    items_devolver.append({
                        "detalle_id": d.id,
                        "cantidad": cant_devolver,
                    })

            motivo_dev = st.text_input(
                "Motivo de devolución",
                key=f"motivo_dev_{venta.id}",
                max_chars=300,
            )

            if st.button("Confirmar Devolución", key=f"btn_dev_{venta.id}",
                         type="primary", disabled=len(items_devolver) == 0):
                try:
                    dev = devolucion_parcial(
                        st.session_state["user_id"],
                        venta.id,
                        items_devolver,
                        motivo_dev,
                    )
                    invalidar_cache_ventas()
                    invalidar_cache_productos()
                    invalidar_cache_clientes()
                    st.success(
                        f"Devolución registrada. "
                        f"Monto devuelto: ${dev.monto_devuelto:,.2f}"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error en devolución: {e}")
