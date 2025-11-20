"""
Módulo de base de datos para la aplicación de rastreo GPS.

Define un modelo sencillo para almacenar posiciones enviadas por dispositivos
GPS. Para simplificar, utilizamos SQLite a través de SQLAlchemy.

La tabla `Position` almacena la última posición recibida por cada dispositivo,
adémas de un historial de posiciones si se consulta a través de la API.

Para una solución de producción, sería recomendable usar PostgreSQL
u otro motor relacional escalable y añadir índices geoespaciales.
"""

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    ForeignKey,
    create_engine,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker, relationship


# Crea la base declarativa para los modelos
Base = declarative_base()


class Position(Base):
    """Modelo que representa una posición GPS recibida del dispositivo."""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed = Column(Float, nullable=True)
    course = Column(Float, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Position(device_id={self.device_id}, lat={self.latitude}, "
            f"lon={self.longitude}, timestamp={self.timestamp})"
        )


def get_engine(db_url: str | None = None):
    """Inicializa el motor de base de datos.

    Se prioriza la variable de entorno ``DATABASE_URL`` y se cae en SQLite
    para entornos locales cuando no está definida. Si se utiliza SQLite,
    se agregan los ``connect_args`` adecuados para permitir conexiones
    multi-hilo durante pruebas o desarrollo.
    """

    url = db_url or os.getenv("DATABASE_URL", "sqlite:///./gps_data.db")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


def init_db(engine=None) -> None:
    """Crea las tablas en la base de datos si no existen."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_session(engine=None) -> Session:
    """Devuelve una sesión de base de datos lista para usar."""
    if engine is None:
        engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def save_position(
    device_id: str,
    latitude: float,
    longitude: float,
    speed: Optional[float] = None,
    course: Optional[float] = None,
    engine=None,
) -> None:
    """Guarda una posición en la base de datos."""
    session = get_session(engine)
    try:
        pos = Position(
            device_id=device_id,
            latitude=latitude,
            longitude=longitude,
            speed=speed,
            course=course,
        )
        session.add(pos)
        session.commit()
    finally:
        session.close()


def get_latest_position(device_id: str, engine=None) -> Optional[Position]:
    """Obtiene la última posición registrada de un dispositivo."""
    session = get_session(engine)
    try:
        return (
            session.query(Position)
            .filter(Position.device_id == device_id)
            .order_by(Position.timestamp.desc())
            .first()
        )
    finally:
        session.close()


def get_all_positions(device_id: str, limit: int = 1000, engine=None) -> list[Position]:
    """Obtiene un historial de posiciones para un dispositivo."""
    session = get_session(engine)
    try:
        return (
            session.query(Position)
            .filter(Position.device_id == device_id)
            .order_by(Position.timestamp.desc())
            .limit(limit)
            .all()
        )
    finally:
        session.close()


class User(Base):
    """Modelo que representa un usuario de la aplicación."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # Relación con dispositivos
    devices = relationship("Device", back_populates="user")


class Device(Base):
    """Modelo que representa un dispositivo GPS asociado a un usuario."""
    __tablename__ = "devices"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=True)
    description = Column(String, nullable=True)

    # Relación con usuario
    user = relationship("User", back_populates="devices")
    positions = relationship("Position", backref="device", cascade="all, delete-orphan")


def get_user(username: str, engine=None) -> Optional[User]:
    """Obtiene un usuario por su nombre de usuario."""
    session = get_session(engine)
    try:
        return session.query(User).filter(User.username == username).first()
    finally:
        session.close()


def create_user(username: str, hashed_password: str, engine=None) -> User:
    """Crea un nuevo usuario con la contraseña ya hasheada."""
    session = get_session(engine)
    try:
        user = User(username=username, hashed_password=hashed_password)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def get_device(device_id: str, engine=None) -> Optional[Device]:
    """Obtiene un dispositivo por su identificador."""
    session = get_session(engine)
    try:
        return session.query(Device).filter(Device.id == device_id).first()
    finally:
        session.close()


def create_device(device_id: str, user: User, name: Optional[str] = None, description: Optional[str] = None, engine=None) -> Device:
    """Crea un nuevo dispositivo asociado a un usuario."""
    session = get_session(engine)
    try:
        device = Device(id=device_id, user_id=user.id, name=name, description=description)
        session.add(device)
        session.commit()
        session.refresh(device)
        return device
    finally:
        session.close()
