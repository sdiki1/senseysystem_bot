from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.enums import BroadcastTarget, SubscriptionStatus, UserStage
from bot.models import Subscription, User


async def get_or_create_user(session: AsyncSession, tg_user: TgUser, admin_ids: list[int]) -> User:
    result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            is_admin=tg_user.id in admin_ids,
            stage=UserStage.NEW,
        )
        session.add(user)
    else:
        user.username = tg_user.username
        user.first_name = tg_user.first_name
        user.last_name = tg_user.last_name
        if tg_user.id in admin_ids:
            user.is_admin = True

    user.last_activity_at = datetime.now(tz=timezone.utc)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def update_user_stage(
    session: AsyncSession,
    user: User,
    stage: UserStage,
    *,
    diagnostic_step: int | None = None,
    answers: dict | None = None,
) -> None:
    user.stage = stage
    user.last_activity_at = datetime.now(tz=timezone.utc)
    if diagnostic_step is not None:
        user.diagnostic_step = diagnostic_step
    if answers is not None:
        user.diagnostic_answers = answers
    await session.commit()


async def list_users_for_broadcast(session: AsyncSession, target: BroadcastTarget) -> list[User]:
    if target == BroadcastTarget.ALL:
        result = await session.execute(select(User))
        return list(result.scalars().all())

    if target == BroadcastTarget.CONSULT:
        result = await session.execute(select(User).where(User.stage == UserStage.CONSULT_BOOKED))
        return list(result.scalars().all())

    # CLUB segment: active stage OR active subscription.
    result = await session.execute(
        select(User)
        .join(Subscription, Subscription.user_id == User.id, isouter=True)
        .where((User.stage == UserStage.CLUB_ACTIVE) | (Subscription.status == SubscriptionStatus.ACTIVE))
        .distinct()
    )
    return list(result.scalars().all())
