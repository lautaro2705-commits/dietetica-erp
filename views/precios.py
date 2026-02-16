"""
views/precios.py - Actualización masiva de precios.
"""

import streamlit as st
from controllers import (
    listar_categorias, listar_proveedores, listar_productos,
    aumento_masivo_precios,
)
from auth import require_admin


def render():
    st.header("Actualización de Precios")

    if not require_admin():
        st.warning("Solo administradores pueden modificar precios.")
        return

    st.markdown(
        "Aplicá un aumento porcentual masivo a los productos filtrados por "
        "**Categoría** y/o **Proveedor**."
    )

    categorias = listar_categorias()
    proveedores = listar_proveedores()

    col1, col2 = st.columns(2)
    with col1:
        cat_options = {"Todas las categorías": None}
        cat_options.update({c.nombre: c.id for c in categorias})
        cat_sel = st.selectbox("Filtrar por Categoría", list(cat_options.keys()))
    with col2:
        prov_options = {"Todos los proveedores": None}
        prov_options.update({p.nombre: p.id for p in proveedores})
        prov_sel = st.selectbox("Filtrar por Proveedor", list(prov_options.keys()))

    porcentaje = st.number_input(
        "Porcentaje de aumento (%)",
        min_value=-50.0, max_value=200.0, value=10.0, step=1.0,
        help="Usá valores negativos para descuentos."
    )

    campos = st.multiselect(
        "Campos a actualizar",
        ["precio_costo", "precio_venta_mayorista"],
        default=["precio_costo", "precio_venta_mayorista"],
    )

    # Preview
    cat_id = cat_options[cat_sel]
    prov_id = prov_options[prov_sel]

    productos = listar_productos()
    if cat_id:
        productos = [p for p in productos if p.categoria_id == cat_id]
    if prov_id:
        productos = [p for p in productos if p.proveedor_id == prov_id]

    if productos:
        st.subheader(f"Vista previa ({len(productos)} productos afectados)")
        factor = 1 + porcentaje / 100
        preview = []
        for p in productos[:20]:
            row = {"Código": p.codigo, "Producto": p.nombre}
            if "precio_costo" in campos:
                row["Costo Actual"] = f"${p.precio_costo:,.2f}"
                row["Costo Nuevo"] = f"${p.precio_costo * factor:,.2f}"
            if "precio_venta_mayorista" in campos:
                row["Mayorista Actual"] = f"${p.precio_venta_mayorista:,.2f}"
                row["Mayorista Nuevo"] = f"${p.precio_venta_mayorista * factor:,.2f}"
            preview.append(row)
        st.dataframe(preview, use_container_width=True, hide_index=True)
        if len(productos) > 20:
            st.caption(f"...y {len(productos) - 20} productos más.")
    else:
        st.info("No hay productos que coincidan con el filtro seleccionado.")

    st.divider()

    col_btn, col_confirm = st.columns([1, 3])
    with col_btn:
        if st.button(
            f"Aplicar {'+' if porcentaje >= 0 else ''}{porcentaje}%",
            type="primary",
            disabled=not productos or not campos,
            use_container_width=True,
        ):
            st.session_state["confirmar_aumento"] = True

    if st.session_state.get("confirmar_aumento"):
        st.warning(
            f"Estás por aplicar **{'+' if porcentaje >= 0 else ''}{porcentaje}%** "
            f"a **{len(productos)} productos**. Esta acción queda registrada en auditoría."
        )
        col_si, col_no = st.columns(2)
        with col_si:
            if st.button("Confirmar", type="primary", use_container_width=True):
                try:
                    count = aumento_masivo_precios(
                        st.session_state["user_id"],
                        porcentaje,
                        categoria_id=cat_id,
                        proveedor_id=prov_id,
                        campos=campos,
                    )
                    st.session_state.pop("confirmar_aumento", None)
                    st.success(f"{count} productos actualizados correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        with col_no:
            if st.button("Cancelar", use_container_width=True):
                st.session_state.pop("confirmar_aumento", None)
                st.rerun()
