from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from bot.enums import ProductType, ReminderKind, ReminderStatus
from bot.models import ReminderTask


async def cancel_pending_reminders(
    session: AsyncSession,
    user_id: int,
    kinds: list[ReminderKind] | None = None,
) -> None:
    query = delete(ReminderTask).where(
        ReminderTask.user_id == user_id,
        ReminderTask.status == ReminderStatus.PENDING,
    )
    if kinds:
        query = query.where(ReminderTask.kind.in_(kinds))
    await session.execute(query)
    await session.commit()


async def _schedule_many(
    session: AsyncSession,
    user_id: int,
    plan: list[tuple[ReminderKind, timedelta]],
    payload: dict | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    for kind, delay in plan:
        reminder = ReminderTask(
            user_id=user_id,
            kind=kind,
            run_at=now + delay,
            status=ReminderStatus.PENDING,
            payload=payload or {},
        )
        session.add(reminder)
    await session.commit()


DIAG_REMINDER_KINDS = [ReminderKind.DIAG_15M, ReminderKind.DIAG_2H, ReminderKind.DIAG_12H]
RESULT_REMINDER_KINDS = [
    ReminderKind.RESULT_12H,
    ReminderKind.RESULT_24H,
    ReminderKind.RESULT_72H,
    ReminderKind.RESULT_7D,
]
PAYMENT_CLUB_REMINDER_KINDS = [ReminderKind.PAYMENT_CLUB_20M, ReminderKind.PAYMENT_CLUB_3H]
PAYMENT_CONSULT_REMINDER_KINDS = [ReminderKind.PAYMENT_CONSULT_20M, ReminderKind.PAYMENT_CONSULT_3H]


async def schedule_diagnostic_pause(session: AsyncSession, user_id: int, expected_step: int) -> None:
    await cancel_pending_reminders(session, user_id, DIAG_REMINDER_KINDS)
    await _schedule_many(
        session,
        user_id,
        plan=[
            (ReminderKind.DIAG_15M, timedelta(minutes=15)),
            (ReminderKind.DIAG_2H, timedelta(hours=2)),
            (ReminderKind.DIAG_12H, timedelta(hours=12)),
        ],
        payload={"expected_step": expected_step},
    )


async def schedule_result_pause(session: AsyncSession, user_id: int) -> None:
    await cancel_pending_reminders(session, user_id, RESULT_REMINDER_KINDS)
    await _schedule_many(
        session,
        user_id,
        plan=[
            (ReminderKind.RESULT_12H, timedelta(hours=12)),
            (ReminderKind.RESULT_24H, timedelta(hours=24)),
            (ReminderKind.RESULT_72H, timedelta(hours=72)),
            (ReminderKind.RESULT_7D, timedelta(days=7)),
        ],
    )


async def schedule_payment_pause(session: AsyncSession, user_id: int, product: ProductType) -> None:
    if product == ProductType.CLUB:
        await cancel_pending_reminders(session, user_id, PAYMENT_CLUB_REMINDER_KINDS)
        await _schedule_many(
            session,
            user_id,
            plan=[
                (ReminderKind.PAYMENT_CLUB_20M, timedelta(minutes=20)),
                (ReminderKind.PAYMENT_CLUB_3H, timedelta(hours=3)),
            ],
        )
        return

    await cancel_pending_reminders(session, user_id, PAYMENT_CONSULT_REMINDER_KINDS)
    await _schedule_many(
        session,
        user_id,
        plan=[
            (ReminderKind.PAYMENT_CONSULT_20M, timedelta(minutes=20)),
            (ReminderKind.PAYMENT_CONSULT_3H, timedelta(hours=3)),
        ],
    )


async def schedule_post_club_payment(session: AsyncSession, user_id: int) -> None:
    await cancel_pending_reminders(session, user_id, [ReminderKind.POST_CLUB_24H])
    await _schedule_many(
        session,
        user_id,
        plan=[(ReminderKind.POST_CLUB_24H, timedelta(hours=24))],
    )
