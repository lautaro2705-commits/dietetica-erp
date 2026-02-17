"""
views/productos.py - ABM de productos y fracciones con edición y vencimiento.
"""

import streamlit as st
from datetime import date
from controllers import (
    crear_producto, actualizar_producto, desactivar_producto,
    listar_productos, crear_fraccion, listar_fracciones,
    calcular_precio_fraccion, listar_categorias, listar_proveedores,
    crear_categoria, crear_proveedor, obtener_producto,
    importar_productos,
)
from auth import require_admin
from utils.cache import (
    cached_query, invalidar_cache_productos, invalidar_cache_catalogos,
    TTL_MEDIO, TTL_LARGO,
)


def render():
    st.header("Productos")

    tabs = ["Listado", "Nuevo Producto", "Categorías", "Proveedores"]
    if require_admin():
        tabs.append("Importar")

    tab_objects = st.tabs(tabs)

    with tab_objects[0]:
        _render_listado()

    with tab_objects[1]:
        if not require_admin():
            st.warning("Solo administradores pueden crear productos.")
        else:
            _render_nuevo_producto()

    with tab_objects[2]:
        _render_categorias()

    with tab_objects[3]:
        _render_proveedores()

    if require_admin() and len(tab_objects) > 4:
        with tab_objects[4]:
            _render_importar()


