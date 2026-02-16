# Dietetica ERP - Sistema de Gestion Mayorista

Sistema de gestion (ERP) para una Dietetica Mayorista. Maneja stock dual (bulto/fraccion), ventas, precios masivos, gastos, caja diaria y auditoria completa.

## Stack

- **Python 3.10+**
- **Streamlit** (interfaz web)
- **SQLite + SQLAlchemy** (base de datos local)

## Instalacion

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/dietetica-erp.git
cd dietetica-erp

# 2. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar
streamlit run app.py
```

El sistema crea automaticamente la base de datos `dietetica.db` y el usuario admin en la primera ejecucion.

## Credenciales por Defecto

| Usuario | Contrasena | Rol   |
|---------|------------|-------|
| admin   | admin      | Admin |

**Importante:** Cambia la contrasena del admin despues del primer ingreso.

## Funcionalidades

### Productos
- ABM de productos con codigo, categoria, proveedor
- Stock dual: venta por bulto completo o por fraccion (ej: 500g de bolsa de 25kg)
- Multiples fracciones por producto con precio manual o automatico por margen

### Ventas
- Carrito de compras con seleccion de producto y fraccion
- Venta mayorista o minorista
- Descuento automatico de stock
- Historial con filtro por fecha

### Stock
- Registro de entradas, salidas y ajustes
- Alertas de stock bajo
- Historial de movimientos

### Precios
- Actualizacion masiva por categoria y/o proveedor
- Vista previa antes de aplicar
- Confirmacion obligatoria

### Gastos
- Registro de gastos operativos por categoria
- Historial con filtro por fecha

### Caja Diaria
- Resumen de ventas vs gastos del dia
- Balance diario y semanal

### Auditoria
- Log inmutable de todas las operaciones (quien, cuando, que, valores anteriores y nuevos)
- Soft delete: nada se borra, todo se marca como inactivo

### Administracion
- Gestion de usuarios (crear, activar/desactivar)
- Roles: Admin (acceso total) y Vendedor (ventas y consultas)
- Backup: descarga del archivo .db completo

## Estructura del Proyecto

```
dietetica-erp/
├── app.py              # Entry point + login + navegacion
├── database.py         # Modelos SQLAlchemy + config DB
├── controllers.py      # Logica de negocio
├── auth.py             # Autenticacion y sesion
├── views/
│   ├── productos.py    # ABM productos + fracciones
│   ├── ventas.py       # Registrar ventas + historial
│   ├── stock.py        # Movimientos de stock
│   ├── precios.py      # Actualizacion masiva de precios
│   ├── gastos.py       # Gastos operativos
│   ├── caja.py         # Resumen diario de caja
│   ├── auditoria.py    # Visor de logs
│   └── admin.py        # Usuarios + backup
├── requirements.txt
├── .gitignore
└── README.md
```

## Licencia

MIT
