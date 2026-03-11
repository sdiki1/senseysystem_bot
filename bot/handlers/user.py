from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.enums import ProductType, UserStage
from bot.keyboards import (
    club_offer_keyboard,
    consult_offer_keyboard,
    diagnostic_question_keyboard,
    diagnostic_result_keyboard,
    payment_url_keyboard,
    welcome_keyboard,
)
from bot.services.payment_service import create_pending_payment
from bot.services.reminder_service import (
    DIAG_REMINDER_KINDS,
    PAYMENT_CLUB_REMINDER_KINDS,
    PAYMENT_CONSULT_REMINDER_KINDS,
    RESULT_REMINDER_KINDS,
    cancel_pending_reminders,
    schedule_diagnostic_pause,
    schedule_payment_pause,
    schedule_result_pause,
)
from bot.services.user_service import get_or_create_user
from bot.texts import (
    CLUB_OFFER_TEXT,
    CONSULT_OFFER_TEXT,
    DIAGNOSTIC_QUESTIONS,
    DIAGNOSTIC_RESULT_TEXT,
    WELCOME_TEXT,
)

router = Router(name="user")


def _build_question_text(index: int) -> str:
    question = DIAGNOSTIC_QUESTIONS[index]
    return f"{question.title}\n{question.body}"


async def _edit_funnel_message(message: Message, text: str, reply_markup) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).lower():
            return
        raise


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user:
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, message.from_user, settings.admin_ids)

        if user.stage not in {UserStage.CLUB_ACTIVE, UserStage.CONSULT_BOOKED}:
            user.stage = UserStage.NEW
            user.diagnostic_step = 0
            user.diagnostic_answers = {}
            await session.commit()
            await cancel_pending_reminders(session, user.id)

    await message.answer(WELCOME_TEXT, reply_markup=welcome_keyboard())


@router.callback_query(F.data == "diag:start")
async def start_diagnostic(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not callback.from_user or not callback.message:
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, callback.from_user, settings.admin_ids)
        user.stage = UserStage.DIAGNOSTIC_IN_PROGRESS
        user.diagnostic_step = 0
        user.diagnostic_answers = {}
        await session.commit()

        await cancel_pending_reminders(session, user.id)
        await schedule_diagnostic_pause(session, user.id, expected_step=0)

    first_question = DIAGNOSTIC_QUESTIONS[0]
    await _edit_funnel_message(
        callback.message,
        _build_question_text(0),
        reply_markup=diagnostic_question_keyboard(0, first_question.options),
    )
    await callback.answer()


@router.callback_query(F.data == "diag:continue")
async def continue_diagnostic(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not callback.from_user:
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, callback.from_user, settings.admin_ids)
        if user.stage != UserStage.DIAGNOSTIC_IN_PROGRESS:
            await callback.answer("Диагностика уже завершена или сброшена.", show_alert=True)
            return

        step = user.diagnostic_step
        if step >= len(DIAGNOSTIC_QUESTIONS):
            await callback.answer()
            return

        await schedule_diagnostic_pause(session, user.id, expected_step=step)

    question = DIAGNOSTIC_QUESTIONS[step]
    if callback.message:
        await _edit_funnel_message(
            callback.message,
            _build_question_text(step),
            reply_markup=diagnostic_question_keyboard(step, question.options),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("diag:answer:"))
async def handle_diagnostic_answer(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not callback.from_user or not callback.message:
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer()
        return

    try:
        question_index = int(parts[2])
        option_index = int(parts[3])
    except ValueError:
        await callback.answer()
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, callback.from_user, settings.admin_ids)
        if user.stage != UserStage.DIAGNOSTIC_IN_PROGRESS:
            await callback.answer("Диагностика не активна", show_alert=True)
            return

        if question_index != user.diagnostic_step:
            current = user.diagnostic_step
            if current < len(DIAGNOSTIC_QUESTIONS):
                question = DIAGNOSTIC_QUESTIONS[current]
                await _edit_funnel_message(
                    callback.message,
                    _build_question_text(current),
                    reply_markup=diagnostic_question_keyboard(current, question.options),
                )
            await callback.answer()
            return

        question = DIAGNOSTIC_QUESTIONS[question_index]
        if option_index < 0 or option_index >= len(question.options):
            await callback.answer()
            return

        answers = dict(user.diagnostic_answers or {})
        answers[str(question_index)] = question.options[option_index]

        next_step = question_index + 1
        user.diagnostic_answers = answers
        user.diagnostic_step = next_step

        if next_step < len(DIAGNOSTIC_QUESTIONS):
            user.stage = UserStage.DIAGNOSTIC_IN_PROGRESS
            await session.commit()
            await schedule_diagnostic_pause(session, user.id, expected_step=next_step)

            next_question = DIAGNOSTIC_QUESTIONS[next_step]
            await _edit_funnel_message(
                callback.message,
                _build_question_text(next_step),
                reply_markup=diagnostic_question_keyboard(next_step, next_question.options),
            )
            await callback.answer()
            return

        user.stage = UserStage.DIAGNOSTIC_RESULT
        await session.commit()

        await cancel_pending_reminders(session, user.id, DIAG_REMINDER_KINDS)
        await schedule_result_pause(session, user.id)

    await _edit_funnel_message(callback.message, DIAGNOSTIC_RESULT_TEXT, reply_markup=diagnostic_result_keyboard())
    await callback.answer()


