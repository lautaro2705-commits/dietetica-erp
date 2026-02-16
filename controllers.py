"""
controllers.py - Lógica de negocio: stock, ventas, precios, auditoría.
"""
from __future__ import annotations

import json
from datetime import datetime, date

from sqlalchemy import func

from database import (
    SessionLocal, Producto, Fraccion, Venta, DetalleVenta,
    MovimientoStock, Auditoria, Gasto, Categoria, Proveedor,
    Usuario, hash_password,
)


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------

def registrar_auditoria(
    session, usuario_id: int, accion: str, tabla: str,
    registro_id: int | None = None,
    valor_anterior: dict | None = None,
    valor_nuevo: dict | None = None,
):
    """Registra un evento inmutable en la tabla de auditoría."""
    log = Auditoria(
        usuario_id=usuario_id,
        accion=accion,
        tabla_afectada=tabla,
        registro_id=registro_id,
        valor_anterior=json.dumps(valor_anterior or {}, ensure_ascii=False, default=str),
        valor_nuevo=json.dumps(valor_nuevo or {}, ensure_ascii=False, default=str),
    )
    session.add(log)


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

def crear_producto(usuario_id: int, **kwargs) -> Producto:
    session = SessionLocal()
    try:
        prod = Producto(**kwargs)
        session.add(prod)
        session.flush()
        registrar_auditoria(
            session, usuario_id, "CREAR", "productos",
            registro_id=prod.id, valor_nuevo=kwargs,
        )
        session.commit()
        session.refresh(prod)
        return prod
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def actualizar_producto(usuario_id: int, producto_id: int, **kwargs) -> Producto:
    session = SessionLocal()
    try:
        prod = session.query(Producto).get(producto_id)
        if not prod:
            raise ValueError("Producto no encontrado")

        anterior = {k: getattr(prod, k) for k in kwargs}
        for k, v in kwargs.items():
            setattr(prod, k, v)
        prod.updated_at = datetime.utcnow()

        registrar_auditoria(
            session, usuario_id, "MODIFICAR", "productos",
            registro_id=prod.id, valor_anterior=anterior, valor_nuevo=kwargs,
        )
        session.commit()
        session.refresh(prod)
        return prod
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def desactivar_producto(usuario_id: int, producto_id: int):
    session = SessionLocal()
    try:
        prod = session.query(Producto).get(producto_id)
        if not prod:
            raise ValueError("Producto no encontrado")
        anterior = {"activo": True}
        prod.activo = False
        prod.updated_at = datetime.utcnow()
        registrar_auditoria(
            session, usuario_id, "DESACTIVAR", "productos",
            registro_id=prod.id, valor_anterior=anterior,
            valor_nuevo={"activo": False},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_productos(solo_activos: bool = True):
    session = SessionLocal()
    try:
        q = session.query(Producto)
        if solo_activos:
            q = q.filter(Producto.activo == True)
        return q.order_by(Producto.nombre).all()
    finally:
        session.close()


def obtener_producto(producto_id: int) -> Producto | None:
    session = SessionLocal()
    try:
        return session.query(Producto).get(producto_id)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Fracciones
# ---------------------------------------------------------------------------

def crear_fraccion(usuario_id: int, producto_padre_id: int, nombre: str,
                   cantidad: float, precio_venta: float | None = None) -> Fraccion:
    session = SessionLocal()
    try:
        frac = Fraccion(
            producto_padre_id=producto_padre_id,
            nombre=nombre,
            cantidad=cantidad,
            precio_venta=precio_venta,
        )
        session.add(frac)
        session.flush()
        registrar_auditoria(
            session, usuario_id, "CREAR", "fracciones",
            registro_id=frac.id,
            valor_nuevo={"producto_padre_id": producto_padre_id,
                         "nombre": nombre, "cantidad": cantidad,
                         "precio_venta": precio_venta},
        )
        session.commit()
        session.refresh(frac)
        return frac
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_fracciones(producto_padre_id: int):
    session = SessionLocal()
    try:
        return (
            session.query(Fraccion)
            .filter_by(producto_padre_id=producto_padre_id, activo=True)
            .order_by(Fraccion.cantidad)
            .all()
        )
    finally:
        session.close()


def calcular_precio_fraccion(producto: Producto, fraccion: Fraccion) -> float:
    """Calcula el precio de venta de una fracción.
    Si tiene precio override, lo usa. Sino calcula por margen.
    """
    if fraccion.precio_venta is not None:
        return fraccion.precio_venta
    costo_por_unidad = producto.precio_costo / producto.contenido_total
    return round(costo_por_unidad * fraccion.cantidad * (1 + producto.margen_minorista_pct / 100), 2)


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------

def registrar_movimiento_stock(
    usuario_id: int, producto_id: int, tipo: str,
    cantidad: float, referencia: str = "",
):
    """Registra un movimiento y actualiza stock_actual del producto."""
    session = SessionLocal()
    try:
        prod = session.query(Producto).get(producto_id)
        if not prod:
            raise ValueError("Producto no encontrado")

        stock_anterior = prod.stock_actual

        if tipo == "entrada":
            prod.stock_actual += cantidad
        elif tipo == "salida":
            prod.stock_actual -= cantidad
        elif tipo == "ajuste":
            prod.stock_actual = cantidad
        else:
            raise ValueError(f"Tipo de movimiento inválido: {tipo}")

        if prod.stock_actual < 0:
            raise ValueError(
                f"Stock insuficiente. Stock actual: {stock_anterior}, "
                f"intentando descontar: {cantidad}"
            )

        mov = MovimientoStock(
            producto_id=producto_id,
            tipo=tipo,
            cantidad=cantidad,
            referencia=referencia,
            usuario_id=usuario_id,
        )
        session.add(mov)

        registrar_auditoria(
            session, usuario_id, "MOVIMIENTO_STOCK", "productos",
            registro_id=producto_id,
            valor_anterior={"stock_actual": stock_anterior},
            valor_nuevo={"stock_actual": prod.stock_actual, "movimiento": tipo,
                         "cantidad": cantidad},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def productos_bajo_stock():
    session = SessionLocal()
    try:
        return (
            session.query(Producto)
            .filter(Producto.activo == True)
            .filter(Producto.stock_actual <= Producto.stock_minimo)
            .order_by(Producto.stock_actual)
            .all()
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Ventas
# ---------------------------------------------------------------------------

def procesar_venta(
    usuario_id: int,
    tipo: str,
    items: list[dict],
    observaciones: str = "",
) -> Venta:
    """Procesa una venta completa.

    items: lista de dicts con:
        - producto_id: int
        - fraccion_id: int | None  (None = venta por bulto)
        - cantidad: float
    """
    session = SessionLocal()
    try:
        venta = Venta(
            usuario_id=usuario_id,
            tipo=tipo,
            observaciones=observaciones,
        )
        session.add(venta)
        session.flush()

        total = 0.0

        for item in items:
            prod = session.query(Producto).get(item["producto_id"])
            if not prod or not prod.activo:
                raise ValueError(f"Producto ID {item['producto_id']} no disponible")

            cantidad = item["cantidad"]
            fraccion_id = item.get("fraccion_id")

            if fraccion_id:
                # Venta fraccionada
                frac = session.query(Fraccion).get(fraccion_id)
                if not frac or not frac.activo:
                    raise ValueError(f"Fracción ID {fraccion_id} no disponible")
                precio_unitario = calcular_precio_fraccion(prod, frac)
                stock_descuento = (frac.cantidad * cantidad) / prod.contenido_total
            else:
                # Venta por bulto
                precio_unitario = prod.precio_venta_mayorista if tipo == "mayorista" else (
                    prod.precio_costo * (1 + prod.margen_minorista_pct / 100)
                )
                stock_descuento = cantidad

            subtotal = round(precio_unitario * cantidad, 2)
            total += subtotal

            detalle = DetalleVenta(
                venta_id=venta.id,
                producto_id=prod.id,
                fraccion_id=fraccion_id,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal=subtotal,
            )
            session.add(detalle)

            # Descontar stock
            stock_anterior = prod.stock_actual
            prod.stock_actual -= stock_descuento
            if prod.stock_actual < 0:
                raise ValueError(
                    f"Stock insuficiente para '{prod.nombre}'. "
                    f"Disponible: {stock_anterior}, requerido: {stock_descuento}"
                )

            mov = MovimientoStock(
                producto_id=prod.id,
                tipo="salida",
                cantidad=stock_descuento,
                referencia=f"Venta #{venta.id}",
                usuario_id=usuario_id,
            )
            session.add(mov)

        venta.total = round(total, 2)

        registrar_auditoria(
            session, usuario_id, "VENTA", "ventas",
            registro_id=venta.id,
            valor_nuevo={"tipo": tipo, "total": venta.total,
                         "items": len(items)},
        )
        session.commit()
        session.refresh(venta)
        return venta
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_ventas(fecha_desde: date | None = None, fecha_hasta: date | None = None):
    session = SessionLocal()
    try:
        q = session.query(Venta).order_by(Venta.fecha.desc())
        if fecha_desde:
            q = q.filter(Venta.fecha >= datetime.combine(fecha_desde, datetime.min.time()))
        if fecha_hasta:
            q = q.filter(Venta.fecha <= datetime.combine(fecha_hasta, datetime.max.time()))
        return q.all()
    finally:
        session.close()


def obtener_detalle_venta(venta_id: int):
    session = SessionLocal()
    try:
        return (
            session.query(DetalleVenta)
            .filter_by(venta_id=venta_id)
            .all()
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Actualización Masiva de Precios
# ---------------------------------------------------------------------------

def aumento_masivo_precios(
    usuario_id: int,
    porcentaje: float,
    categoria_id: int | None = None,
    proveedor_id: int | None = None,
    campos: list[str] | None = None,
) -> int:
    """Aplica aumento porcentual a productos filtrados.

    campos: lista de campos a actualizar. Default: precio_costo y precio_venta_mayorista.
    Retorna la cantidad de productos actualizados.
    """
    if campos is None:
        campos = ["precio_costo", "precio_venta_mayorista"]

    session = SessionLocal()
    try:
        q = session.query(Producto).filter(Producto.activo == True)
        if categoria_id:
            q = q.filter(Producto.categoria_id == categoria_id)
        if proveedor_id:
            q = q.filter(Producto.proveedor_id == proveedor_id)

        productos = q.all()
        factor = 1 + porcentaje / 100
        count = 0

        for prod in productos:
            anterior = {}
            nuevo = {}
            for campo in campos:
                val_anterior = getattr(prod, campo)
                val_nuevo = round(val_anterior * factor, 2)
                anterior[campo] = val_anterior
                nuevo[campo] = val_nuevo
                setattr(prod, campo, val_nuevo)

            prod.updated_at = datetime.utcnow()

            registrar_auditoria(
                session, usuario_id, "AUMENTO_MASIVO", "productos",
                registro_id=prod.id,
                valor_anterior=anterior,
                valor_nuevo={**nuevo, "porcentaje": porcentaje},
            )
            count += 1

        session.commit()
        return count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Gastos
# ---------------------------------------------------------------------------

def registrar_gasto(usuario_id: int, descripcion: str, monto: float,
                    categoria_gasto: str = "General") -> Gasto:
    session = SessionLocal()
    try:
        gasto = Gasto(
            descripcion=descripcion,
            monto=monto,
            categoria_gasto=categoria_gasto,
            usuario_id=usuario_id,
        )
        session.add(gasto)
        session.flush()
        registrar_auditoria(
            session, usuario_id, "CREAR", "gastos",
            registro_id=gasto.id,
            valor_nuevo={"descripcion": descripcion, "monto": monto,
                         "categoria_gasto": categoria_gasto},
        )
        session.commit()
        session.refresh(gasto)
        return gasto
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_gastos(fecha_desde: date | None = None, fecha_hasta: date | None = None):
    session = SessionLocal()
    try:
        q = session.query(Gasto).filter(Gasto.activo == True).order_by(Gasto.fecha.desc())
        if fecha_desde:
            q = q.filter(Gasto.fecha >= datetime.combine(fecha_desde, datetime.min.time()))
        if fecha_hasta:
            q = q.filter(Gasto.fecha <= datetime.combine(fecha_hasta, datetime.max.time()))
        return q.all()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Caja Diaria
# ---------------------------------------------------------------------------

def resumen_caja(fecha: date | None = None):
    """Calcula resumen de caja para una fecha (default: hoy)."""
    if fecha is None:
        fecha = date.today()

    inicio = datetime.combine(fecha, datetime.min.time())
    fin = datetime.combine(fecha, datetime.max.time())

    session = SessionLocal()
    try:
        total_ventas = (
            session.query(func.coalesce(func.sum(Venta.total), 0.0))
            .filter(Venta.fecha >= inicio, Venta.fecha <= fin)
            .scalar()
        )
        total_gastos = (
            session.query(func.coalesce(func.sum(Gasto.monto), 0.0))
            .filter(Gasto.activo == True)
            .filter(Gasto.fecha >= inicio, Gasto.fecha <= fin)
            .scalar()
        )
        cant_ventas = (
            session.query(func.count(Venta.id))
            .filter(Venta.fecha >= inicio, Venta.fecha <= fin)
            .scalar()
        )
        return {
            "fecha": fecha,
            "total_ventas": float(total_ventas),
            "total_gastos": float(total_gastos),
            "balance": float(total_ventas) - float(total_gastos),
            "cant_ventas": int(cant_ventas),
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Auditoría (lectura)
# ---------------------------------------------------------------------------

def listar_auditoria(limit: int = 100):
    session = SessionLocal()
    try:
        return (
            session.query(Auditoria)
            .order_by(Auditoria.fecha.desc())
            .limit(limit)
            .all()
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

def crear_usuario(admin_id: int, username: str, password: str,
                  nombre: str, rol: str = "vendedor") -> Usuario:
    session = SessionLocal()
    try:
        existing = session.query(Usuario).filter_by(username=username).first()
        if existing:
            raise ValueError(f"El usuario '{username}' ya existe")

        pw_hash, pw_salt = hash_password(password)
        user = Usuario(
            username=username,
            password_hash=pw_hash,
            password_salt=pw_salt,
            nombre=nombre,
            rol=rol,
        )
        session.add(user)
        session.flush()
        registrar_auditoria(
            session, admin_id, "CREAR", "usuarios",
            registro_id=user.id,
            valor_nuevo={"username": username, "nombre": nombre, "rol": rol},
        )
        session.commit()
        session.refresh(user)
        return user
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_usuarios():
    session = SessionLocal()
    try:
        return session.query(Usuario).order_by(Usuario.nombre).all()
    finally:
        session.close()


def desactivar_usuario(admin_id: int, user_id: int):
    session = SessionLocal()
    try:
        user = session.query(Usuario).get(user_id)
        if not user:
            raise ValueError("Usuario no encontrado")
        if user.username == "admin":
            raise ValueError("No se puede desactivar al usuario admin principal")
        user.activo = not user.activo
        registrar_auditoria(
            session, admin_id, "MODIFICAR", "usuarios",
            registro_id=user.id,
            valor_anterior={"activo": not user.activo},
            valor_nuevo={"activo": user.activo},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Categorías y Proveedores
# ---------------------------------------------------------------------------

def listar_categorias(solo_activas: bool = True):
    session = SessionLocal()
    try:
        q = session.query(Categoria)
        if solo_activas:
            q = q.filter(Categoria.activo == True)
        return q.order_by(Categoria.nombre).all()
    finally:
        session.close()


def crear_categoria(usuario_id: int, nombre: str) -> Categoria:
    session = SessionLocal()
    try:
        cat = Categoria(nombre=nombre)
        session.add(cat)
        session.flush()
        registrar_auditoria(
            session, usuario_id, "CREAR", "categorias",
            registro_id=cat.id, valor_nuevo={"nombre": nombre},
        )
        session.commit()
        session.refresh(cat)
        return cat
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_proveedores(solo_activos: bool = True):
    session = SessionLocal()
    try:
        q = session.query(Proveedor)
        if solo_activos:
            q = q.filter(Proveedor.activo == True)
        return q.order_by(Proveedor.nombre).all()
    finally:
        session.close()


def crear_proveedor(usuario_id: int, nombre: str, contacto: str = "",
                    telefono: str = "") -> Proveedor:
    session = SessionLocal()
    try:
        prov = Proveedor(nombre=nombre, contacto=contacto, telefono=telefono)
        session.add(prov)
        session.flush()
        registrar_auditoria(
            session, usuario_id, "CREAR", "proveedores",
            registro_id=prov.id,
            valor_nuevo={"nombre": nombre, "contacto": contacto,
                         "telefono": telefono},
        )
        session.commit()
        session.refresh(prov)
        return prov
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
