from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import get_settings
from bot.db import build_engine, build_sessionmaker, init_models
from bot.handlers import register_routers
from bot.services.scheduler_service import ReminderScheduler
from bot.web.server import TributeWebhookServer


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def run() -> None:
    setup_logging()
    settings = get_settings()

    engine = build_engine(settings)
    session_factory = build_sessionmaker(engine)
    await init_models(engine)

    bot = Bot(token=settings.bot_token)
    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)
    register_routers(dispatcher)

    reminder_scheduler = ReminderScheduler(bot, session_factory, settings)
    webhook_server = TributeWebhookServer(bot, session_factory, settings)

    await reminder_scheduler.start()
    await webhook_server.start()

    try:
        await dispatcher.start_polling(
            bot,
            settings=settings,
            session_factory=session_factory,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await reminder_scheduler.stop()
        await webhook_server.stop()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
