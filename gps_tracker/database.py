"""
Módulo de base de datos para la aplicación de rastreo GPS.

Define modelos sencillos para posiciones, usuarios y entidades
configurables como geocercas, alertas y contactos. Utiliza SQLite
por defecto para facilitar las pruebas locales.
"""

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    ForeignKey,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker, relationship


# Crea la base declarativa para los modelos
Base = declarative_base()


class Position(Base):
    """Modelo que representa una posición GPS recibida del dispositivo."""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, ForeignKey("devices.id"), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed = Column(Float, nullable=True)
    course = Column(Float, nullable=True)
    ignition = Column(Boolean, nullable=True)
    event_type = Column(String, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Position(device_id={self.device_id}, lat={self.latitude}, "
            f"lon={self.longitude}, timestamp={self.timestamp})"
        )


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
    token = Column(String, unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=True)
    description = Column(String, nullable=True)

    # Relación con usuario
    user = relationship("User", back_populates="devices")
    positions = relationship("Position", backref="device", cascade="all, delete-orphan")


class Geofence(Base):
    """Geocerca definida por el usuario."""

    __tablename__ = "geofences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    geometry = Column(Text, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", backref="geofences")


class Contact(Base):
    """Contacto para notificaciones de alertas."""

    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    channel_preferences = Column(String, nullable=True)

    user = relationship("User", backref="contacts")


