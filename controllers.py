"""
controllers.py - Lógica de negocio: stock, ventas, precios, auditoría.
"""
from __future__ import annotations

import json
from datetime import datetime, date

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from database import (
    SessionLocal, Producto, Fraccion, Venta, DetalleVenta,
    MovimientoStock, Auditoria, Gasto, Categoria, Proveedor,
    Usuario, hash_password, verify_password, Compra, DetalleCompra,
    Cliente, MovimientoCuenta, Devolucion, CajaDiaria, RetiroEfectivo,
    PrecioEspecial, Base, engine,
    ahora_argentina, hoy_argentina,
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
        prod.updated_at = ahora_argentina()

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
        prod.updated_at = ahora_argentina()
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
        q = (
            session.query(Producto)
            .options(joinedload(Producto.categoria))
            .options(joinedload(Producto.proveedor))
        )
        if solo_activos:
            q = q.filter(Producto.activo == True)
        return q.order_by(Producto.nombre).all()
    finally:
        session.close()


def obtener_producto(producto_id: int) -> Producto | None:
    session = SessionLocal()
    try:
        return (
            session.query(Producto)
            .options(joinedload(Producto.categoria))
            .options(joinedload(Producto.proveedor))
            .get(producto_id)
        )
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
            .options(joinedload(Fraccion.producto_padre))
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
            .options(joinedload(Producto.categoria))
            .options(joinedload(Producto.proveedor))
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
    metodo_pago: str = "efectivo",
    cliente_id: int | None = None,
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
            metodo_pago=metodo_pago,
            cliente_id=cliente_id,
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

            # Capturar costo al momento de la venta para cálculo de ganancia
            if fraccion_id and frac:
                costo_unit = (prod.precio_costo / prod.contenido_total) * frac.cantidad
            else:
                costo_unit = prod.precio_costo

            detalle = DetalleVenta(
                venta_id=venta.id,
                producto_id=prod.id,
                fraccion_id=fraccion_id,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal=subtotal,
                costo_unitario=round(costo_unit, 2),
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

        # Cuenta corriente: si paga en cta cte, cargar al cliente
        if metodo_pago == "cuenta_corriente" and cliente_id:
            cliente = session.query(Cliente).get(cliente_id)
            if cliente:
                cliente.saldo_cuenta_corriente += venta.total
                mov_cc = MovimientoCuenta(
                    cliente_id=cliente_id,
                    tipo="cargo",
                    monto=venta.total,
                    referencia=f"Venta #{venta.id}",
                    usuario_id=usuario_id,
                )
                session.add(mov_cc)

        registrar_auditoria(
            session, usuario_id, "VENTA", "ventas",
            registro_id=venta.id,
            valor_nuevo={"tipo": tipo, "total": venta.total,
                         "metodo_pago": metodo_pago,
                         "cliente_id": cliente_id,
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
        q = (
            session.query(Venta)
            .options(joinedload(Venta.usuario))
            .options(joinedload(Venta.cliente))
            .order_by(Venta.fecha.desc())
        )
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
            .options(joinedload(DetalleVenta.producto))
            .options(joinedload(DetalleVenta.fraccion))
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

            prod.updated_at = ahora_argentina()

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
        q = (
            session.query(Gasto)
            .options(joinedload(Gasto.usuario))
            .filter(Gasto.activo == True)
            .order_by(Gasto.fecha.desc())
        )
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
        fecha = hoy_argentina()

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

        # Desglose por método de pago
        metodos = ["efectivo", "transferencia", "cuenta_corriente"]
        desglose = {}
        for m in metodos:
            val = (
                session.query(func.coalesce(func.sum(Venta.total), 0.0))
                .filter(Venta.fecha >= inicio, Venta.fecha <= fin)
                .filter(Venta.metodo_pago == m)
                .scalar()
            )
            desglose[m] = float(val)

        # Cobrado real = todo menos cuenta corriente
        cobrado_real = desglose.get("efectivo", 0) + desglose.get("transferencia", 0)

        return {
            "fecha": fecha,
            "total_ventas": float(total_ventas),
            "total_gastos": float(total_gastos),
            "balance": float(total_ventas) - float(total_gastos),
            "cobrado_real": cobrado_real,
            "balance_real": cobrado_real - float(total_gastos),
            "cant_ventas": int(cant_ventas),
            "desglose_pago": desglose,
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
            .options(joinedload(Auditoria.usuario))
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
# Compras
# ---------------------------------------------------------------------------

def procesar_compra(
    usuario_id: int,
    proveedor_id: int | None,
    items: list[dict],
    numero_factura: str = "",
    observaciones: str = "",
) -> Compra:
    """Procesa una compra completa.

    items: lista de dicts con:
        - producto_id: int
        - cantidad: float (bultos)
        - precio_unitario: float (costo por bulto)
        - actualizar_costo: bool
    """
    session = SessionLocal()
    try:
        compra = Compra(
            usuario_id=usuario_id,
            proveedor_id=proveedor_id,
            numero_factura=numero_factura,
            observaciones=observaciones,
        )
        session.add(compra)
        session.flush()

        total = 0.0

        for item in items:
            prod = session.query(Producto).get(item["producto_id"])
            if not prod:
                raise ValueError(f"Producto ID {item['producto_id']} no encontrado")

            cantidad = item["cantidad"]
            precio_unitario = item["precio_unitario"]
            subtotal = round(precio_unitario * cantidad, 2)
            total += subtotal
            actualizar = item.get("actualizar_costo", True)

            detalle = DetalleCompra(
                compra_id=compra.id,
                producto_id=prod.id,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal=subtotal,
                actualizar_costo=actualizar,
            )
            session.add(detalle)

            # Entrada de stock
            stock_anterior = prod.stock_actual
            prod.stock_actual += cantidad

            mov = MovimientoStock(
                producto_id=prod.id,
                tipo="entrada",
                cantidad=cantidad,
                referencia=f"Compra #{compra.id}"
                           + (f" Fact: {numero_factura}" if numero_factura else ""),
                usuario_id=usuario_id,
            )
            session.add(mov)

            # Actualizar precio de costo si corresponde
            costo_anterior = prod.precio_costo
            if actualizar:
                prod.precio_costo = precio_unitario
                prod.updated_at = ahora_argentina()

            registrar_auditoria(
                session, usuario_id, "COMPRA", "productos",
                registro_id=prod.id,
                valor_anterior={"stock_actual": stock_anterior,
                                "precio_costo": costo_anterior},
                valor_nuevo={"stock_actual": prod.stock_actual,
                             "precio_costo": prod.precio_costo,
                             "cantidad_comprada": cantidad,
                             "costo_actualizado": actualizar},
            )

        compra.total = round(total, 2)

        registrar_auditoria(
            session, usuario_id, "COMPRA", "compras",
            registro_id=compra.id,
            valor_nuevo={"total": compra.total, "items": len(items),
                         "proveedor_id": proveedor_id},
        )
        session.commit()
        session.refresh(compra)
        return compra
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_compras(fecha_desde: date | None = None, fecha_hasta: date | None = None):
    session = SessionLocal()
    try:
        q = (
            session.query(Compra)
            .options(joinedload(Compra.usuario))
            .options(joinedload(Compra.proveedor))
            .order_by(Compra.fecha.desc())
        )
        if fecha_desde:
            q = q.filter(Compra.fecha >= datetime.combine(fecha_desde, datetime.min.time()))
        if fecha_hasta:
            q = q.filter(Compra.fecha <= datetime.combine(fecha_hasta, datetime.max.time()))
        return q.all()
    finally:
        session.close()


def obtener_detalle_compra(compra_id: int):
    session = SessionLocal()
    try:
        return (
            session.query(DetalleCompra)
            .options(joinedload(DetalleCompra.producto))
            .filter_by(compra_id=compra_id)
            .all()
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Clientes y Cuenta Corriente
# ---------------------------------------------------------------------------

def crear_cliente(usuario_id: int, nombre: str, cuit: str = "",
                  telefono: str = "", email: str = "",
                  direccion: str = "") -> Cliente:
    session = SessionLocal()
    try:
        cliente = Cliente(
            nombre=nombre, cuit=cuit, telefono=telefono,
            email=email, direccion=direccion,
        )
        session.add(cliente)
        session.flush()
        registrar_auditoria(
            session, usuario_id, "CREAR", "clientes",
            registro_id=cliente.id,
            valor_nuevo={"nombre": nombre, "cuit": cuit},
        )
        session.commit()
        session.refresh(cliente)
        return cliente
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_clientes(solo_activos: bool = True):
    session = SessionLocal()
    try:
        q = session.query(Cliente)
        if solo_activos:
            q = q.filter(Cliente.activo == True)
        return q.order_by(Cliente.nombre).all()
    finally:
        session.close()


def obtener_cliente(cliente_id: int) -> Cliente | None:
    session = SessionLocal()
    try:
        return session.query(Cliente).get(cliente_id)
    finally:
        session.close()


def registrar_pago_cliente(
    usuario_id: int, cliente_id: int, monto: float, referencia: str = "Pago"
):
    """Registra un pago del cliente y reduce su saldo."""
    session = SessionLocal()
    try:
        cliente = session.query(Cliente).get(cliente_id)
        if not cliente:
            raise ValueError("Cliente no encontrado")

        saldo_anterior = cliente.saldo_cuenta_corriente
        cliente.saldo_cuenta_corriente -= monto

        mov = MovimientoCuenta(
            cliente_id=cliente_id,
            tipo="pago",
            monto=monto,
            referencia=referencia,
            usuario_id=usuario_id,
        )
        session.add(mov)

        registrar_auditoria(
            session, usuario_id, "PAGO_CLIENTE", "clientes",
            registro_id=cliente_id,
            valor_anterior={"saldo": saldo_anterior},
            valor_nuevo={"saldo": cliente.saldo_cuenta_corriente, "pago": monto},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_movimientos_cuenta(cliente_id: int):
    session = SessionLocal()
    try:
        return (
            session.query(MovimientoCuenta)
            .options(joinedload(MovimientoCuenta.usuario))
            .filter_by(cliente_id=cliente_id)
            .order_by(MovimientoCuenta.fecha.desc())
            .limit(200)
            .all()
        )
    finally:
        session.close()


def productos_proximos_a_vencer(dias: int = 30):
    """Productos con fecha de vencimiento dentro de los próximos N días."""
    from datetime import timedelta
    session = SessionLocal()
    try:
        hoy = hoy_argentina()
        limite = hoy + timedelta(days=dias)
        return (
            session.query(Producto)
            .options(joinedload(Producto.categoria))
            .options(joinedload(Producto.proveedor))
            .filter(Producto.activo == True)
            .filter(Producto.fecha_vencimiento != None)
            .filter(Producto.fecha_vencimiento <= limite)
            .order_by(Producto.fecha_vencimiento)
            .all()
        )
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


# ---------------------------------------------------------------------------
# Devoluciones y Anulaciones
# ---------------------------------------------------------------------------

def anular_venta(usuario_id: int, venta_id: int, motivo: str = "") -> Devolucion:
    """Anula una venta completa: reingresa stock, revierte cuenta corriente."""
    session = SessionLocal()
    try:
        venta = session.query(Venta).get(venta_id)
        if not venta:
            raise ValueError("Venta no encontrada")
        if venta.anulada:
            raise ValueError("Esta venta ya fue anulada")

        venta.anulada = True

        # Reingresar stock de cada item
        detalles = session.query(DetalleVenta).filter_by(venta_id=venta_id).all()
        for d in detalles:
            prod = session.query(Producto).get(d.producto_id)
            if prod:
                if d.fraccion_id:
                    frac = session.query(Fraccion).get(d.fraccion_id)
                    if frac:
                        stock_a_devolver = (frac.cantidad * d.cantidad) / prod.contenido_total
                    else:
                        stock_a_devolver = d.cantidad
                else:
                    stock_a_devolver = d.cantidad

                prod.stock_actual += stock_a_devolver
                mov = MovimientoStock(
                    producto_id=prod.id,
                    tipo="entrada",
                    cantidad=stock_a_devolver,
                    referencia=f"Anulación Venta #{venta_id}",
                    usuario_id=usuario_id,
                )
                session.add(mov)

        # Revertir cuenta corriente si aplica
        metodo = getattr(venta, "metodo_pago", "efectivo") or "efectivo"
        if metodo == "cuenta_corriente" and venta.cliente_id:
            cliente = session.query(Cliente).get(venta.cliente_id)
            if cliente:
                cliente.saldo_cuenta_corriente -= venta.total
                mov_cc = MovimientoCuenta(
                    cliente_id=venta.cliente_id,
                    tipo="pago",
                    monto=venta.total,
                    referencia=f"Anulación Venta #{venta_id}",
                    usuario_id=usuario_id,
                )
                session.add(mov_cc)

        dev = Devolucion(
            venta_id=venta_id,
            usuario_id=usuario_id,
            motivo=motivo,
            tipo="anulacion_total",
            monto_devuelto=venta.total,
        )
        session.add(dev)

        registrar_auditoria(
            session, usuario_id, "ANULAR_VENTA", "ventas",
            registro_id=venta_id,
            valor_anterior={"total": venta.total, "anulada": False},
            valor_nuevo={"anulada": True, "motivo": motivo},
        )
        session.commit()
        session.refresh(dev)
        return dev
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def devolucion_parcial(
    usuario_id: int, venta_id: int, items_devolver: list[dict], motivo: str = ""
) -> Devolucion:
    """Devolución parcial de items de una venta.

    items_devolver: lista de dicts con:
        - detalle_id: int (ID del DetalleVenta)
        - cantidad: float (cantidad a devolver)
    """
    session = SessionLocal()
    try:
        venta = session.query(Venta).get(venta_id)
        if not venta:
            raise ValueError("Venta no encontrada")
        if venta.anulada:
            raise ValueError("Esta venta ya fue anulada")

        monto_devuelto = 0.0

        for item in items_devolver:
            detalle = session.query(DetalleVenta).get(item["detalle_id"])
            if not detalle or detalle.venta_id != venta_id:
                raise ValueError(f"Detalle {item['detalle_id']} no pertenece a esta venta")

            cant_devolver = item["cantidad"]
            if cant_devolver > detalle.cantidad:
                raise ValueError(
                    f"No se puede devolver {cant_devolver}, cantidad original: {detalle.cantidad}"
                )

            monto_item = round(detalle.precio_unitario * cant_devolver, 2)
            monto_devuelto += monto_item

            # Reingresar stock
            prod = session.query(Producto).get(detalle.producto_id)
            if prod:
                if detalle.fraccion_id:
                    frac = session.query(Fraccion).get(detalle.fraccion_id)
                    if frac:
                        stock_a_devolver = (frac.cantidad * cant_devolver) / prod.contenido_total
                    else:
                        stock_a_devolver = cant_devolver
                else:
                    stock_a_devolver = cant_devolver

                prod.stock_actual += stock_a_devolver
                mov = MovimientoStock(
                    producto_id=prod.id,
                    tipo="entrada",
                    cantidad=stock_a_devolver,
                    referencia=f"Devolución parcial Venta #{venta_id}",
                    usuario_id=usuario_id,
                )
                session.add(mov)

        # Revertir cuenta corriente parcial si aplica
        metodo = getattr(venta, "metodo_pago", "efectivo") or "efectivo"
        if metodo == "cuenta_corriente" and venta.cliente_id:
            cliente = session.query(Cliente).get(venta.cliente_id)
            if cliente:
                cliente.saldo_cuenta_corriente -= monto_devuelto
                mov_cc = MovimientoCuenta(
                    cliente_id=venta.cliente_id,
                    tipo="pago",
                    monto=monto_devuelto,
                    referencia=f"Devolución parcial Venta #{venta_id}",
                    usuario_id=usuario_id,
                )
                session.add(mov_cc)

        dev = Devolucion(
            venta_id=venta_id,
            usuario_id=usuario_id,
            motivo=motivo,
            tipo="devolucion_parcial",
            monto_devuelto=round(monto_devuelto, 2),
        )
        session.add(dev)

        registrar_auditoria(
            session, usuario_id, "DEVOLUCION_PARCIAL", "ventas",
            registro_id=venta_id,
            valor_nuevo={"monto_devuelto": monto_devuelto, "motivo": motivo,
                         "items": len(items_devolver)},
        )
        session.commit()
        session.refresh(dev)
        return dev
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def obtener_venta(venta_id: int) -> Venta | None:
    session = SessionLocal()
    try:
        return (
            session.query(Venta)
            .options(joinedload(Venta.usuario))
            .options(joinedload(Venta.cliente))
            .get(venta_id)
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Caja Diaria — Apertura, Cierre, Retiros
# ---------------------------------------------------------------------------

def obtener_caja_hoy() -> CajaDiaria | None:
    """Obtiene la caja del día de hoy (si existe)."""
    session = SessionLocal()
    try:
        return (
            session.query(CajaDiaria)
            .options(joinedload(CajaDiaria.usuario_apertura))
            .options(joinedload(CajaDiaria.usuario_cierre))
            .filter_by(fecha=hoy_argentina())
            .first()
        )
    finally:
        session.close()


def caja_abierta_hoy() -> bool:
    """Retorna True si hay una caja abierta hoy."""
    caja = obtener_caja_hoy()
    return caja is not None and caja.estado == "abierta"


def abrir_caja(usuario_id: int, monto_apertura: float,
               observaciones: str = "") -> CajaDiaria:
    """Abre la caja del día."""
    session = SessionLocal()
    try:
        existente = session.query(CajaDiaria).filter_by(fecha=hoy_argentina()).first()
        if existente:
            raise ValueError("Ya existe una caja para hoy")

        caja = CajaDiaria(
            fecha=hoy_argentina(),
            usuario_apertura_id=usuario_id,
            monto_apertura=monto_apertura,
            estado="abierta",
            observaciones_apertura=observaciones,
        )
        session.add(caja)
        session.flush()
        registrar_auditoria(
            session, usuario_id, "ABRIR_CAJA", "cajas_diarias",
            registro_id=caja.id,
            valor_nuevo={"monto_apertura": monto_apertura, "fecha": str(hoy_argentina())},
        )
        session.commit()
        session.refresh(caja)
        return caja
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def cerrar_caja(usuario_id: int, monto_cierre: float,
                observaciones: str = "") -> CajaDiaria:
    """Cierra la caja del día."""
    session = SessionLocal()
    try:
        caja = session.query(CajaDiaria).filter_by(fecha=hoy_argentina()).first()
        if not caja:
            raise ValueError("No hay caja abierta hoy")
        if caja.estado == "cerrada":
            raise ValueError("La caja ya fue cerrada")

        caja.estado = "cerrada"
        caja.usuario_cierre_id = usuario_id
        caja.monto_cierre = monto_cierre
        caja.hora_cierre = ahora_argentina()
        caja.observaciones_cierre = observaciones

        registrar_auditoria(
            session, usuario_id, "CERRAR_CAJA", "cajas_diarias",
            registro_id=caja.id,
            valor_anterior={"estado": "abierta"},
            valor_nuevo={"estado": "cerrada", "monto_cierre": monto_cierre},
        )
        session.commit()
        session.refresh(caja)
        return caja
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def registrar_retiro(usuario_id: int, monto: float,
                     motivo: str = "") -> RetiroEfectivo:
    """Registra un retiro de efectivo de la caja del día."""
    session = SessionLocal()
    try:
        caja = session.query(CajaDiaria).filter_by(fecha=hoy_argentina()).first()
        if not caja or caja.estado != "abierta":
            raise ValueError("No hay caja abierta hoy")

        retiro = RetiroEfectivo(
            caja_id=caja.id,
            usuario_id=usuario_id,
            monto=monto,
            motivo=motivo,
        )
        session.add(retiro)
        session.flush()
        registrar_auditoria(
            session, usuario_id, "RETIRO_EFECTIVO", "retiros_efectivo",
            registro_id=retiro.id,
            valor_nuevo={"monto": monto, "motivo": motivo},
        )
        session.commit()
        session.refresh(retiro)
        return retiro
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_retiros(caja_id: int):
    session = SessionLocal()
    try:
        return (
            session.query(RetiroEfectivo)
            .options(joinedload(RetiroEfectivo.usuario))
            .filter_by(caja_id=caja_id)
            .order_by(RetiroEfectivo.fecha.desc())
            .all()
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------

def reporte_ventas_periodo(
    fecha_desde: date, fecha_hasta: date, agrupacion: str = "dia"
) -> list[dict]:
    """Ventas agrupadas por día, semana o mes."""
    from datetime import timedelta
    session = SessionLocal()
    try:
        inicio = datetime.combine(fecha_desde, datetime.min.time())
        fin = datetime.combine(fecha_hasta, datetime.max.time())

        ventas = (
            session.query(Venta)
            .filter(Venta.fecha >= inicio, Venta.fecha <= fin)
            .filter(Venta.anulada == False)
            .order_by(Venta.fecha)
            .all()
        )

        grupos = {}
        for v in ventas:
            if agrupacion == "dia":
                key = v.fecha.strftime("%Y-%m-%d")
            elif agrupacion == "semana":
                # Lunes de la semana
                lunes = v.fecha.date() - timedelta(days=v.fecha.weekday())
                key = lunes.strftime("%Y-%m-%d")
            else:  # mes
                key = v.fecha.strftime("%Y-%m")

            if key not in grupos:
                grupos[key] = {"periodo": key, "total": 0.0, "cantidad": 0}
            grupos[key]["total"] += v.total
            grupos[key]["cantidad"] += 1

        return sorted(grupos.values(), key=lambda x: x["periodo"])
    finally:
        session.close()


def reporte_productos_vendidos(
    fecha_desde: date, fecha_hasta: date, limit: int = 10
) -> list[dict]:
    """Top productos vendidos por cantidad y por monto."""
    session = SessionLocal()
    try:
        inicio = datetime.combine(fecha_desde, datetime.min.time())
        fin = datetime.combine(fecha_hasta, datetime.max.time())

        resultados = (
            session.query(
                DetalleVenta.producto_id,
                Producto.nombre,
                func.sum(DetalleVenta.cantidad).label("total_cantidad"),
                func.sum(DetalleVenta.subtotal).label("total_monto"),
            )
            .join(Producto, DetalleVenta.producto_id == Producto.id)
            .join(Venta, DetalleVenta.venta_id == Venta.id)
            .filter(Venta.fecha >= inicio, Venta.fecha <= fin)
            .filter(Venta.anulada == False)
            .group_by(DetalleVenta.producto_id, Producto.nombre)
            .order_by(func.sum(DetalleVenta.subtotal).desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "producto": r.nombre,
                "cantidad": float(r.total_cantidad),
                "monto": float(r.total_monto),
            }
            for r in resultados
        ]
    finally:
        session.close()


def reporte_ganancia(
    fecha_desde: date, fecha_hasta: date, agrupacion: str = "dia"
) -> list[dict]:
    """Ganancia real: ventas - costo mercadería - gastos, agrupada por período."""
    from datetime import timedelta
    session = SessionLocal()
    try:
        inicio = datetime.combine(fecha_desde, datetime.min.time())
        fin = datetime.combine(fecha_hasta, datetime.max.time())

        # Obtener ventas con detalle
        ventas = (
            session.query(Venta)
            .filter(Venta.fecha >= inicio, Venta.fecha <= fin)
            .filter(Venta.anulada == False)
            .all()
        )

        # Obtener gastos
        gastos = (
            session.query(Gasto)
            .filter(Gasto.activo == True)
            .filter(Gasto.fecha >= inicio, Gasto.fecha <= fin)
            .all()
        )

        grupos = {}

        for v in ventas:
            if agrupacion == "dia":
                key = v.fecha.strftime("%Y-%m-%d")
            elif agrupacion == "semana":
                lunes = v.fecha.date() - timedelta(days=v.fecha.weekday())
                key = lunes.strftime("%Y-%m-%d")
            else:
                key = v.fecha.strftime("%Y-%m")

            if key not in grupos:
                grupos[key] = {"periodo": key, "ventas": 0.0, "costo": 0.0, "gastos": 0.0}
            grupos[key]["ventas"] += v.total

            # Calcular costo de mercadería
            detalles = session.query(DetalleVenta).filter_by(venta_id=v.id).all()
            for d in detalles:
                if d.costo_unitario is not None:
                    grupos[key]["costo"] += d.costo_unitario * d.cantidad
                else:
                    # Fallback: usar precio_costo actual del producto
                    prod = session.query(Producto).get(d.producto_id)
                    if prod:
                        if d.fraccion_id:
                            frac = session.query(Fraccion).get(d.fraccion_id)
                            if frac:
                                costo = (prod.precio_costo / prod.contenido_total) * frac.cantidad
                            else:
                                costo = prod.precio_costo
                        else:
                            costo = prod.precio_costo
                        grupos[key]["costo"] += costo * d.cantidad

        for g in gastos:
            if agrupacion == "dia":
                key = g.fecha.strftime("%Y-%m-%d")
            elif agrupacion == "semana":
                lunes = g.fecha.date() - timedelta(days=g.fecha.weekday())
                key = lunes.strftime("%Y-%m-%d")
            else:
                key = g.fecha.strftime("%Y-%m")

            if key not in grupos:
                grupos[key] = {"periodo": key, "ventas": 0.0, "costo": 0.0, "gastos": 0.0}
            grupos[key]["gastos"] += g.monto

        # Calcular ganancia
        resultado = []
        for g in sorted(grupos.values(), key=lambda x: x["periodo"]):
            g["ganancia_bruta"] = round(g["ventas"] - g["costo"], 2)
            g["ganancia_neta"] = round(g["ventas"] - g["costo"] - g["gastos"], 2)
            g["margen_pct"] = round(
                (g["ganancia_bruta"] / g["ventas"] * 100) if g["ventas"] > 0 else 0, 1
            )
            resultado.append(g)

        return resultado
    finally:
        session.close()


def reporte_stock_valorizado() -> dict:
    """Stock valorizado por categoría."""
    session = SessionLocal()
    try:
        productos = (
            session.query(Producto)
            .options(joinedload(Producto.categoria))
            .filter(Producto.activo == True)
            .all()
        )

        por_categoria = {}
        total = 0.0

        for p in productos:
            cat_nombre = p.categoria.nombre if p.categoria else "Sin categoría"
            valor = p.stock_actual * p.precio_costo

            if cat_nombre not in por_categoria:
                por_categoria[cat_nombre] = 0.0
            por_categoria[cat_nombre] += valor
            total += valor

        return {
            "por_categoria": por_categoria,
            "total": round(total, 2),
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Importación Masiva de Productos
# ---------------------------------------------------------------------------

def importar_productos(
    usuario_id: int, datos: list[dict], modo: str = "crear"
) -> dict:
    """Importa productos masivamente desde CSV/Excel parseado.

    modo: 'crear' (solo nuevos) | 'actualizar' (actualiza existentes por código)
    datos: lista de dicts con claves: codigo, nombre, precio_costo,
           precio_venta_mayorista, categoria, proveedor, unidad_medida,
           stock_actual, margen_minorista_pct
    Retorna: {creados: int, actualizados: int, errores: list[str]}
    """
    session = SessionLocal()
    try:
        creados = 0
        actualizados = 0
        errores = []

        # Cache de categorías y proveedores para no consultar cada vez
        cats = {c.nombre.lower(): c.id for c in session.query(Categoria).all()}
        provs = {p.nombre.lower(): p.id for p in session.query(Proveedor).all()}

        for i, row in enumerate(datos, start=1):
            try:
                codigo = str(row.get("codigo", "")).strip()
                nombre = str(row.get("nombre", "")).strip()
                if not codigo or not nombre:
                    errores.append(f"Fila {i}: código o nombre vacío")
                    continue

                existente = session.query(Producto).filter_by(codigo=codigo).first()

                # Resolver categoría
                cat_name = str(row.get("categoria", "")).strip().lower()
                cat_id = cats.get(cat_name)

                # Resolver proveedor
                prov_name = str(row.get("proveedor", "")).strip().lower()
                prov_id = provs.get(prov_name)

                precio_costo = float(row.get("precio_costo", 0) or 0)
                precio_mayorista = float(row.get("precio_venta_mayorista", 0) or 0)
                margen = float(row.get("margen_minorista_pct", 30) or 30)
                stock = float(row.get("stock_actual", 0) or 0)
                unidad = str(row.get("unidad_medida", "kg")).strip() or "kg"

                if existente and modo == "actualizar":
                    anterior = {
                        "precio_costo": existente.precio_costo,
                        "precio_venta_mayorista": existente.precio_venta_mayorista,
                    }
                    existente.precio_costo = precio_costo
                    existente.precio_venta_mayorista = precio_mayorista
                    existente.margen_minorista_pct = margen
                    if stock > 0:
                        existente.stock_actual = stock
                    existente.updated_at = ahora_argentina()
                    registrar_auditoria(
                        session, usuario_id, "IMPORTAR_ACTUALIZAR", "productos",
                        registro_id=existente.id, valor_anterior=anterior,
                        valor_nuevo={"precio_costo": precio_costo,
                                     "precio_venta_mayorista": precio_mayorista},
                    )
                    actualizados += 1
                elif existente and modo == "crear":
                    errores.append(f"Fila {i}: código '{codigo}' ya existe")
                else:
                    prod = Producto(
                        codigo=codigo, nombre=nombre,
                        precio_costo=precio_costo,
                        precio_venta_mayorista=precio_mayorista,
                        margen_minorista_pct=margen,
                        stock_actual=stock,
                        unidad_medida=unidad,
                        categoria_id=cat_id,
                        proveedor_id=prov_id,
                    )
                    session.add(prod)
                    session.flush()
                    registrar_auditoria(
                        session, usuario_id, "IMPORTAR_CREAR", "productos",
                        registro_id=prod.id,
                        valor_nuevo={"codigo": codigo, "nombre": nombre},
                    )
                    creados += 1
            except Exception as e:
                errores.append(f"Fila {i}: {str(e)}")

        session.commit()
        return {"creados": creados, "actualizados": actualizados, "errores": errores}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Backup y Restore
# ---------------------------------------------------------------------------

def generar_backup_completo() -> dict:
    """Genera un backup JSON completo de todas las tablas con metadata."""
    from sqlalchemy import inspect as sa_inspect
    session = SessionLocal()
    try:
        backup = {
            "_metadata": {
                "fecha": ahora_argentina().isoformat(),
                "version": "3.0",
                "tablas": {},
            },
            "datos": {},
        }
        inspector = sa_inspect(engine)
        table_names = inspector.get_table_names()

        for table_name in table_names:
            if table_name not in Base.metadata.tables:
                continue
            rows = session.execute(
                Base.metadata.tables[table_name].select()
            ).fetchall()
            columns = [col["name"] for col in inspector.get_columns(table_name)]
            registros = [
                {col: val for col, val in zip(columns, row)}
                for row in rows
            ]
            backup["datos"][table_name] = registros
            backup["_metadata"]["tablas"][table_name] = len(registros)

        return backup
    finally:
        session.close()


def restaurar_backup(
    usuario_id: int, data: dict
) -> dict:
    """Restaura un backup JSON en modo merge (solo agrega registros que no existen).

    Retorna: {tabla: registros_restaurados} por tabla.
    """
    from sqlalchemy import inspect as sa_inspect
    session = SessionLocal()
    try:
        resultado = {}
        datos = data.get("datos", data)  # Soportar formato viejo (sin _metadata)
        inspector = sa_inspect(engine)

        for table_name, registros in datos.items():
            if table_name.startswith("_"):
                continue
            if table_name not in Base.metadata.tables:
                continue

            table = Base.metadata.tables[table_name]
            pk_cols = [col.name for col in table.primary_key.columns]
            if not pk_cols:
                continue

            existing_ids = set()
            for row in session.execute(table.select()).fetchall():
                pk_val = tuple(getattr(row, pk) for pk in pk_cols)
                existing_ids.add(pk_val)

            count = 0
            for reg in registros:
                pk_val = tuple(reg.get(pk) for pk in pk_cols)
                if pk_val not in existing_ids:
                    try:
                        # Filtrar solo columnas que existen en la tabla actual
                        valid_cols = [c.name for c in table.columns]
                        clean_reg = {k: v for k, v in reg.items() if k in valid_cols}
                        session.execute(table.insert().values(**clean_reg))
                        count += 1
                    except Exception:
                        continue  # Saltar registros con errores de FK, etc.

            resultado[table_name] = count

        registrar_auditoria(
            session, usuario_id, "RESTAURAR_BACKUP", "sistema",
            valor_nuevo={"tablas_restauradas": resultado},
        )
        session.commit()
        return resultado
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Seguridad: Cambio de Contraseña
# ---------------------------------------------------------------------------

def cambiar_password(
    usuario_id: int, password_actual: str, password_nueva: str
) -> bool:
    """Cambia la contraseña del usuario si la actual es correcta."""
    session = SessionLocal()
    try:
        user = session.query(Usuario).get(usuario_id)
        if not user:
            raise ValueError("Usuario no encontrado")
        if not verify_password(password_actual, user.password_hash, user.password_salt):
            raise ValueError("La contraseña actual es incorrecta")
        if len(password_nueva) < 4:
            raise ValueError("La nueva contraseña debe tener al menos 4 caracteres")
        if password_actual == password_nueva:
            raise ValueError("La nueva contraseña debe ser diferente a la actual")

        new_hash, new_salt = hash_password(password_nueva)
        user.password_hash = new_hash
        user.password_salt = new_salt

        registrar_auditoria(
            session, usuario_id, "CAMBIAR_PASSWORD", "usuarios",
            registro_id=usuario_id,
        )
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def resetear_password(admin_id: int, target_usuario_id: int) -> str:
    """Reset de contraseña por admin. Retorna contraseña temporal."""
    import secrets as _secrets
    session = SessionLocal()
    try:
        admin = session.query(Usuario).get(admin_id)
        if not admin or admin.rol != "admin":
            raise ValueError("Solo administradores pueden resetear contraseñas")

        user = session.query(Usuario).get(target_usuario_id)
        if not user:
            raise ValueError("Usuario no encontrado")

        temp_password = _secrets.token_urlsafe(6)  # ~8 chars legibles
        new_hash, new_salt = hash_password(temp_password)
        user.password_hash = new_hash
        user.password_salt = new_salt

        registrar_auditoria(
            session, admin_id, "RESETEAR_PASSWORD", "usuarios",
            registro_id=target_usuario_id,
            valor_nuevo={"reseteado_por": admin_id},
        )
        session.commit()
        return temp_password
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Precios Especiales por Cliente
# ---------------------------------------------------------------------------

def obtener_precio_cliente(
    cliente_id: int | None, producto_id: int, tipo_venta: str
) -> tuple[float, str]:
    """Resuelve el precio para un cliente/producto.

    Prioridad:
    1. PrecioEspecial(cliente, producto) → precio fijo
    2. Cliente.descuento_general_pct > 0 → descuento sobre mayorista
    3. Precio normal según tipo de venta

    Retorna (precio, etiqueta) donde etiqueta indica el tipo de precio aplicado.
    """
    session = SessionLocal()
    try:
        prod = session.query(Producto).get(producto_id)
        if not prod:
            raise ValueError("Producto no encontrado")

        # Precio normal según tipo
        if tipo_venta == "mayorista":
            precio_normal = prod.precio_venta_mayorista
        else:
            precio_normal = prod.precio_costo * (1 + prod.margen_minorista_pct / 100)

        if not cliente_id:
            return round(precio_normal, 2), ""

        # 1. Precio especial fijo
        pe = (
            session.query(PrecioEspecial)
            .filter_by(cliente_id=cliente_id, producto_id=producto_id, activo=True)
            .first()
        )
        if pe:
            return round(pe.precio_fijo, 2), "🏷️ Precio especial"

        # 2. Descuento general del cliente
        cliente = session.query(Cliente).get(cliente_id)
        if cliente and cliente.descuento_general_pct > 0:
            precio_desc = prod.precio_venta_mayorista * (1 - cliente.descuento_general_pct / 100)
            return round(precio_desc, 2), f"🏷️ -{cliente.descuento_general_pct:g}%"

        # 3. Normal
        return round(precio_normal, 2), ""
    finally:
        session.close()


def asignar_precio_especial(
    usuario_id: int, cliente_id: int, producto_id: int, precio: float
) -> PrecioEspecial:
    """Asigna o actualiza un precio especial fijo para un cliente/producto."""
    session = SessionLocal()
    try:
        existente = (
            session.query(PrecioEspecial)
            .filter_by(cliente_id=cliente_id, producto_id=producto_id)
            .first()
        )
        if existente:
            anterior = {"precio_fijo": existente.precio_fijo, "activo": existente.activo}
            existente.precio_fijo = precio
            existente.activo = True
            registrar_auditoria(
                session, usuario_id, "MODIFICAR", "precios_especiales",
                registro_id=existente.id, valor_anterior=anterior,
                valor_nuevo={"precio_fijo": precio},
            )
            session.commit()
            session.refresh(existente)
            return existente
        else:
            pe = PrecioEspecial(
                cliente_id=cliente_id,
                producto_id=producto_id,
                precio_fijo=precio,
            )
            session.add(pe)
            session.flush()
            registrar_auditoria(
                session, usuario_id, "CREAR", "precios_especiales",
                registro_id=pe.id,
                valor_nuevo={"cliente_id": cliente_id, "producto_id": producto_id,
                             "precio_fijo": precio},
            )
            session.commit()
            session.refresh(pe)
            return pe
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def listar_precios_especiales(cliente_id: int) -> list:
    """Lista todos los precios especiales activos de un cliente."""
    session = SessionLocal()
    try:
        return (
            session.query(PrecioEspecial)
            .options(joinedload(PrecioEspecial.producto))
            .filter_by(cliente_id=cliente_id, activo=True)
            .all()
        )
    finally:
        session.close()


def eliminar_precio_especial(usuario_id: int, precio_especial_id: int):
    """Desactiva un precio especial."""
    session = SessionLocal()
    try:
        pe = session.query(PrecioEspecial).get(precio_especial_id)
        if not pe:
            raise ValueError("Precio especial no encontrado")
        pe.activo = False
        registrar_auditoria(
            session, usuario_id, "DESACTIVAR", "precios_especiales",
            registro_id=pe.id,
            valor_anterior={"activo": True},
            valor_nuevo={"activo": False},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def actualizar_descuento_cliente(
    usuario_id: int, cliente_id: int, descuento_pct: float
):
    """Actualiza el descuento general de un cliente."""
    session = SessionLocal()
    try:
        cliente = session.query(Cliente).get(cliente_id)
        if not cliente:
            raise ValueError("Cliente no encontrado")
        anterior = {"descuento_general_pct": cliente.descuento_general_pct}
        cliente.descuento_general_pct = descuento_pct
        registrar_auditoria(
            session, usuario_id, "MODIFICAR", "clientes",
            registro_id=cliente_id, valor_anterior=anterior,
            valor_nuevo={"descuento_general_pct": descuento_pct},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
