"""
app.py - Entry point del ERP Dietética Mayorista.
Ejecutar: streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Dietética ERP",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

from database import init_db
from auth import require_login, require_admin, logout
from views import productos, ventas, stock, precios, gastos, caja, auditoria, admin

# Inicializar base de datos
init_db()

# --- Guard: Login ---
if not require_login():
    st.stop()

# --- Sidebar: Navegación ---
with st.sidebar:
    st.markdown(f"### 🌱 Dietética ERP")
    st.caption(f"Sesión: **{st.session_state['nombre']}** ({st.session_state['rol'].upper()})")
    st.divider()

    # Menú dinámico según rol
    paginas = {
        "Ventas": "ventas",
        "Productos": "productos",
        "Stock": "stock",
        "Caja Diaria": "caja",
        "Gastos": "gastos",
    }
    if require_admin():
        paginas["Precios Masivos"] = "precios"
        paginas["Auditoría"] = "auditoria"
        paginas["Administración"] = "admin"

    seleccion = st.radio("Navegación", list(paginas.keys()), label_visibility="collapsed")

    st.divider()
    if st.button("Cerrar Sesión", use_container_width=True):
        logout()

# --- Renderizar vista seleccionada ---
vista = paginas[seleccion]

try:
    if vista == "productos":
        productos.render()
    elif vista == "ventas":
        ventas.render()
    elif vista == "stock":
        stock.render()
    elif vista == "precios":
        precios.render()
    elif vista == "gastos":
        gastos.render()
    elif vista == "caja":
        caja.render()
    elif vista == "auditoria":
        auditoria.render()
    elif vista == "admin":
        admin.render()
except Exception as e:
    st.error(f"Error inesperado: {e}")
    st.caption("Si el problema persiste, contactá al administrador del sistema.")
