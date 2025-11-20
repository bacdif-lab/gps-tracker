"""Carga datos seed para desarrollo local.

Crea tablas si no existen y añade un usuario de demo, un dispositivo y
algunas posiciones para pruebas manuales.
"""

from datetime import datetime, timedelta

from gps_tracker.auth import get_password_hash
from gps_tracker.database import (
    Position,
    create_device,
    create_user,
    get_device,
    get_engine,
    get_session,
    get_user,
    init_db,
)


def seed() -> None:
    engine = get_engine()
    init_db(engine=engine)
    session = get_session(engine)
    try:
        user = get_user("demo", engine=engine)
        if not user:
            user = create_user("demo", get_password_hash("changeme"), engine=engine)

        device = get_device("demo-device", engine=engine)
        if not device:
            device = create_device(
                "demo-device",
                user=user,
                name="Rastreador de prueba",
                description="Equipo de demostración para el stack local",
                engine=engine,
            )

        if not session.query(Position).filter(Position.device_id == device.id).first():
            now = datetime.utcnow()
            for idx in range(5):
                session.add(
                    Position(
                        device_id=device.id,
                        latitude=40.4168 + idx * 0.0001,
                        longitude=-3.7038 - idx * 0.0001,
                        speed=30 + idx,
                        course=90,
                        timestamp=now - timedelta(minutes=idx * 5),
                    )
                )
            session.commit()
            print("Datos de demo insertados")
        else:
            print("Datos de demo ya existentes; no se insertan duplicados")
    finally:
        session.close()


if __name__ == "__main__":
    seed()
