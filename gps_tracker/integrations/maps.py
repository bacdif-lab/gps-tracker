"""Clientes HTTP para mapas (tiles, geocodificación inversa y rutas).

El módulo soporta Mapbox y OSM mediante REST, con un modo ``mock`` que
permite probar sin conectividad externa. Las claves y URLs se leen de
variables de entorno para facilitar despliegues en distintas nubes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - fallback para entornos sin dependencias opcionales
    import httpx
except ImportError:  # pragma: no cover - ejecución offline
    httpx = None


MAPBOX_STYLE = os.getenv("MAPBOX_STYLE", "streets-v12")


@dataclass
class RouteLeg:
    """Segmento de una ruta calculada."""

    distance_km: float
    duration_minutes: float
    geometry: list[tuple[float, float]]


@dataclass
class ReverseGeocodeResult:
    """Resultado de una geocodificación inversa."""

    label: str
    latitude: float
    longitude: float
    provider: str


class MapProvider:
    """Interfaz de proveedores de mapas."""

    name = "base"

    def tile_url(self, z: int, x: int, y: int) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    async def reverse_geocode(self, latitude: float, longitude: float) -> ReverseGeocodeResult:
        raise NotImplementedError

    async def route(
        self, origin: tuple[float, float], destination: tuple[float, float], waypoints: list[tuple[float, float]] | None = None
    ) -> list[RouteLeg]:
        raise NotImplementedError


class MapboxProvider(MapProvider):
    """Cliente de Mapbox usando REST."""

    name = "mapbox"

    def __init__(self, token: str) -> None:
        self.token = token

    def tile_url(self, z: int, x: int, y: int) -> str:
        return (
            f"https://api.mapbox.com/styles/v1/mapbox/{MAPBOX_STYLE}/tiles/256/{z}/{x}/{y}"
            f"?access_token={self.token}"
        )

    async def reverse_geocode(self, latitude: float, longitude: float) -> ReverseGeocodeResult:
        if httpx is None:
            raise RuntimeError("httpx no disponible; use proveedor mock")
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{longitude},{latitude}.json"
        params = {"language": "es", "access_token": self.token}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        feature = data.get("features", [{}])[0]
        place = feature.get("place_name", "Desconocido")
        coords = feature.get("center", [longitude, latitude])
        return ReverseGeocodeResult(
            label=place,
            longitude=coords[0],
            latitude=coords[1],
            provider=self.name,
        )

    async def route(
        self, origin: tuple[float, float], destination: tuple[float, float], waypoints: list[tuple[float, float]] | None = None
    ) -> list[RouteLeg]:
        if httpx is None:
            raise RuntimeError("httpx no disponible; use proveedor mock")
        coords = [origin, *(waypoints or []), destination]
        coord_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
        url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coord_str}"
        params = {"geometries": "geojson", "overview": "full", "language": "es", "access_token": self.token}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        legs = []
        for leg in payload.get("routes", [{}])[0].get("legs", []):
            geometry = [(coord[1], coord[0]) for coord in leg.get("geometry", {}).get("coordinates", [])]
            legs.append(
                RouteLeg(
                    distance_km=leg.get("distance", 0.0) / 1000,
                    duration_minutes=leg.get("duration", 0.0) / 60,
                    geometry=geometry,
                )
            )
        return legs


class OsmProvider(MapProvider):
    """Implementación OSM/Nominatim/OSRM sin claves."""

    name = "osm"

    def tile_url(self, z: int, x: int, y: int) -> str:
        return f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"

    async def reverse_geocode(self, latitude: float, longitude: float) -> ReverseGeocodeResult:
        if httpx is None:
            raise RuntimeError("httpx no disponible; use proveedor mock")
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"lat": latitude, "lon": longitude, "format": "json", "addressdetails": 0, "zoom": 16}
        headers = {"User-Agent": "gps-tracker/0.1"}
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        return ReverseGeocodeResult(
            label=data.get("display_name", "Desconocido"),
            longitude=float(data.get("lon", longitude)),
            latitude=float(data.get("lat", latitude)),
            provider=self.name,
        )

    async def route(
        self, origin: tuple[float, float], destination: tuple[float, float], waypoints: list[tuple[float, float]] | None = None
    ) -> list[RouteLeg]:
        if httpx is None:
            raise RuntimeError("httpx no disponible; use proveedor mock")
        coords = [origin, *(waypoints or []), destination]
        coord_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
        url = f"https://router.project-osrm.org/route/v1/driving/{coord_str}"
        params = {"overview": "full", "geometries": "geojson", "alternatives": "false"}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        legs: list[RouteLeg] = []
        for leg in payload.get("routes", [{}])[0].get("legs", []):
            geometry = [(coord[1], coord[0]) for coord in leg.get("geometry", {}).get("coordinates", [])]
            legs.append(
                RouteLeg(
                    distance_km=leg.get("distance", 0.0) / 1000,
                    duration_minutes=leg.get("duration", 0.0) / 60,
                    geometry=geometry,
                )
            )
        return legs


class MockMapProvider(MapProvider):
    """Proveedor ficticio para entornos sin salida a internet."""

    name = "mock"

    def tile_url(self, z: int, x: int, y: int) -> str:
        return f"https://tiles.invalid/{z}/{x}/{y}.png"

    async def reverse_geocode(self, latitude: float, longitude: float) -> ReverseGeocodeResult:
        label = f"Mocked address ({latitude:.4f},{longitude:.4f})"
        return ReverseGeocodeResult(label=label, latitude=latitude, longitude=longitude, provider=self.name)

    async def route(
        self, origin: tuple[float, float], destination: tuple[float, float], waypoints: list[tuple[float, float]] | None = None
    ) -> list[RouteLeg]:
        waypoints = waypoints or []
        geometry = [origin, *waypoints, destination]
        return [RouteLeg(distance_km=12.0, duration_minutes=18.0, geometry=geometry)]


class MapService:
    """Fachada que selecciona proveedor y maneja fallback."""

    def __init__(self, provider: MapProvider) -> None:
        self.provider = provider

    @classmethod
    def from_env(cls) -> "MapService":
        provider_name = os.getenv("MAP_PROVIDER", "osm").lower()
        token = os.getenv("MAPBOX_TOKEN")
        if httpx is None:
            provider = MockMapProvider()
        elif provider_name == "mapbox" and token:
            provider: MapProvider = MapboxProvider(token)
        elif provider_name == "mock":
            provider = MockMapProvider()
        else:
            provider = OsmProvider()
        return cls(provider)

    def tile_url(self, z: int, x: int, y: int) -> str:
        return self.provider.tile_url(z, x, y)

    async def reverse_geocode(self, latitude: float, longitude: float) -> ReverseGeocodeResult:
        try:
            return await self.provider.reverse_geocode(latitude, longitude)
        except Exception:
            return ReverseGeocodeResult(
                label=f"{latitude:.5f},{longitude:.5f}",
                latitude=latitude,
                longitude=longitude,
                provider="fallback",
            )

    async def route(
        self, origin: tuple[float, float], destination: tuple[float, float], waypoints: list[tuple[float, float]] | None = None
    ) -> list[RouteLeg]:
        try:
            return await self.provider.route(origin, destination, waypoints)
        except Exception:
            geometry = [origin, *(waypoints or []), destination]
            return [RouteLeg(distance_km=0.0, duration_minutes=0.0, geometry=geometry)]


def parse_coordinate_pair(value: str) -> tuple[float, float]:
    """Convierte ``lat,lon`` en tupla validada."""

    lat_str, lon_str = value.split(",")
    return float(lat_str), float(lon_str)


def as_geojson(points: list[tuple[float, float]]) -> dict[str, Any]:
    """Devuelve un GeoJSON LineString simple para consumo del frontend."""

    coordinates = [[lon, lat] for lat, lon in points]
    return {"type": "LineString", "coordinates": coordinates}

