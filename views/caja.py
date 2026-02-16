"""
views/caja.py - Resumen diario de caja.
"""

import streamlit as st
from datetime import date, timedelta
from controllers import resumen_caja


def render():
    st.header("Caja Diaria")

    fecha = st.date_input("Fecha", value=date.today())
    resumen = resumen_caja(fecha)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ventas del Día", f"${resumen['total_ventas']:,.2f}")
    col2.metric("Gastos del Día", f"${resumen['total_gastos']:,.2f}")
    col3.metric(
        "Balance",
        f"${resumen['balance']:,.2f}",
        delta=f"${resumen['balance']:,.2f}",
        delta_color="normal",
    )
    col4.metric("Cantidad de Ventas", resumen["cant_ventas"])

    # Resumen semanal
    st.divider()
    st.subheader("Resumen Últimos 7 Días")

    datos_semana = []
    for i in range(6, -1, -1):
        dia = date.today() - timedelta(days=i)
        r = resumen_caja(dia)
        datos_semana.append({
            "Fecha": dia.strftime("%d/%m"),
            "Ventas": r["total_ventas"],
            "Gastos": r["total_gastos"],
            "Balance": r["balance"],
        })

    st.dataframe(datos_semana, use_container_width=True, hide_index=True)

    # Totales de la semana
    total_ventas_sem = sum(d["Ventas"] for d in datos_semana)
    total_gastos_sem = sum(d["Gastos"] for d in datos_semana)
    balance_sem = total_ventas_sem - total_gastos_sem

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total Ventas (7 días)", f"${total_ventas_sem:,.2f}")
    col_b.metric("Total Gastos (7 días)", f"${total_gastos_sem:,.2f}")
    col_c.metric("Balance Semanal", f"${balance_sem:,.2f}")
