from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.enums import PaymentStatus, ProductType, SubscriptionStatus, UserStage
from bot.models import Payment, Subscription, User


async def collect_stats(session: AsyncSession) -> dict:
    users_total = await session.scalar(select(func.count()).select_from(User))
    started_diag = await session.scalar(select(func.count()).select_from(User).where(User.diagnostic_step > 0))
    finished_diag = await session.scalar(select(func.count()).select_from(User).where(User.stage != UserStage.NEW))

    active_club = await session.scalar(
        select(func.count()).select_from(Subscription).where(
            Subscription.product == ProductType.CLUB,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
    )

    consult_booked = await session.scalar(
        select(func.count()).select_from(User).where(User.stage == UserStage.CONSULT_BOOKED)
    )

    payment_row = await session.execute(
        select(
            func.count(case((Payment.status == PaymentStatus.PAID, 1))).label("paid_count"),
            func.coalesce(func.sum(case((Payment.status == PaymentStatus.PAID, Payment.amount_rub), else_=0)), 0).label(
                "revenue_rub"
            ),
            func.count(case((Payment.product == ProductType.CLUB, 1))).label("club_payments"),
            func.count(case((Payment.product == ProductType.CONSULT, 1))).label("consult_payments"),
        )
    )
    payment_stats = payment_row.mappings().one()

    return {
        "users_total": int(users_total or 0),
        "started_diag": int(started_diag or 0),
        "finished_diag": int(finished_diag or 0),
        "active_club": int(active_club or 0),
        "consult_booked": int(consult_booked or 0),
        "paid_count": int(payment_stats["paid_count"] or 0),
        "revenue_rub": int(payment_stats["revenue_rub"] or 0),
        "club_payments": int(payment_stats["club_payments"] or 0),
        "consult_payments": int(payment_stats["consult_payments"] or 0),
    }