class AlertRule(Base):
    """Regla de alerta configurable."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    geofence_id = Column(Integer, ForeignKey("geofences.id"), nullable=True)
    speed_threshold = Column(Float, nullable=True)
    notify_on_entry = Column(Boolean, default=True, nullable=False)
    notify_on_exit = Column(Boolean, default=False, nullable=False)
    contact_ids = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", backref="alerts")
    geofence = relationship("Geofence", backref="alerts")


class AccountProfile(Base):
    """Perfil y datos de facturación de una cuenta."""

    __tablename__ = "account_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    full_name = Column(String, nullable=True)
    company = Column(String, nullable=True)
    billing_email = Column(String, nullable=True)
    payment_method = Column(String, nullable=True)
    plan = Column(String, nullable=True)
    tax_id = Column(String, nullable=True)

    user = relationship("User", backref="account_profile", uselist=False)


# Funciones de infraestructura base

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


# Consultas y mutaciones sobre posiciones y dispositivos

def save_position(
    device_id: str,
    latitude: float,
    longitude: float,
    speed: Optional[float] = None,
    course: Optional[float] = None,
    ignition: Optional[bool] = None,
    event_type: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    engine=None,
) -> Position:
    """Guarda una posición en la base de datos y la devuelve."""
    session = get_session(engine)
    try:
        pos = Position(
            device_id=device_id,
            timestamp=timestamp or datetime.utcnow(),
            latitude=latitude,
            longitude=longitude,
            speed=speed,
            course=course,
            ignition=ignition,
            event_type=event_type,
        )
        session.add(pos)
        session.commit()
        session.refresh(pos)
        return pos
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


def get_positions_in_range(
    device_id: str, start: datetime, end: datetime, engine=None
) -> list[Position]:
    """Posiciones de un dispositivo dentro de un rango temporal."""
    session = get_session(engine)
    try:
        return (
            session.query(Position)
            .filter(
                Position.device_id == device_id,
                Position.timestamp >= start,
                Position.timestamp <= end,
            )
            .order_by(Position.timestamp.asc())
            .all()
        )
    finally:
        session.close()


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


def create_device(
    device_id: str,
    user: User,
    token: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    engine=None,
) -> Device:
    """Crea un nuevo dispositivo asociado a un usuario."""
    session = get_session(engine)
    try:
        device = Device(
            id=device_id,
            token=token,
            user_id=user.id,
            name=name,
            description=description,
        )
        session.add(device)
        session.commit()
        session.refresh(device)
        return device
    finally:
        session.close()


def get_device_by_token(token: str, engine=None) -> Optional[Device]:
    """Obtiene un dispositivo a partir de su token de autenticación."""

    session = get_session(engine)
    try:
        return session.query(Device).filter(Device.token == token).first()
    finally:
        session.close()


def list_devices_for_user(user: User, engine=None) -> list[Device]:
    """Devuelve todos los dispositivos asociados a un usuario."""
    session = get_session(engine)
    try:
        return session.query(Device).filter(Device.user_id == user.id).all()
    finally:
        session.close()


# Geocercas, contactos y alertas

def create_geofence(
    user: User,
    name: str,
    geometry: str,
    description: Optional[str] = None,
    active: bool = True,
    engine=None,
) -> Geofence:
    session = get_session(engine)
    try:
        geofence = Geofence(
            user_id=user.id,
            name=name,
            geometry=geometry,
            description=description,
            active=active,
        )
        session.add(geofence)
        session.commit()
        session.refresh(geofence)
        return geofence
    finally:
        session.close()


def list_geofences(user: User, engine=None) -> list[Geofence]:
    session = get_session(engine)
    try:
        return session.query(Geofence).filter(Geofence.user_id == user.id).all()
    finally:
        session.close()


def get_geofence(geofence_id: int, user: User, engine=None) -> Optional[Geofence]:
    session = get_session(engine)
    try:
        return (
            session.query(Geofence)
            .filter(Geofence.id == geofence_id, Geofence.user_id == user.id)
            .first()
        )
    finally:
        session.close()


def update_geofence(
    geofence: Geofence,
    name: Optional[str] = None,
    geometry: Optional[str] = None,
    description: Optional[str] = None,
    active: Optional[bool] = None,
    engine=None,
) -> Geofence:
    session = get_session(engine)
    try:
        record = session.merge(geofence)
        if name is not None:
            record.name = name
        if geometry is not None:
            record.geometry = geometry
        if description is not None:
            record.description = description
        if active is not None:
            record.active = active
        session.commit()
        session.refresh(record)
        return record
    finally:
        session.close()


def delete_geofence(geofence: Geofence, engine=None) -> None:
    session = get_session(engine)
    try:
        record = session.merge(geofence)
        session.delete(record)
        session.commit()
    finally:
        session.close()


def create_contact(
    user: User,
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    channel_preferences: Optional[str] = None,
    engine=None,
) -> Contact:
    session = get_session(engine)
    try:
        contact = Contact(
            user_id=user.id,
            name=name,
            email=email,
            phone=phone,
            channel_preferences=channel_preferences,
        )
        session.add(contact)
        session.commit()
        session.refresh(contact)
        return contact
    finally:
        session.close()


def list_contacts(user: User, engine=None) -> list[Contact]:
    session = get_session(engine)
    try:
        return session.query(Contact).filter(Contact.user_id == user.id).all()
    finally:
        session.close()


def create_alert(
    user: User,
    name: str,
    description: Optional[str] = None,
    geofence_id: Optional[int] = None,
    speed_threshold: Optional[float] = None,
    notify_on_entry: bool = True,
    notify_on_exit: bool = False,
    contact_ids: Optional[str] = None,
    active: bool = True,
    engine=None,
) -> AlertRule:
    session = get_session(engine)
    try:
        alert = AlertRule(
            user_id=user.id,
            name=name,
            description=description,
            geofence_id=geofence_id,
            speed_threshold=speed_threshold,
            notify_on_entry=notify_on_entry,
            notify_on_exit=notify_on_exit,
            contact_ids=contact_ids,
            active=active,
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        return alert
    finally:
        session.close()


def list_alerts(user: User, engine=None) -> list[AlertRule]:
    session = get_session(engine)
    try:
        return session.query(AlertRule).filter(AlertRule.user_id == user.id).all()
    finally:
        session.close()


# Perfil de cuenta y facturación

def save_account_profile(
    user: User,
    full_name: Optional[str] = None,
    company: Optional[str] = None,
    billing_email: Optional[str] = None,
    payment_method: Optional[str] = None,
    plan: Optional[str] = None,
    tax_id: Optional[str] = None,
    engine=None,
) -> AccountProfile:
    session = get_session(engine)
    try:
        profile = (
            session.query(AccountProfile)
            .filter(AccountProfile.user_id == user.id)
            .first()
        )
        if profile is None:
            profile = AccountProfile(user_id=user.id)
            session.add(profile)
            session.flush()
        profile.full_name = full_name or profile.full_name
        profile.company = company or profile.company
        profile.billing_email = billing_email or profile.billing_email
        profile.payment_method = payment_method or profile.payment_method
        profile.plan = plan or profile.plan
        profile.tax_id = tax_id or profile.tax_id
        session.commit()
        session.refresh(profile)
        return profile
    finally:
        session.close()


def get_account_profile(user: User, engine=None) -> Optional[AccountProfile]:
    session = get_session(engine)
    try:
        return session.query(AccountProfile).filter(AccountProfile.user_id == user.id).first()
    finally:
        session.close()
