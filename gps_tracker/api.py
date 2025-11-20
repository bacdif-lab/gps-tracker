"""
API REST para consultar las posiciones GPS almacenadas.

Utiliza FastAPI para exponer endpoints que devuelven la última posición
de un dispositivo o un historial de posiciones. También proporciona un
endpoint de salud para comprobar que la API está corriendo.
"""

import asyncio
import json
from datetime import datetime, timedelta
from fastapi import Depends, FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
try:
    from prometheus_fastapi_instrumentator import Instrumentator
except ImportError:  # pragma: no cover - dependencia opcional
    Instrumentator = None

import importlib.util

MULTIPART_AVAILABLE = importlib.util.find_spec("multipart") is not None

from .database import (
    Position,
    create_device,
    get_all_positions,
    get_engine,
    get_latest_position,
    get_device_by_token,
    init_db,
    save_position,
    create_user,
    get_user,
)
from .auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

app = FastAPI(title="GPS Tracking API", version="0.1")

init_db()


if Instrumentator:
    Instrumentator().instrument(app).expose(app)


class PositionResponse(BaseModel):
    device_id: str
    timestamp: str
    latitude: float
    longitude: float
    speed: float | None = None
    course: float | None = None
    ignition: bool | None = None
    event_type: str | None = None

    @classmethod
    def from_orm(cls, position: Position) -> "PositionResponse":
        return cls(
            device_id=position.device_id,
            timestamp=position.timestamp.isoformat(),
            latitude=position.latitude,
            longitude=position.longitude,
            speed=position.speed,
            course=position.course,
            ignition=position.ignition,
            event_type=position.event_type,
        )


class UserCreate(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class IngestPayload(BaseModel):
    latitude: float = Field(..., description="Latitud en grados decimales")
    longitude: float = Field(..., description="Longitud en grados decimales")
    speed: float | None = Field(None, description="Velocidad en km/h")
    course: float | None = Field(None, description="Rumbo en grados")
    ignition: bool | None = Field(None, description="Estado de ignición del vehículo")
    event_type: str | None = Field(None, description="Evento discreto reportado por el dispositivo")
    timestamp: datetime | None = Field(None, description="Fecha de la posición si el dispositivo la incluye")

    def normalized(self) -> dict:
        """Normaliza valores y protege contra coordenadas fuera de rango."""

        lat = max(min(self.latitude, 90.0), -90.0)
        lon = max(min(self.longitude, 180.0), -180.0)
        ts = self.timestamp or datetime.utcnow()
        return {
            "latitude": lat,
            "longitude": lon,
            "speed": self.speed,
            "course": self.course,
            "ignition": self.ignition,
            "event_type": self.event_type,
            "timestamp": ts,
        }


class DeviceRegistration(BaseModel):
    device_id: str
    token: str
    username: str
    password: str
    name: str | None = None
    description: str | None = None


class LiveBroadcaster:
    """Difunde posiciones en vivo a través de WebSockets y SSE."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._event_queue: asyncio.Queue[dict] = asyncio.Queue()

    async def register(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def unregister(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        """Envía el payload a clientes conectados y lo añade al stream SSE."""

        stale: list[WebSocket] = []
        for connection in self._connections:
            try:
                await connection.send_json(payload)
            except Exception:  # pragma: no cover - desconexiones inesperadas
                stale.append(connection)
        for connection in stale:
            self.unregister(connection)
        await self._event_queue.put(payload)

    async def sse_stream(self):
        while True:
            payload = await self._event_queue.get()
            yield f"data: {json.dumps(payload)}\n\n"


broadcaster = LiveBroadcaster()


@app.get("/health")
async def health():
    """Endpoint de salud para comprobar que la API funciona."""
    return {"status": "ok"}


@app.get("/devices/{device_id}/latest", response_model=PositionResponse)
async def latest_position(device_id: str):
    """Devuelve la última posición conocida de un dispositivo."""
    position = get_latest_position(device_id, engine=get_engine())
    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return PositionResponse.from_orm(position)


@app.get("/devices/{device_id}/positions", response_model=list[PositionResponse])
async def all_positions(device_id: str, limit: int = 100):
    """Devuelve un historial de posiciones para un dispositivo."""
    positions = get_all_positions(device_id, limit=limit, engine=get_engine())
    return [PositionResponse.from_orm(pos) for pos in positions]


@app.post("/register")
async def register_user(user: UserCreate):
    """Registra un nuevo usuario."""
    existing_user = get_user(user.username)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El nombre de usuario ya existe")
    hashed_password = get_password_hash(user.password)
    new_user = create_user(user.username, hashed_password)
    return {"id": new_user.id, "username": new_user.username}


@app.post("/devices/register")
async def register_device(body: DeviceRegistration):
    """Registra un dispositivo y vincula su token de ingestión a un usuario."""

    user = get_user(body.username)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    device = create_device(
        device_id=body.device_id,
        token=body.token,
        user=user,
        name=body.name,
        description=body.description,
    )
    return {"device_id": device.id, "token": device.token}


@app.post("/ingest/http", response_model=PositionResponse)
async def ingest_http(
    payload: IngestPayload,
    x_device_token: str = Header(..., alias="X-Device-Token"),
):
    """Ingesta de posiciones vía HTTP autenticadas por token de dispositivo."""

    device = get_device_by_token(x_device_token)
    if not device:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de dispositivo inválido")

    normalized = payload.normalized()
    engine = get_engine()
    position = save_position(
        device_id=device.id,
        latitude=normalized["latitude"],
        longitude=normalized["longitude"],
        speed=normalized["speed"],
        course=normalized["course"],
        ignition=normalized["ignition"],
        event_type=normalized["event_type"],
        timestamp=normalized["timestamp"],
        engine=engine,
    )

    await broadcaster.broadcast(PositionResponse.from_orm(position).dict())
    return PositionResponse.from_orm(position)


@app.websocket("/ws/positions")
async def websocket_positions(websocket: WebSocket):
    await broadcaster.register(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        broadcaster.unregister(websocket)


@app.get("/stream/sse")
async def sse_positions():
    return StreamingResponse(broadcaster.sse_stream(), media_type="text/event-stream")


if MULTIPART_AVAILABLE:

    @app.post("/token", response_model=Token)
    async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
        """Genera un token de acceso para un usuario autenticado."""
        user = get_user(form_data.username)
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
else:

    class LoginBody(BaseModel):
        username: str
        password: str

    @app.post("/token", response_model=Token)
    async def login_for_access_token_json(body: LoginBody):
        """Alternativa JSON cuando no está disponible python-multipart."""

        user = get_user(body.username)
        if not user or not verify_password(body.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}


