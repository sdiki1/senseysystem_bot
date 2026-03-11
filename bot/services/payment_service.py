from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.enums import PaymentStatus, ProductType, SubscriptionStatus, UserStage
from bot.models import Payment, Subscription, User


def _try_parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None

    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _safe_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


async def create_pending_payment(
    session: AsyncSession,
    user_id: int,
    product: ProductType,
    amount_rub: int,
    checkout_url: str,
    payload: dict | None = None,
) -> Payment:
    payment = Payment(
        user_id=user_id,
        product=product,
        status=PaymentStatus.PENDING,
        amount_rub=amount_rub,
        checkout_url=checkout_url,
        payload=payload or {},
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def get_latest_pending_payment(
    session: AsyncSession,
    user_id: int,
    product: ProductType,
) -> Payment | None:
    result = await session.execute(
        select(Payment)
        .where(
            Payment.user_id == user_id,
            Payment.product == product,
            Payment.status == PaymentStatus.PENDING,
        )
        .order_by(desc(Payment.created_at))
    )
    return result.scalars().first()


async def mark_payment_success(
    session: AsyncSession,
    user: User,
    product: ProductType,
    event_type: str,
    payload: dict,
    provider_payment_id: str | None,
    *,
    is_recurrent: bool = False,
) -> Payment:
    payment = await get_latest_pending_payment(session, user.id, product)
    now = datetime.now(timezone.utc)
    amount = _safe_int(payload.get("amount") or payload.get("price"), 3000 if product == ProductType.CLUB else 10000)

    if payment is None:
        payment = Payment(
            user_id=user.id,
            product=product,
            status=PaymentStatus.PAID,
            amount_rub=amount,
            checkout_url=None,
            provider_payment_id=provider_payment_id,
            provider_event_type=event_type,
            payload=payload,
            paid_at=now,
            is_recurrent=is_recurrent,
        )
        session.add(payment)
    else:
        payment.status = PaymentStatus.PAID
        payment.provider_payment_id = provider_payment_id
        payment.provider_event_type = event_type
        payment.payload = payload
        payment.paid_at = now
        payment.is_recurrent = is_recurrent

    if product == ProductType.CLUB:
        await _activate_club_subscription(session, user, payload)
        user.stage = UserStage.CLUB_ACTIVE
    else:
        user.stage = UserStage.CONSULT_BOOKED

    await session.commit()
    await session.refresh(payment)
    return payment


async def mark_payment_failed(
    session: AsyncSession,
    user_id: int,
    product: ProductType,
    payload: dict,
    provider_payment_id: str | None,
) -> None:
    payment = await get_latest_pending_payment(session, user_id, product)
    if payment is None:
        payment = Payment(
            user_id=user_id,
            product=product,
            status=PaymentStatus.FAILED,
            amount_rub=_safe_int(payload.get("amount") or payload.get("price"), 0),
            provider_payment_id=provider_payment_id,
            payload=payload,
        )
        session.add(payment)
    else:
        payment.status = PaymentStatus.FAILED
        payment.provider_payment_id = provider_payment_id
        payment.payload = payload
    await session.commit()


async def _activate_club_subscription(session: AsyncSession, user: User, payload: dict) -> Subscription:
    provider_subscription_id = (
        payload.get("subscription_id")
        or payload.get("id")
        or payload.get("subscription", {}).get("id")
    )

    result = await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.product == ProductType.CLUB,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        .order_by(desc(Subscription.created_at))
    )
    subscription = result.scalars().first()

    next_billing_at = (
        _try_parse_dt(payload.get("next_billing_at"))
        or _try_parse_dt(payload.get("renewal_at"))
        or _try_parse_dt(payload.get("expires_at"))
        or datetime.now(timezone.utc) + timedelta(days=30)
    )

    if subscription is None:
        subscription = Subscription(
            user_id=user.id,
            product=ProductType.CLUB,
            status=SubscriptionStatus.ACTIVE,
            provider_subscription_id=str(provider_subscription_id) if provider_subscription_id else None,
            next_billing_at=next_billing_at,
        )
        session.add(subscription)
    else:
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.provider_subscription_id = (
            str(provider_subscription_id) if provider_subscription_id else subscription.provider_subscription_id
        )
        subscription.next_billing_at = next_billing_at

    return subscription


async def cancel_subscription(session: AsyncSession, user: User, payload: dict) -> None:
    result = await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.product == ProductType.CLUB,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        .order_by(desc(Subscription.created_at))
    )
    subscription = result.scalars().first()
    if subscription is None:
        return

    subscription.status = SubscriptionStatus.CANCELLED
    subscription.canceled_at = datetime.now(timezone.utc)
    subscription.next_billing_at = _try_parse_dt(payload.get("expires_at")) or subscription.next_billing_at
    await session.commit()
