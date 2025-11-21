"""Cliente HTTP asíncrono liviano para sondas sintéticas.

Este módulo evita dependencias externas (como ``httpx``) que no siempre
están disponibles en entornos restringidos. Soporta dos modos:

* ``asgi://``: invoca directamente la aplicación FastAPI en memoria.
* ``http(s)://``: usa la librería estándar ``urllib``.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import time
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Callable, Mapping, MutableMapping
from urllib import error, parse, request

from gps_tracker.api import app as default_app


class _Elapsed:
    def __init__(self, seconds: float) -> None:
        self._seconds = seconds

    def total_seconds(self) -> float:
        return self._seconds


class ProbeResponse:
    def __init__(self, status_code: int, body: bytes, elapsed_seconds: float) -> None:
        self.status_code = status_code
        self._body = body
        self.elapsed = _Elapsed(elapsed_seconds)

    def json(self) -> Any:
        if not self._body:
            return None
        return json.loads(self._body.decode())

    def raise_for_status(self) -> None:
        if 400 <= self.status_code:
            raise RuntimeError(f"HTTP {self.status_code}")


@dataclass
class _AsgiConfig:
    app: Callable
    base_path: str


class AsyncProbeClient:
    """Cliente minimalista para GET/POST asíncronos."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: int = 10,
        verify: bool = True,
        app=None,
    ) -> None:
        parsed = parse.urlparse(base_url)
        self._scheme = parsed.scheme or "http"
        self._base_url = base_url.rstrip("/") if parsed.scheme else f"http://{base_url.rstrip('/')}"
        self._timeout = timeout
        self._verify = verify
        self._asgi: _AsgiConfig | None = None
        self._lifespan_cm = None
        if self._scheme == "asgi":
            base_path = parsed.path if parsed.path else ""
            if not base_path.startswith("/"):
                base_path = f"/{base_path}" if base_path else ""
            self._asgi = _AsgiConfig(app=app or default_app, base_path=base_path)
        self._ssl_context = None if verify else ssl._create_unverified_context()

    async def __aenter__(self) -> "AsyncProbeClient":
        if self._asgi:
            lifespan = self._asgi.app.router.lifespan_context(self._asgi.app)
            self._lifespan_cm = lifespan
            await lifespan.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._lifespan_cm:
            await self._lifespan_cm.__aexit__(exc_type, exc, tb)

    async def get(self, path: str, headers: Mapping[str, str] | None = None) -> ProbeResponse:
        return await self._request("GET", path, headers=headers)

    async def post(
        self,
        path: str,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> ProbeResponse:
        return await self._request("POST", path, headers=headers, json_body=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> ProbeResponse:
        headers = {k: v for k, v in (headers or {}).items()}
        body_bytes = b""
        if json_body is not None:
            body_bytes = json.dumps(json_body).encode()
            headers.setdefault("Content-Type", "application/json")

        if self._asgi:
            return await self._asgi_request(method, path, headers, body_bytes)

        return await self._http_request(method, path, headers, body_bytes)

    async def _http_request(
        self,
        method: str,
        path: str,
        headers: MutableMapping[str, str],
        body_bytes: bytes,
    ) -> ProbeResponse:
        url = parse.urljoin(f"{self._base_url}/", path.lstrip("/"))
        req = request.Request(url, headers=headers, method=method, data=body_bytes or None)

        def _call() -> ProbeResponse:
            start = time.perf_counter()
            try:
                with request.urlopen(req, context=self._ssl_context, timeout=self._timeout) as resp:
                    body = resp.read()
                    elapsed = time.perf_counter() - start
                    return ProbeResponse(resp.status, body, elapsed)
            except error.HTTPError as http_err:
                body = http_err.read()
                elapsed = time.perf_counter() - start
                return ProbeResponse(http_err.code, body, elapsed)

        return await asyncio.to_thread(_call)

    async def _asgi_request(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body_bytes: bytes,
    ) -> ProbeResponse:
        assert self._asgi  # garante modo ASGI

        full_path = f"{self._asgi.base_path.rstrip('/')}{path}" or "/"
        if not full_path.startswith("/"):
            full_path = "/" + full_path

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": method.upper(),
            "path": full_path,
            "raw_path": full_path.encode(),
            "scheme": "https",
            "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        }

        body_sent = False
        response_body = bytearray()
        status_code = 500
        start = time.perf_counter()

        async def receive() -> dict:
            nonlocal body_sent
            if body_sent:
                return {"type": "http.disconnect"}
            body_sent = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        async def send(message: dict) -> None:
            nonlocal status_code, response_body
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))

        await self._asgi.app(scope, receive, send)
        elapsed = time.perf_counter() - start
        return ProbeResponse(status_code, bytes(response_body), elapsed)
