"""
views/caja.py - Caja diaria con apertura/cierre, retiros y resumen.
"""

import streamlit as st
from datetime import date, timedelta

from controllers import (
    resumen_caja,
    obtener_caja_hoy,
    caja_abierta_hoy,
    abrir_caja,
    cerrar_caja,
    registrar_retiro,
    listar_retiros,
)


def render():
    st.header("Caja Diaria")

    caja = obtener_caja_hoy()

    # Indicador de estado
    if caja and caja.estado == "abierta":
        st.success(
            f"✅ Caja **abierta** — Apertura: ${caja.monto_apertura:,.2f} "
            f"({caja.hora_apertura.strftime('%H:%M')})"
        )
    elif caja and caja.estado == "cerrada":
        st.info(
            f"🔒 Caja **cerrada** — Cierre: ${caja.monto_cierre:,.2f} "
            f"({caja.hora_cierre.strftime('%H:%M') if caja.hora_cierre else ''})"
        )
    else:
        st.warning("⚠️ No hay caja abierta hoy. Abrí la caja para habilitar ventas.")

    tab_apertura, tab_retiros, tab_resumen, tab_semanal = st.tabs([
        "Apertura / Cierre",
        "Retiros de Efectivo",
        "Resumen del Día",
        "Resumen Semanal",
    ])

    with tab_apertura:
        _render_apertura_cierre(caja)

    with tab_retiros:
        _render_retiros(caja)

    with tab_resumen:
        _render_resumen_dia(caja)

    with tab_semanal:
        _render_resumen_semanal()


# ---------------------------------------------------------------------------
# Tab: Apertura / Cierre
# ---------------------------------------------------------------------------

def _render_apertura_cierre(caja):
    if caja is None:
        # No hay caja hoy → formulario de apertura
        st.subheader("Abrir Caja")
        with st.form("form_abrir_caja"):
            monto = st.number_input(
                "Monto inicial en caja ($)",
                min_value=0.0, value=0.0, step=1000.0,
                help="Contá el efectivo y colocá el monto inicial.",
            )
            obs = st.text_area("Observaciones de apertura", max_chars=300)
            submitted = st.form_submit_button("Abrir Caja", type="primary")

        if submitted:
            try:
                abrir_caja(
                    st.session_state["user_id"],
                    monto,
                    obs,
                )
                st.success("Caja abierta correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al abrir caja: {e}")

    elif caja.estado == "abierta":
        # Caja abierta → formulario de cierre
        st.subheader("Cerrar Caja")

        # Calcular esperado
        resumen = resumen_caja(date.today())
        retiros_lista = listar_retiros(caja.id)
        total_retiros = sum(r.monto for r in retiros_lista)

        efectivo_ventas = resumen.get("desglose_pago", {}).get("efectivo", 0)
        gastos_del_dia = resumen["total_gastos"]

        esperado = caja.monto_apertura + efectivo_ventas - total_retiros - gastos_del_dia

        st.info(
            f"**Cálculo esperado:**\n\n"
            f"Apertura: ${caja.monto_apertura:,.2f} "
            f"+ Ventas efectivo: ${efectivo_ventas:,.2f} "
            f"- Retiros: ${total_retiros:,.2f} "
            f"- Gastos: ${gastos_del_dia:,.2f} "
            f"= **${esperado:,.2f}**"
        )

        with st.form("form_cerrar_caja"):
            monto_cierre = st.number_input(
                "Monto final contado en caja ($)",
                min_value=0.0, value=0.0, step=1000.0,
                help="Contá el efectivo y colocá el monto real.",
            )
            obs = st.text_area("Observaciones de cierre", max_chars=300)
            submitted = st.form_submit_button("Cerrar Caja", type="primary")

        if submitted:
            try:
                cerrar_caja(
                    st.session_state["user_id"],
                    monto_cierre,
                    obs,
                )
                st.success("Caja cerrada correctamente.")

                # Mostrar diferencia
                diferencia = monto_cierre - esperado
                if abs(diferencia) < 1:
                    st.balloons()
                    st.success("¡Caja cuadrada! Sin diferencias.")
                elif diferencia > 0:
                    st.warning(f"Sobrante de ${diferencia:,.2f}")
                else:
                    st.error(f"Faltante de ${abs(diferencia):,.2f}")

                st.rerun()
            except Exception as e:
                st.error(f"Error al cerrar caja: {e}")

    else:
        # Caja cerrada
        st.subheader("Caja cerrada")
        st.info(
            f"La caja de hoy ya fue cerrada por "
            f"**{caja.usuario_cierre.nombre if caja.usuario_cierre else '—'}** "
            f"a las {caja.hora_cierre.strftime('%H:%M') if caja.hora_cierre else '—'}."
        )
        if caja.observaciones_cierre:
            st.caption(f"Observaciones: {caja.observaciones_cierre}")


