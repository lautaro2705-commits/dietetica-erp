"""
utils/cache.py - Caché ligero en session_state con TTL para evitar
re-queries en cada rerun de Streamlit.

En Streamlit, CADA interacción re-ejecuta todo el script.
Este módulo almacena resultados en session_state con timestamps
y los reusa si no pasó el TTL.

Las funciones de escritura llaman a invalidar_cache_*() para forzar
la recarga de datos frescos en el próximo rerun.
"""
from __future__ import annotations

import time
import streamlit as st

# TTL en segundos
TTL_CORTO = 15       # datos que cambian seguido (caja, ventas recientes)
TTL_MEDIO = 60       # datos que cambian poco (productos, clientes, stock)
TTL_LARGO = 180      # datos casi estáticos (categorías, proveedores, usuarios)


def cached_query(key: str, query_fn, ttl: int = TTL_MEDIO, *args, **kwargs):
    """
    Ejecuta query_fn solo si el caché expiró o fue invalidado.
    Almacena resultado + timestamp en st.session_state.

    Args:
        key: Clave única del caché (ej: "productos_activos")
        query_fn: Función que ejecuta la query (callable)
        ttl: Tiempo de vida en segundos
        *args, **kwargs: Argumentos para query_fn

    Returns:
        Resultado cacheado o fresco de la query.
    """
    cache_key = f"_cache_{key}"
    ts_key = f"_cache_ts_{key}"

    now = time.time()
    cached_ts = st.session_state.get(ts_key, 0)

    if now - cached_ts < ttl and cache_key in st.session_state:
        return st.session_state[cache_key]

    # Ejecutar query fresca
    result = query_fn(*args, **kwargs)
    st.session_state[cache_key] = result
    st.session_state[ts_key] = now
    return result


def invalidar(key: str):
    """Invalida un caché específico por clave."""
    cache_key = f"_cache_{key}"
    ts_key = f"_cache_ts_{key}"
    st.session_state.pop(cache_key, None)
    st.session_state.pop(ts_key, None)


def invalidar_grupo(prefijo: str):
    """Invalida todos los cachés cuya clave empieza con el prefijo dado."""
    keys_to_remove = [
        k for k in st.session_state
        if k.startswith(f"_cache_{prefijo}") or k.startswith(f"_cache_ts_{prefijo}")
    ]
    for k in keys_to_remove:
        del st.session_state[k]


def invalidar_cache_productos():
    """Limpia caches de productos, fracciones, stock."""
    invalidar_grupo("productos")
    invalidar_grupo("fracciones")
    invalidar_grupo("stock")
    invalidar_grupo("reporte_stock")


def invalidar_cache_ventas():
    """Limpia caches de ventas, caja, reportes."""
    invalidar_grupo("ventas")
    invalidar_grupo("caja")
    invalidar_grupo("reporte")


def invalidar_cache_clientes():
    """Limpia caches de clientes y cuenta corriente."""
    invalidar_grupo("clientes")
    invalidar_grupo("movimientos_cuenta")
    invalidar_grupo("precios_especiales")


def invalidar_cache_catalogos():
    """Limpia caches de categorías, proveedores, usuarios."""
    invalidar_grupo("categorias")
    invalidar_grupo("proveedores")
    invalidar_grupo("usuarios")


def invalidar_cache_caja():
    """Limpia caches de caja diaria."""
    invalidar_grupo("caja")
    invalidar_grupo("retiros")


def invalidar_cache_gastos():
    """Limpia caches de gastos."""
    invalidar_grupo("gastos")
    invalidar_grupo("caja")  # caja depende de gastos


def invalidar_todo():
    """Limpia absolutamente todo el caché."""
    keys_to_remove = [
        k for k in st.session_state
        if k.startswith("_cache_")
    ]
    for k in keys_to_remove:
        del st.session_state[k]
