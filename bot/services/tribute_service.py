from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any

from bot.config import Settings
from bot.enums import ProductType, UserStage
from bot.models import User


SUBSCRIPTION_EVENTS = {"new_subscription", "renewed_subscription", "cancelled_subscription"}


@dataclass(slots=True)
class ParsedTributeEvent:
    event_type: str
    payload: dict[str, Any]
    telegram_id: int | None
    provider_payment_id: str | None
    product: ProductType
    is_recurrent: bool


def verify_tribute_signature(body: bytes, signature_header: str | None, settings: Settings) -> bool:
    if not settings.tribute_verify_signature:
        return True

    secret = settings.tribute_webhook_secret or settings.tribute_api_key
    if not secret:
        return False
    if not signature_header:
        return False

    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def parse_tribute_event(raw: dict[str, Any], settings: Settings, user: User | None = None) -> ParsedTributeEvent:
    event_type = str(raw.get("event") or raw.get("type") or raw.get("name") or "").strip()
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw

    telegram_id = _extract_telegram_id(payload)
    provider_payment_id = str(
        payload.get("payment_id")
        or payload.get("transaction_id")
        or payload.get("id")
        or payload.get("uuid")
        or payload.get("chargeUuid")
        or payload.get("charge_uuid")
        or payload.get("subscription_id")
        or ""
    ).strip() or None

    product = _resolve_product(event_type, payload, settings, user)
    is_recurrent = event_type == "renewed_subscription" or bool(payload.get("is_recurrent"))

    return ParsedTributeEvent(
        event_type=event_type,
        payload=payload,
        telegram_id=telegram_id,
        provider_payment_id=provider_payment_id,
        product=product,
        is_recurrent=is_recurrent,
    )


def _extract_telegram_id(payload: dict[str, Any]) -> int | None:
    possible = [
        payload.get("telegram_id"),
        payload.get("telegramId"),
        payload.get("telegramID"),
        payload.get("user_id"),
        payload.get("customer_id"),
        payload.get("customerId"),
        payload.get("subscriber", {}).get("telegram_id") if isinstance(payload.get("subscriber"), dict) else None,
        payload.get("user", {}).get("telegram_id") if isinstance(payload.get("user"), dict) else None,
        payload.get("customer", {}).get("telegram_id") if isinstance(payload.get("customer"), dict) else None,
        payload.get("customer", {}).get("telegramId") if isinstance(payload.get("customer"), dict) else None,
    ]
    for value in possible:
        if value is None:
            continue
        converted = _coerce_int(value)
        if converted is not None:
            return converted
    return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        pass

    if isinstance(value, str):
        match = re.search(r"\d{5,}", value)
        if match:
            try:
                return int(match.group(0))
            except ValueError:
                return None
    return None


def _resolve_product(event_type: str, payload: dict[str, Any], settings: Settings, user: User | None) -> ProductType:
    product_id = str(
        payload.get("product_id")
        or payload.get("plan_id")
        or payload.get("subscription", {}).get("product_id")
        or ""
    )

    if settings.tribute_consult_product_id and product_id == settings.tribute_consult_product_id:
        return ProductType.CONSULT
    if settings.tribute_club_product_id and product_id == settings.tribute_club_product_id:
        return ProductType.CLUB

    if event_type in SUBSCRIPTION_EVENTS:
        return ProductType.CLUB

    if user is not None and user.stage == UserStage.PAYMENT_CONSULT:
        return ProductType.CONSULT

    return ProductType.CLUB
