import asyncio
import os
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

# La base de datos se define antes de importar la app para que init_db use el destino correcto.
os.environ["DATABASE_URL"] = "sqlite:///./test_ingest.db"

from gps_tracker.api import ingest_http  # noqa: E402
from gps_tracker.database import (  # noqa: E402
    create_device,
    create_user,
    get_all_positions,
    get_engine,
    init_db,
)
from gps_tracker.api import IngestPayload  # noqa: E402


def setup_module(module):
    db_path = pathlib.Path("test_ingest.db")
    if db_path.exists():
        db_path.unlink()
    init_db()


def test_http_ingest_happy_path():
    engine = get_engine()
    user = create_user("demo", "demo", engine=engine)
    device = create_device("dev-1", user=user, token="secret-token", engine=engine)

    payload = IngestPayload(latitude=40.0, longitude=-3.0, speed=50.0, ignition=True)
    response = asyncio.run(ingest_http(payload, x_device_token=device.token))

    assert response.device_id == device.id
    assert response.ignition is True

    # Se ha guardado en base de datos y la consulta histórica lo devuelve.
    history = get_all_positions(device.id, engine=engine)
    assert len(history) == 1
    assert history[0].speed == 50.0


def test_http_ingest_rejects_invalid_token():
    payload = IngestPayload(latitude=0.0, longitude=0.0)
    try:
        asyncio.run(ingest_http(payload, x_device_token="bad"))
    except Exception as exc:  # noqa: BLE001
        assert "Token de dispositivo inválido" in str(exc)
