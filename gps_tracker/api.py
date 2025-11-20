"""
API REST para consultar las posiciones GPS almacenadas.

Utiliza FastAPI para exponer endpoints que devuelven la última posición
de un dispositivo o un historial de posiciones. También proporciona un
endpoint de salud para comprobar que la API está corriendo.
"""

from datetime import timedelta
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
try:
    from prometheus_fastapi_instrumentator import Instrumentator
except ImportError:  # pragma: no cover - dependencia opcional
    Instrumentator = None
try:  # pragma: no cover - dependencia opcional en entorno de CI
    import multipart  # type: ignore

    MULTIPART_AVAILABLE = True
except ImportError:  # pragma: no cover
    MULTIPART_AVAILABLE = False

from .database import (
    Position,
    get_all_positions,
    get_engine,
    get_latest_position,
    User,
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

if Instrumentator:
    Instrumentator().instrument(app).expose(app)


class PositionResponse(BaseModel):
    device_id: str
    timestamp: str
    latitude: float
    longitude: float
    speed: float | None = None
    course: float | None = None

    @classmethod
    def from_orm(cls, position: Position) -> "PositionResponse":
        return cls(
            device_id=position.device_id,
            timestamp=position.timestamp.isoformat(),
            latitude=position.latitude,
            longitude=position.longitude,
            speed=position.speed,
            course=position.course,
        )


class UserCreate(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


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
