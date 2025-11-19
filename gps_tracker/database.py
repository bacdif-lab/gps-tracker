"""
Módulo de base de datos para la aplicación de rastreo GPS.

Define un modelo sencillo para almacenar posiciones enviadas por dispositivos
GPS. Para simplificar, utilizamos SQLite a través de SQLAlchemy.

La tabla `Position` almacena la última posición recibida por cada dispositivo,
adémas de un historial de posiciones si se consulta a través de la API.

Para una solución de producción, sería recomendable usar PostgreSQL
u otro motor relacional escalable y añadir índices geoespaciales.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker


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


def get_engine(db_url: str = "sqlite:///./gps_data.db"):
    """Inicializa el motor de base de datos."""
    return create_engine(db_url, connect_args={"check_same_thread": False})


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
