import os
import pathlib
import sys

import pytest

httpx = pytest.importorskip("httpx")
AsyncClient = httpx.AsyncClient

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

os.environ["DATABASE_URL"] = "sqlite:///./test_synthetic.db"

from gps_tracker.api import IngestPayload, app  # noqa: E402
from gps_tracker.database import (  # noqa: E402
    create_device,
    create_user,
    get_engine,
    get_latest_position,
    init_db,
)


def setup_module(module):
    db_path = pathlib.Path("test_synthetic.db")
    if db_path.exists():
        db_path.unlink()
    init_db()


@pytest.fixture(scope="module")
def device_token():
    engine = get_engine()
    user = create_user("synthetic-user", "strong-pass", engine=engine)
    device = create_device("synthetic-dev", user=user, token="synthetic-token", engine=engine)
    return device.token


@pytest.mark.asyncio
async def test_health_probe_multiple_regions():
    regions = ["us-east-1", "eu-west-1", "sa-east-1"]
    async with AsyncClient(app=app, base_url="https://test") as client:
        for region in regions:
            response = await client.get("/health", headers={"X-Region": region})
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ingestion_probe_from_region(device_token):
    payload = IngestPayload(latitude=10.0, longitude=-70.0, speed=32.5, event_type="synthetic")
    async with AsyncClient(app=app, base_url="https://test") as client:
        response = await client.post(
            "/ingest/http",
            json=payload.dict(),
            headers={"X-Device-Token": device_token, "X-Region": "eu-west-1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["device_id"] == "synthetic-dev"

    latest = get_latest_position("synthetic-dev", engine=get_engine())
    assert latest is not None
    assert latest.event_type == "synthetic"
