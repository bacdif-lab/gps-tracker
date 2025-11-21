import asyncio
import os
import pathlib
import sys

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

os.environ["DATABASE_URL"] = "sqlite:///./test_realtime.db"

from gps_tracker.api import IngestPayload, broadcaster, ingest_http  # noqa: E402
from gps_tracker.database import (  # noqa: E402
    create_device,
    create_user,
    get_engine,
    get_latest_position,
    init_db,
)
from gps_tracker.gps_server import GPSServer  # noqa: E402
from gps_tracker.integrations.notifications import (  # noqa: E402
    NotificationDispatcher,
    NotificationMessage,
    NotificationQueue,
)
from gps_tracker.protocols import DecodedPosition, TeltonikaAdapter  # noqa: E402


def setup_module(module):
    db_path = pathlib.Path("test_realtime.db")
    if db_path.exists():
        db_path.unlink()
    init_db()


@pytest.fixture(scope="module")
def device():
    engine = get_engine()
    user = create_user("realtime-user", "not-secure", engine=engine)
    return create_device("realtime-dev", user=user, token="token-123", engine=engine)


def test_http_ingest_normalizes_and_persists(device):
    payload = IngestPayload(latitude=95.0, longitude=-200.0, speed=72.3, ignition=True)
    response = asyncio.run(ingest_http(payload, x_device_token=device.token))

    assert response.latitude == 90.0
    assert response.longitude == -180.0

    latest = get_latest_position(device.id, engine=get_engine())
    assert latest is not None
    assert latest.latitude == 90.0
    assert latest.longitude == -180.0


def test_websocket_broadcast_after_ingest(device):
    class DummyWebSocket:
        def __init__(self):
            self.messages: list[dict] = []

        async def accept(self) -> None:
            return None

        async def send_json(self, payload: dict) -> None:
            self.messages.append(payload)

    websocket = DummyWebSocket()
    asyncio.run(broadcaster.register(websocket))

    payload = IngestPayload(latitude=10.1234, longitude=-70.5678, speed=12.0)
    asyncio.run(ingest_http(payload, x_device_token=device.token))

    assert websocket.messages, "El broadcast no entregó datos al cliente"
    message = websocket.messages[-1]
    assert message["device_id"] == device.id
    assert message["speed"] == pytest.approx(12.0)
    broadcaster.unregister(websocket)


def test_tcp_ingest_via_teltonika_adapter(device):
    async def run_flow():
        engine = get_engine()
        server = GPSServer(host="127.0.0.1", port=0)
        teltonika = TeltonikaAdapter()
        position = DecodedPosition(
            device_id=device.id,
            latitude=19.4326,
            longitude=-99.1332,
            speed=45.5,
            course=180,
            event_type="tcp",
        )

        srv = await asyncio.start_server(server.handle_client, server.host, server.port)
        port = srv.sockets[0].getsockname()[1]

        _reader, writer = await asyncio.open_connection(server.host, port)
        writer.write(f"teltonika|{teltonika.simulate_payload(position).decode()}\n".encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()

        await asyncio.sleep(0.2)
        srv.close()
        await srv.wait_closed()

        latest = get_latest_position(device.id, engine=engine)
        assert latest is not None
        assert latest.event_type == "tcp"
        assert latest.speed == pytest.approx(45.5)

    asyncio.run(run_flow())


def test_notification_queue_dispatches_to_push_channel():
    class Recorder:
        def __init__(self, label: str):
            self.label = label
            self.messages = []

        async def send(self, message: NotificationMessage):
            self.messages.append(message)
            return {"sent": self.label, "recipient": message.recipient}

    email = Recorder("email")
    sms = Recorder("sms")
    push = Recorder("push")

    dispatcher = NotificationDispatcher(email, sms, push)
    queue = NotificationQueue(redis_url=None)

    alert = NotificationMessage(
        channel="push",
        recipient="mobile-user",
        subject="Exceso de velocidad",
        body="El vehículo superó el umbral configurado",
        metadata={"device_token": "abc123", "platform": "fcm"},
    )

    async def run_flow():
        await queue.enqueue(alert)
        dequeued = await queue.dequeue(timeout=1)
        assert dequeued is not None

        result = await dispatcher.dispatch(dequeued)
        assert push.messages[0].recipient == "mobile-user"
        assert result["sent"] == "push"
        assert not email.messages
        assert not sms.messages

    asyncio.run(run_flow())