def _render_listado():
    productos = cached_query("productos_activos", listar_productos, TTL_MEDIO)
    if not productos:
        st.info("No hay productos cargados.")
        return

    busqueda = st.text_input("Buscar producto", placeholder="Nombre o código...")
    if busqueda:
        productos = [p for p in productos
                     if busqueda.lower() in p.nombre.lower()
                     or busqueda.lower() in p.codigo.lower()]

    for prod in productos:
        # Indicador de vencimiento en el título
        venc_badge = ""
        if prod.fecha_vencimiento:
            dias_restantes = (prod.fecha_vencimiento - date.today()).days
            if dias_restantes < 0:
                venc_badge = " 🔴 VENCIDO"
            elif dias_restantes <= 30:
                venc_badge = " 🟡 Próximo a vencer"

        with st.expander(
            f"**{prod.codigo}** — {prod.nombre} | "
            f"Stock: {prod.stock_actual} {prod.unidad_medida}{venc_badge}"
        ):
            col1, col2, col3 = st.columns(3)
            col1.metric("Costo", f"${prod.precio_costo:,.2f}")
            col2.metric("Mayorista", f"${prod.precio_venta_mayorista:,.2f}")
            col3.metric("Margen Min.", f"{prod.margen_minorista_pct}%")

            venc_text = (
                prod.fecha_vencimiento.strftime("%d/%m/%Y")
                if prod.fecha_vencimiento else "Sin vencimiento"
            )
            st.caption(
                f"Contenido: {prod.contenido_total} {prod.unidad_medida} | "
                f"Stock mín: {prod.stock_minimo} | "
                f"Categoría: {prod.categoria.nombre if prod.categoria else '—'} | "
                f"Proveedor: {prod.proveedor.nombre if prod.proveedor else '—'} | "
                f"Vencimiento: {venc_text}"
            )

            # Fracciones
            fracciones = cached_query(f"fracciones_{prod.id}", listar_fracciones, TTL_MEDIO, prod.id)
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
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    _render_agregar_fraccion(prod)
                with col_b:
                    _render_editar_producto(prod)
                with col_c:
                    if st.button(f"Desactivar", key=f"desact_{prod.id}", type="secondary"):
                        try:
                            desactivar_producto(st.session_state["user_id"], prod.id)
                            invalidar_cache_productos()
                            st.success(f"'{prod.nombre}' desactivado.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))


def _render_editar_producto(prod):
    """Popover para editar un producto existente."""
    with st.popover("✏️ Editar"):
        categorias = cached_query("categorias_activas", listar_categorias, TTL_LARGO)
        proveedores = cached_query("proveedores_activos", listar_proveedores, TTL_LARGO)

        cat_options = {"Sin categoría": None}
        for c in categorias:
            cat_options[c.nombre] = c.id
        prov_options = {"Sin proveedor": None}
        for p in proveedores:
            prov_options[p.nombre] = p.id

        # Encontrar selección actual
        cat_actual = "Sin categoría"
        for name, cid in cat_options.items():
            if cid == prod.categoria_id:
                cat_actual = name
                break
        prov_actual = "Sin proveedor"
        for name, pid in prov_options.items():
            if pid == prod.proveedor_id:
                prov_actual = name
                break

        with st.form(f"edit_form_{prod.id}"):
            nombre = st.text_input("Nombre", value=prod.nombre, key=f"en_{prod.id}")
            descripcion = st.text_area("Descripción", value=prod.descripcion or "",
                                       key=f"ed_{prod.id}")

            col1, col2 = st.columns(2)
            with col1:
                cat_sel = st.selectbox(
                    "Categoría", list(cat_options.keys()),
                    index=list(cat_options.keys()).index(cat_actual),
                    key=f"ec_{prod.id}",
                )
                unidad = st.selectbox(
                    "Unidad", ["kg", "litro", "unidad"],
                    index=["kg", "litro", "unidad"].index(prod.unidad_medida),
                    key=f"eu_{prod.id}",
                )
            with col2:
                prov_sel = st.selectbox(
                    "Proveedor", list(prov_options.keys()),
                    index=list(prov_options.keys()).index(prov_actual),
                    key=f"ep_{prod.id}",
                )
                contenido = st.number_input(
                    "Contenido por bulto", min_value=0.01,
                    value=float(prod.contenido_total), step=0.5,
                    key=f"eco_{prod.id}",
                )

            st.divider()
            col3, col4, col5 = st.columns(3)
            with col3:
                precio_costo = st.number_input(
                    "Precio Costo $", min_value=0.0,
                    value=float(prod.precio_costo), step=100.0,
                    key=f"epc_{prod.id}",
                )
            with col4:
                precio_mayorista = st.number_input(
                    "Precio Mayorista $", min_value=0.0,
                    value=float(prod.precio_venta_mayorista), step=100.0,
                    key=f"epm_{prod.id}",
                )
            with col5:
                margen = st.number_input(
                    "Margen Minorista %", min_value=0.0,
                    value=float(prod.margen_minorista_pct), step=5.0,
                    key=f"emm_{prod.id}",
                )

            col6, col7 = st.columns(2)
            with col6:
                stock_minimo = st.number_input(
                    "Stock Mínimo", min_value=0.0,
                    value=float(prod.stock_minimo), step=1.0,
                    key=f"esm_{prod.id}",
                )
            with col7:
                tiene_venc = st.checkbox(
                    "Tiene fecha de vencimiento",
                    value=prod.fecha_vencimiento is not None,
                    key=f"etv_{prod.id}",
                )
                if tiene_venc:
                    fecha_venc = st.date_input(
                        "Fecha de vencimiento",
                        value=prod.fecha_vencimiento or date.today(),
                        key=f"efv_{prod.id}",
                    )
                else:
                    fecha_venc = None

            if st.form_submit_button("Guardar Cambios", use_container_width=True):
                try:
                    actualizar_producto(
                        st.session_state["user_id"],
                        prod.id,
                        nombre=nombre,
                        descripcion=descripcion,
                        categoria_id=cat_options.get(cat_sel),
                        proveedor_id=prov_options.get(prov_sel),
                        unidad_medida=unidad,
                        contenido_total=contenido,
                        precio_costo=precio_costo,
                        precio_venta_mayorista=precio_mayorista,
                        margen_minorista_pct=margen,
                        stock_minimo=stock_minimo,
                        fecha_vencimiento=fecha_venc,
                    )
                    invalidar_cache_productos()
                    st.success(f"Producto '{nombre}' actualizado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


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
                        invalidar_cache_productos()
                        st.success(f"Fracción '{nombre}' creada.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


def _render_nuevo_producto():
    categorias = cached_query("categorias_activas", listar_categorias, TTL_LARGO)
    proveedores = cached_query("proveedores_activos", listar_proveedores, TTL_LARGO)

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
            stock_minimo = st.number_input("Stock Mínimo (alerta)", min_value=0.0, step=1.0)
        with col7:
            tiene_venc = st.checkbox("Tiene fecha de vencimiento", value=False)
            if tiene_venc:
                fecha_venc = st.date_input("Fecha de vencimiento", value=date.today())
            else:
                fecha_venc = None

        submitted = st.form_submit_button("Crear Producto", use_container_width=True)

        if submitted:
            if not codigo or not nombre:
                st.error("Código y Nombre son obligatorios.")
            else:
                try:
                    kwargs = dict(
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
                    if fecha_venc:
                        kwargs["fecha_vencimiento"] = fecha_venc
                    crear_producto(
                        st.session_state["user_id"],
                        **kwargs,
                    )
                    invalidar_cache_productos()
                    st.success(f"Producto '{nombre}' creado exitosamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


def _render_categorias():
    cats = cached_query("categorias_activas", listar_categorias, TTL_LARGO)
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
                        invalidar_cache_catalogos()
                        st.success(f"Categoría '{nombre}' creada.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


def _render_proveedores():
    provs = cached_query("proveedores_activos", listar_proveedores, TTL_LARGO)
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
                        invalidar_cache_catalogos()
                        st.success(f"Proveedor '{nombre}' creado.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


def _render_importar():
    """Tab de importación masiva de productos desde CSV/Excel."""
    import pandas as pd

    st.subheader("Importación Masiva de Productos")
    st.markdown(
        "Subí un archivo **CSV** o **Excel (.xlsx)** con los productos a importar. "
        "Columnas esperadas: `codigo`, `nombre`, `precio_costo`, `precio_venta_mayorista`, "
        "`categoria`, `proveedor`, `unidad_medida`, `stock_actual`, `margen_minorista_pct`"
    )

    archivo = st.file_uploader(
        "Seleccionar archivo", type=["csv", "xlsx"],
        key="import_file",
    )

    if archivo is None:
        # Mostrar plantilla de ejemplo
        st.caption("📋 Ejemplo de formato esperado:")
        st.dataframe([{
            "codigo": "HAR-001", "nombre": "Harina 000 x 25kg",
            "precio_costo": 15000, "precio_venta_mayorista": 18000,
            "categoria": "Harinas", "proveedor": "", "unidad_medida": "kg",
            "stock_actual": 10, "margen_minorista_pct": 30,
        }], use_container_width=True, hide_index=True)
        return

    try:
        if archivo.name.endswith(".csv"):
            df = pd.read_csv(archivo)
        else:
            df = pd.read_excel(archivo)
    except Exception as e:
        st.error(f"Error leyendo archivo: {e}")
        return

    if df.empty:
        st.warning("El archivo está vacío.")
        return

    st.success(f"Archivo leído: **{len(df)} filas**, columnas: {', '.join(df.columns)}")

    # Mapeo de columnas
    st.subheader("Vista previa")
    st.dataframe(df.head(20), use_container_width=True, hide_index=True)

    # Validaciones básicas
    cols_requeridas = ["codigo", "nombre"]
    faltantes = [c for c in cols_requeridas if c not in df.columns]
    if faltantes:
        st.error(f"Faltan columnas obligatorias: {', '.join(faltantes)}")
        return

    # Modo de importación
    modo = st.radio(
        "Modo de importación",
        ["crear", "actualizar"],
        format_func=lambda x: {
            "crear": "Crear nuevos (solo agrega productos que no existen)",
            "actualizar": "Actualizar existentes (actualiza precios por código)",
        }[x],
        horizontal=True,
    )

    st.warning(
        f"Se procesarán **{len(df)} registros** en modo **{modo}**. "
        f"Esta operación no se puede deshacer fácilmente."
    )

    if st.button("Importar Productos", type="primary", use_container_width=True):
        with st.spinner("Importando..."):
            datos = df.fillna("").to_dict("records")
            resultado = importar_productos(
                st.session_state["user_id"], datos, modo,
            )

        col1, col2, col3 = st.columns(3)
        col1.metric("Creados", resultado["creados"])
        col2.metric("Actualizados", resultado["actualizados"])
        col3.metric("Errores", len(resultado["errores"]))

        if resultado["errores"]:
            with st.expander("Ver errores"):
                for err in resultado["errores"]:
                    st.caption(f"⚠️ {err}")

        if resultado["creados"] > 0 or resultado["actualizados"] > 0:
            invalidar_cache_productos()
            invalidar_cache_catalogos()
            st.success("Importación completada.")
            st.rerun()
