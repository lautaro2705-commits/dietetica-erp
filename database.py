"""
database.py - Modelos SQLAlchemy y configuración de la base de datos.
ERP Dietética Mayorista.
"""
from __future__ import annotations

import os
import hashlib
import secrets
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # Carga variables desde .env

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime,
    Text, ForeignKey, event
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Conexión: PostgreSQL (Supabase) en producción, SQLite local como fallback
# ---------------------------------------------------------------------------

def _get_database_url() -> str:
    """Obtiene la URL de conexión. Prioridad: st.secrets > env var > SQLite local."""
    # 1. Intentar Streamlit secrets (para Streamlit Cloud)
    try:
        import streamlit as st
        url = st.secrets.get("DATABASE_URL", "")
        if url:
            return url
    except Exception:
        pass
    # 2. Variable de entorno (para desarrollo local con PostgreSQL)
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    # 3. Fallback: SQLite local (desarrollo sin PostgreSQL)
    db_path = os.path.join(BASE_DIR, "dietetica.db")
    return f"sqlite:///{db_path}"


DATABASE_URL = _get_database_url()
_is_sqlite = DATABASE_URL.startswith("sqlite")

_engine_kwargs = {"echo": False}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_size"] = 5

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Genera hash SHA-256 con salt. Retorna (hash, salt)."""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return hashed, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    hashed, _ = hash_password(password, salt)
    return hashed == stored_hash


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(64), nullable=False)
    password_salt = Column(String(32), nullable=False)
    nombre = Column(String(100), nullable=False)
    rol = Column(String(20), nullable=False, default="vendedor")  # admin | vendedor
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Categoria(Base):
    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), unique=True, nullable=False)
    activo = Column(Boolean, default=True)

    productos = relationship("Producto", back_populates="categoria")


class Proveedor(Base):
    __tablename__ = "proveedores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    contacto = Column(String(150), default="")
    telefono = Column(String(50), default="")
    activo = Column(Boolean, default=True)

    productos = relationship("Producto", back_populates="proveedor")


class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), unique=True, nullable=False)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, default="")
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=True)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=True)
    unidad_medida = Column(String(20), nullable=False, default="kg")  # kg, litro, unidad
    contenido_total = Column(Float, nullable=False, default=1.0)  # ej: 25 para bolsa 25kg
    precio_costo = Column(Float, nullable=False, default=0.0)
    precio_venta_mayorista = Column(Float, nullable=False, default=0.0)
    margen_minorista_pct = Column(Float, nullable=False, default=30.0)
    stock_actual = Column(Float, nullable=False, default=0.0)
    stock_minimo = Column(Float, nullable=False, default=0.0)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    categoria = relationship("Categoria", back_populates="productos")
    proveedor = relationship("Proveedor", back_populates="productos")
    fracciones = relationship("Fraccion", back_populates="producto_padre")


class Fraccion(Base):
    __tablename__ = "fracciones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    producto_padre_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    nombre = Column(String(100), nullable=False)  # ej: "500g", "1kg"
    cantidad = Column(Float, nullable=False)  # ej: 0.5, 1.0 (en unidad del padre)
    precio_venta = Column(Float, nullable=True)  # override manual; null = usa margen
    activo = Column(Boolean, default=True)

    producto_padre = relationship("Producto", back_populates="fracciones")


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    tipo = Column(String(20), nullable=False, default="minorista")  # mayorista | minorista
    total = Column(Float, nullable=False, default=0.0)
    observaciones = Column(Text, default="")

    usuario = relationship("Usuario")
    detalles = relationship("DetalleVenta", back_populates="venta")


class DetalleVenta(Base):
    __tablename__ = "detalle_ventas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    fraccion_id = Column(Integer, ForeignKey("fracciones.id"), nullable=True)
    cantidad = Column(Float, nullable=False, default=1.0)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto")
    fraccion = relationship("Fraccion")


class MovimientoStock(Base):
    __tablename__ = "movimientos_stock"

    id = Column(Integer, primary_key=True, autoincrement=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    tipo = Column(String(20), nullable=False)  # entrada | salida | ajuste
    cantidad = Column(Float, nullable=False)
    referencia = Column(String(200), default="")
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)

    producto = relationship("Producto")
    usuario = relationship("Usuario")


class Gasto(Base):
    __tablename__ = "gastos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    descripcion = Column(String(300), nullable=False)
    monto = Column(Float, nullable=False)
    categoria_gasto = Column(String(100), default="General")
    fecha = Column(DateTime, default=datetime.utcnow)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    activo = Column(Boolean, default=True)

    usuario = relationship("Usuario")


class Auditoria(Base):
    __tablename__ = "auditoria"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    accion = Column(String(50), nullable=False)  # CREAR | MODIFICAR | DESACTIVAR | VENTA | AUMENTO_MASIVO
    tabla_afectada = Column(String(50), nullable=False)
    registro_id = Column(Integer, nullable=True)
    valor_anterior = Column(Text, default="{}")  # JSON
    valor_nuevo = Column(Text, default="{}")  # JSON
    fecha = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario")


# ---------------------------------------------------------------------------
# Inicialización
# ---------------------------------------------------------------------------

def init_db():
    """Crea todas las tablas y el usuario Admin por defecto si no existen."""
    Base.metadata.create_all(engine)

    session = SessionLocal()
    try:
        admin = session.query(Usuario).filter_by(username="admin").first()
        if not admin:
            pw_hash, pw_salt = hash_password("admin")
            admin = Usuario(
                username="admin",
                password_hash=pw_hash,
                password_salt=pw_salt,
                nombre="Administrador",
                rol="admin",
            )
            session.add(admin)

            # Categorías por defecto para dietética
            categorias_default = [
                "Harinas", "Frutos Secos", "Semillas", "Especias",
                "Cereales", "Legumbres", "Aceites", "Endulzantes",
                "Suplementos", "Otros"
            ]
            for cat_name in categorias_default:
                session.add(Categoria(nombre=cat_name))

            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
