"""Integración simplificada de pasarelas de pago con webhooks seguros."""

from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


PAYMENT_WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET", "change-me")


@dataclass
class PaymentSession:
    """Datos mínimos de una sesión de checkout."""

    provider: str
    checkout_url: str
    amount: int
    currency: str
    description: str


class PaymentProvider:
    """Interfaz para distintas pasarelas (Stripe, MercadoPago)."""

    def create_session(self, amount: int, currency: str, description: str) -> PaymentSession:  # pragma: no cover - interface
        raise NotImplementedError


class StripeProvider(PaymentProvider):
    """Implementación ligera sin dependencias del SDK oficial."""

    def __init__(self, secret_key: str, publishable_key: str | None = None) -> None:
        self.secret_key = secret_key
        self.publishable_key = publishable_key

    def create_session(self, amount: int, currency: str, description: str) -> PaymentSession:
        url = "https://checkout.stripe.com/pay/mock-session"
        return PaymentSession(provider="stripe", checkout_url=url, amount=amount, currency=currency, description=description)


class MercadoPagoProvider(PaymentProvider):
    """Proveedor para MercadoPago usando URLs de preferencia."""

    def __init__(self, access_token: str) -> None:
        self.access_token = access_token

    def create_session(self, amount: int, currency: str, description: str) -> PaymentSession:
        url = "https://www.mercadopago.com/checkout/v1/mock"
        return PaymentSession(provider="mercadopago", checkout_url=url, amount=amount, currency=currency, description=description)


class PaymentGateway:
    """Fachada para seleccionar proveedor y validar webhooks."""

    def __init__(self, provider: PaymentProvider) -> None:
        self.provider = provider

    @classmethod
    def from_env(cls, provider_name: str | None = None) -> "PaymentGateway":
        provider_name = (provider_name or os.getenv("PAYMENT_PROVIDER", "stripe")).lower()
        if provider_name == "mercadopago":
            access_token = os.getenv("MP_ACCESS_TOKEN", "test")
            provider: PaymentProvider = MercadoPagoProvider(access_token)
        else:
            provider = StripeProvider(os.getenv("STRIPE_SECRET", "test"), publishable_key=os.getenv("STRIPE_PUBLISHABLE"))
        return cls(provider)

    def create_checkout(self, amount: int, currency: str, description: str) -> PaymentSession:
        return self.provider.create_session(amount, currency, description)

    @staticmethod
    def sign_payload(payload: bytes) -> str:
        return hmac.new(PAYMENT_WEBHOOK_SECRET.encode(), payload, sha256).hexdigest()

    @staticmethod
    def verify_signature(signature: str, payload: bytes) -> bool:
        expected = PaymentGateway.sign_payload(payload)
        return hmac.compare_digest(signature, expected)

    @staticmethod
    def parse_event(payload: bytes) -> dict[str, Any]:
        try:
            return json.loads(payload.decode())
        except json.JSONDecodeError:
            return {"raw": payload.decode(errors="ignore")}

