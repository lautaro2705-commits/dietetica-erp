"""
views/productos.py - ABM de productos y fracciones.
"""

import streamlit as st
from controllers import (
    crear_producto, actualizar_producto, desactivar_producto,
    listar_productos, crear_fraccion, listar_fracciones,
    calcular_precio_fraccion, listar_categorias, listar_proveedores,
    crear_categoria, crear_proveedor, obtener_producto,
)
from auth import require_admin


def render():
    st.header("Productos")

    tab_listado, tab_nuevo, tab_categorias, tab_proveedores = st.tabs([
        "Listado", "Nuevo Producto", "Categorías", "Proveedores"
    ])

    with tab_listado:
        _render_listado()

    with tab_nuevo:
        if not require_admin():
            st.warning("Solo administradores pueden crear productos.")
        else:
            _render_nuevo_producto()

    with tab_categorias:
        _render_categorias()

    with tab_proveedores:
        _render_proveedores()


def _render_listado():
    productos = listar_productos()
    if not productos:
        st.info("No hay productos cargados.")
        return

    busqueda = st.text_input("Buscar producto", placeholder="Nombre o código...")
    if busqueda:
        productos = [p for p in productos
                     if busqueda.lower() in p.nombre.lower()
                     or busqueda.lower() in p.codigo.lower()]

    for prod in productos:
        with st.expander(f"**{prod.codigo}** — {prod.nombre} | Stock: {prod.stock_actual} {prod.unidad_medida}"):
            col1, col2, col3 = st.columns(3)
            col1.metric("Costo", f"${prod.precio_costo:,.2f}")
            col2.metric("Mayorista", f"${prod.precio_venta_mayorista:,.2f}")
            col3.metric("Margen Min.", f"{prod.margen_minorista_pct}%")

            st.caption(
                f"Contenido: {prod.contenido_total} {prod.unidad_medida} | "
                f"Stock mín: {prod.stock_minimo} | "
                f"Categoría: {prod.categoria.nombre if prod.categoria else '—'} | "
                f"Proveedor: {prod.proveedor.nombre if prod.proveedor else '—'}"
            )

            # Fracciones
            fracciones = listar_fracciones(prod.id)
            if fracciones:
                st.markdown("**Fracciones:**")
                frac_data = []
                for f in fracciones:
                    precio = calcular_precio_fraccion(prod, f)
                    tipo_precio = "Manual" if f.precio_venta is not None else "Automático"
                    frac_data.append({
                        "Nombre": f.nombre,
                        "Cantidad": f"{f.cantidad} {prod.unidad_medida}",
                        "Precio": f"${precio:,.2f}",
                        "Tipo": tipo_precio,
                    })
                st.dataframe(frac_data, use_container_width=True, hide_index=True)

            # Acciones admin
            if require_admin():
                col_a, col_b = st.columns(2)
                with col_a:
                    _render_agregar_fraccion(prod)
                with col_b:
                    if st.button(f"Desactivar", key=f"desact_{prod.id}", type="secondary"):
                        try:
                            desactivar_producto(st.session_state["user_id"], prod.id)
                            st.success(f"'{prod.nombre}' desactivado.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))


def _render_agregar_fraccion(prod):
    with st.popover("+ Fracción"):
        with st.form(f"frac_form_{prod.id}"):
            nombre = st.text_input("Nombre", placeholder="ej: 500g", key=f"fn_{prod.id}")
            cantidad = st.number_input(
                f"Cantidad ({prod.unidad_medida})",
                min_value=0.001, step=0.1, value=0.5, key=f"fc_{prod.id}",
            )
            precio = st.number_input(
                "Precio manual (dejar 0 para automático)",
                min_value=0.0, step=10.0, value=0.0, key=f"fp_{prod.id}",
            )
            if st.form_submit_button("Guardar"):
                if not nombre:
                    st.error("El nombre es obligatorio.")
                else:
                    try:
                        crear_fraccion(
                            st.session_state["user_id"],
                            prod.id, nombre, cantidad,
                            precio if precio > 0 else None,
                        )
                        st.success(f"Fracción '{nombre}' creada.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


def _render_nuevo_producto():
    categorias = listar_categorias()
    proveedores = listar_proveedores()

    with st.form("nuevo_producto"):
        col1, col2 = st.columns(2)
        with col1:
            codigo = st.text_input("Código *", placeholder="HAR-001")
            nombre = st.text_input("Nombre *", placeholder="Harina 000 x 25kg")
            descripcion = st.text_area("Descripción")
        with col2:
            cat_options = {c.nombre: c.id for c in categorias}
            cat_sel = st.selectbox("Categoría", ["Sin categoría"] + list(cat_options.keys()))
            prov_options = {p.nombre: p.id for p in proveedores}
            prov_sel = st.selectbox("Proveedor", ["Sin proveedor"] + list(prov_options.keys()))
            unidad = st.selectbox("Unidad de medida", ["kg", "litro", "unidad"])
            contenido = st.number_input("Contenido total por bulto", min_value=0.01, value=25.0, step=0.5)

        st.divider()
        col3, col4, col5 = st.columns(3)
        with col3:
            precio_costo = st.number_input("Precio Costo $", min_value=0.0, step=100.0)
        with col4:
            precio_mayorista = st.number_input("Precio Mayorista $", min_value=0.0, step=100.0)
        with col5:
            margen = st.number_input("Margen Minorista %", min_value=0.0, value=30.0, step=5.0)

        col6, col7 = st.columns(2)
        with col6:
            stock_inicial = st.number_input("Stock Inicial (bultos)", min_value=0.0, step=1.0)
        with col7:
            stock_minimo = st.number_input("Stock Mínimo (alerta)", min_value=0.0, step=1.0)

        submitted = st.form_submit_button("Crear Producto", use_container_width=True)

        if submitted:
            if not codigo or not nombre:
                st.error("Código y Nombre son obligatorios.")
            else:
                try:
                    crear_producto(
                        st.session_state["user_id"],
                        codigo=codigo,
                        nombre=nombre,
                        descripcion=descripcion,
                        categoria_id=cat_options.get(cat_sel),
                        proveedor_id=prov_options.get(prov_sel),
                        unidad_medida=unidad,
                        contenido_total=contenido,
                        precio_costo=precio_costo,
                        precio_venta_mayorista=precio_mayorista,
                        margen_minorista_pct=margen,
                        stock_actual=stock_inicial,
                        stock_minimo=stock_minimo,
                    )
                    st.success(f"Producto '{nombre}' creado exitosamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


def _render_categorias():
    cats = listar_categorias()
    if cats:
        st.dataframe(
            [{"ID": c.id, "Nombre": c.nombre} for c in cats],
            use_container_width=True, hide_index=True,
        )

    if require_admin():
        with st.form("nueva_cat"):
            nombre = st.text_input("Nueva categoría")
            if st.form_submit_button("Crear"):
                if nombre:
                    try:
                        crear_categoria(st.session_state["user_id"], nombre)
                        st.success(f"Categoría '{nombre}' creada.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


def _render_proveedores():
    provs = listar_proveedores()
    if provs:
        st.dataframe(
            [{"ID": p.id, "Nombre": p.nombre, "Contacto": p.contacto,
              "Teléfono": p.telefono} for p in provs],
            use_container_width=True, hide_index=True,
        )

    if require_admin():
        with st.form("nuevo_prov"):
            col1, col2, col3 = st.columns(3)
            with col1:
                nombre = st.text_input("Nombre *")
            with col2:
                contacto = st.text_input("Contacto")
            with col3:
                telefono = st.text_input("Teléfono")
            if st.form_submit_button("Crear"):
                if nombre:
                    try:
                        crear_proveedor(
                            st.session_state["user_id"], nombre, contacto, telefono
                        )
                        st.success(f"Proveedor '{nombre}' creado.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
