"""
views/caja.py - Resumen diario de caja con desglose por método de pago.
"""

import streamlit as st
from datetime import date, timedelta
from controllers import resumen_caja


def render():
    st.header("Caja Diaria")

    fecha = st.date_input("Fecha", value=date.today())
    resumen = resumen_caja(fecha)

    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ventas del Día", f"${resumen['total_ventas']:,.2f}")
    col2.metric("Cobrado Real", f"${resumen['cobrado_real']:,.2f}",
                help="Efectivo + Transferencias (sin cuenta corriente)")
    col3.metric("Gastos del Día", f"${resumen['total_gastos']:,.2f}")
    col4.metric("Cantidad de Ventas", resumen["cant_ventas"])

    # Balance
    col_b1, col_b2 = st.columns(2)
    col_b1.metric(
        "Balance Total",
        f"${resumen['balance']:,.2f}",
        delta=f"${resumen['balance']:,.2f}",
        delta_color="normal",
        help="Total ventas (incluye cuenta corriente) - Gastos",
    )
    col_b2.metric(
        "Balance Real (Caja)",
        f"${resumen['balance_real']:,.2f}",
        delta=f"${resumen['balance_real']:,.2f}",
        delta_color="normal",
        help="Solo efectivo + transferencias - Gastos",
    )

    # Desglose por método de pago
    st.divider()
    st.subheader("Desglose por Método de Pago")

    desglose = resumen.get("desglose_pago", {})
    col_e, col_t, col_c = st.columns(3)

    efectivo = desglose.get("efectivo", 0)
    transferencia = desglose.get("transferencia", 0)
    cuenta_cte = desglose.get("cuenta_corriente", 0)

    col_e.metric("💵 Efectivo", f"${efectivo:,.2f}")
    col_t.metric("🏦 Transferencia", f"${transferencia:,.2f}")
    col_c.metric("📋 Cuenta Corriente", f"${cuenta_cte:,.2f}")

    if cuenta_cte > 0:
        st.caption(
            f"⚠️ ${cuenta_cte:,.2f} vendidos a cuenta corriente "
            f"(pendiente de cobro)."
        )

    # Resumen semanal
    st.divider()
    st.subheader("Resumen Últimos 7 Días")

    datos_semana = []
    for i in range(6, -1, -1):
        dia = date.today() - timedelta(days=i)
        r = resumen_caja(dia)
        desg = r.get("desglose_pago", {})
        datos_semana.append({
            "Fecha": dia.strftime("%d/%m"),
            "Ventas": r["total_ventas"],
            "Efectivo": desg.get("efectivo", 0),
            "Transferencia": desg.get("transferencia", 0),
            "Cta. Cte.": desg.get("cuenta_corriente", 0),
            "Gastos": r["total_gastos"],
            "Balance Real": r["balance_real"],
        })

    st.dataframe(datos_semana, use_container_width=True, hide_index=True)

    # Totales de la semana
    total_ventas_sem = sum(d["Ventas"] for d in datos_semana)
    total_efectivo_sem = sum(d["Efectivo"] for d in datos_semana)
    total_transf_sem = sum(d["Transferencia"] for d in datos_semana)
    total_cta_sem = sum(d["Cta. Cte."] for d in datos_semana)
    total_gastos_sem = sum(d["Gastos"] for d in datos_semana)
    cobrado_sem = total_efectivo_sem + total_transf_sem
    balance_sem = cobrado_sem - total_gastos_sem

    st.markdown("#### Totales Semanales")
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total Ventas (7 días)", f"${total_ventas_sem:,.2f}")
    col_b.metric("Total Cobrado (7 días)", f"${cobrado_sem:,.2f}")
    col_c.metric("Balance Semanal Real", f"${balance_sem:,.2f}")

    if total_cta_sem > 0:
        st.caption(
            f"📋 Acumulado en cuenta corriente esta semana: "
            f"${total_cta_sem:,.2f}"
        )
