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

from .database import (
    Position,
    get_all_positions,
    get_engine,
    get_latest_position,
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
asyn...