from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.enums import ReminderKind, ReminderStatus, UserStage
from bot.keyboards import continue_diagnostic_keyboard, payment_url_keyboard, reminder_result_keyboard
from bot.models import ReminderTask, User
from bot.texts import (
    POST_PAYMENT_CLUB_24H_TEXT,
    REMINDER_DIAG_12H,
    REMINDER_DIAG_15M,
    REMINDER_DIAG_2H,
    REMINDER_PAYMENT_CLUB_20M,
    REMINDER_PAYMENT_CLUB_3H,
    REMINDER_PAYMENT_CONSULT_20M,
    REMINDER_PAYMENT_CONSULT_3H,
    REMINDER_RESULT_12H,
    REMINDER_RESULT_24H,
    REMINDER_RESULT_72H,
    REMINDER_RESULT_7D,
)

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        poll_interval_seconds: int = 15,
    ) -> None:
        self.bot = bot
        self.session_factory = session_factory
        self.settings = settings
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="reminder_scheduler")

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.process_once()
            except Exception:
                logger.exception("Failed to process reminder scheduler tick")
            await asyncio.sleep(self.poll_interval_seconds)

    async def process_once(self) -> None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            result = await session.execute(
                select(ReminderTask)
                .where(ReminderTask.status == ReminderStatus.PENDING, ReminderTask.run_at <= now)
                .order_by(ReminderTask.run_at)
                .limit(200)
            )
            tasks = list(result.scalars().all())

            for task in tasks:
                await self._process_single(session, task)

            await session.commit()

    async def _process_single(self, session: AsyncSession, task: ReminderTask) -> None:
        user = await session.get(User, task.user_id)
        if user is None:
            task.status = ReminderStatus.CANCELLED
            return

        text, markup, should_send = self._render_reminder(task, user)
        if not should_send:
            task.status = ReminderStatus.CANCELLED
            return

        try:
            await self.bot.send_message(user.telegram_id, text, reply_markup=markup)
            task.status = ReminderStatus.SENT
            task.sent_at = datetime.now(timezone.utc)
        except Exception:
            logger.exception("Failed to send reminder kind=%s user_id=%s", task.kind, user.telegram_id)
            task.status = ReminderStatus.CANCELLED

    def _render_reminder(self, task: ReminderTask, user: User) -> tuple[str, object | None, bool]:
        expected_step = int(task.payload.get("expected_step", -1))

        if task.kind == ReminderKind.DIAG_15M:
            if user.stage != UserStage.DIAGNOSTIC_IN_PROGRESS or user.diagnostic_step != expected_step:
                return "", None, False
            return REMINDER_DIAG_15M, continue_diagnostic_keyboard("▶️ Продолжить диагностику"), True

        if task.kind == ReminderKind.DIAG_2H:
            if user.stage != UserStage.DIAGNOSTIC_IN_PROGRESS or user.diagnostic_step != expected_step:
                return "", None, False
            return REMINDER_DIAG_2H, continue_diagnostic_keyboard("▶️ Завершить диагностику"), True

        if task.kind == ReminderKind.DIAG_12H:
            if user.stage != UserStage.DIAGNOSTIC_IN_PROGRESS or user.diagnostic_step != expected_step:
                return "", None, False
            return REMINDER_DIAG_12H, continue_diagnostic_keyboard("▶️ Вернуться к диагностике"), True

        if task.kind == ReminderKind.RESULT_12H:
            if user.stage != UserStage.DIAGNOSTIC_RESULT:
                return "", None, False
            return REMINDER_RESULT_12H, reminder_result_keyboard(), True

        if task.kind == ReminderKind.RESULT_24H:
            if user.stage != UserStage.DIAGNOSTIC_RESULT:
                return "", None, False
            return REMINDER_RESULT_24H, reminder_result_keyboard(), True

        if task.kind == ReminderKind.RESULT_72H:
            if user.stage != UserStage.DIAGNOSTIC_RESULT:
                return "", None, False
            return REMINDER_RESULT_72H, reminder_result_keyboard(), True

        if task.kind == ReminderKind.RESULT_7D:
            if user.stage != UserStage.DIAGNOSTIC_RESULT:
                return "", None, False
            return REMINDER_RESULT_7D, reminder_result_keyboard(), True

        if task.kind == ReminderKind.PAYMENT_CLUB_20M:
            if user.stage != UserStage.PAYMENT_CLUB or not self.settings.tribute_club_payment_url:
                return "", None, False
            return (
                REMINDER_PAYMENT_CLUB_20M,
                payment_url_keyboard("💳 Завершить оплату", self.settings.tribute_club_payment_url),
                True,
            )

        if task.kind == ReminderKind.PAYMENT_CLUB_3H:
            if user.stage != UserStage.PAYMENT_CLUB or not self.settings.tribute_club_payment_url:
                return "", None, False
            return (
                REMINDER_PAYMENT_CLUB_3H,
                payment_url_keyboard("💳 Войти в SENSEY club", self.settings.tribute_club_payment_url),
                True,
            )

        if task.kind == ReminderKind.PAYMENT_CONSULT_20M:
            if user.stage != UserStage.PAYMENT_CONSULT or not self.settings.tribute_consult_payment_url:
                return "", None, False
            return (
                REMINDER_PAYMENT_CONSULT_20M,
                payment_url_keyboard("📅 Завершить запись", self.settings.tribute_consult_payment_url),
                True,
            )

        if task.kind == ReminderKind.PAYMENT_CONSULT_3H:
            if user.stage != UserStage.PAYMENT_CONSULT or not self.settings.tribute_consult_payment_url:
                return "", None, False
            return (
                REMINDER_PAYMENT_CONSULT_3H,
                payment_url_keyboard("📅 Забронировать разбор", self.settings.tribute_consult_payment_url),
                True,
            )

        if task.kind == ReminderKind.POST_CLUB_24H:
            if user.stage != UserStage.CLUB_ACTIVE:
                return "", None, False
            return POST_PAYMENT_CLUB_24H_TEXT, None, True

        return "", None, False
