from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.enums import BroadcastContentType, BroadcastTarget, PaymentStatus
from bot.keyboards import (
    admin_broadcast_target_keyboard,
    admin_broadcast_type_keyboard,
    admin_main_keyboard,
)
from bot.models import Broadcast, Payment, User
from bot.services.stats_service import collect_stats
from bot.services.user_service import get_or_create_user, list_users_for_broadcast
from bot.states import AdminBroadcastState

router = Router(name="admin")


def _is_admin(message_from_user_id: int, settings: Settings) -> bool:
    return message_from_user_id in settings.admin_ids


@router.message(Command("admin"))
async def admin_panel(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id, settings):
        return

    async with session_factory() as session:
        await get_or_create_user(session, message.from_user, settings.admin_ids)

    await message.answer("Админ-панель", reply_markup=admin_main_keyboard())


@router.message(Command("stats"))
async def admin_stats_cmd(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user or not _is_admin(message.from_user.id, settings):
        return

    async with session_factory() as session:
        stats = await collect_stats(session)

    await message.answer(_render_stats(stats))


@router.callback_query(F.data == "admin:stats")
async def admin_stats_callback(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id, settings):
        await callback.answer()
        return

    async with session_factory() as session:
        stats = await collect_stats(session)

    await callback.message.answer(_render_stats(stats))
    await callback.answer()


@router.callback_query(F.data == "admin:users")
async def admin_users_callback(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not callback.from_user or not callback.message or not _is_admin(callback.from_user.id, settings):
        await callback.answer()
        return

    async with session_factory() as session:
        total = await session.scalar(select(func.count()).select_from(User))
        result = await session.execute(select(User).order_by(desc(User.created_at)).limit(15))
        users = list(result.scalars().all())

    lines = [f"Пользователей: {int(total or 0)}", "", "Последние 15:"]
    for user in users:
        lines.append(
            f"{user.telegram_id} | @{user.username or '-'} | {user.stage.value} | шаг {user.diagnostic_step}"
        )
    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data == "admin:payments")
async def admin_payments_callback(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not callback.from_user or not callback.message or not _is_admin(callback.from_user.id, settings):
        await callback.answer()
        return

    async with session_factory() as session:
        result = await session.execute(
            select(Payment)
            .where(Payment.status == PaymentStatus.PAID)
            .order_by(desc(Payment.paid_at), desc(Payment.created_at))
            .limit(15)
        )
        payments = list(result.scalars().all())

    if not payments:
        await callback.message.answer("Оплаченных платежей пока нет.")
        await callback.answer()
        return

    lines = ["Последние оплаты:"]
    for payment in payments:
        paid_at = payment.paid_at.isoformat() if payment.paid_at else "-"
        recur = "recur" if payment.is_recurrent else "first"
        lines.append(
            f"{payment.product.value} | {payment.amount_rub} RUB | user_id={payment.user_id} | {recur} | {paid_at}"
        )

    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not callback.from_user or not callback.message or not _is_admin(callback.from_user.id, settings):
        await callback.answer()
        return

    await state.set_state(AdminBroadcastState.waiting_target)
    await callback.message.answer("Выбери сегмент рассылки:", reply_markup=admin_broadcast_target_keyboard())
    await callback.answer()


@router.callback_query(AdminBroadcastState.waiting_target, F.data.startswith("admin:broadcast_target:"))
async def admin_broadcast_choose_target(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not callback.from_user or not callback.message or not _is_admin(callback.from_user.id, settings):
        await callback.answer()
        return

    target = callback.data.split(":")[-1]
    await state.update_data(target=target)
    await state.set_state(AdminBroadcastState.waiting_content_type)
    await callback.message.answer("Выбери формат контента:", reply_markup=admin_broadcast_type_keyboard())
    await callback.answer()


@router.callback_query(AdminBroadcastState.waiting_content_type, F.data.startswith("admin:broadcast_type:"))
async def admin_broadcast_choose_type(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not callback.from_user or not callback.message or not _is_admin(callback.from_user.id, settings):
        await callback.answer()
        return

    content_type = callback.data.split(":")[-1]
    await state.update_data(content_type=content_type)
    await state.set_state(AdminBroadcastState.waiting_content)

    if content_type == BroadcastContentType.TEXT.value:
        prompt = "Пришли текст рассылки одним сообщением."
    elif content_type == BroadcastContentType.PHOTO.value:
        prompt = "Пришли фото (caption опционально)."
    else:
        prompt = "Пришли видео (caption опционально)."

    await callback.message.answer(prompt)
    await callback.answer()


@router.message(AdminBroadcastState.waiting_content)
async def admin_broadcast_send(
    message: Message,
    state: FSMContext,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user or not _is_admin(message.from_user.id, settings):
        return

    data = await state.get_data()
    target_raw = data.get("target")
    content_type_raw = data.get("content_type")

    if target_raw not in {target.value for target in BroadcastTarget}:
        await message.answer("Некорректная цель рассылки. Запусти /admin заново.")
        await state.clear()
        return

    if content_type_raw not in {item.value for item in BroadcastContentType}:
        await message.answer("Некорректный формат контента. Запусти /admin заново.")
        await state.clear()
        return

    content_type = BroadcastContentType(content_type_raw)
    target = BroadcastTarget(target_raw)

    text: str | None = None
    file_id: str | None = None

    if content_type == BroadcastContentType.TEXT:
        if not message.text:
            await message.answer("Ожидаю текстовое сообщение.")
            return
        text = message.text

    if content_type == BroadcastContentType.PHOTO:
        if not message.photo:
            await message.answer("Ожидаю фото.")
            return
        file_id = message.photo[-1].file_id
        text = message.caption

    if content_type == BroadcastContentType.VIDEO:
        if not message.video:
            await message.answer("Ожидаю видео.")
            return
        file_id = message.video.file_id
        text = message.caption

    await message.answer("Рассылка запущена...")

    async with session_factory() as session:
        admin_user = await get_or_create_user(session, message.from_user, settings.admin_ids)
        users = await list_users_for_broadcast(session, target)

        broadcast = Broadcast(
            admin_user_id=admin_user.id,
            target=target,
            content_type=content_type,
            text=text,
            file_id=file_id,
            total=len(users),
        )
        session.add(broadcast)
        await session.commit()
        await session.refresh(broadcast)

    sent = 0
    failed = 0

    for user in users:
        try:
            if content_type == BroadcastContentType.TEXT:
                await message.bot.send_message(user.telegram_id, text or "")
            elif content_type == BroadcastContentType.PHOTO:
                await message.bot.send_photo(user.telegram_id, photo=file_id, caption=text)
            else:
                await message.bot.send_video(user.telegram_id, video=file_id, caption=text)
            sent += 1
        except Exception:
            failed += 1

        await asyncio.sleep(0.03)

    async with session_factory() as session:
        entity = await session.get(Broadcast, broadcast.id)
        if entity:
            entity.sent = sent
            entity.failed = failed
            entity.finished_at = datetime.now(timezone.utc)
            await session.commit()

    await state.clear()
    await message.answer(f"Рассылка завершена. Всего: {len(users)}, доставлено: {sent}, ошибок: {failed}")


def _render_stats(stats: dict) -> str:
    return (
        "Статистика:\n"
        f"- Пользователей: {stats['users_total']}\n"
        f"- Начали диагностику: {stats['started_diag']}\n"
        f"- Дошли до результата/дальше: {stats['finished_diag']}\n"
        f"- Активных подписок CLUB: {stats['active_club']}\n"
        f"- Записей на разбор: {stats['consult_booked']}\n"
        f"- Оплаченных платежей: {stats['paid_count']}\n"
        f"- Выручка: {stats['revenue_rub']} RUB\n"
        f"- Платежей CLUB: {stats['club_payments']}\n"
        f"- Платежей Разбор: {stats['consult_payments']}"
    )
