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
    AccountProfile,
    AlertRule,
    Contact,
    Geofence,
    create_alert,
    create_contact,
    create_device,
    create_geofence,
    create_user,
    get_account_profile,
    get_all_positions,
    get_device,
    get_device_by_token,
    get_engine,
    get_geofence,
    get_latest_position,
    get_positions_in_range,
    get_user,
    init_db,
    list_alerts,
    list_contacts,
    list_devices_for_user,
    list_geofences,
    save_account_profile,
    save_position,
    update_geofence,
    delete_geofence,
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


class LiveStatus(BaseModel):
    device_id: str
    name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    speed: float | None = None
    ignition: bool | None = None
    last_update: str | None = None


class DateRangeQuery(BaseModel):
    start: datetime
    end: datetime

    @classmethod
    def from_strings(cls, start: str, end: str) -> "DateRangeQuery":
        return cls(start=datetime.fromisoformat(start), end=datetime.fromisoformat(end))


class UserCreate(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_user_or_404(username: str):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return user


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


class GeofencePayload(BaseModel):
    username: str
    name: str
    geometry: str
    description: str | None = None
    active: bool = True


class GeofenceResponse(BaseModel):
    id: int
    name: str
    description: str | None
    geometry: str
    active: bool

    @classmethod
    def from_orm(cls, geofence: Geofence) -> "GeofenceResponse":
        return cls(
            id=geofence.id,
            name=geofence.name,
            description=geofence.description,
            geometry=geofence.geometry,
            active=geofence.active,
        )


class ContactPayload(BaseModel):
    username: str
    name: str
    email: str | None = None
    phone: str | None = None
    channel_preferences: str | None = None


class ContactResponse(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    channel_preferences: str | None

    @classmethod
    def from_orm(cls, contact: Contact) -> "ContactResponse":
        return cls(
            id=contact.id,
            name=contact.name,
            email=contact.email,
            phone=contact.phone,
            channel_preferences=contact.channel_preferences,
        )


class AlertPayload(BaseModel):
    username: str
    name: str
    description: str | None = None
    geofence_id: int | None = None
    speed_threshold: float | None = None
    notify_on_entry: bool = True
    notify_on_exit: bool = False
    contact_ids: list[int] | None = None
    active: bool = True


class AlertResponse(BaseModel):
    id: int
    name: str
    description: str | None
    geofence_id: int | None
    speed_threshold: float | None
    notify_on_entry: bool
    notify_on_exit: bool
    contact_ids: list[int] | None
    active: bool

    @classmethod
    def from_orm(cls, alert: AlertRule) -> "AlertResponse":
        contact_ids = json.loads(alert.contact_ids) if alert.contact_ids else None
        return cls(
            id=alert.id,
            name=alert.name,
            description=alert.description,
            geofence_id=alert.geofence_id,
            speed_threshold=alert.speed_threshold,
            notify_on_entry=alert.notify_on_entry,
            notify_on_exit=alert.notify_on_exit,
            contact_ids=contact_ids,
            active=alert.active,
        )


class AccountProfilePayload(BaseModel):
    username: str
    full_name: str | None = None
    company: str | None = None
    billing_email: str | None = None
    payment_method: str | None = None
    plan: str | None = None
    tax_id: str | None = None


class AccountProfileResponse(BaseModel):
    full_name: str | None
    company: str | None
    billing_email: str | None
    payment_method: str | None
    plan: str | None
    tax_id: str | None

    @classmethod
    def from_orm(cls, profile: AccountProfile) -> "AccountProfileResponse":
        return cls(
            full_name=profile.full_name,
            company=profile.company,
            billing_email=profile.billing_email,
            payment_method=profile.payment_method,
            plan=profile.plan,
            tax_id=profile.tax_id,
        )


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


@app.get("/devices/{device_id}/positions/range", response_model=list[PositionResponse])
async def positions_in_range(device_id: str, start: str, end: str):
    """Devuelve posiciones dentro de un rango temporal para reproducción histórica."""

    try:
        date_range = DateRangeQuery.from_strings(start, end)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fechas inválidas, usa ISO8601")

    positions = get_positions_in_range(device_id, date_range.start, date_range.end, engine=get_engine())
    return [PositionResponse.from_orm(pos) for pos in positions]


@app.get("/fleet/live", response_model=list[LiveStatus])
async def fleet_live(username: str, device_id: str | None = None):
    """Vista de mapa en vivo por flota/vehículo con estado principal."""

    user = get_user_or_404(username)
    devices = list_devices_for_user(user, engine=get_engine())
    if device_id:
        devices = [d for d in devices if d.id == device_id]
    statuses: list[LiveStatus] = []
    for device in devices:
        latest = get_latest_position(device.id, engine=get_engine())
        statuses.append(
            LiveStatus(
                device_id=device.id,
                name=device.name,
                latitude=latest.latitude if latest else None,
                longitude=latest.longitude if latest else None,
                speed=latest.speed if latest else None,
                ignition=latest.ignition if latest else None,
                last_update=latest.timestamp.isoformat() if latest else None,
            )
        )
    return statuses


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


@app.post("/geofences", response_model=GeofenceResponse)
async def create_geofence_endpoint(payload: GeofencePayload):
    """Crea una geocerca definida por el usuario."""

    user = get_user_or_404(payload.username)
    geofence = create_geofence(
        user=user,
        name=payload.name,
        geometry=payload.geometry,
        description=payload.description,
        active=payload.active,
        engine=get_engine(),
    )
    return GeofenceResponse.from_orm(geofence)


@app.get("/geofences", response_model=list[GeofenceResponse])
async def list_geofences_endpoint(username: str):
    user = get_user_or_404(username)
    geofences = list_geofences(user, engine=get_engine())
    return [GeofenceResponse.from_orm(g) for g in geofences]


@app.put("/geofences/{geofence_id}", response_model=GeofenceResponse)
async def update_geofence_endpoint(geofence_id: int, payload: GeofencePayload):
    user = get_user_or_404(payload.username)
    geofence = get_geofence(geofence_id, user=user, engine=get_engine())
    if not geofence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geocerca no encontrada")
    updated = update_geofence(
        geofence,
        name=payload.name,
        geometry=payload.geometry,
        description=payload.description,
        active=payload.active,
        engine=get_engine(),
    )
    return GeofenceResponse.from_orm(updated)


@app.delete("/geofences/{geofence_id}")
async def delete_geofence_endpoint(geofence_id: int, username: str):
    user = get_user_or_404(username)
    geofence = get_geofence(geofence_id, user=user, engine=get_engine())
    if not geofence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geocerca no encontrada")
    delete_geofence(geofence, engine=get_engine())
    return {"deleted": True}


@app.post("/contacts", response_model=ContactResponse)
async def create_contact_endpoint(payload: ContactPayload):
    user = get_user_or_404(payload.username)
    contact = create_contact(
        user=user,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        channel_preferences=payload.channel_preferences,
        engine=get_engine(),
    )
    return ContactResponse.from_orm(contact)


@app.get("/contacts", response_model=list[ContactResponse])
async def list_contacts_endpoint(username: str):
    user = get_user_or_404(username)
    contacts = list_contacts(user, engine=get_engine())
    return [ContactResponse.from_orm(contact) for contact in contacts]


@app.post("/alerts", response_model=AlertResponse)
async def create_alert_endpoint(payload: AlertPayload):
    user = get_user_or_404(payload.username)
    geofence = None
    if payload.geofence_id is not None:
        geofence = get_geofence(payload.geofence_id, user=user, engine=get_engine())
        if not geofence:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geocerca no encontrada")

    contact_ids = json.dumps(payload.contact_ids) if payload.contact_ids else None
    alert = create_alert(
        user=user,
        name=payload.name,
        description=payload.description,
        geofence_id=geofence.id if geofence else None,
        speed_threshold=payload.speed_threshold,
        notify_on_entry=payload.notify_on_entry,
        notify_on_exit=payload.notify_on_exit,
        contact_ids=contact_ids,
        active=payload.active,
        engine=get_engine(),
    )
    return AlertResponse.from_orm(alert)


@app.get("/alerts", response_model=list[AlertResponse])
async def list_alerts_endpoint(username: str):
    user = get_user_or_404(username)
    alerts = list_alerts(user, engine=get_engine())
    return [AlertResponse.from_orm(alert) for alert in alerts]


def _positions_to_csv(rows: list[Position]) -> str:
    header = "timestamp,latitude,longitude,speed,course,ignition"
    lines = [header]
    for pos in rows:
        lines.append(
            ",".join(
                [
                    pos.timestamp.isoformat(),
                    str(pos.latitude),
                    str(pos.longitude),
                    str(pos.speed or 0),
                    str(pos.course or 0),
                    str(pos.ignition if pos.ignition is not None else ""),
                ]
            )
        )
    return "\n".join(lines)


def _stops_report(rows: list[Position]) -> str:
    stops = [p for p in rows if (p.speed or 0) <= 1]
    header = "timestamp,latitude,longitude"
    lines = [header]
    for pos in stops:
        lines.append(
            ",".join(
                [pos.timestamp.isoformat(), str(pos.latitude), str(pos.longitude)]
            )
        )
    return "\n".join(lines)


def _speeding_report(rows: list[Position], threshold: float) -> str:
    offenders = [p for p in rows if p.speed and p.speed > threshold]
    header = "timestamp,latitude,longitude,speed"
    lines = [header]
    for pos in offenders:
        lines.append(
            ",".join(
                [
                    pos.timestamp.isoformat(),
                    str(pos.latitude),
                    str(pos.longitude),
                    str(pos.speed),
                ]
            )
        )
    return "\n".join(lines)


def _usage_report(rows: list[Position]) -> str:
    buckets: dict[int, int] = {}
    for pos in rows:
        hour = pos.timestamp.hour
        buckets[hour] = buckets.get(hour, 0) + 1
    header = "hour,count"
    lines = [header]
    for hour in sorted(buckets.keys()):
        lines.append(f"{hour},{buckets[hour]}")
    return "\n".join(lines)


@app.get("/reports/download")
async def download_report(device_id: str, username: str, start: str, end: str, report_type: str = "routes", speeding_threshold: float = 80.0):
    """Genera reportes descargables (rutas, paradas, excesos de velocidad, uso horario)."""

    user = get_user_or_404(username)
    device = get_device(device_id, engine=get_engine())
    if not device or device.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo no encontrado")

    try:
        date_range = DateRangeQuery.from_strings(start, end)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fechas inválidas, usa ISO8601")

    rows = get_positions_in_range(device_id, date_range.start, date_range.end, engine=get_engine())
    if report_type == "routes":
        content = _positions_to_csv(rows)
    elif report_type == "stops":
        content = _stops_report(rows)
    elif report_type == "speeding":
        content = _speeding_report(rows, threshold=speeding_threshold)
    elif report_type == "usage":
        content = _usage_report(rows)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de reporte inválido")

    filename = f"{device_id}-{report_type}.csv"
    return StreamingResponse(iter([content]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.put("/account/profile", response_model=AccountProfileResponse)
async def update_account_profile(body: AccountProfilePayload):
    user = get_user_or_404(body.username)
    profile = save_account_profile(
        user,
        full_name=body.full_name,
        company=body.company,
        billing_email=body.billing_email,
        payment_method=body.payment_method,
        plan=body.plan,
        tax_id=body.tax_id,
        engine=get_engine(),
    )
    return AccountProfileResponse.from_orm(profile)


@app.get("/account/profile", response_model=AccountProfileResponse)
async def get_account_profile_endpoint(username: str):
    user = get_user_or_404(username)
    profile = get_account_profile(user, engine=get_engine())
    if not profile:
        profile = save_account_profile(user, engine=get_engine())
    return AccountProfileResponse.from_orm(profile)


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


