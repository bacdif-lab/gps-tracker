"""Sondeos sintéticos básicos desde múltiples "regiones" lógicas.

Ejemplo:
    SYNTHETIC_DEVICE_TOKEN=token python scripts/synthetic_checks.py
"""

import asyncio
import os
from dataclasses import dataclass
from typing import Sequence

import httpx

DEFAULT_REGIONS = ("us-east-1", "eu-west-1", "sa-east-1")


@dataclass
class ProbeResult:
    region: str
    health_status: str
    ingest_status: str
    latency_ms: float


async def probe_region(client: httpx.AsyncClient, base_url: str, region: str, device_token: str | None) -> ProbeResult:
    health_resp = await client.get(f"{base_url}/health", headers={"X-Region": region})
    health_resp.raise_for_status()
    ingest_status = "skipped"

    if device_token:
        payload = {"latitude": 1.0, "longitude": 1.0, "speed": 10}
        ingest = await client.post(
            f"{base_url}/ingest/http",
            headers={"X-Device-Token": device_token, "X-Region": region},
            json=payload,
        )
        ingest_status = f"{ingest.status_code}"

    return ProbeResult(
        region=region,
        health_status=health_resp.json().get("status", "unknown"),
        ingest_status=ingest_status,
        latency_ms=health_resp.elapsed.total_seconds() * 1000,
    )


async def main(regions: Sequence[str]) -> None:
    base_url = os.getenv("SYNTHETIC_BASE_URL", "https://localhost:8443/api")
    device_token = os.getenv("SYNTHETIC_DEVICE_TOKEN")
    timeout = int(os.getenv("SYNTHETIC_TIMEOUT", "10"))

    async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
        results = await asyncio.gather(*(probe_region(client, base_url, region, device_token) for region in regions))

    for result in results:
        print(
            f"[{result.region}] health={result.health_status} "
            f"ingest_status={result.ingest_status} latency_ms={result.latency_ms:.1f}"
        )


if __name__ == "__main__":
    regions_env = os.getenv("SYNTHETIC_REGIONS")
    regions = regions_env.split(",") if regions_env else DEFAULT_REGIONS
    asyncio.run(main(regions))