# ---------------------------------------------------------------------------
# Tab: Retiros de Efectivo
# ---------------------------------------------------------------------------

def _render_retiros(caja):
    if not caja or caja.estado != "abierta":
        st.info("Los retiros solo se pueden hacer con la caja abierta.")
        return

    st.subheader("Registrar Retiro")
    with st.form("form_retiro"):
        monto = st.number_input(
            "Monto a retirar ($)", min_value=0.0, step=500.0,
        )
        motivo = st.text_input("Motivo del retiro", max_chars=300)
        submitted = st.form_submit_button("Registrar Retiro", type="primary")

    if submitted:
        if monto <= 0:
            st.error("El monto debe ser mayor a cero.")
        else:
            try:
                registrar_retiro(
                    st.session_state["user_id"],
                    monto,
                    motivo,
                )
                st.success(f"Retiro de ${monto:,.2f} registrado.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al registrar retiro: {e}")

    # Listar retiros del día
    st.divider()
    st.subheader("Retiros del Día")

    retiros = listar_retiros(caja.id)
    if not retiros:
        st.caption("No hay retiros registrados hoy.")
    else:
        total_retiros = 0.0
        for r in retiros:
            col1, col2, col3 = st.columns([2, 1, 2])
            col1.write(f"${r.monto:,.2f}")
            col2.write(r.fecha.strftime("%H:%M"))
            col3.write(r.motivo or "—")
            total_retiros += r.monto
        st.markdown(f"**Total retiros: ${total_retiros:,.2f}**")


# ---------------------------------------------------------------------------
# Tab: Resumen del Día
# ---------------------------------------------------------------------------

def _render_resumen_dia(caja):
    resumen = resumen_caja(date.today())

    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ventas del Día", f"${resumen['total_ventas']:,.2f}")
    col2.metric("Cobrado Real", f"${resumen['cobrado_real']:,.2f}",
                help="Efectivo + Transferencias (sin cuenta corriente)")
    col3.metric("Gastos del Día", f"${resumen['total_gastos']:,.2f}")
    col4.metric("Cantidad de Ventas", resumen["cant_ventas"])

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

    # Cuadre de caja (solo si hay caja abierta o cerrada)
    if caja:
        st.divider()
        st.subheader("Cuadre de Caja")

        retiros_lista = listar_retiros(caja.id) if caja else []
        total_retiros = sum(r.monto for r in retiros_lista)

        esperado = caja.monto_apertura + efectivo - total_retiros - resumen["total_gastos"]

        col_a, col_b = st.columns(2)
        col_a.metric("Apertura", f"${caja.monto_apertura:,.2f}")
        col_b.metric("Retiros", f"${total_retiros:,.2f}")

        col_c, col_d = st.columns(2)
        col_c.metric("Esperado en Caja", f"${esperado:,.2f}",
                     help="Apertura + Ventas Efectivo - Retiros - Gastos")

        if caja.estado == "cerrada" and caja.monto_cierre is not None:
            diferencia = caja.monto_cierre - esperado
            col_d.metric(
                "Conteo Real",
                f"${caja.monto_cierre:,.2f}",
                delta=f"${diferencia:,.2f} diferencia",
                delta_color="normal" if abs(diferencia) < 1 else "inverse",
            )
        else:
            col_d.metric("Conteo Real", "— (caja abierta)")

    # Balance
    st.divider()
    col_b1, col_b2 = st.columns(2)
    col_b1.metric(
        "Balance Total",
        f"${resumen['balance']:,.2f}",
        help="Total ventas (incluye cuenta corriente) - Gastos",
    )
    col_b2.metric(
        "Balance Real (Caja)",
        f"${resumen['balance_real']:,.2f}",
        help="Solo efectivo + transferencias - Gastos",
    )


# ---------------------------------------------------------------------------
# Tab: Resumen Semanal
# ---------------------------------------------------------------------------

def _render_resumen_semanal():
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
