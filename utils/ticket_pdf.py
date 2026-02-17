"""
utils/ticket_pdf.py - Generación de tickets de venta en PDF.
Formato: 80mm de ancho (estándar ticket térmico).
"""

from io import BytesIO
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import landscape
from reportlab.pdfgen import canvas

from controllers import obtener_venta, obtener_detalle_venta


# Ancho 80mm, alto dinámico (se calcula según items)
TICKET_WIDTH = 80 * mm


def generar_ticket_pdf(venta_id: int) -> bytes:
    """Genera un ticket PDF en memoria y retorna los bytes."""
    venta = obtener_venta(venta_id)
    if not venta:
        raise ValueError(f"Venta #{venta_id} no encontrada")

    detalles = obtener_detalle_venta(venta_id)

    # Calcular alto dinámico: encabezado + items + pie
    n_items = len(detalles)
    alto_base = 160  # mm para encabezado, separadores y pie
    alto_items = n_items * 12  # ~12mm por item (nombre + precio)
    alto_total = (alto_base + alto_items) * mm

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(TICKET_WIDTH, alto_total))

    y = alto_total - 10 * mm  # Empezar desde arriba

    # --- Encabezado ---
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(TICKET_WIDTH / 2, y, "Aquí y Ahora")
    y -= 5 * mm
    c.setFont("Helvetica", 7)
    c.drawCentredString(TICKET_WIDTH / 2, y, "Dietética Mayorista")
    y -= 6 * mm

    # Línea separadora
    c.setLineWidth(0.5)
    c.line(3 * mm, y, TICKET_WIDTH - 3 * mm, y)
    y -= 5 * mm

    # --- Datos de la venta ---
    c.setFont("Helvetica", 8)
    c.drawString(3 * mm, y, f"Venta: #{venta.id}")
    c.drawRightString(TICKET_WIDTH - 3 * mm, y, venta.fecha.strftime("%d/%m/%Y %H:%M"))
    y -= 4 * mm

    vendedor = venta.usuario.nombre if venta.usuario else "—"
    c.drawString(3 * mm, y, f"Vendedor: {vendedor}")
    y -= 4 * mm

    tipo_label = "Mayorista" if venta.tipo == "mayorista" else "Minorista"
    c.drawString(3 * mm, y, f"Tipo: {tipo_label}")
    y -= 4 * mm

    metodo = getattr(venta, "metodo_pago", "efectivo") or "efectivo"
    pago_label = {"efectivo": "Efectivo", "transferencia": "Transferencia",
                  "cuenta_corriente": "Cuenta Corriente"}.get(metodo, metodo)
    c.drawString(3 * mm, y, f"Pago: {pago_label}")
    y -= 4 * mm

    if venta.cliente:
        c.drawString(3 * mm, y, f"Cliente: {venta.cliente.nombre}")
        y -= 4 * mm

    # Línea separadora
    y -= 2 * mm
    c.line(3 * mm, y, TICKET_WIDTH - 3 * mm, y)
    y -= 5 * mm

    # --- Cabecera de items ---
    c.setFont("Helvetica-Bold", 7)
    c.drawString(3 * mm, y, "Producto")
    c.drawString(45 * mm, y, "Cant")
    c.drawString(55 * mm, y, "P.Unit")
    c.drawRightString(TICKET_WIDTH - 3 * mm, y, "Subtotal")
    y -= 4 * mm
    c.line(3 * mm, y, TICKET_WIDTH - 3 * mm, y)
    y -= 4 * mm

    # --- Items ---
    c.setFont("Helvetica", 7)
    for d in detalles:
        nombre_prod = d.producto.nombre if d.producto else "—"
        frac_label = f" ({d.fraccion.nombre})" if d.fraccion else ""
        nombre_completo = f"{nombre_prod}{frac_label}"

        # Truncar nombre si es muy largo
        if len(nombre_completo) > 25:
            nombre_completo = nombre_completo[:24] + "…"

        c.drawString(3 * mm, y, nombre_completo)
        c.drawString(45 * mm, y, f"{d.cantidad:g}")
        c.drawString(55 * mm, y, f"${d.precio_unitario:,.0f}")
        c.drawRightString(TICKET_WIDTH - 3 * mm, y, f"${d.subtotal:,.2f}")
        y -= 4 * mm

    # Línea separadora
    y -= 2 * mm
    c.line(3 * mm, y, TICKET_WIDTH - 3 * mm, y)
    y -= 6 * mm

    # --- Total ---
    c.setFont("Helvetica-Bold", 12)
    c.drawString(3 * mm, y, "TOTAL:")
    c.drawRightString(TICKET_WIDTH - 3 * mm, y, f"${venta.total:,.2f}")
    y -= 8 * mm

    # --- Observaciones ---
    if venta.observaciones:
        c.setFont("Helvetica", 7)
        c.drawString(3 * mm, y, f"Obs: {venta.observaciones[:50]}")
        y -= 5 * mm

    # --- Estado anulada ---
    anulada = getattr(venta, "anulada", False)
    if anulada:
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(TICKET_WIDTH / 2, y, "*** ANULADA ***")
        y -= 6 * mm

    # Línea separadora
    c.line(3 * mm, y, TICKET_WIDTH - 3 * mm, y)
    y -= 5 * mm

    # --- Pie ---
    c.setFont("Helvetica", 7)
    c.drawCentredString(TICKET_WIDTH / 2, y, "¡Gracias por su compra!")
    y -= 4 * mm
    c.drawCentredString(TICKET_WIDTH / 2, y, "Aquí y Ahora — Dietética Mayorista")

    c.save()
    buf.seek(0)
    return buf.read()


def generar_link_whatsapp(venta_id: int, total: float) -> str:
    """Genera un link wa.me para compartir los datos de la venta."""
    import urllib.parse
    texto = (
        f"📋 Ticket Venta #{venta_id}\n"
        f"💰 Total: ${total:,.2f}\n"
        f"🌱 Aquí y Ahora - Dietética Mayorista"
    )
    return f"https://wa.me/?text={urllib.parse.quote(texto)}"
