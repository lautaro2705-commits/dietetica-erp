# Fase 2: Reportes, Tickets, Devoluciones y Caja Mejorada

## Resumen

Cuatro módulos nuevos para el ERP "Aquí y Ahora":
1. Dashboard con gráficos Plotly (ventas, ganancia, stock valorizado)
2. Tickets PDF con opción de compartir por WhatsApp
3. Devoluciones y anulación de ventas
4. Caja diaria con apertura/cierre y retiros de efectivo

## Dependencias nuevas

- `plotly` — gráficos interactivos
- `reportlab` — generación de PDF

## 1. Reportes y Dashboard

**Vista:** `views/reportes.py` con 4 tabs.

**Tab "Ventas por período":**
- Selector de rango de fechas + agrupación (día/semana/mes)
- Gráfico de barras Plotly: monto vendido por período
- Línea superpuesta: cantidad de operaciones
- Métricas: total vendido, promedio diario, ticket promedio

**Tab "Productos más vendidos":**
- Top 10 por cantidad y por monto (dos gráficos de barras horizontales)
- Filtrable por rango de fechas
- Tabla detallada debajo

**Tab "Ganancia real":**
- Fórmula: ventas - costo_mercadería - gastos
- Requiere guardar `costo_unitario` en `DetalleVenta` (captura costo al momento de venta)
- Gráfico de barras: ganancia por día/semana/mes
- Métricas: margen bruto %, ganancia neta

**Tab "Stock valorizado":**
- SUM(stock_actual × precio_costo) por categoría
- Gráfico de torta Plotly
- Total invertido en mercadería

**Cambios en modelos:**
- `DetalleVenta.costo_unitario` (Float, nullable=True) — migración automática
- En `procesar_venta()`, guardar `prod.precio_costo` como `costo_unitario`

**Controllers nuevos:**
- `reporte_ventas_periodo(fecha_desde, fecha_hasta, agrupacion)`
- `reporte_productos_vendidos(fecha_desde, fecha_hasta, limit)`
- `reporte_ganancia(fecha_desde, fecha_hasta, agrupacion)`
- `reporte_stock_valorizado()`

## 2. Tickets PDF + WhatsApp

**Archivo:** `utils/ticket_pdf.py`

**Función principal:** `generar_ticket_pdf(venta_id) -> bytes`
- Usa ReportLab con Canvas
- Ancho 80mm (formato ticket térmico estándar)
- Contenido: logo texto "Aquí y Ahora", fecha/hora, nº venta, vendedor, cliente, tabla items, total, método de pago, pie
- Genera en memoria (BytesIO), no graba en disco

**Integración en ventas.py:**
- Post-confirmación: `st.download_button("📄 Descargar Ticket", pdf_bytes)`
- Botón WhatsApp: link `wa.me/?text=...` con datos de la venta
- En historial: botón para regenerar ticket de cualquier venta pasada

## 3. Devoluciones / Anulación

**Modelo nuevo: `Devolucion`**
- id, venta_id (FK), usuario_id (FK)
- fecha, motivo, tipo (anulacion_total | devolucion_parcial)
- monto_devuelto

**Cambio en Venta:** `anulada = Column(Boolean, default=False)` — con migración

**Lógica de anulación total:**
1. Marcar venta.anulada = True
2. Reingresar stock de cada item
3. Si fue cuenta_corriente: reducir saldo_cuenta_corriente del cliente
4. Crear MovimientoStock tipo "entrada" por cada item
5. Registrar Devolucion + Auditoria

**Lógica de devolución parcial:**
1. Seleccionar items y cantidades a devolver
2. Reingresar stock parcial
3. Si fue cuenta_corriente: reducir saldo parcial
4. Crear Devolucion con monto_devuelto parcial
5. Registrar auditoría

**Restricciones:** Solo admin. Confirmación obligatoria. Auditoría completa.

**UI en historial de ventas:** Botones "Anular" y "Devolución Parcial" dentro del expander de cada venta (ocultos para ventas ya anuladas).

## 4. Caja Diaria Mejorada

**Modelos nuevos:**

`CajaDiaria`:
- id, fecha (Date, unique)
- usuario_apertura_id (FK), usuario_cierre_id (FK nullable)
- monto_apertura, monto_cierre (nullable)
- estado: "abierta" | "cerrada"
- hora_apertura (DateTime), hora_cierre (DateTime nullable)
- observaciones_apertura, observaciones_cierre

`RetiroEfectivo`:
- id, caja_id (FK CajaDiaria), usuario_id (FK)
- monto, motivo, fecha (DateTime)

**Flujo operativo:**
1. Si no hay caja abierta hoy → mostrar "Abrir Caja" con monto inicial
2. Caja abierta → ventas habilitadas, retiros habilitados
3. Cerrar caja → conteo final, sistema muestra diferencia esperado vs real
4. Caja cerrada → ventas bloqueadas hasta el día siguiente

**Bloqueo de ventas:** En `views/ventas.py`, antes de renderizar, verificar si hay caja abierta hoy. Si no, mostrar warning y bloquear.

**Controllers:**
- `abrir_caja(usuario_id, monto_apertura, observaciones)`
- `cerrar_caja(usuario_id, monto_cierre, observaciones)`
- `obtener_caja_hoy() -> CajaDiaria | None`
- `registrar_retiro(usuario_id, caja_id, monto, motivo)`
- `listar_retiros(caja_id)`
- `caja_abierta_hoy() -> bool`

**Vista `views/caja.py` actualizada:**
- Tab "Apertura / Cierre": formularios según estado
- Tab "Retiros de Efectivo": registrar + listar retiros del día
- Tab "Resumen del Día": métricas actuales + cuadre de caja
- Tab "Resumen Semanal": existente con mejoras

**Cuadre de caja:**
- Esperado = apertura + ventas_efectivo - retiros - gastos_efectivo
- Real = monto_cierre (conteo manual)
- Diferencia = real - esperado

## Orden de implementación

1. **Database**: Modelos nuevos + migraciones (CajaDiaria, RetiroEfectivo, Devolucion, campos nuevos)
2. **Controllers**: Funciones de negocio para las 4 funcionalidades
3. **utils/ticket_pdf.py**: Generador de PDF
4. **views/reportes.py**: Dashboard completo con Plotly
5. **views/caja.py**: Reescritura con apertura/cierre/retiros
6. **views/ventas.py**: Tickets + devoluciones + bloqueo por caja
7. **app.py**: Wiring de reportes + dependencias
8. **Verificación**: Sintaxis, imports, migraciones
9. **Deploy**: Commit, PR, merge
