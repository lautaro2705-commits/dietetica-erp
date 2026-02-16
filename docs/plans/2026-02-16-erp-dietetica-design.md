# ERP Dietética Mayorista - Design Document

## Overview
Sistema de gestión para una Dietética Mayorista. Stack: Python + Streamlit + SQLite/SQLAlchemy.

## Architecture: Monolito Modular

```
dietetica-erp/
├── app.py              # Entry point + login + navegación
├── database.py         # SQLAlchemy models + engine setup
├── controllers.py      # Lógica de negocio (stock, ventas, precios)
├── auth.py             # Autenticación y gestión de sesión
├── views/
│   ├── __init__.py
│   ├── productos.py    # ABM productos + fracciones
│   ├── ventas.py       # Registrar ventas + historial
│   ├── stock.py        # Movimientos de stock + alertas
│   ├── precios.py      # Actualización masiva de precios
│   ├── gastos.py       # Registro de gastos operativos
│   ├── caja.py         # Resumen diario de caja
│   ├── auditoria.py    # Visor de logs inmutables
│   └── admin.py        # Gestión usuarios + backup DB
├── requirements.txt
├── .gitignore
└── README.md
```

## Data Model

### Usuarios
- id, username, password_hash, nombre, rol (admin/vendedor), activo, created_at

### Categorias
- id, nombre, activo

### Proveedores
- id, nombre, contacto, telefono, activo

### Productos (Padre/Bulto)
- id, codigo, nombre, descripcion, categoria_id, proveedor_id
- unidad_medida (kg, litro, unidad), contenido_total (ej: 25 para bolsa 25kg)
- precio_costo, precio_venta_mayorista, margen_minorista_pct
- stock_actual, stock_minimo, activo, created_at, updated_at

### Fracciones
- id, producto_padre_id, nombre (ej: "500g"), cantidad (0.5)
- precio_venta (override manual, nullable — si null usa margen automático)
- activo

### Ventas
- id, usuario_id, fecha, tipo (mayorista/minorista), total, observaciones

### DetalleVenta
- id, venta_id, producto_id, fraccion_id (nullable), cantidad, precio_unitario, subtotal

### MovimientosStock
- id, producto_id, tipo (entrada/salida/ajuste), cantidad, referencia, usuario_id, fecha

### Gastos
- id, descripcion, monto, categoria_gasto, fecha, usuario_id, activo

### Auditoria (INMUTABLE — sin soft delete)
- id, usuario_id, accion, tabla_afectada, registro_id, valor_anterior (JSON), valor_nuevo (JSON), fecha

## Key Business Logic

### Stock Dual
- Venta por bulto: descuenta 1 unidad del stock del producto padre
- Venta fraccionada: descuenta fraccion.cantidad del contenido del producto padre
- Precio fraccionado: usa fraccion.precio_venta si existe, sino calcula (precio_costo / contenido_total * cantidad * (1 + margen_minorista_pct/100))

### Actualización Masiva de Precios
- Filtrar por categoría O proveedor
- Aplicar % de aumento a precio_costo, precio_venta_mayorista (y recalcular minorista)
- Generar registro de auditoría por cada producto modificado

### Auditoría
- Toda operación CUD genera log
- Soft delete: activo=False, nunca DELETE real
- Log inmutable: la tabla Auditoria no tiene UPDATE ni DELETE

### Roles
- Admin: acceso total + gestión usuarios + backup
- Vendedor: ventas, consultar stock, consultar precios (sin modificar)
