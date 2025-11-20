"""Servicios de notificación encolados (correo, SMS y push).

El procesamiento se desacopla mediante Redis o una cola interna en memoria
para evitar bloquear peticiones HTTP. Cada proveedor expone un método
``send`` que puede sustituirse por mocks en pruebas o integraciones reales
con SES/Twilio/FCM/APNs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

import redis


logger = logging.getLogger(__name__)


@dataclass
class NotificationMessage:
    """Mensaje genérico a enviar por un canal específico."""

    channel: str
    recipient: str
    subject: str | None = None
    body: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "channel": self.channel,
            "recipient": self.recipient,
            "subject": self.subject,
            "body": self.body,
            "metadata": self.metadata,
        })

    @classmethod
    def from_json(cls, raw: str) -> "NotificationMessage":
        data = json.loads(raw)
        return cls(
            channel=data["channel"],
            recipient=data["recipient"],
            subject=data.get("subject"),
            body=data.get("body"),
            metadata=data.get("metadata", {}),
        )


class NotificationQueue:
    """Cola basada en Redis con fallback en memoria."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self._client = redis.from_url(self.redis_url) if self.redis_url else None
        self._memory_queue: asyncio.Queue[str] = asyncio.Queue()
        self.key = "notifications:pending"

    async def enqueue(self, message: NotificationMessage) -> None:
        payload = message.to_json()
        if self._client:
            self._client.rpush(self.key, payload)
        else:
            await self._memory_queue.put(payload)

    async def dequeue(self, timeout: int = 1) -> NotificationMessage | None:
        if self._client:
            raw = self._client.blpop(self.key, timeout=timeout)
            if raw:
                return NotificationMessage.from_json(raw[1].decode())
            return None
        try:
            raw = await asyncio.wait_for(self._memory_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        return NotificationMessage.from_json(raw)


class EmailProvider:
    """Envío por correo (SES u otro SMTP compatible)."""

    def __init__(self, sender: str | None = None):
        self.sender = sender or os.getenv("EMAIL_SENDER", "noreply@gps.local")

    async def send(self, message: NotificationMessage) -> dict[str, Any]:
        logger.info("Enviando correo a %s", message.recipient)
        return {"provider": "ses", "recipient": message.recipient, "subject": message.subject}


class SmsProvider:
    """Envío de SMS mediante Twilio."""

    def __init__(self, from_number: str | None = None):
        self.from_number = from_number or os.getenv("TWILIO_FROM", "+10000000000")

    async def send(self, message: NotificationMessage) -> dict[str, Any]:
        logger.info("Enviando SMS a %s", message.recipient)
        return {"provider": "twilio", "recipient": message.recipient, "from": self.from_number}


class PushProvider:
    """Notificaciones push hacia FCM/APNs."""

    def __init__(self, fcm_key: str | None = None, apns_key: str | None = None) -> None:
        self.fcm_key = fcm_key or os.getenv("FCM_KEY")
        self.apns_key = apns_key or os.getenv("APNS_KEY")

    async def send(self, message: NotificationMessage) -> dict[str, Any]:
        target = message.metadata.get("device_token") or message.recipient
        platform = message.metadata.get("platform", "fcm" if self.fcm_key else "apns")
        logger.info("Enviando push %s a %s", platform, target)
        return {"provider": platform, "target": target, "title": message.subject}


class NotificationDispatcher:
    """Despacha mensajes al proveedor adecuado."""

    def __init__(self, email_provider: EmailProvider, sms_provider: SmsProvider, push_provider: PushProvider) -> None:
        self.email_provider = email_provider
        self.sms_provider = sms_provider
        self.push_provider = push_provider
        self._routes: dict[str, Callable[[NotificationMessage], Any]] = {
            "email": self.email_provider.send,
            "sms": self.sms_provider.send,
            "push": self.push_provider.send,
        }

    async def dispatch(self, message: NotificationMessage) -> dict[str, Any]:
        handler = self._routes.get(message.channel)
        if not handler:
            raise ValueError(f"Canal no soportado: {message.channel}")
        return await handler(message)


class NotificationService:
    """Fachada que junta cola y dispatcher con un worker asíncrono."""

    def __init__(self, queue: NotificationQueue, dispatcher: NotificationDispatcher) -> None:
        self.queue = queue
        self.dispatcher = dispatcher
        self._worker_task: asyncio.Task | None = None

    @classmethod
    def from_env(cls) -> "NotificationService":
        queue = NotificationQueue()
        dispatcher = NotificationDispatcher(EmailProvider(), SmsProvider(), PushProvider())
        return cls(queue, dispatcher)

    async def start_worker(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def _worker_loop(self) -> None:
        while True:
            message = await self.queue.dequeue(timeout=1)
            if not message:
                await asyncio.sleep(0.1)
                continue
            try:
                await self.dispatcher.dispatch(message)
            except Exception as exc:  # pragma: no cover - logging de fallas externas
                logger.error("No se pudo despachar notificación: %s", exc)

    async def enqueue(self, message: NotificationMessage) -> None:
        await self.queue.enqueue(message)

