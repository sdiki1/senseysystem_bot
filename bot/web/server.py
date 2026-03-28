from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import web
from aiogram import Bot
from aiogram.types import ChatInviteLink
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.enums import PaymentStatus, ProductType
from bot.keyboards import channel_access_keyboard
from bot.models import Payment, User
from bot.services.payment_service import cancel_subscription, mark_payment_failed, mark_payment_success
from bot.services.reminder_service import cancel_pending_reminders, schedule_post_club_payment
from bot.services.tribute_service import parse_tribute_event, verify_tribute_signature
from bot.texts import POST_PAYMENT_CLUB_TEXT, POST_PAYMENT_CONSULT_TEXT, RENEWED_SUBSCRIPTION_TEXT

logger = logging.getLogger(__name__)

SUCCESS_EVENTS = {
    "new_subscription",
    "renewed_subscription",
    "payment_succeeded",
    "payment_success",
    "new_order",
    "new_purchase",
}
FAIL_EVENTS = {"payment_failed", "payment_cancelled", "payment_canceled"}
RENEWAL_EVENTS = {"renewed_subscription"}


class TributeWebhookServer:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self.bot = bot
        self.session_factory = session_factory
        self.settings = settings
        self._app = web.Application()
        self._app.router.add_post(settings.webhook_path, self.handle_tribute_webhook)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self.settings.web_host, port=self.settings.web_port)
        await self._site.start()
        logger.info("Webhook server started at %s:%s%s", self.settings.web_host, self.settings.web_port, self.settings.webhook_path)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    async def handle_tribute_webhook(self, request: web.Request) -> web.Response:
        raw_body = await request.read()
        signature = request.headers.get("trbt-signature")

        if not verify_tribute_signature(raw_body, signature, self.settings):
            logger.warning("Invalid Tribute webhook signature")
            return web.json_response({"ok": False, "error": "invalid_signature"}, status=401)

        try:
            data = await request.json()
        except Exception:
            logger.exception("Invalid webhook JSON")
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

        await self.process_tribute_event(data, source="webhook")

        return web.json_response({"ok": True})

    async def process_tribute_event(self, data: dict[str, Any], source: str = "polling") -> None:
        async with self.session_factory() as session:
            parsed = parse_tribute_event(data, self.settings)
            if parsed.telegram_id is None:
                logger.warning("Tribute event has no telegram_id source=%s event=%s", source, parsed.event_type)
                return

            user = await self._get_or_create_user(session, parsed.telegram_id)

            if parsed.event_type in FAIL_EVENTS:
                if parsed.provider_payment_id and await self._is_duplicate_payment_event(
                    session,
                    parsed.provider_payment_id,
                    PaymentStatus.FAILED,
                ):
                    logger.info("Duplicate failed payment ignored source=%s provider_payment_id=%s", source, parsed.provider_payment_id)
                    return
                await mark_payment_failed(
                    session,
                    user.id,
                    parsed.product,
                    parsed.payload,
                    parsed.provider_payment_id,
                )
                return

            if parsed.event_type == "cancelled_subscription":
                await cancel_subscription(session, user, parsed.payload)
                return

            if parsed.event_type in SUCCESS_EVENTS:
                if parsed.provider_payment_id and await self._is_duplicate_payment_event(
                    session,
                    parsed.provider_payment_id,
                    PaymentStatus.PAID,
                ):
                    logger.info("Duplicate paid payment ignored source=%s provider_payment_id=%s", source, parsed.provider_payment_id)
                    return
                await mark_payment_success(
                    session,
                    user,
                    parsed.product,
                    parsed.event_type,
                    parsed.payload,
                    parsed.provider_payment_id,
                    is_recurrent=parsed.is_recurrent,
                )

                await cancel_pending_reminders(session, user.id)

                if parsed.product == ProductType.CLUB:
                    await self._on_club_payment(session, user, parsed.event_type)
                else:
                    await self._on_consult_payment(user)
            else:
                logger.info("Ignoring Tribute event source=%s type=%s", source, parsed.event_type)

    async def _get_or_create_user(self, session: AsyncSession, telegram_id: int) -> User:
        existing = await session.execute(select(User).where(User.telegram_id == telegram_id).limit(1))
        user = existing.scalar_one_or_none()
        if user:
            return user

        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    async def _on_consult_payment(self, user: User) -> None:
        try:
            await self.bot.send_message(user.telegram_id, POST_PAYMENT_CONSULT_TEXT)
        except Exception:
            logger.exception("Failed to send consult success message user=%s", user.telegram_id)

    async def _on_club_payment(self, session: AsyncSession, user: User, event_type: str) -> None:
        # Renewal events should not send a new invite.
        if event_type in RENEWAL_EVENTS:
            try:
                await self.bot.send_message(user.telegram_id, RENEWED_SUBSCRIPTION_TEXT)
            except Exception:
                logger.exception("Failed to send renewal message user=%s", user.telegram_id)
            return

        try:
            invite_link = await self._get_invite_link(user.telegram_id)
            await self.bot.send_message(user.telegram_id, POST_PAYMENT_CLUB_TEXT)
            if invite_link:
                await self.bot.send_message(
                    user.telegram_id,
                    "Доступ в канал:",
                    reply_markup=channel_access_keyboard(invite_link),
                )
            else:
                await self.bot.send_message(
                    user.telegram_id,
                    "Не удалось автоматически создать ссылку в канал. Напиши в поддержку, чтобы выдали доступ вручную.",
                )
        except Exception:
            logger.exception("Failed to send club success message user=%s", user.telegram_id)

        await schedule_post_club_payment(session, user.id)

    async def _get_invite_link(self, telegram_id: int) -> str | None:
        if self.settings.sensey_channel_id:
            try:
                expire = datetime.now(timezone.utc) + timedelta(hours=2)
                invite: ChatInviteLink = await self.bot.create_chat_invite_link(
                    chat_id=self.settings.sensey_channel_id,
                    member_limit=1,
                    expire_date=expire,
                    name=f"sensey_{telegram_id}",
                )
                return invite.invite_link
            except Exception:
                logger.exception("Failed to create channel invite for user=%s", telegram_id)

        if self.settings.sensey_channel_invite_link:
            return self.settings.sensey_channel_invite_link

        return None

    async def _is_duplicate_payment_event(
        self,
        session: AsyncSession,
        provider_payment_id: str,
        status: PaymentStatus,
    ) -> bool:
        row = await session.execute(
            select(Payment.id).where(
                Payment.provider_payment_id == provider_payment_id,
                Payment.status == status,
            ).limit(1)
        )
        return row.scalar_one_or_none() is not None
