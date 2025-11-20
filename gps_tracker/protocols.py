"""Adaptadores de protocolos GPS populares con utilidades de simulación."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class DecodedPosition:
    """Representación normalizada de un mensaje GPS."""

    device_id: str
    latitude: float
    longitude: float
    speed: float | None = None
    course: float | None = None
    event_type: str | None = None
    timestamp: datetime | None = None


class ProtocolAdapter:
    """Interfaz base para adaptadores de protocolos."""

    name = "base"

    def decode_message(self, payload: bytes) -> DecodedPosition:  # pragma: no cover - interface
        raise NotImplementedError

    def simulate_payload(self, position: DecodedPosition) -> bytes:  # pragma: no cover - interface
        raise NotImplementedError


class TeltonikaAdapter(ProtocolAdapter):
    """Decodificador mínimo estilo Teltonika (AVL, simplificado)."""

    name = "teltonika"

    def decode_message(self, payload: bytes) -> DecodedPosition:
        try:
            decoded = json.loads(payload.decode())
        except Exception:
            decoded = {"id": "unknown", "lat": 0, "lon": 0}
        return DecodedPosition(
            device_id=str(decoded.get("id")),
            latitude=float(decoded.get("lat")),
            longitude=float(decoded.get("lon")),
            speed=float(decoded.get("speed")) if decoded.get("speed") is not None else None,
            course=float(decoded.get("course")) if decoded.get("course") is not None else None,
            event_type=decoded.get("event"),
            timestamp=datetime.fromisoformat(decoded["ts"]) if decoded.get("ts") else None,
        )

    def simulate_payload(self, position: DecodedPosition) -> bytes:
        body = {
            "id": position.device_id,
            "lat": position.latitude,
            "lon": position.longitude,
            "speed": position.speed,
            "course": position.course,
            "event": position.event_type,
            "ts": (position.timestamp or datetime.utcnow()).isoformat(),
        }
        return json.dumps(body).encode()


class QueclinkAdapter(ProtocolAdapter):
    """Parser básico compatible con tramas ASCII de Queclink."""

    name = "queclink"

    def decode_message(self, payload: bytes) -> DecodedPosition:
        text = payload.decode(errors="ignore")
        parts = text.split(",")
        device_id = parts[1] if len(parts) > 1 else "unknown"
        latitude = float(parts[7]) if len(parts) > 7 else 0.0
        longitude = float(parts[8]) if len(parts) > 8 else 0.0
        speed = float(parts[11]) if len(parts) > 11 else None
        course = float(parts[12]) if len(parts) > 12 else None
        return DecodedPosition(
            device_id=device_id,
            latitude=latitude,
            longitude=longitude,
            speed=speed,
            course=course,
            event_type="queclink",
        )

    def simulate_payload(self, position: DecodedPosition) -> bytes:
        # Formato: +RESP:GTFRI,<device>,,,,,,<lat>,<lon>,,,,,<speed>,<course>
        payload = (
            f"+RESP:GTFRI,{position.device_id},,,,,,{position.latitude},"
            f"{position.longitude},,,,,{position.speed},{position.course}"
        )
        return payload.encode()


class ConcoxAdapter(ProtocolAdapter):
    """Soporte mínimo para tramas Concox en Base64."""

    name = "concox"

    def decode_message(self, payload: bytes) -> DecodedPosition:
        try:
            decoded = base64.b64decode(payload)
        except Exception:
            decoded = payload
        if len(decoded) < 12:
            return DecodedPosition(device_id="unknown", latitude=0.0, longitude=0.0)
        latitude = int.from_bytes(decoded[4:8], "big", signed=True) / 1000000
        longitude = int.from_bytes(decoded[8:12], "big", signed=True) / 1000000
        device_id = decoded[:4].hex()
        return DecodedPosition(device_id=device_id, latitude=latitude, longitude=longitude, event_type="concox")

    def simulate_payload(self, position: DecodedPosition) -> bytes:
        device_bytes = bytes.fromhex(position.device_id.zfill(8))[:4]
        lat_bytes = int(position.latitude * 1000000).to_bytes(4, "big", signed=True)
        lon_bytes = int(position.longitude * 1000000).to_bytes(4, "big", signed=True)
        return base64.b64encode(device_bytes + lat_bytes + lon_bytes)


def get_adapter(protocol: str) -> ProtocolAdapter:
    name = protocol.lower()
    adapters: dict[str, ProtocolAdapter] = {
        "teltonika": TeltonikaAdapter(),
        "queclink": QueclinkAdapter(),
        "concox": ConcoxAdapter(),
    }
    if name not in adapters:
        raise ValueError(f"Protocolo no soportado: {protocol}")
    return adapters[name]


def decode_with(protocol: str, payload: bytes) -> DecodedPosition:
    adapter = get_adapter(protocol)
    return adapter.decode_message(payload)