@router.callback_query(F.data == "offer:club")
async def offer_club(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not callback.from_user or not callback.message:
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, callback.from_user, settings.admin_ids)
        user.stage = UserStage.OFFER_CLUB
        await session.commit()
        await cancel_pending_reminders(session, user.id, RESULT_REMINDER_KINDS)

    await _edit_funnel_message(callback.message, CLUB_OFFER_TEXT, reply_markup=club_offer_keyboard())
    await callback.answer()


@router.callback_query(F.data == "offer:consult")
async def offer_consult(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not callback.from_user or not callback.message:
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, callback.from_user, settings.admin_ids)
        user.stage = UserStage.OFFER_CONSULT
        await session.commit()
        await cancel_pending_reminders(session, user.id, RESULT_REMINDER_KINDS)

    await _edit_funnel_message(callback.message, CONSULT_OFFER_TEXT, reply_markup=consult_offer_keyboard())
    await callback.answer()


@router.callback_query(F.data == "pay:club")
async def pay_club(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not callback.from_user or not callback.message:
        return

    if not settings.tribute_club_payment_url:
        await callback.answer("Не настроен TRIBUTE_CLUB_PAYMENT_URL", show_alert=True)
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, callback.from_user, settings.admin_ids)
        user.stage = UserStage.PAYMENT_CLUB
        await session.commit()

        await cancel_pending_reminders(session, user.id, RESULT_REMINDER_KINDS)
        await cancel_pending_reminders(session, user.id, PAYMENT_CLUB_REMINDER_KINDS)

        await create_pending_payment(
            session,
            user_id=user.id,
            product=ProductType.CLUB,
            amount_rub=settings.club_price_rub,
            checkout_url=settings.tribute_club_payment_url,
            payload={"source": "button"},
        )
        await schedule_payment_pause(session, user.id, ProductType.CLUB)

    await _edit_funnel_message(
        callback.message,
        "Оплата SENSEY club. Нажми кнопку ниже.",
        reply_markup=payment_url_keyboard("💳 Войти в SENSEY club — 3000 ₽", settings.tribute_club_payment_url),
    )
    await callback.answer()


@router.callback_query(F.data == "pay:consult")
async def pay_consult(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not callback.from_user or not callback.message:
        return

    if not settings.tribute_consult_payment_url:
        await callback.answer("Не настроен TRIBUTE_CONSULT_PAYMENT_URL", show_alert=True)
        return

    async with session_factory() as session:
        user = await get_or_create_user(session, callback.from_user, settings.admin_ids)
        user.stage = UserStage.PAYMENT_CONSULT
        await session.commit()

        await cancel_pending_reminders(session, user.id, RESULT_REMINDER_KINDS)
        await cancel_pending_reminders(session, user.id, PAYMENT_CONSULT_REMINDER_KINDS)

        await create_pending_payment(
            session,
            user_id=user.id,
            product=ProductType.CONSULT,
            amount_rub=settings.consult_price_rub,
            checkout_url=settings.tribute_consult_payment_url,
            payload={"source": "button"},
        )
        await schedule_payment_pause(session, user.id, ProductType.CONSULT)

    await _edit_funnel_message(
        callback.message,
        "Запись на личный разбор. Нажми кнопку ниже.",
        reply_markup=payment_url_keyboard("💳 Записаться на разбор — 10 000 ₽", settings.tribute_consult_payment_url),
    )
    await callback.answer()
