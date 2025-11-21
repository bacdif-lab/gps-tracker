"""Sondeos sintéticos básicos desde múltiples "regiones" lógicas.

Ejemplo:
    SYNTHETIC_DEVICE_TOKEN=token python scripts/synthetic_checks.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Sequence
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from gps_tracker.synthetic_client import AsyncProbeClient

DEFAULT_REGIONS = ("us-east-1", "eu-west-1", "sa-east-1")


@dataclass
class ProbeResult:
    region: str
    health_status: str
    ingest_status: str
    latency_ms: float


async def probe_region(client: AsyncProbeClient, region: str, device_token: str | None) -> ProbeResult:
    try:
        health_resp = await client.get("/health", headers={"X-Region": region})
        health_resp.raise_for_status()
        health_status = health_resp.json().get("status", "unknown")
        latency_ms = health_resp.elapsed.total_seconds() * 1000
    except Exception as exc:  # pragma: no cover - cualquier fallo debe registrarse
        return ProbeResult(region=region, health_status=f"error:{exc}", ingest_status="skipped", latency_ms=-1)

    ingest_status = "skipped"

    if device_token:
        payload = {"latitude": 1.0, "longitude": 1.0, "speed": 10}
        try:
            ingest = await client.post(
                "/ingest/http",
                headers={"X-Device-Token": device_token, "X-Region": region},
                json_body=payload,
            )
            ingest_status = f"{ingest.status_code}"
        except Exception as exc:  # pragma: no cover - se reporta pero no se detiene el resto
            ingest_status = f"error:{exc}"

    return ProbeResult(
        region=region,
        health_status=health_status,
        ingest_status=ingest_status,
        latency_ms=latency_ms,
    )


def resolve_base_url(env: str | None) -> str:
    explicit = os.getenv("SYNTHETIC_BASE_URL")
    if explicit:
        return explicit

    if env:
        env_override = os.getenv(f"SYNTHETIC_BASE_URL_{env.upper()}")
        if env_override:
            return env_override

    return os.getenv("SYNTHETIC_BASE_URL_LOCAL", "asgi://local")


async def main(regions: Sequence[str], base_url: str) -> None:
    device_token = os.getenv("SYNTHETIC_DEVICE_TOKEN")
    timeout = int(os.getenv("SYNTHETIC_TIMEOUT", "10"))
    verify_tls = os.getenv("SYNTHETIC_VERIFY_TLS", "false").lower() == "true"

    async with AsyncProbeClient(base_url, timeout=timeout, verify=verify_tls) as client:
        results = await asyncio.gather(*(probe_region(client, region, device_token) for region in regions))

    for result in results:
        print(
            f"[{result.region}] health={result.health_status} "
            f"ingest_status={result.ingest_status} latency_ms={result.latency_ms:.1f}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejecución de sondas sintéticas")
    parser.add_argument("--env", dest="env", help="Nombre de entorno (staging|prod|local)")
    parser.add_argument(
        "--regions",
        dest="regions",
        help="Lista de regiones separadas por coma (p.ej. us-east-1,eu-west-1)",
    )
    args = parser.parse_args()

    regions_env = args.regions or os.getenv("SYNTHETIC_REGIONS")
    regions = regions_env.split(",") if regions_env else DEFAULT_REGIONS

    base_url = resolve_base_url(args.env)
    asyncio.run(main(regions, base_url))
