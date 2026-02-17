# Fase 3: Import, Barcode, Backup, Seguridad y Listas de Precios

## Resumen

Cinco módulos para el ERP "Aquí y Ahora":
1. Importación masiva de productos (CSV/Excel)
2. Lector de código de barras por cámara (búsqueda rápida en ventas)
3. Backup JSON mejorado + restore
4. Seguridad: cambio de contraseña
5. Múltiples listas de precios (descuento por cliente + precio fijo por producto)

## Dependencias nuevas

- `pandas` — parseo de CSV/Excel
- `openpyxl` — lectura de archivos .xlsx

## 1. Importación Masiva de Productos

**Vista:** Nueva tab "Importar" en `views/productos.py`.

**Flujo:**
1. `st.file_uploader` acepta `.csv` y `.xlsx`
2. pandas parsea el archivo y muestra tabla preview
3. Mapeo de columnas: el usuario confirma qué columna corresponde a qué campo
4. Validación: código duplicado, campos requeridos, categoría/proveedor existente
5. Dos modos: "Crear nuevos" (solo crea) y "Actualizar existentes" (actualiza precios por código)
6. Resumen post-importación: X creados, Y actualizados, Z errores con detalle

**Columnas esperadas:** codigo, nombre, precio_costo, precio_venta_mayorista, categoria, proveedor, unidad_medida, stock_actual, margen_minorista_pct

**Controllers nuevos:**
- `importar_productos(usuario_id, datos: list[dict], modo: str) -> dict` — retorna resumen {creados, actualizados, errores}

## 2. Lector de Código de Barras (Cámara)

**Enfoque:** Componente HTML/JS con `html5-qrcode` embebido via `st.components.v1.html()`.

**Flujo:**
1. En "Nueva Venta", botón "📷 Escanear" abre un componente con la cámara
2. La cámara detecta código (EAN-13, QR, o código interno)
3. El código escaneado se busca en `productos.codigo`
4. Si encuentra match → agrega al carrito con cantidad 1 (precio según tipo de venta)
5. Si no encuentra → muestra "Producto no encontrado" con el código leído

**Implementación:**
- `utils/barcode_scanner.py` — función que retorna el HTML/JS del scanner
- Comunicación JS→Streamlit via `streamlit-js-eval` pattern (query param o session)
- Sin dependencias externas — todo HTML/JS inline con CDN de html5-qrcode

**Cambios en ventas.py:**
- Agregar campo de búsqueda rápida por código (text_input + búsqueda)
- Botón "📷 Escanear" que abre el scanner
- Auto-add al carrito cuando se detecta un código válido

## 3. Backup JSON Mejorado + Restore

**Backup mejorado:**
- Incluir todas las tablas (incluyendo CajaDiaria, RetiroEfectivo, Devolucion, PrecioEspecial)
- Metadata: fecha, versión, cantidad de registros por tabla
- JSON indentado legible
- Nombre de archivo: `backup_aqui_y_ahora_YYYY-MM-DD.json`

**Restore:**
- `st.file_uploader` para subir JSON
- Preview: resumen de registros por tabla
- Modo merge: solo agrega registros que no existen (por ID)
- Confirmación obligatoria con warning
- Auditoría de la operación

**Controllers nuevos:**
- `generar_backup_completo() -> dict` — genera el dict completo
- `restaurar_backup(usuario_id, data: dict) -> dict` — retorna resumen {tabla: registros_restaurados}

**Vista:** Mejorar tab en `views/admin.py` → "Backup y Restauración"

## 4. Seguridad: Cambio de Contraseña

**Cambio propio:**
- Botón en sidebar "🔑 Cambiar contraseña"
- Formulario: contraseña actual + nueva + confirmar nueva
- Validación: mínimo 4 caracteres, nueva ≠ actual, coinciden nueva/confirmar

**Reset por admin:**
- En Administración → Usuarios, botón "Resetear contraseña" por usuario
- Genera contraseña temporal (mostrada una sola vez)

**Sin timeout de sesión** — se mantiene el comportamiento por defecto de Streamlit (sesión hasta cerrar pestaña).

**Controllers nuevos:**
- `cambiar_password(usuario_id, password_actual, password_nueva) -> bool`
- `resetear_password(admin_id, target_usuario_id) -> str` — retorna contraseña temporal

**Cambios en auth.py:** Agregar lógica de cambio de contraseña.

## 5. Múltiples Listas de Precios

**Modelo híbrido:**
- `Cliente.descuento_general_pct` (Float, default=0) — campo nuevo en tabla existente
- `PrecioEspecial` (tabla nueva): cliente_id + producto_id + precio_fijo

**Prioridad de precios en venta:**
1. Si existe `PrecioEspecial(cliente, producto)` → usa precio fijo
2. Si cliente tiene `descuento_general_pct > 0` → aplica descuento sobre precio mayorista
3. Si no → precio normal (mayorista o minorista según tipo de venta)

**Modelo nuevo: `PrecioEspecial`:**
- id, cliente_id (FK), producto_id (FK)
- precio_fijo (Float)
- activo (Boolean, default=True)
- Unique constraint: (cliente_id, producto_id)

**Controllers nuevos:**
- `obtener_precio_cliente(cliente_id, producto_id, tipo_venta) -> float` — resuelve el precio
- `asignar_precio_especial(usuario_id, cliente_id, producto_id, precio) -> PrecioEspecial`
- `listar_precios_especiales(cliente_id) -> list`
- `eliminar_precio_especial(usuario_id, precio_especial_id)`

**Cambios en ventas.py:**
- Cuando se selecciona un cliente, recalcular precios del carrito
- Badge visual: "🏷️ Precio especial" o "🏷️ -X% descuento"

**Cambios en clientes.py:**
- Nueva tab "Precios Especiales" con:
  - `descuento_general_pct` editable
  - Tabla de precios fijos por producto (CRUD)

## Migraciones

- `Cliente.descuento_general_pct` — ALTER TABLE ADD COLUMN
- `PrecioEspecial` — CREATE TABLE (via create_all)

## Orden de implementación

1. **Database**: PrecioEspecial + campo descuento_general_pct + migraciones
2. **Controllers**: Import, backup/restore, password, precios especiales
3. **utils/barcode_scanner.py**: Componente HTML/JS del scanner
4. **views/productos.py**: Tab de importación masiva
5. **views/admin.py**: Backup mejorado + restore
6. **views/clientes.py**: Tab precios especiales
7. **views/ventas.py**: Scanner + precios dinámicos por cliente
8. **auth.py + sidebar**: Cambio de contraseña
9. **app.py + requirements.txt**: Wiring + dependencias
10. **Verificación**: Sintaxis, imports, migraciones
11. **Deploy**: Commit, PR, merge
