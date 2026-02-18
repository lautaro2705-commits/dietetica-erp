"""
views/stock.py - Movimientos de stock, alertas, vencimientos, góndola y
eliminación de productos.
"""

import streamlit as st
from datetime import date
from database import SessionLocal, MovimientoStock, hoy_argentina
from controllers import (
    listar_productos, registrar_movimiento_stock, productos_bajo_stock,
    productos_proximos_a_vencer, desactivar_producto, listar_categorias,
)
from auth import require_admin
from utils.cache import (
    cached_query, invalidar_cache_productos,
    TTL_CORTO, TTL_MEDIO, TTL_LARGO,
)


def render():
    st.header("Stock")

    tab_names = [
        "🏪 Góndola",
        "Registrar Movimiento",
        "Alertas Stock Bajo",
        "🗓️ Vencimientos",
        "Historial",
    ]
    if require_admin():
        tab_names.append("🗑️ Eliminar Producto")

    tab_objects = st.tabs(tab_names)

    with tab_objects[0]:
        _render_gondola()

    with tab_objects[1]:
        _render_movimiento()

    with tab_objects[2]:
        _render_alertas()

    with tab_objects[3]:
        _render_vencimientos()

    with tab_objects[4]:
        _render_historial()

    if require_admin() and len(tab_objects) > 5:
        with tab_objects[5]:
            _render_eliminar_producto()


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
    hoy = hoy_argentina()
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


# ---------------------------------------------------------------------------
# Góndola — Vista completa de stock categorizado
# ---------------------------------------------------------------------------

def _render_gondola():
    """Muestra todo el stock organizado por categoría, como una góndola."""
    productos = cached_query("productos_activos", listar_productos, TTL_MEDIO)
    if not productos:
        st.info("No hay productos cargados.")
        return

    # Filtro de búsqueda rápida
    busqueda = st.text_input(
        "🔍 Buscar en góndola",
        placeholder="Nombre o código...",
        key="gondola_busqueda",
    )
    if busqueda:
        busqueda_lower = busqueda.lower()
        productos = [
            p for p in productos
            if busqueda_lower in p.nombre.lower()
            or busqueda_lower in p.codigo.lower()
        ]

    if not productos:
        st.warning("No se encontraron productos con ese filtro.")
        return

    # Agrupar por categoría
    por_categoria = {}
    for p in productos:
        cat_nombre = p.categoria.nombre if p.categoria else "Sin categoría"
        por_categoria.setdefault(cat_nombre, []).append(p)

    # Ordenar categorías alfabéticamente ("Sin categoría" al final)
    categorias_ordenadas = sorted(
        por_categoria.keys(),
        key=lambda c: (c == "Sin categoría", c),
    )

    # Métricas generales
    total_productos = len(productos)
    total_stock_valor = sum(p.stock_actual * p.precio_costo for p in productos)
    productos_sin_stock = sum(1 for p in productos if p.stock_actual <= 0)

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Total Productos", total_productos)
    col_m2.metric("Categorías", len(categorias_ordenadas))
    col_m3.metric("Stock Valorizado", f"${total_stock_valor:,.0f}")
    col_m4.metric("Sin Stock", productos_sin_stock)

    st.divider()

    # Renderizar cada categoría como sección de góndola
    for cat_nombre in categorias_ordenadas:
        prods = por_categoria[cat_nombre]
        total_cat = sum(p.stock_actual * p.precio_costo for p in prods)

        st.subheader(f"📦 {cat_nombre}  ({len(prods)} productos)")

        # Mostrar productos en grilla de 4 columnas
        cols_per_row = 4
        for i in range(0, len(prods), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(prods):
                    break
                p = prods[idx]
                with col:
                    # Indicador visual de estado de stock
                    if p.stock_actual <= 0:
                        estado = "🔴"
                    elif p.stock_actual <= p.stock_minimo:
                        estado = "🟡"
                    else:
                        estado = "🟢"

                    # Indicador de vencimiento
                    venc_icon = ""
                    if p.fecha_vencimiento:
                        dias = (p.fecha_vencimiento - hoy_argentina()).days
                        if dias < 0:
                            venc_icon = " ⚠️"
                        elif dias <= 30:
                            venc_icon = " ⏰"

                    st.markdown(
                        f"**{estado} {p.nombre}**{venc_icon}\n\n"
                        f"`{p.codigo}`\n\n"
                        f"Stock: **{p.stock_actual}** {p.unidad_medida}\n\n"
                        f"Costo: ${p.precio_costo:,.0f} | "
                        f"May: ${p.precio_venta_mayorista:,.0f}"
                    )

        st.caption(f"Valor en stock: ${total_cat:,.0f}")
        st.divider()


# ---------------------------------------------------------------------------
# Eliminar Producto (admin only)
# ---------------------------------------------------------------------------

def _render_eliminar_producto():
    """Permite al admin desactivar (eliminar) productos del sistema."""
    if not require_admin():
        st.warning("Solo administradores pueden eliminar productos.")
        return

    st.markdown(
        "⚠️ **Eliminar** un producto lo **desactiva** del sistema. "
        "No aparecerá en ventas, stock ni listados, pero su historial "
        "se conserva en auditoría."
    )

    productos = cached_query("productos_activos", listar_productos, TTL_MEDIO)
    if not productos:
        st.info("No hay productos activos.")
        return

    # Búsqueda
    busqueda = st.text_input(
        "Buscar producto a eliminar",
        placeholder="Nombre o código...",
        key="eliminar_busqueda",
    )
    if busqueda:
        busqueda_lower = busqueda.lower()
        productos = [
            p for p in productos
            if busqueda_lower in p.nombre.lower()
            or busqueda_lower in p.codigo.lower()
        ]

    if not productos:
        st.warning("No se encontraron productos.")
        return

    st.caption(f"{len(productos)} producto(s) encontrado(s)")

    for p in productos:
        col1, col2, col3 = st.columns([4, 2, 1])
        col1.write(f"**{p.codigo}** — {p.nombre}")
        col2.write(
            f"Stock: {p.stock_actual} {p.unidad_medida} | "
            f"${p.precio_costo:,.0f}"
        )

        # Confirmación en dos pasos usando session_state
        confirm_key = f"confirmar_eliminar_{p.id}"
        if st.session_state.get(confirm_key):
            col3.empty()
            st.warning(
                f"¿Eliminar **{p.nombre}** ({p.codigo})? "
                f"Stock actual: {p.stock_actual} {p.unidad_medida}"
            )
            col_si, col_no = st.columns(2)
            with col_si:
                if st.button(
                    "✅ Sí, eliminar",
                    key=f"si_elim_{p.id}",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        desactivar_producto(
                            st.session_state["user_id"], p.id
                        )
                        invalidar_cache_productos()
                        st.session_state.pop(confirm_key, None)
                        st.success(f"'{p.nombre}' eliminado del sistema.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            with col_no:
                if st.button(
                    "Cancelar",
                    key=f"no_elim_{p.id}",
                    use_container_width=True,
                ):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
        else:
            with col3:
                if st.button("🗑️", key=f"btn_elim_{p.id}"):
                    st.session_state[confirm_key] = True
                    st.rerun()
