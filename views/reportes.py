"""
views/reportes.py - Dashboard de reportes con gráficos Plotly.
Ventas por período, productos más vendidos, ganancia real, stock valorizado.
"""

import streamlit as st
import plotly.graph_objects as go
from datetime import date, timedelta

from controllers import (
    reporte_ventas_periodo,
    reporte_productos_vendidos,
    reporte_ganancia,
    reporte_stock_valorizado,
)


def render():
    st.header("📊 Reportes y Dashboard")

    tab_ventas, tab_productos, tab_ganancia, tab_stock = st.tabs([
        "Ventas por Período",
        "Productos Más Vendidos",
        "Ganancia Real",
        "Stock Valorizado",
    ])

    with tab_ventas:
        _render_ventas_periodo()

    with tab_productos:
        _render_productos_vendidos()

    with tab_ganancia:
        _render_ganancia()

    with tab_stock:
        _render_stock_valorizado()


# ---------------------------------------------------------------------------
# Tab: Ventas por Período
# ---------------------------------------------------------------------------

def _render_ventas_periodo():
    col1, col2, col3 = st.columns(3)
    with col1:
        fecha_desde = st.date_input(
            "Desde", value=date.today() - timedelta(days=30),
            key="rp_desde",
        )
    with col2:
        fecha_hasta = st.date_input("Hasta", value=date.today(), key="rp_hasta")
    with col3:
        agrupacion = st.selectbox(
            "Agrupar por",
            ["dia", "semana", "mes"],
            format_func=lambda x: {"dia": "Día", "semana": "Semana", "mes": "Mes"}[x],
            key="rp_agrup",
        )

    datos = reporte_ventas_periodo(fecha_desde, fecha_hasta, agrupacion)

    if not datos:
        st.info("No hay datos para el período seleccionado.")
        return

    periodos = [d["periodo"] for d in datos]
    totales = [d["total"] for d in datos]
    cantidades = [d["cantidad"] for d in datos]

    # Métricas
    total_vendido = sum(totales)
    total_ops = sum(cantidades)
    dias_periodo = max((fecha_hasta - fecha_desde).days, 1)
    promedio_diario = total_vendido / dias_periodo
    ticket_promedio = total_vendido / total_ops if total_ops > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Vendido", f"${total_vendido:,.2f}")
    m2.metric("Operaciones", f"{total_ops}")
    m3.metric("Promedio Diario", f"${promedio_diario:,.2f}")
    m4.metric("Ticket Promedio", f"${ticket_promedio:,.2f}")

    # Gráfico
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=periodos, y=totales,
        name="Monto Vendido",
        marker_color="#2ecc71",
    ))
    fig.add_trace(go.Scatter(
        x=periodos, y=cantidades,
        name="Operaciones",
        yaxis="y2",
        mode="lines+markers",
        line=dict(color="#3498db", width=2),
        marker=dict(size=6),
    ))
    fig.update_layout(
        title="Ventas por Período",
        yaxis=dict(title="Monto ($)", side="left"),
        yaxis2=dict(title="Operaciones", side="right", overlaying="y"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Tab: Productos Más Vendidos
# ---------------------------------------------------------------------------

def _render_productos_vendidos():
    col1, col2 = st.columns(2)
    with col1:
        fecha_desde = st.date_input(
            "Desde", value=date.today() - timedelta(days=30),
            key="pp_desde",
        )
    with col2:
        fecha_hasta = st.date_input("Hasta", value=date.today(), key="pp_hasta")

    datos = reporte_productos_vendidos(fecha_desde, fecha_hasta, limit=10)

    if not datos:
        st.info("No hay datos para el período seleccionado.")
        return

    nombres = [d["producto"] for d in datos]
    cantidades = [d["cantidad"] for d in datos]
    montos = [d["monto"] for d in datos]

    # Dos gráficos lado a lado
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        fig_cant = go.Figure(go.Bar(
            y=nombres[::-1], x=cantidades[::-1],
            orientation="h",
            marker_color="#e74c3c",
        ))
        fig_cant.update_layout(
            title="Top 10 por Cantidad",
            xaxis_title="Cantidad Vendida",
            height=400,
            margin=dict(l=150),
        )
        st.plotly_chart(fig_cant, use_container_width=True)

    with col_g2:
        fig_monto = go.Figure(go.Bar(
            y=nombres[::-1], x=montos[::-1],
            orientation="h",
            marker_color="#9b59b6",
        ))
        fig_monto.update_layout(
            title="Top 10 por Monto",
            xaxis_title="Monto ($)",
            height=400,
            margin=dict(l=150),
        )
        st.plotly_chart(fig_monto, use_container_width=True)

    # Tabla detallada
    st.subheader("Detalle")
    tabla = [
        {
            "Producto": d["producto"],
            "Cantidad": f"{d['cantidad']:g}",
            "Monto Total": f"${d['monto']:,.2f}",
        }
        for d in datos
    ]
    st.dataframe(tabla, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Tab: Ganancia Real
# ---------------------------------------------------------------------------

def _render_ganancia():
    col1, col2, col3 = st.columns(3)
    with col1:
        fecha_desde = st.date_input(
            "Desde", value=date.today() - timedelta(days=30),
            key="rg_desde",
        )
    with col2:
        fecha_hasta = st.date_input("Hasta", value=date.today(), key="rg_hasta")
    with col3:
        agrupacion = st.selectbox(
            "Agrupar por",
            ["dia", "semana", "mes"],
            format_func=lambda x: {"dia": "Día", "semana": "Semana", "mes": "Mes"}[x],
            key="rg_agrup",
        )

    datos = reporte_ganancia(fecha_desde, fecha_hasta, agrupacion)

    if not datos:
        st.info("No hay datos para el período seleccionado.")
        return

    # Métricas globales
    total_ventas = sum(d["ventas"] for d in datos)
    total_costo = sum(d["costo"] for d in datos)
    total_gastos = sum(d["gastos"] for d in datos)
    ganancia_bruta = total_ventas - total_costo
    ganancia_neta = ganancia_bruta - total_gastos
    margen_bruto = (ganancia_bruta / total_ventas * 100) if total_ventas > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ventas Totales", f"${total_ventas:,.2f}")
    m2.metric("Costo Mercadería", f"${total_costo:,.2f}")
    m3.metric("Ganancia Bruta", f"${ganancia_bruta:,.2f}",
              delta=f"{margen_bruto:.1f}% margen")
    m4.metric("Ganancia Neta", f"${ganancia_neta:,.2f}",
              delta=f"-${total_gastos:,.2f} gastos", delta_color="inverse")

    # Gráfico
    periodos = [d["periodo"] for d in datos]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=periodos, y=[d["ventas"] for d in datos],
        name="Ventas", marker_color="#2ecc71",
    ))
    fig.add_trace(go.Bar(
        x=periodos, y=[d["costo"] for d in datos],
        name="Costo Mercadería", marker_color="#e74c3c",
    ))
    fig.add_trace(go.Bar(
        x=periodos, y=[d["gastos"] for d in datos],
        name="Gastos", marker_color="#f39c12",
    ))
    fig.add_trace(go.Scatter(
        x=periodos, y=[d["ganancia_neta"] for d in datos],
        name="Ganancia Neta",
        mode="lines+markers",
        line=dict(color="#3498db", width=3),
        marker=dict(size=8),
    ))
    fig.update_layout(
        title="Ganancia por Período",
        barmode="group",
        yaxis_title="Monto ($)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tabla detallada
    st.subheader("Detalle por Período")
    tabla = [
        {
            "Período": d["periodo"],
            "Ventas": f"${d['ventas']:,.2f}",
            "Costo": f"${d['costo']:,.2f}",
            "Gastos": f"${d['gastos']:,.2f}",
            "Ganancia Bruta": f"${d['ganancia_bruta']:,.2f}",
            "Ganancia Neta": f"${d['ganancia_neta']:,.2f}",
            "Margen %": f"{d['margen_pct']}%",
        }
        for d in datos
    ]
    st.dataframe(tabla, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Tab: Stock Valorizado
# ---------------------------------------------------------------------------

def _render_stock_valorizado():
    datos = reporte_stock_valorizado()

    st.metric("💰 Total Invertido en Mercadería", f"${datos['total']:,.2f}")

    por_cat = datos["por_categoria"]
    if not por_cat:
        st.info("No hay stock cargado.")
        return

    categorias = list(por_cat.keys())
    valores = list(por_cat.values())

    # Gráfico de torta
    fig = go.Figure(go.Pie(
        labels=categorias,
        values=valores,
        hole=0.35,
        textinfo="label+percent",
        textposition="outside",
        marker=dict(colors=[
            "#2ecc71", "#3498db", "#e74c3c", "#f39c12", "#9b59b6",
            "#1abc9c", "#e67e22", "#34495e", "#16a085", "#c0392b",
        ]),
    ))
    fig.update_layout(
        title="Stock Valorizado por Categoría",
        height=450,
        showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tabla
    tabla = [
        {"Categoría": cat, "Valor": f"${val:,.2f}"}
        for cat, val in sorted(por_cat.items(), key=lambda x: x[1], reverse=True)
    ]
    st.dataframe(tabla, use_container_width=True, hide_index=True)
